"""Repositorio de decisiones (Sprint C2, SAFE-003/ORC-002)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.domain.decision import DecisionResult
from app.repositories.db import session_scope


class DecisionRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def add(self, *, session_id: str, decision: DecisionResult) -> dict[str, Any]:
        decision_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO decisions
                    (id, session_id, level, should_escalate, trigger_codes, rationale, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    session_id,
                    decision.level.value,
                    int(decision.should_escalate),
                    json.dumps(decision.trigger_codes),
                    decision.rationale,
                    now,
                ),
            )
        return {"id": decision_id, "session_id": session_id, "created_at": now}

    def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        results = []
        for row in rows:
            record = dict(row)
            record["trigger_codes"] = json.loads(record["trigger_codes"])
            record["should_escalate"] = bool(record["should_escalate"])
            results.append(record)
        return results


__all__ = ["DecisionRepository"]
