"""`EscalationRecord` (SAFE-004, spec.md §8.3/§11.1) — registro de
escalamiento simulado. En el reto, "alertar" es un evento visible y
auditable, no una integración real (architecture.md §8.3): nunca llama,
envía mensajes ni escribe en un EHR real.

Idempotencia (BR-025): la alerta es idempotente por
`session_id + trigger_set + decision_level`. `idempotency_key` se deriva
de esos tres campos con un hash estable — repetir la misma condición en la
misma sesión nunca produce una segunda fila."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.decision import DecisionLevel


def compute_idempotency_key(
    *, session_id: str, decision_level: DecisionLevel, trigger_codes: list[str]
) -> str:
    normalized_triggers = ",".join(sorted(trigger_codes))
    raw = f"{session_id}|{decision_level.value}|{normalized_triggers}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EscalationRecord(BaseModel):
    id: str
    session_id: str
    decision_level: DecisionLevel
    reasons: list[str] = Field(default_factory=list)
    trigger_codes: list[str] = Field(default_factory=list)
    idempotency_key: str
    created_at: datetime
    was_duplicate: bool = False


__all__ = ["EscalationRecord", "compute_idempotency_key"]
