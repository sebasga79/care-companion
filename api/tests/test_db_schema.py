"""DB-001 — schema idempotente. RAG-001 extiende este archivo con las
columnas/tabla FTS5 nuevas sobre `documents`/`document_chunks`/`citations`."""

from __future__ import annotations

from app.repositories.db import apply_schema, get_connection

_EXPECTED_TABLES = {
    "knowledge_version",
    "sessions",
    "turns",
    "events",
    "documents",
    "document_chunks",
    "document_chunks_fts",
    "citations",
    "metrics",
    "followup_records",
}

_EXPECTED_DOCUMENT_COLUMNS = {
    "id",
    "title",
    "filename",
    "checksum",
    "status",
    "mime",
    "size_bytes",
    "applicability",
    "knowledge_version",  # reutilizada como "knowledge_version_added"
    "knowledge_version_deleted",
    "deleted_at",
    "deleted_by",
    "error_reason",
    "created_at",
    "updated_at",
}

_EXPECTED_CHUNK_COLUMNS = {
    "id",
    "document_id",
    "section",
    "page",
    "text",
    "created_at",
    "chunk_index",
    "char_start",
    "char_end",
    "content_hash",
    "embedding",
    "embedding_dim",
}

_EXPECTED_CITATION_COLUMNS = {
    "id",
    "turn_id",
    "document_id",
    "chunk_id",
    "document_version",
    "title",
    "section",
    "page",
    "knowledge_version",
    "created_at",
}


def test_apply_schema_creates_all_tables(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        table_names = {row["name"] for row in rows}
        assert _EXPECTED_TABLES.issubset(table_names)
    finally:
        conn.close()


def test_apply_schema_is_idempotent(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        apply_schema(conn)  # segunda aplicación no debe fallar ni duplicar
        rows = conn.execute("SELECT COUNT(*) AS n FROM knowledge_version").fetchone()
        assert rows["n"] == 1
    finally:
        conn.close()


def test_knowledge_version_seeded_to_one(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        row = conn.execute("SELECT version FROM knowledge_version WHERE id = 1").fetchone()
        assert row["version"] == 1
    finally:
        conn.close()


def test_wal_and_foreign_keys_enabled(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert journal_mode.lower() == "wal"
        assert foreign_keys == 1
    finally:
        conn.close()


def test_foreign_key_violation_is_rejected(db_path: str) -> None:
    import sqlite3

    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        try:
            conn.execute(
                "INSERT INTO turns "
                "(id, session_id, speaker, text, is_final, sequence, created_at) "
                "VALUES "
                "('t1', 'nonexistent-session', 'patient', 'hola', 1, 1, '2026-01-01T00:00:00Z')"
            )
            conn.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
        assert raised, "una FK inexistente debe rechazarse, no insertarse silenciosamente"
    finally:
        conn.close()


def test_rag_001_documents_table_has_expected_columns(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
        assert _EXPECTED_DOCUMENT_COLUMNS.issubset(columns)
    finally:
        conn.close()


def test_rag_001_document_chunks_table_has_expected_columns(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(document_chunks)")}
        assert _EXPECTED_CHUNK_COLUMNS.issubset(columns)
    finally:
        conn.close()


def test_rag_001_citations_table_has_expected_columns(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(citations)")}
        assert _EXPECTED_CITATION_COLUMNS.issubset(columns)
    finally:
        conn.close()


def test_rag_001_fts5_table_is_queryable(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        conn.execute(
            "INSERT INTO document_chunks_fts (chunk_id, document_id, text) "
            "VALUES ('c1', 'd1', 'texto de prueba sobre cuidado postoperatorio')"
        )
        rows = conn.execute(
            "SELECT chunk_id FROM document_chunks_fts WHERE document_chunks_fts MATCH 'cuidado'"
        ).fetchall()
        assert [r["chunk_id"] for r in rows] == ["c1"]
    finally:
        conn.close()


def test_rag_001_additive_migration_is_idempotent_on_preexisting_db(db_path: str) -> None:
    """Simula una BD creada ANTES de RAG-001 (solo columnas originales) y
    verifica que aplicar el schema actualizado agrega las columnas nuevas
    sin duplicarlas ni fallar en corridas repetidas — el caso real que
    `_ensure_additive_columns` (app/repositories/db.py) existe para cubrir."""
    conn = get_connection(db_path)
    try:
        # Recreamos manualmente el shape "viejo" de `documents` (antes de
        # RAG-001), sin usar apply_schema, para simular una BD heredada.
        conn.execute(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                checksum TEXT NOT NULL,
                status TEXT NOT NULL,
                knowledge_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO documents "
            "(id, title, checksum, status, knowledge_version, created_at, updated_at) "
            "VALUES ('legacy-1','Legado','chk','ready',1,'2026-01-01T00:00:00Z',"
            "'2026-01-01T00:00:00Z')"
        )
        conn.commit()

        apply_schema(conn)
        apply_schema(conn)  # segunda corrida: no debe fallar ni duplicar columnas

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
        assert _EXPECTED_DOCUMENT_COLUMNS.issubset(columns)

        legacy_row = conn.execute("SELECT * FROM documents WHERE id = 'legacy-1'").fetchone()
        assert legacy_row is not None
        assert legacy_row["filename"] == ""  # default backfill para la fila preexistente
        assert legacy_row["applicability"] == "{}"
    finally:
        conn.close()
