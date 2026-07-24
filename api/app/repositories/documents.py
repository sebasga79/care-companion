"""Repositorio de documentos RAG (RAG-001/008/009).

Los métodos de lectura standalone (`list_all`, `get`, `active_checksums`)
abren su propia conexión corta, igual que el resto de repositorios
(DB-002). Los métodos de escritura usados por el pipeline de
aprendizaje/olvido (`insert`, `update_status`, `mark_deleted`) reciben una
conexión ya abierta por el llamador (`sqlite3.Connection`, no
`database_path`) — deben participar en la MISMA transacción que
`DocumentChunkRepository` y el incremento de `knowledge_version`, para que
un fallo de consulta canaria haga rollback de todo el conjunto
(spec.md §9.2/9.3, BR-016/BR-017)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Literal

from app.repositories.db import session_scope

DocumentStatus = Literal["processing", "ready", "deleted", "failed"]


def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    try:
        record["applicability"] = json.loads(record["applicability"] or "{}")
    except json.JSONDecodeError:
        record["applicability"] = {}
    return record


class DocumentRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def list_all(self, *, include_deleted: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM documents"
        if not include_deleted:
            query += " WHERE status != 'deleted'"
        query += " ORDER BY created_at DESC"
        with session_scope(self._database_path) as conn:
            rows = conn.execute(query).fetchall()
        return [_row_to_document(row) for row in rows]

    def get(self, document_id: str) -> dict[str, Any] | None:
        with session_scope(self._database_path) as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return _row_to_document(row) if row is not None else None

    def active_checksums(self) -> frozenset[str]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT checksum FROM documents WHERE status IN ('processing', 'ready')"
            ).fetchall()
        return frozenset(row["checksum"] for row in rows)

    # -- escritura, dentro de una transacción del llamador (RAG-008/009) --

    def insert(
        self,
        conn: sqlite3.Connection,
        *,
        document_id: str,
        filename: str,
        checksum: str,
        status: DocumentStatus,
        mime: str,
        size_bytes: int,
        applicability: dict[str, Any],
        knowledge_version_added: int,
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO documents
                (id, title, filename, checksum, status, mime, size_bytes, applicability,
                 knowledge_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                filename,
                filename,
                checksum,
                status,
                mime,
                size_bytes,
                json.dumps(applicability),
                knowledge_version_added,
                created_at,
                created_at,
            ),
        )

    def update_status(
        self,
        conn: sqlite3.Connection,
        document_id: str,
        *,
        status: DocumentStatus,
        updated_at: str,
        error_reason: str | None = None,
    ) -> None:
        conn.execute(
            "UPDATE documents SET status = ?, error_reason = ?, updated_at = ? WHERE id = ?",
            (status, error_reason, updated_at, document_id),
        )

    def mark_deleted(
        self,
        conn: sqlite3.Connection,
        document_id: str,
        *,
        knowledge_version_deleted: int,
        deleted_at: str,
        deleted_by: str | None,
    ) -> None:
        conn.execute(
            """
            UPDATE documents
            SET status = 'deleted',
                knowledge_version_deleted = ?,
                deleted_at = ?,
                deleted_by = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (knowledge_version_deleted, deleted_at, deleted_by, deleted_at, document_id),
        )

    def get_conn(self, conn: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return _row_to_document(row) if row is not None else None
