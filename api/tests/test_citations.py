"""RAG-007 — contrato de citas: `CitationRef` (spec.md §8.2) persistido y
recuperado sin pérdida de campos. Trace test: turno -> cita -> documento."""

from __future__ import annotations

import uuid

from app.domain.models import CitationRef
from app.repositories.citations import CitationRepository
from app.repositories.db import apply_schema, get_connection
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()


def test_citation_round_trips_through_persistence(db_path: str) -> None:
    _init_db(db_path)
    session_repo = SessionRepository(db_path)
    turn_repo = TurnRepository(db_path)
    citation_repo = CitationRepository()

    session = session_repo.create(case_id="demo-case-001", state="responding", knowledge_version=3)
    turn = turn_repo.add(
        session_id=session["id"], speaker="agent", text="Cuide la herida...", sequence=1
    )

    citation = CitationRef(
        citation_id=str(uuid.uuid4()),
        document_id="doc-1",
        document_version=2,
        chunk_id="chunk-1",
        title="Guía de alta posoperatoria",
        section="Signos de alarma",
        page=4,
        knowledge_version=3,
    )

    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        # documents/document_chunks son FK de citations: se insertan
        # mínimamente para que la FK sea válida (foreign_keys=ON).
        conn.execute(
            "INSERT INTO documents "
            "(id, title, filename, checksum, status, mime, size_bytes, applicability, "
            " knowledge_version, created_at, updated_at) "
            "VALUES ('doc-1','Guía de alta posoperatoria','g.md','chk','ready','text/markdown',"
            "10,'{}',2,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO document_chunks "
            "(id, document_id, section, page, text, created_at, chunk_index, char_start, "
            " char_end, content_hash, embedding, embedding_dim) "
            "VALUES ('chunk-1','doc-1','Signos de alarma',4,'texto','2026-01-01T00:00:00Z',"
            "0,0,5,'h',NULL,0)"
        )
        citation_repo.record(
            conn, turn_id=turn["id"], citation=citation, created_at="2026-01-01T00:00:00Z"
        )
        conn.commit()

        rows = citation_repo.list_for_turn(conn, turn["id"])
        assert len(rows) == 1
        recovered = citation_repo.to_citation_ref(rows[0])
    finally:
        conn.close()

    assert recovered.document_id == citation.document_id
    assert recovered.document_version == citation.document_version
    assert recovered.chunk_id == citation.chunk_id
    assert recovered.title == citation.title
    assert recovered.section == citation.section
    assert recovered.page == citation.page
    assert recovered.knowledge_version == citation.knowledge_version


def test_citation_persists_even_after_source_document_is_deleted(db_path: str) -> None:
    """BR: una cita ya emitida es un hecho histórico de auditoría — no
    desaparece si el documento fuente se borra después (RAG-009 solo
    purga contenido/índice, no las citas ya registradas)."""
    _init_db(db_path)
    session_repo = SessionRepository(db_path)
    turn_repo = TurnRepository(db_path)
    citation_repo = CitationRepository()

    session = session_repo.create(case_id="demo-case-001", state="responding", knowledge_version=1)
    turn = turn_repo.add(session_id=session["id"], speaker="agent", text="...", sequence=1)

    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO documents "
            "(id, title, filename, checksum, status, mime, size_bytes, applicability, "
            " knowledge_version, created_at, updated_at) "
            "VALUES ('doc-2','Doc','d.md','chk2','ready','text/markdown',10,'{}',1,"
            "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO document_chunks "
            "(id, document_id, section, page, text, created_at, chunk_index, char_start, "
            " char_end, content_hash, embedding, embedding_dim) "
            "VALUES ('chunk-2','doc-2',NULL,NULL,'texto','2026-01-01T00:00:00Z',0,0,5,'h',NULL,0)"
        )
        citation_repo.record(
            conn,
            turn_id=turn["id"],
            citation=CitationRef(
                citation_id=str(uuid.uuid4()),
                document_id="doc-2",
                document_version=1,
                chunk_id="chunk-2",
                title="Doc",
                knowledge_version=1,
            ),
            created_at="2026-01-01T00:00:00Z",
        )
        conn.commit()

        # Simula el borrado RAG-009: se cambia el status del documento pero
        # la cita ya registrada no se toca.
        conn.execute("UPDATE documents SET status = 'deleted' WHERE id = 'doc-2'")
        conn.commit()

        rows = citation_repo.list_for_turn(conn, turn["id"])
        assert len(rows) == 1
    finally:
        conn.close()
