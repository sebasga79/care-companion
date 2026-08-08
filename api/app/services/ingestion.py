"""`KnowledgeIngestionService` — aprender/olvidar documentos en caliente
(RAG-008/RAG-009, architecture.md §9.2/§9.3).

Servicio determinista (architecture.md §6.2: "`KnowledgeIngestionService`
... se implementa como servicio determinista, no LLM agent"): valida,
fragmenta, embebe, indexa y borra — nunca interpreta el CONTENIDO de un
documento como instrucción (spec.md §11, BR-015). El texto de un documento
solo se usa como dato: se fragmenta, se embebe y se indexa; nunca se
concatena a un prompt de sistema ni se ejecuta como comando.

`learn()` y `forget()` corren su pipeline completo — incluida la consulta
canaria — dentro de una única transacción SQLite (`session_scope`). Si la
canaria falla, se lanza `KnowledgeCanaryError` DENTRO del bloque
`with session_scope(...)`, que ya implementa "except Exception: rollback;
raise" (`app/repositories/db.py`) — así que un fallo de canaria revierte
absolutamente todo (documento, chunks, FTS, embeddings, incremento de
`knowledge_version`): "TODO en una transacción ... con rollback limpio si
la canaria falla" (RAG-008/009) se cumple literalmente, no por
aproximación."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.domain.chunking import ChunkRecord, chunk_document
from app.repositories.db import session_scope
from app.repositories.document_chunks import DocumentChunkRepository
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge import increment_knowledge_version_conn
from app.services.embeddings_cache import EmbeddingsCache, text_checksum
from app.services.pdf_extraction import extract_pdf_pages
from app.services.retrieval import RetrievalResult, hybrid_search
from app.services.upload_validation import UploadRejected, ValidatedUpload, validate_upload

_MIME_BY_EXTENSION = {"txt": "text/plain", "md": "text/markdown", "pdf": "application/pdf"}
_CANARY_WORD_COUNT = 8
_CANARY_SEARCH_TOP_K = 50
_CANARY_SEARCH_CANDIDATE_POOL_SIZE = 500


class KnowledgeCanaryError(Exception):
    """La consulta canaria no confirmó lo esperado (positiva en learn,
    negativa en forget). Lanzada dentro de la transacción para forzar
    rollback — nunca se atrapa silenciosamente aquí."""


class DocumentNotFoundError(Exception):
    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(f"Documento no encontrado: {document_id}")


class DocumentAlreadyDeletedError(Exception):
    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        super().__init__(f"El documento ya está eliminado: {document_id}")


class LearnResult:
    def __init__(
        self, *, document: dict[str, Any], knowledge_version: int, chunk_count: int
    ) -> None:
        self.document = document
        self.knowledge_version = knowledge_version
        self.chunk_count = chunk_count


class ForgetResult:
    def __init__(
        self, *, document: dict[str, Any], knowledge_version: int, purged_chunk_count: int
    ) -> None:
        self.document = document
        self.knowledge_version = knowledge_version
        self.purged_chunk_count = purged_chunk_count


class KnowledgeIngestionService:
    def __init__(
        self,
        database_path: str,
        *,
        embeddings_cache: EmbeddingsCache,
        settings: Settings,
        document_repo: DocumentRepository | None = None,
        chunk_repo: DocumentChunkRepository | None = None,
    ) -> None:
        self._database_path = database_path
        self._embeddings_cache = embeddings_cache
        self._settings = settings
        self._document_repo = document_repo or DocumentRepository(database_path)
        self._chunk_repo = chunk_repo or DocumentChunkRepository()

    async def learn(
        self,
        *,
        raw_filename: str,
        content: bytes,
        applicability: dict[str, Any] | None = None,
    ) -> LearnResult:
        """Pipeline completo de RAG-008. Puede lanzar `UploadRejected`
        (RAG-002, antes de tocar la BD) o `KnowledgeCanaryError` (después
        de escribir todo dentro de la transacción, que se revierte)."""
        validated = validate_upload(
            raw_filename=raw_filename,
            content=content,
            allowed_extensions=self._settings.rag_allowed_extensions_set,
            max_bytes=self._settings.rag_max_upload_bytes,
            existing_active_checksums=self._document_repo.active_checksums(),
        )
        document_id = str(uuid.uuid4())
        chunks = self._chunk_content(document_id, validated.extension, content)
        if not chunks:
            raise UploadRejected(
                "El documento no produjo ningún fragmento indexable "
                "(contenido vacío tras normalizar espacios en blanco)",
                code="empty_after_chunking",
            )

        vectors = await self._embeddings_cache.embed_batch([chunk.text for chunk in chunks])
        canary_query = _pick_canary_query(chunks[0].text)
        now = datetime.now(UTC).isoformat()

        with session_scope(self._database_path) as conn:
            new_version = increment_knowledge_version_conn(conn)

            self._document_repo.insert(
                conn,
                document_id=document_id,
                filename=validated.safe_filename,
                checksum=validated.checksum,
                status="processing",
                mime=_MIME_BY_EXTENSION[validated.extension],
                size_bytes=validated.size_bytes,
                applicability=applicability or {},
                knowledge_version_added=new_version,
                created_at=now,
            )
            for chunk, vector in zip(chunks, vectors, strict=True):
                self._chunk_repo.insert(
                    conn,
                    chunk_id=chunk.chunk_id,
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    section=chunk.section,
                    page=chunk.page,
                    text=chunk.text,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    content_hash=text_checksum(chunk.text),
                    embedding=vector,
                    created_at=now,
                )

            # El filtro de retrieval exige status='ready' (BR-011); para que
            # la canaria pueda encontrar el documento hay que adelantar el
            # cambio de estado ANTES de consultarlo. Es seguro: si la
            # canaria falla, `raise` revierte la transacción completa,
            # incluido este UPDATE — el documento nunca queda "ready" sin
            # haber pasado la canaria (BR-016).
            self._document_repo.update_status(conn, document_id, status="ready", updated_at=now)

            expected_chunk_ids = {chunk.chunk_id for chunk in chunks}
            found = await self._canary_found(
                conn, query=canary_query, session_knowledge_version=new_version
            )
            matched_new_doc = any(
                r.document_id == document_id and r.chunk_id in expected_chunk_ids for r in found
            )
            if not matched_new_doc:
                raise KnowledgeCanaryError(
                    f"Consulta canaria positiva no encontró el documento recién cargado "
                    f"(query={canary_query!r}); se revierte la carga completa."
                )

            document = self._document_repo.get_conn(conn, document_id)

        assert document is not None  # acabamos de confirmarlo en la misma transacción
        return LearnResult(
            document=document, knowledge_version=new_version, chunk_count=len(chunks)
        )

    def _chunk_content(self, document_id: str, extension: str, content: bytes) -> list[ChunkRecord]:
        """Deriva el texto según el tipo de archivo y lo fragmenta.

        `txt`/`md`: un único blob de texto UTF-8, `page=None` (comportamiento
        original). `pdf`: una página a la vez (`app/services/pdf_extraction`),
        con `page` real estampado y `chunk_index` global acumulado entre
        páginas — dos páginas nunca comparten `chunk_index`, así que el id
        determinista (`document_id|chunk_index|text`) sigue siendo único."""
        if extension == "pdf":
            chunks: list[ChunkRecord] = []
            for page_number, page_text in enumerate(
                extract_pdf_pages(
                    content,
                    allow_empty_password=self._settings.rag_allow_empty_pdf_password,
                ),
                start=1,
            ):
                if not page_text.strip():
                    continue
                chunks.extend(
                    chunk_document(
                        document_id,
                        page_text,
                        chunk_size_chars=self._settings.rag_chunk_size_chars,
                        overlap_chars=self._settings.rag_chunk_overlap_chars,
                        page=page_number,
                        chunk_index_start=len(chunks),
                    )
                )
            return chunks

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejected(
                f"El archivo no es texto UTF-8 válido: {exc}",
                code="invalid_encoding",
            ) from exc
        return chunk_document(
            document_id,
            text,
            chunk_size_chars=self._settings.rag_chunk_size_chars,
            overlap_chars=self._settings.rag_chunk_overlap_chars,
        )

    async def forget(self, document_id: str, *, actor: str | None = None) -> ForgetResult:
        """Pipeline completo de RAG-009. `actor` es quien ejecuta el
        borrado (para el tombstone); puede ser `None` en contextos sin
        usuario autenticado explícito (p. ej. scripts internos)."""
        document = self._document_repo.get(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if document["status"] == "deleted":
            raise DocumentAlreadyDeletedError(document_id)

        now = datetime.now(UTC).isoformat()

        with session_scope(self._database_path) as conn:
            purged_rows = self._chunk_repo.delete_for_document(conn, document_id)
            purged_chunk_ids = [row["id"] for row in purged_rows]

            remaining = _find_remaining_chunk_rows(conn, purged_chunk_ids)
            if remaining:
                raise KnowledgeCanaryError(
                    f"Borrado incompleto: {len(remaining)} chunk(s) siguen presentes en "
                    f"document_chunks/FTS tras la purga; se revierte el borrado completo."
                )

            new_version = increment_knowledge_version_conn(conn)
            self._document_repo.mark_deleted(
                conn,
                document_id,
                knowledge_version_deleted=new_version,
                deleted_at=now,
                deleted_by=actor,
            )

            if purged_rows:
                canary_query = _pick_canary_query(purged_rows[0]["text"])
                still_found = await self._canary_found(
                    conn, query=canary_query, session_knowledge_version=new_version
                )
                leaked = any(
                    r.document_id == document_id or r.chunk_id in purged_chunk_ids
                    for r in still_found
                )
                if leaked:
                    raise KnowledgeCanaryError(
                        f"Consulta canaria negativa aún encuentra contenido del documento "
                        f"{document_id} tras el borrado; se revierte."
                    )

            document_after = self._document_repo.get_conn(conn, document_id)

        self._embeddings_cache.evict([row["text"] for row in purged_rows])

        assert document_after is not None
        return ForgetResult(
            document=document_after,
            knowledge_version=new_version,
            purged_chunk_count=len(purged_rows),
        )

    async def _canary_found(
        self, conn: sqlite3.Connection, *, query: str, session_knowledge_version: int
    ) -> list[RetrievalResult]:
        # top_k/candidate_pool_size deliberadamente MÁS ALTOS que los de
        # retrieval normal (Settings.rag_retrieval_top_k, típicamente 5):
        # el propósito de la canaria no es "¿rankea entre los mejores
        # resultados clínicos?" sino "¿el chunk recién escrito es
        # localizable en absoluto?". Con top_k=5 fallaba en la práctica
        # contra un corpus real de tamaño moderado (probado con los 107 PDFs
        # del reto, docs/auditoria-kit-oficial-2026-08-07.md §9.2): un
        # snippet de las primeras palabras de un chunk suele ser boilerplate
        # de journal ("Contents lists available at ScienceDirect...",
        # fechas de revisión) que decenas de otros documentos comparten:
        # con miles de chunks ya indexados, el fragmento recién insertado
        # quedaba fuera del top-5 aunque SÍ estuviera indexado — falso
        # negativo que revertía una carga válida.
        return await hybrid_search(
            conn,
            query,
            embeddings=self._embeddings_cache,
            session_knowledge_version=session_knowledge_version,
            top_k=_CANARY_SEARCH_TOP_K,
            candidate_pool_size=_CANARY_SEARCH_CANDIDATE_POOL_SIZE,
        )


def _pick_canary_query(text: str) -> str:
    words = text.split()
    snippet = " ".join(words[:_CANARY_WORD_COUNT])
    return snippet or text


def _find_remaining_chunk_rows(conn: sqlite3.Connection, chunk_ids: list[str]) -> list[str]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    remaining: list[str] = []
    # `placeholders` es únicamente una repetición de "?" (uno por elemento
    # de `chunk_ids`); los valores reales siempre van parametrizados en la
    # tupla del segundo argumento — no hay interpolación de datos externos
    # en el SQL. S608 no distingue esto de una concatenación insegura.
    rows = conn.execute(
        f"SELECT id FROM document_chunks WHERE id IN ({placeholders})",  # noqa: S608
        chunk_ids,
    ).fetchall()
    remaining.extend(row["id"] for row in rows)
    fts_rows = conn.execute(
        f"SELECT chunk_id FROM document_chunks_fts WHERE chunk_id IN ({placeholders})",  # noqa: S608
        chunk_ids,
    ).fetchall()
    remaining.extend(row["chunk_id"] for row in fts_rows)
    return remaining


__all__ = [
    "DocumentAlreadyDeletedError",
    "DocumentNotFoundError",
    "ForgetResult",
    "KnowledgeCanaryError",
    "KnowledgeIngestionService",
    "LearnResult",
    "UploadRejected",
    "ValidatedUpload",
]
