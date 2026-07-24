"""Repositorio de sesiones (DB-002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.repositories.db import session_scope


class SessionRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def create(self, *, case_id: str, state: str, knowledge_version: int) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (id, case_id, state, knowledge_version, created_at, updated_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (session_id, case_id, state, knowledge_version, now, now),
            )
        record = self.get(session_id)
        assert record is not None  # acabamos de crearlo en la misma llamada
        return record

    def get(self, session_id: str) -> dict[str, Any] | None:
        with session_scope(self._database_path) as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row is not None else None

    def update_state(
        self, session_id: str, *, state: str, closed_at: str | None = None
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                UPDATE sessions
                SET state = ?, updated_at = ?, closed_at = COALESCE(?, closed_at)
                WHERE id = ?
                """,
                (state, now, closed_at, session_id),
            )
        return self.get(session_id)

    def list_all(self) -> list[dict[str, Any]]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
