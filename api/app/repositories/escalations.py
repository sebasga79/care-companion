"""Repositorio de escalamientos (SAFE-004) — `create_if_absent` es la
única vía de escritura, e implementa la idempotencia por
`session_id + trigger_set + decision_level` exigida por BR-025: primero
comprueba si ya existe una fila con el mismo `idempotency_key` para la
sesión (defensa a nivel de aplicación) y además confía en el índice único
`idx_escalations_session_idem` (defensa a nivel de esquema) por si dos
llamadas concurrentes pasan la comprobación al mismo tiempo — en ese caso
se atrapa el `IntegrityError` y se devuelve la fila ya existente en vez de
fallar o duplicar."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from app.domain.decision import DecisionResult
from app.domain.escalation import EscalationRecord, compute_idempotency_key
from app.repositories.db import session_scope


class EscalationRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def create_if_absent(self, *, session_id: str, decision: DecisionResult) -> EscalationRecord:
        idempotency_key = compute_idempotency_key(
            session_id=session_id,
            decision_level=decision.level,
            trigger_codes=decision.trigger_codes,
        )
        reasons = [decision.rationale]

        with session_scope(self._database_path) as conn:
            existing = conn.execute(
                "SELECT * FROM escalations WHERE session_id = ? AND idempotency_key = ?",
                (session_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return _row_to_record(existing, was_duplicate=True)

            escalation_id = str(uuid.uuid4())
            now = datetime.now(UTC).isoformat()
            try:
                conn.execute(
                    """
                    INSERT INTO escalations
                        (id, session_id, decision_level, reasons, trigger_codes,
                         idempotency_key, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        escalation_id,
                        session_id,
                        decision.level.value,
                        json.dumps(reasons),
                        json.dumps(decision.trigger_codes),
                        idempotency_key,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                # Carrera concurrente: otra transacción insertó la misma
                # condición entre nuestro SELECT y este INSERT. El índice
                # único ya impidió el duplicado a nivel de esquema; aquí
                # solo recuperamos la fila ganadora en vez de fallar.
                row = conn.execute(
                    "SELECT * FROM escalations WHERE session_id = ? AND idempotency_key = ?",
                    (session_id, idempotency_key),
                ).fetchone()
                assert row is not None
                return _row_to_record(row, was_duplicate=True)

            row = conn.execute(
                "SELECT * FROM escalations WHERE id = ?", (escalation_id,)
            ).fetchone()
        assert row is not None
        return _row_to_record(row, was_duplicate=False)

    def list_for_session(self, session_id: str) -> list[EscalationRecord]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM escalations WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [_row_to_record(row, was_duplicate=False) for row in rows]


def _row_to_record(row: sqlite3.Row, *, was_duplicate: bool) -> EscalationRecord:
    record = dict(row)
    return EscalationRecord(
        id=record["id"],
        session_id=record["session_id"],
        decision_level=record["decision_level"],
        reasons=json.loads(record["reasons"]),
        trigger_codes=json.loads(record["trigger_codes"]),
        idempotency_key=record["idempotency_key"],
        created_at=record["created_at"],
        was_duplicate=was_duplicate,
    )


__all__ = ["EscalationRepository"]
