"""`CallSummary` — resumen estructurado de llamada (SUM-001/SUM-002,
spec.md §8.3).

SUM-001 define el schema y produce una instancia "vacía-válida" al cerrar
una sesión sin turnos (sigue soportado: `build_call_summary` con listas
vacías reproduce ese mismo resultado). SUM-002 añade `build_call_summary`,
que llena el resumen a partir de lo que el `CallCycleOrchestrator`
(ORC-002) ya persistió durante la llamada — observaciones, decisiones,
citas y uso — sin inventar ni inferir nada que no esté en esas fuentes
(BR-006/spec.md §11.2: nada de datos "recordados" por el LLM en el
resumen, todo viene de repositorios)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.decision import DecisionLevel
from app.domain.escalation import EscalationRecord
from app.domain.models import CitationRef, UsageMetrics
from app.domain.observation import Observation


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


def _observation_entry(observation: Observation) -> dict[str, Any]:
    """Proyección estable de `Observation` para las cuatro listas del
    resumen — conserva texto original y turno fuente (BR-006: nunca se
    colapsa a un booleano sin procedencia)."""
    return {
        "code": observation.code,
        "label": observation.label,
        "value": observation.value,
        "certainty": observation.certainty,
        "original_text": observation.original_text,
        "normalized_text": observation.normalized_text,
        "source_turn_id": observation.source_turn_id,
    }


def _decision_to_risk(decision_record: dict[str, Any]) -> RiskSummary:
    return RiskSummary(
        level=DecisionLevel(decision_record["level"]),
        should_escalate=bool(decision_record["should_escalate"]),
        trigger_codes=list(decision_record["trigger_codes"]),
    )


def build_call_summary(
    *,
    session: dict[str, Any],
    observations: list[Observation],
    decisions: list[dict[str, Any]],
    citations: list[CitationRef],
    escalations: list[EscalationRecord],
    procedure: str | None = None,
    usage: UsageMetrics | None = None,
    ended_at: datetime | None = None,
) -> CallSummary:
    """Construye el `CallSummary` real de una sesión (SUM-002).

    Parámetros ya vienen de repositorios (`SessionRepository.get`,
    `ObservationRepository.list_for_session`, `DecisionRepository.list_for_session`,
    `CitationRepository.list_for_session` + `to_citation_ref`,
    `EscalationRepository.list_for_session`) — esta función es pura
    respecto a esas listas, no hace I/O ni llama al LLM.

    Reglas de bucketing (spec.md §11.2, "silencio ≠ negación";
    docs/fixtures/conversational-scenarios.md escenarios A/B/D):

    - `certainty="confirmed"`  -> `patient_reported`
    - `certainty="denied"`     -> `explicit_denials`
    - `certainty="not_assessed"` -> `not_assessed`
    - `certainty="uncertain"`  -> `clarifications` (ambigüedad o
      contradicción que no llegó a resolverse dentro de la llamada — nunca
      se fuerza a "confirmed"/"denied") y también alimenta
      `follow_up_items`, para que quede visible que requiere seguimiento.

    `risk`/`handoff` reflejan el estado MÁS RECIENTE (última decisión y
    último registro de escalamiento) — una sesión puede pasar por varias
    decisiones dentro del loop Respond->Interview (architecture.md §7); el
    resumen final es un snapshot del desenlace, no un historial completo
    (ese historial ya vive en `decisions`/`escalations` vía la API de
    auditoría, no se duplica aquí)."""
    started_at = datetime.fromisoformat(session["created_at"])

    patient_reported: list[dict[str, Any]] = []
    explicit_denials: list[dict[str, Any]] = []
    not_assessed: list[dict[str, Any]] = []
    clarifications: list[dict[str, Any]] = []
    follow_up_items: list[str] = []

    for observation in observations:
        entry = _observation_entry(observation)
        if observation.certainty == "confirmed":
            patient_reported.append(entry)
        elif observation.certainty == "denied":
            explicit_denials.append(entry)
        elif observation.certainty == "not_assessed":
            not_assessed.append(entry)
        else:  # "uncertain"
            clarifications.append(entry)
            follow_up_items.append(
                f"{observation.label}: aclaración no resuelta durante la llamada "
                f"(texto original: {observation.original_text!r})"
            )

    risk = _decision_to_risk(decisions[-1]) if decisions else RiskSummary()

    if escalations:
        last_escalation = escalations[-1]
        handoff = HandoffSummary(
            status="created",
            reason=last_escalation.reasons[0] if last_escalation.reasons else None,
        )
    else:
        handoff = HandoffSummary()

    return CallSummary(
        session_id=UUID(session["id"]),
        case_id=session["case_id"],
        procedure=procedure,
        started_at=started_at,
        ended_at=ended_at,
        patient_reported=patient_reported,
        explicit_denials=explicit_denials,
        not_assessed=not_assessed,
        clarifications=clarifications,
        risk=risk,
        citations=list(citations),
        handoff=handoff,
        follow_up_items=follow_up_items,
        usage=usage if usage is not None else UsageMetrics(),
        knowledge_version=session["knowledge_version"],
    )
