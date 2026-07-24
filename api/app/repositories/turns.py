"""Repositorio de turnos de conversación (DB-002)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from app.repositories.db import session_scope

Speaker = Literal["patient", "agent", "system"]


class TurnRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def add(
        self,
        *,
        session_id: str,
        speaker: Speaker,
        text: str,
        sequence: int,
        is_final: bool = True,
    ) -> dict[str, Any]:
        turn_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO turns (id, session_id, speaker, text, is_final, sequence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (turn_id, session_id, speaker, text, int(is_final), sequence, now),
            )
        return {
            "id": turn_id,
            "session_id": session_id,
            "speaker": speaker,
            "text": text,
            "is_final": is_final,
            "sequence": sequence,
            "created_at": now,
        }

    def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY sequence ASC",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]
