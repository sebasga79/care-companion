"""`CallSummary` — resumen estructurado de llamada (SUM-001, spec.md §8.3).

En esta fase solo se define el schema y se produce una instancia
"vacía-válida" al cerrar una sesión (stub). El llenado real con
observaciones/decisión/citas llega en SUM-002 (Sprint C2), cuando existan
`InterviewAgent`/`TriageAgent`/`RetrievalAgent`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.decision import DecisionLevel
from app.domain.models import CitationRef, UsageMetrics


class RiskSummary(BaseModel):
    level: DecisionLevel = DecisionLevel.ROUTINE_FOLLOW_UP
    should_escalate: bool = False
    trigger_codes: list[str] = Field(default_factory=list)


class HandoffSummary(BaseModel):
    status: Literal["none", "created", "acknowledged"] = "none"
    reason: str | None = None


class CallSummary(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: UUID
    case_id: str
    procedure: str | None = None
    started_at: datetime
    ended_at: datetime | None = None

    patient_reported: list[dict] = Field(default_factory=list)
    explicit_denials: list[dict] = Field(default_factory=list)
    not_assessed: list[dict] = Field(default_factory=list)
    clarifications: list[dict] = Field(default_factory=list)

    risk: RiskSummary = Field(default_factory=RiskSummary)
    citations: list[CitationRef] = Field(default_factory=list)
    handoff: HandoffSummary = Field(default_factory=HandoffSummary)
    follow_up_items: list[str] = Field(default_factory=list)

    usage: UsageMetrics = Field(default_factory=UsageMetrics)
    knowledge_version: int
