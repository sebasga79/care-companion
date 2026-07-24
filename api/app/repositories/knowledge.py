"""Acceso a la versión global de conocimiento (DB-001, extendido en RAG-008/009).

`get_current_knowledge_version` abre su propia conexión corta — la usa
`POST /api/v1/sessions` para fijar `knowledge_version` al crear una sesión
(spec.md §11.2 BR-001). `get_current_knowledge_version_conn` /
`increment_knowledge_version_conn` operan sobre una conexión ya abierta por
el llamador: el learn/forget transaccional (RAG-008/RAG-009) necesita que
el incremento de versión viva en la MISMA transacción que la escritura de
documento/chunks/FTS y la consulta canaria, para que un fallo de canaria
haga rollback de todo junto — no solo de las filas de contenido."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.repositories.db import session_scope


def get_current_knowledge_version(database_path: str) -> int:
    with session_scope(database_path) as conn:
        return get_current_knowledge_version_conn(conn)


def get_current_knowledge_version_conn(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT version FROM knowledge_version WHERE id = 1").fetchone()
    return int(row["version"]) if row is not None else 1


def increment_knowledge_version_conn(conn: sqlite3.Connection) -> int:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE knowledge_version SET version = version + 1, updated_at = ? WHERE id = 1", (now,)
    )
    return get_current_knowledge_version_conn(conn)
