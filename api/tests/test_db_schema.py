"""DB-001 — schema idempotente."""

from __future__ import annotations

from app.repositories.db import apply_schema, get_connection

_EXPECTED_TABLES = {
    "knowledge_version",
    "sessions",
    "turns",
    "events",
    "documents",
    "document_chunks",
    "citations",
    "metrics",
}


def test_apply_schema_creates_all_tables(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
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
