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


def apply_schema(conn: sqlite3.Connection) -> None:
    """Aplica `db/schema.sql`. Idempotente: solo usa CREATE TABLE IF NOT
    EXISTS / INSERT OR IGNORE, seguro de correr en cada arranque."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


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
