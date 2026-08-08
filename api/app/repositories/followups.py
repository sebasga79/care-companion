"""Persistencia idempotente de la proyección longitudinal de una llamada."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.domain.summary import FollowupRecord
from app.repositories.db import session_scope


class FollowupRecordRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def upsert(self, *, session_id: str, case_id: str, record: FollowupRecord) -> dict[str, Any]:
        if not record.patient_id:
            raise ValueError("followup record requiere patient_id")
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO followup_records
                    (session_id, patient_id, case_id, recorded_at, payload,
                     decision_level, should_escalate, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    patient_id = excluded.patient_id,
                    case_id = excluded.case_id,
                    recorded_at = excluded.recorded_at,
                    payload = excluded.payload,
                    decision_level = excluded.decision_level,
                    should_escalate = excluded.should_escalate,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    record.patient_id,
                    case_id,
                    record.recorded_at.isoformat(),
                    payload,
                    record.decision_level.value,
                    int(record.alerta_equipo_medico),
                    now,
                    now,
                ),
            )
        return self.get_for_session(session_id) or {}

    def get_for_session(self, session_id: str) -> dict[str, Any] | None:
        with session_scope(self._database_path) as conn:
            row = conn.execute(
                "SELECT * FROM followup_records WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def list_for_patient(self, patient_id: str) -> list[dict[str, Any]]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM followup_records
                WHERE patient_id = ?
                ORDER BY recorded_at ASC
                """,
                (patient_id,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["payload"] = json.loads(result["payload"])
    result["should_escalate"] = bool(result["should_escalate"])
    return result


__all__ = ["FollowupRecordRepository"]
