"""Conexión SQLite WAL + aplicación de schema (DB-001/DB-002).

Sin ORM (política de dependencias). Cada repositorio abre una conexión
corta por operación vía `session_scope`, en vez de compartir una conexión
larga entre requests — favorece transacciones cortas y es más seguro bajo
concurrencia con el driver stdlib `sqlite3` (una conexión por uso, no por
hilo compartido)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def get_connection(database_path: str) -> sqlite3.Connection:
    """Abre una conexión con WAL y foreign_keys activados. Crea el
    directorio contenedor si no existe (arranque limpio, REL-001)."""
    path = Path(database_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(database_path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Columnas agregadas por RAG-001 sobre tablas que ya existían (documents,
# document_chunks, citations). `CREATE TABLE IF NOT EXISTS` no agrega
# columnas a una tabla preexistente, así que la migración real vive aquí:
# por cada tabla, se agrega cada columna que falte vía `ALTER TABLE ... ADD
# COLUMN`, verificado con `PRAGMA table_info` antes de intentarlo. Correrlo
# dos veces es un no-op (ninguna columna falta la segunda vez) — mismo
# contrato de idempotencia que `apply_schema` (DB-001).
_ADDITIVE_COLUMNS: dict[str, list[str]] = {
    "documents": [
        "filename TEXT NOT NULL DEFAULT ''",
        "mime TEXT NOT NULL DEFAULT 'text/plain'",
        "size_bytes INTEGER NOT NULL DEFAULT 0",
        "applicability TEXT NOT NULL DEFAULT '{}'",
        "knowledge_version_deleted INTEGER",
        "deleted_at TEXT",
        "deleted_by TEXT",
        "error_reason TEXT",
    ],
    "document_chunks": [
        "chunk_index INTEGER NOT NULL DEFAULT 0",
        "char_start INTEGER",
        "char_end INTEGER",
        "content_hash TEXT NOT NULL DEFAULT ''",
        "embedding BLOB",
        "embedding_dim INTEGER NOT NULL DEFAULT 0",
    ],
    "citations": [
        "title TEXT NOT NULL DEFAULT ''",
        "section TEXT",
        "page INTEGER",
        "knowledge_version INTEGER NOT NULL DEFAULT 0",
    ],
}


def _ensure_additive_columns(conn: sqlite3.Connection) -> None:
    for table, column_defs in _ADDITIVE_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column_def in column_defs:
            column_name = column_def.split()[0]
            if column_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def apply_schema(conn: sqlite3.Connection) -> None:
    """Aplica `db/schema.sql`. Idempotente: solo usa CREATE TABLE IF NOT
    EXISTS / INSERT OR IGNORE, seguro de correr en cada arranque. Luego
    aplica `_ensure_additive_columns` (RAG-001) para las columnas nuevas
    sobre tablas preexistentes — igualmente idempotente."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    _ensure_additive_columns(conn)


@contextmanager
def session_scope(database_path: str) -> Iterator[sqlite3.Connection]:
    """Transacción corta: abre, ejecuta, hace commit o rollback, y cierra
    siempre. Ningún repositorio debe mantener una conexión abierta fuera de
    este bloque (DB-002)."""
    conn = get_connection(database_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
