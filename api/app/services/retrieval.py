"""Retrieval híbrido: BM25 (FTS5) + coseno (NumPy) + fusión RRF (RAG-005).

architecture.md §9.1: "SQLite con FTS5 (léxico) + embeddings BLOB con
coseno en NumPy, fusión por RRF". El coseno se calcula sobre un conjunto
acotado de candidatos (`candidate_pool_size`), no sobre toda la tabla —
"similitud coseno calculada con NumPy sobre candidatos acotados".

Filtros aplicados ANTES de rankear (nunca después, para no desperdiciar el
`top_k` en resultados que se van a descartar):

- `status = 'ready'` — excluye SIEMPRE documentos `deleted`/`processing`/
  `failed` (BR-011: una fuente eliminada no puede sustentar sesiones nuevas).
- `knowledge_version <= session_knowledge_version` — una sesión fijada a una
  versión no ve documentos agregados después de que empezó (spec.md §11.2).
- aplicabilidad — si el llamador pasa un filtro (p. ej.
  `{"procedure": "appendectomy"}`), se excluyen documentos cuya
  `applicability` declare explícitamente un valor distinto para esa clave;
  un documento que no declara la clave se trata como "general" y aplica."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

import numpy as np

from app.ports.embeddings import EmbeddingsPort
from app.services.embedding_codec import unpack_embedding

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    document_id: str
    document_title: str
    document_version: int
    section: str | None
    page: int | None
    text: str
    lexical_rank: int | None
    lexical_score: float | None
    semantic_rank: int | None
    semantic_score: float | None
    rrf_score: float
    applicability: dict
    knowledge_version: int


async def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    embeddings: EmbeddingsPort,
    session_knowledge_version: int,
    applicability_filter: dict[str, str] | None = None,
    top_k: int = 5,
    rrf_k: int = 60,
    candidate_pool_size: int = 200,
) -> list[RetrievalResult]:
    eligible_docs = _eligible_documents(conn, session_knowledge_version, applicability_filter)
    if not eligible_docs:
        return []
    eligible_doc_ids = list(eligible_docs.keys())

    lexical_ranking = _lexical_search(conn, query, eligible_doc_ids, candidate_pool_size)

    [query_vector] = await embeddings.embed([query])
    semantic_ranking = _semantic_search(conn, query_vector, eligible_doc_ids, candidate_pool_size)

    fused = _reciprocal_rank_fusion(lexical_ranking, semantic_ranking, k=rrf_k)
    top_chunk_ids = [chunk_id for chunk_id, _ in fused[:top_k]]
    if not top_chunk_ids:
        return []

    lexical_rank_of = {cid: rank for rank, (cid, _) in enumerate(lexical_ranking, start=1)}
    lexical_score_of = dict(lexical_ranking)
    semantic_rank_of = {cid: rank for rank, (cid, _) in enumerate(semantic_ranking, start=1)}
    semantic_score_of = dict(semantic_ranking)
    rrf_score_of = dict(fused)

    # `placeholders` es solo "?" repetido; los valores van parametrizados
    # (ver mismo comentario en `_lexical_search`/`_semantic_search` más abajo).
    placeholders = ",".join("?" for _ in top_chunk_ids)
    rows = conn.execute(
        f"SELECT * FROM document_chunks WHERE id IN ({placeholders})",  # noqa: S608
        top_chunk_ids,
    ).fetchall()
    chunk_by_id = {row["id"]: dict(row) for row in rows}

    results: list[RetrievalResult] = []
    for chunk_id in top_chunk_ids:
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            continue  # defensivo: no debería pasar, el índice FTS/vector está sincronizado
        doc = eligible_docs[chunk["document_id"]]
        results.append(
            RetrievalResult(
                chunk_id=chunk_id,
                document_id=doc["id"],
                document_title=doc["title"],
                document_version=doc["knowledge_version"],
                section=chunk["section"],
                page=chunk["page"],
                text=chunk["text"],
                lexical_rank=lexical_rank_of.get(chunk_id),
                lexical_score=lexical_score_of.get(chunk_id),
                semantic_rank=semantic_rank_of.get(chunk_id),
                semantic_score=semantic_score_of.get(chunk_id),
                rrf_score=rrf_score_of[chunk_id],
                applicability=doc["applicability"],
                knowledge_version=session_knowledge_version,
            )
        )
    results.sort(key=lambda r: r.rrf_score, reverse=True)
    return results


def _eligible_documents(
    conn: sqlite3.Connection,
    session_knowledge_version: int,
    applicability_filter: dict[str, str] | None,
) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT * FROM documents WHERE status = 'ready' AND knowledge_version <= ?",
        (session_knowledge_version,),
    ).fetchall()
    docs: dict[str, dict] = {}
    for row in rows:
        doc = dict(row)
        try:
            doc["applicability"] = json.loads(doc["applicability"] or "{}")
        except json.JSONDecodeError:
            doc["applicability"] = {}
        if applicability_filter is None or _applicability_matches(
            doc["applicability"], applicability_filter
        ):
            docs[doc["id"]] = doc
    return docs


def _applicability_matches(doc_applicability: dict, query_filter: dict[str, str]) -> bool:
    for key, value in query_filter.items():
        doc_value = doc_applicability.get(key)
        if doc_value is not None and doc_value != value:
            return False
    return True


def _build_fts_query(query: str) -> str:
    tokens = _TOKEN_RE.findall(query.lower())
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def _lexical_search(
    conn: sqlite3.Connection, query: str, eligible_doc_ids: list[str], limit: int
) -> list[tuple[str, float]]:
    fts_query = _build_fts_query(query)
    if not fts_query or not eligible_doc_ids:
        return []
    # `placeholders` es solo "?" repetido una vez por id elegible; los ids
    # reales siempre van parametrizados, nunca interpolados en el SQL.
    placeholders = ",".join("?" for _ in eligible_doc_ids)
    rows = conn.execute(
        f"""
        SELECT chunk_id, bm25(document_chunks_fts) AS score
        FROM document_chunks_fts
        WHERE document_chunks_fts MATCH ? AND document_id IN ({placeholders})
        ORDER BY score ASC
        LIMIT ?
        """,  # noqa: S608
        (fts_query, *eligible_doc_ids, limit),
    ).fetchall()
    return [(row["chunk_id"], row["score"]) for row in rows]


def _semantic_search(
    conn: sqlite3.Connection, query_vector: list[float], eligible_doc_ids: list[str], limit: int
) -> list[tuple[str, float]]:
    if not eligible_doc_ids:
        return []
    # Mismo caso que `_lexical_search`: solo "?" repetidos, valores parametrizados.
    placeholders = ",".join("?" for _ in eligible_doc_ids)
    rows = conn.execute(
        f"""
        SELECT id AS chunk_id, embedding FROM document_chunks
        WHERE document_id IN ({placeholders}) LIMIT ?
        """,  # noqa: S608
        (*eligible_doc_ids, limit),
    ).fetchall()
    if not rows:
        return []
    chunk_ids = [row["chunk_id"] for row in rows]
    matrix = np.stack([unpack_embedding(row["embedding"]) for row in rows])
    query_arr = np.asarray(query_vector, dtype=np.float32)
    query_norm = float(np.linalg.norm(query_arr))
    if query_norm == 0.0:
        return []
    matrix_norms = np.linalg.norm(matrix, axis=1)
    denom = matrix_norms * query_norm
    cosine = np.divide(matrix @ query_arr, denom, out=np.zeros_like(matrix_norms), where=denom > 0)
    order = np.argsort(-cosine)
    return [(chunk_ids[i], float(cosine[i])) for i in order]


def _reciprocal_rank_fusion(*rankings: list[tuple[str, float]], k: int) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (item_id, _score) in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
