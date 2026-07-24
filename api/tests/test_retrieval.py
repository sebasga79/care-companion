"""RAG-005 — retrieval híbrido (BM25 + coseno + RRF) sobre un corpus fixture.

Los documentos se insertan directamente por SQL (no vía
`KnowledgeIngestionService`) para aislar el retrieval de la ingestión —
RAG-008 cubre el pipeline completo end-to-end por separado."""

from __future__ import annotations

import json
import sqlite3

from app.adapters.fake_embeddings import FakeEmbeddings
from app.repositories.db import apply_schema, get_connection
from app.services.embedding_codec import pack_embedding
from app.services.retrieval import hybrid_search

_DIMENSIONS = 128


async def _seed_document(
    conn: sqlite3.Connection,
    embeddings: FakeEmbeddings,
    *,
    doc_id: str,
    title: str,
    status: str,
    knowledge_version: int,
    applicability: dict,
    chunks: list[tuple[str, str | None, str]],  # (chunk_id, section, text)
) -> None:
    conn.execute(
        """
        INSERT INTO documents
            (id, title, filename, checksum, status, mime, size_bytes, applicability,
             knowledge_version, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            title,
            title,
            f"checksum-{doc_id}",
            status,
            "text/markdown",
            100,
            json.dumps(applicability),
            knowledge_version,
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    for index, (chunk_id, section, text) in enumerate(chunks):
        vector = (await embeddings.embed([text]))[0]
        conn.execute(
            """
            INSERT INTO document_chunks
                (id, document_id, section, page, text, created_at, chunk_index,
                 char_start, char_end, content_hash, embedding, embedding_dim)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                doc_id,
                section,
                None,
                text,
                "2026-01-01T00:00:00Z",
                index,
                0,
                len(text),
                f"hash-{chunk_id}",
                pack_embedding(vector),
                len(vector),
            ),
        )
        conn.execute(
            "INSERT INTO document_chunks_fts (chunk_id, document_id, text) VALUES (?, ?, ?)",
            (chunk_id, doc_id, text),
        )
    conn.commit()


async def _build_fixture_corpus() -> tuple[sqlite3.Connection, FakeEmbeddings]:
    conn = get_connection(":memory:")
    apply_schema(conn)
    embeddings = FakeEmbeddings(dimensions=_DIMENSIONS)

    await _seed_document(
        conn,
        embeddings,
        doc_id="doc-alta",
        title="Guia de alta postoperatoria",
        status="ready",
        knowledge_version=1,
        applicability={"procedure": "appendectomy"},
        chunks=[
            (
                "chunk-alarma",
                "Signos de alarma",
                "Si siente calor en la herida o fiebre mayor a 38 grados, "
                "contacte al equipo medico de inmediato.",
            ),
            (
                "chunk-cuidado",
                "Cuidado de la herida",
                "Mantenga la herida limpia y seca, cambie el vendaje segun indicaciones.",
            ),
        ],
    )
    await _seed_document(
        conn,
        embeddings,
        doc_id="doc-clima",
        title="Bienestar general",
        status="ready",
        knowledge_version=1,
        applicability={},
        chunks=[
            (
                "chunk-clima",
                None,
                "El clima de hoy esta soleado y agradable para salir a caminar.",
            ),
        ],
    )
    await _seed_document(
        conn,
        embeddings,
        doc_id="doc-otro-procedimiento",
        title="Guia de rodilla",
        status="ready",
        knowledge_version=1,
        applicability={"procedure": "knee_surgery"},
        chunks=[
            (
                "chunk-rodilla-calor",
                "Signos de alarma",
                "Si siente calor en la rodilla o fiebre, contacte al equipo medico.",
            ),
        ],
    )
    await _seed_document(
        conn,
        embeddings,
        doc_id="doc-borrado",
        title="Documento eliminado",
        status="deleted",
        knowledge_version=1,
        applicability={},
        chunks=[
            (
                "chunk-fantasma",
                None,
                "Contenido fantasma que nunca deberia aparecer en busquedas activas.",
            ),
        ],
    )
    await _seed_document(
        conn,
        embeddings,
        doc_id="doc-futuro",
        title="Documento agregado despues",
        status="ready",
        knowledge_version=5,
        applicability={},
        chunks=[
            (
                "chunk-futuro",
                None,
                "Contenido agregado en una version futura de conocimiento.",
            ),
        ],
    )
    return conn, embeddings


async def test_known_query_recovers_expected_chunk_in_top_3() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results = await hybrid_search(
            conn,
            "calor en la herida y fiebre, signos de alarma",
            embeddings=embeddings,
            session_knowledge_version=1,
            top_k=3,
        )
        top_chunk_ids = [r.chunk_id for r in results]
        assert "chunk-alarma" in top_chunk_ids
        assert top_chunk_ids.index("chunk-alarma") < 3
    finally:
        conn.close()


async def test_unrelated_chunk_ranks_below_relevant_ones() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results = await hybrid_search(
            conn,
            "calor en la herida fiebre alarma postoperatoria",
            embeddings=embeddings,
            session_knowledge_version=1,
            top_k=5,
        )
        chunk_ids = [r.chunk_id for r in results]
        assert "chunk-clima" not in chunk_ids[:2]
    finally:
        conn.close()


async def test_deleted_documents_are_always_excluded() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results = await hybrid_search(
            conn,
            "contenido fantasma que nunca deberia aparecer",
            embeddings=embeddings,
            session_knowledge_version=1,
            top_k=5,
        )
        assert all(r.chunk_id != "chunk-fantasma" for r in results)
        assert all(r.document_id != "doc-borrado" for r in results)
    finally:
        conn.close()


async def test_session_pinned_to_old_version_does_not_see_future_document() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results_old_session = await hybrid_search(
            conn,
            "contenido agregado en una version futura",
            embeddings=embeddings,
            session_knowledge_version=1,
            top_k=5,
        )
        assert all(r.document_id != "doc-futuro" for r in results_old_session)

        results_new_session = await hybrid_search(
            conn,
            "contenido agregado en una version futura",
            embeddings=embeddings,
            session_knowledge_version=5,
            top_k=5,
        )
        assert any(r.document_id == "doc-futuro" for r in results_new_session)
    finally:
        conn.close()


async def test_applicability_filter_excludes_other_procedure() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results = await hybrid_search(
            conn,
            "calor y fiebre, signos de alarma",
            embeddings=embeddings,
            session_knowledge_version=1,
            applicability_filter={"procedure": "appendectomy"},
            top_k=5,
        )
        assert all(r.document_id != "doc-otro-procedimiento" for r in results)
        assert any(r.document_id == "doc-alta" for r in results)
    finally:
        conn.close()


async def test_applicability_filter_includes_general_documents() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results = await hybrid_search(
            conn,
            "clima soleado agradable caminar",
            embeddings=embeddings,
            session_knowledge_version=1,
            applicability_filter={"procedure": "appendectomy"},
            top_k=5,
        )
        # doc-clima no declara "procedure" -> se trata como general, debe aparecer
        assert any(r.document_id == "doc-clima" for r in results)
    finally:
        conn.close()


async def test_rrf_fusion_combines_lexical_and_semantic_signals() -> None:
    conn, embeddings = await _build_fixture_corpus()
    try:
        results = await hybrid_search(
            conn,
            "calor herida fiebre",
            embeddings=embeddings,
            session_knowledge_version=1,
            top_k=5,
        )
        alarma = next(r for r in results if r.chunk_id == "chunk-alarma")
        assert alarma.lexical_rank is not None
        assert alarma.semantic_rank is not None
        assert alarma.rrf_score > 0
    finally:
        conn.close()


async def test_empty_corpus_returns_no_results() -> None:
    conn = get_connection(":memory:")
    apply_schema(conn)
    try:
        embeddings = FakeEmbeddings(dimensions=_DIMENSIONS)
        results = await hybrid_search(
            conn, "cualquier cosa", embeddings=embeddings, session_knowledge_version=1
        )
        assert results == []
    finally:
        conn.close()
