"""RAG-008/RAG-009 — learn/forget transaccional end-to-end.

Estos tests ejercitan el pipeline REAL completo (validación -> chunk ->
embed -> index -> canaria -> ready / delete -> purge -> canaria -> deleted)
contra una base SQLite real, no mocks — es la demostración de
AC-E2E-005/006 (spec.md §10)."""

from __future__ import annotations

import pytest

from app.adapters.fake_embeddings import FakeEmbeddings
from app.core.config import Settings
from app.repositories.db import apply_schema, get_connection
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge import get_current_knowledge_version
from app.services.embeddings_cache import EmbeddingsCache
from app.services.ingestion import (
    DocumentAlreadyDeletedError,
    DocumentNotFoundError,
    KnowledgeCanaryError,
    KnowledgeIngestionService,
)
from app.services.retrieval import hybrid_search
from app.services.upload_validation import UploadRejected

_CONTENT = b"""# Guia de alta postoperatoria

## Signos de alarma

Si siente calor en la herida quirurgica o fiebre mayor a 38 grados, \
contacte al equipo medico de inmediato. Esta es una senal de alarma \
importante que no debe ignorarse.

## Cuidado general

Mantenga la herida limpia y seca segun las indicaciones del equipo medico.
"""


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()


def _service(db_path: str) -> tuple[KnowledgeIngestionService, EmbeddingsCache, Settings]:
    settings = Settings(DATABASE_PATH=db_path)
    cache = EmbeddingsCache(FakeEmbeddings(dimensions=settings.rag_embedding_dimensions))
    svc = KnowledgeIngestionService(db_path, embeddings_cache=cache, settings=settings)
    return svc, cache, settings


async def test_learn_e2e_positive_canary_reaches_ready(db_path: str) -> None:
    """AC-E2E-005: se carga un documento con un hecho canario; el estado
    llega a `ready`; una sesión nueva recupera y cita ese documento."""
    _init_db(db_path)
    svc, cache, settings = _service(db_path)

    version_before = get_current_knowledge_version(db_path)
    result = await svc.learn(
        raw_filename="guia_alta.md",
        content=_CONTENT,
        applicability={"procedure": "appendectomy"},
    )

    assert result.document["status"] == "ready"
    assert result.chunk_count >= 1
    assert result.knowledge_version == version_before + 1
    assert get_current_knowledge_version(db_path) == version_before + 1

    # una "sesión nueva" (fijada a la versión resultante) recupera el hecho
    conn = get_connection(db_path)
    try:
        found = await hybrid_search(
            conn,
            "calor en la herida quirurgica fiebre alarma",
            embeddings=cache,
            session_knowledge_version=result.knowledge_version,
            top_k=3,
        )
        assert any(r.document_id == result.document["id"] for r in found)
    finally:
        conn.close()


async def test_learn_rejects_duplicate_checksum(db_path: str) -> None:
    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)
    await svc.learn(raw_filename="guia.md", content=_CONTENT, applicability={})
    with pytest.raises(UploadRejected) as exc_info:
        await svc.learn(raw_filename="copia.md", content=_CONTENT, applicability={})
    assert exc_info.value.code == "duplicate_checksum"


async def test_learn_canary_failure_rolls_back_everything(
    db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fuerza un fallo de canaria (simulando un índice corrupto/roto) y
    verifica que TODO se revierte: sin documento, sin chunks, sin filas
    FTS, y `knowledge_version` sin incrementar — 'rollback limpio'."""
    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)

    async def _always_empty(self, conn, *, query, session_knowledge_version):
        return []

    monkeypatch.setattr(KnowledgeIngestionService, "_canary_found", _always_empty)

    version_before = get_current_knowledge_version(db_path)
    with pytest.raises(KnowledgeCanaryError):
        await svc.learn(raw_filename="guia.md", content=_CONTENT, applicability={})

    assert get_current_knowledge_version(db_path) == version_before

    conn = get_connection(db_path)
    try:
        doc_count = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        chunk_count = conn.execute("SELECT COUNT(*) AS n FROM document_chunks").fetchone()["n"]
        fts_count = conn.execute(
            "SELECT COUNT(*) AS n FROM document_chunks_fts"
        ).fetchone()["n"]
    finally:
        conn.close()

    assert doc_count == 0
    assert chunk_count == 0
    assert fts_count == 0


async def test_forget_e2e_negative_canary_reaches_deleted(db_path: str) -> None:
    """AC-E2E-006: se elimina el documento; se incrementa `knowledge_version`;
    una consulta y sesión nuevas no recuperan el hecho; sin texto clínico
    en el tombstone."""
    _init_db(db_path)
    svc, cache, _settings = _service(db_path)

    learn_result = await svc.learn(
        raw_filename="guia_alta.md", content=_CONTENT, applicability={}
    )
    document_id = learn_result.document["id"]

    forget_result = await svc.forget(document_id, actor="admin@care-companion.test")

    assert forget_result.document["status"] == "deleted"
    assert forget_result.document["knowledge_version_deleted"] == forget_result.knowledge_version
    assert forget_result.knowledge_version == learn_result.knowledge_version + 1
    assert forget_result.purged_chunk_count == learn_result.chunk_count
    # tombstone: sin texto clínico persistido en `documents` (el texto solo
    # vivía en `document_chunks`, ya purgado)
    assert "chunks" not in forget_result.document

    conn = get_connection(db_path)
    try:
        remaining_chunks = conn.execute(
            "SELECT COUNT(*) AS n FROM document_chunks WHERE document_id = ?", (document_id,)
        ).fetchone()["n"]
        remaining_fts = conn.execute(
            "SELECT COUNT(*) AS n FROM document_chunks_fts WHERE document_id = ?", (document_id,)
        ).fetchone()["n"]
        assert remaining_chunks == 0
        assert remaining_fts == 0

        found_after = await hybrid_search(
            conn,
            "calor en la herida quirurgica fiebre alarma",
            embeddings=cache,
            session_knowledge_version=forget_result.knowledge_version,
            top_k=5,
        )
        assert all(r.document_id != document_id for r in found_after)

        # una sesión "vieja" fijada a la versión previa (cuando el doc
        # estaba ready) tampoco debe recuperarlo tras el borrado — BR-011:
        # una fuente eliminada no sustenta ninguna sesión, nueva o vieja.
        found_old_session = await hybrid_search(
            conn,
            "calor en la herida quirurgica fiebre alarma",
            embeddings=cache,
            session_knowledge_version=learn_result.knowledge_version,
            top_k=5,
        )
        assert all(r.document_id != document_id for r in found_old_session)
    finally:
        conn.close()


async def test_forget_evicts_embeddings_cache_entries(db_path: str) -> None:
    _init_db(db_path)
    svc, cache, _settings = _service(db_path)
    result = await svc.learn(raw_filename="guia.md", content=_CONTENT, applicability={})
    cache_size_after_learn = len(cache)
    assert cache_size_after_learn >= result.chunk_count

    await svc.forget(result.document["id"])
    assert len(cache) < cache_size_after_learn


async def test_forget_missing_document_raises_not_found(db_path: str) -> None:
    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)
    with pytest.raises(DocumentNotFoundError):
        await svc.forget("does-not-exist")


async def test_forget_already_deleted_document_raises(db_path: str) -> None:
    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)
    result = await svc.learn(raw_filename="guia.md", content=_CONTENT, applicability={})
    await svc.forget(result.document["id"])
    with pytest.raises(DocumentAlreadyDeletedError):
        await svc.forget(result.document["id"])


async def test_learn_then_delete_then_relearn_same_content_is_allowed(db_path: str) -> None:
    """Volver a "aprender" contenido previamente borrado es legítimo, no
    un duplicado (RAG-002: el checksum solo se compara contra documentos
    activos, no eliminados)."""
    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)
    first = await svc.learn(raw_filename="guia.md", content=_CONTENT, applicability={})
    await svc.forget(first.document["id"])

    second = await svc.learn(raw_filename="guia_v2.md", content=_CONTENT, applicability={})
    assert second.document["status"] == "ready"
    assert second.document["id"] != first.document["id"]


async def test_document_repository_reflects_full_lifecycle(db_path: str) -> None:
    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)
    repo = DocumentRepository(db_path)

    result = await svc.learn(raw_filename="guia.md", content=_CONTENT, applicability={})
    listed = repo.list_all()
    assert any(d["id"] == result.document["id"] and d["status"] == "ready" for d in listed)

    await svc.forget(result.document["id"])
    after = repo.get(result.document["id"])
    assert after is not None
    assert after["status"] == "deleted"
    assert after["deleted_at"] is not None
    assert after["knowledge_version_deleted"] is not None


def _build_test_pdf(*page_texts: str) -> bytes:
    """PDF real generado con `pypdf` (mismo mecanismo que
    `test_pdf_extraction.py`) — corpus mínimo para el pipeline completo,
    no fixture binaria opaca."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=200, height=200)
        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")
        resources = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = writer._add_object(font)  # noqa: SLF001
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources
        stream_obj = StreamObject()
        stream_obj.set_data(f"BT /F1 24 Tf 10 100 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream_obj)  # noqa: SLF001
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def test_learn_e2e_pdf_extracts_text_indexes_by_page_and_is_findable(
    db_path: str,
) -> None:
    """RAG-002 ampliado: el corpus real del reto (`dataset/textos/`) es
    PDF. Corre el pipeline completo (validación -> extracción por página ->
    chunk -> embed -> index -> canaria) contra un PDF real de dos páginas y
    verifica que el fragmento recuperado lleva el número de página real."""
    _init_db(db_path)
    svc, cache, _settings = _service(db_path)

    pdf_bytes = _build_test_pdf(
        "Signos de alarma postoperatoria fiebre",
        "Segunda pagina con informacion adicional",
    )

    result = await svc.learn(
        raw_filename="protocolo.pdf", content=pdf_bytes, applicability={}
    )
    assert result.document["status"] == "ready"
    assert result.document["mime"] == "application/pdf"
    assert result.chunk_count == 2  # una página con texto -> un chunk cada una

    conn = get_connection(db_path)
    try:
        found = await hybrid_search(
            conn,
            "signos de alarma fiebre postoperatoria",
            embeddings=cache,
            session_knowledge_version=result.knowledge_version,
            top_k=3,
        )
        match = next((r for r in found if r.document_id == result.document["id"]), None)
        assert match is not None
        assert match.page == 1
    finally:
        conn.close()


async def test_learn_rejects_pdf_without_extractable_text(db_path: str) -> None:
    """PDF escaneado sin capa de texto (caso conocido en el corpus oficial,
    carpeta `Appendicitis/`) — se rechaza explícito, nunca se indexa vacío."""
    import io

    from pypdf import PdfWriter

    _init_db(db_path)
    svc, _cache, _settings = _service(db_path)

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    with pytest.raises(UploadRejected) as exc_info:
        await svc.learn(raw_filename="escaneado.pdf", content=buf.getvalue(), applicability={})
    assert exc_info.value.code == "pdf_no_text_layer"
