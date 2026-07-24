"""Repositorio de observaciones (Sprint C2, CON-001/ORC-002)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.domain.observation import Observation
from app.repositories.db import session_scope


class ObservationRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def add(self, *, session_id: str, observation: Observation) -> dict[str, Any]:
        observation_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO observations
                    (id, session_id, code, label, value, certainty, original_text,
                     normalized_text, source_turn_id, normalized_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    session_id,
                    observation.code,
                    observation.label,
                    json.dumps(observation.value),
                    observation.certainty,
                    observation.original_text,
                    observation.normalized_text,
                    observation.source_turn_id,
                    observation.normalized_by,
                    now,
                ),
            )
        return {"id": observation_id, "session_id": session_id, "created_at": now}

    def list_for_session(self, session_id: str) -> list[Observation]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM observations WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [_row_to_observation(row) for row in rows]


def _row_to_observation(row: Any) -> Observation:
    record = dict(row)
    try:
        value = json.loads(record["value"]) if record["value"] is not None else None
    except json.JSONDecodeError:
        value = record["value"]
    return Observation(
        code=record["code"],
        label=record["label"],
        value=value,
        certainty=record["certainty"],
        original_text=record["original_text"],
        normalized_text=record["normalized_text"],
        source_turn_id=record["source_turn_id"],
        normalized_by=record["normalized_by"],
    )


__all__ = ["ObservationRepository"]
