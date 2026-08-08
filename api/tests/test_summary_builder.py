"""SUM-002 — `build_call_summary`: llenado real del `CallSummary` a partir
de observaciones/decisión/citas/escalamientos ya persistidos por ORC-002.

Incluye un golden snapshot (estructura completa esperada) además de tests
de bucketing puntuales por regla de negocio."""

from __future__ import annotations

from uuid import uuid4

from app.domain.decision import DecisionLevel
from app.domain.escalation import EscalationRecord
from app.domain.models import CitationRef, UsageMetrics
from app.domain.observation import Observation
from app.domain.summary import build_call_summary

_SESSION_ID = str(uuid4())


def _session(**overrides: object) -> dict:
    base = {
        "id": _SESSION_ID,
        "case_id": "demo-case-001",
        "state": "summarizing",
        "knowledge_version": 3,
        "created_at": "2026-08-08T10:00:00+00:00",
        "updated_at": "2026-08-08T10:05:00+00:00",
        "closed_at": None,
    }
    base.update(overrides)
    return base


def test_empty_session_produces_the_sum001_empty_valid_summary() -> None:
    summary = build_call_summary(
        session=_session(),
        observations=[],
        decisions=[],
        citations=[],
        escalations=[],
    )
    assert summary.patient_reported == []
    assert summary.explicit_denials == []
    assert summary.not_assessed == []
    assert summary.clarifications == []
    assert summary.risk.level == DecisionLevel.ROUTINE_FOLLOW_UP
    assert summary.risk.should_escalate is False
    assert summary.citations == []
    assert summary.handoff.status == "none"
    assert summary.follow_up_items == []


def test_observations_bucket_by_certainty() -> None:
    observations = [
        Observation(
            code="FEVER",
            label="fiebre",
            certainty="confirmed",
            original_text="sí, tuvo fiebre anoche",
            source_turn_id="t1",
        ),
        Observation(
            code="WOUND_DISCHARGE",
            label="secreción de la herida",
            certainty="denied",
            original_text="no, nada de eso",
            source_turn_id="t2",
        ),
        Observation.not_assessed(code="INTAKE", label="tolerancia a líquidos"),
        Observation(
            code="GENERAL_STATE",
            label="ánimo general",
            certainty="uncertain",
            original_text="la vi un poco maluca",
            source_turn_id="t3",
        ),
    ]
    summary = build_call_summary(
        session=_session(),
        observations=observations,
        decisions=[],
        citations=[],
        escalations=[],
    )
    assert [o["code"] for o in summary.patient_reported] == ["FEVER"]
    assert [o["code"] for o in summary.explicit_denials] == ["WOUND_DISCHARGE"]
    assert [o["code"] for o in summary.not_assessed] == ["INTAKE"]
    assert [o["code"] for o in summary.clarifications] == ["GENERAL_STATE"]
    # texto original nunca se pierde (BR-006)
    assert summary.patient_reported[0]["original_text"] == "sí, tuvo fiebre anoche"
    # una ambigüedad no resuelta queda visible como pendiente de seguimiento
    assert len(summary.follow_up_items) == 1
    assert "maluca" in summary.follow_up_items[0]


def test_risk_reflects_most_recent_decision() -> None:
    decisions = [
        {
            "level": "MODEL_MODERATE_RISK",
            "should_escalate": False,
            "trigger_codes": [],
            "rationale": "primero",
            "created_at": "t1",
        },
        {
            "level": "HARD_RED_FLAG",
            "should_escalate": True,
            "trigger_codes": ["FEVER_WITH_WOUND_DISCHARGE"],
            "rationale": "después",
            "created_at": "t2",
        },
    ]
    summary = build_call_summary(
        session=_session(),
        observations=[],
        decisions=decisions,
        citations=[],
        escalations=[],
    )
    assert summary.risk.level == DecisionLevel.HARD_RED_FLAG
    assert summary.risk.should_escalate is True
    assert summary.risk.trigger_codes == ["FEVER_WITH_WOUND_DISCHARGE"]


def test_handoff_reflects_last_escalation_when_present() -> None:
    escalations = [
        EscalationRecord(
            id="e1",
            session_id=_SESSION_ID,
            decision_level=DecisionLevel.HARD_RED_FLAG,
            reasons=["Señal(es) de alarma determinista(s) activa(s)."],
            trigger_codes=["FEVER_WITH_WOUND_DISCHARGE"],
            idempotency_key="k1",
            created_at="2026-08-08T10:02:00+00:00",
        )
    ]
    summary = build_call_summary(
        session=_session(),
        observations=[],
        decisions=[],
        citations=[],
        escalations=escalations,
    )
    assert summary.handoff.status == "created"
    assert summary.handoff.reason == "Señal(es) de alarma determinista(s) activa(s)."


def test_followup_record_uses_dataset_axes_and_alert_decision() -> None:
    observations = [
        Observation(
            code="PAIN_SEVERITY",
            label="intensidad del dolor",
            value="8",
            certainty="confirmed",
            original_text="ocho de diez",
            source_turn_id="t1",
        ),
        Observation(
            code="FEVER",
            label="fiebre",
            value="39.2",
            certainty="confirmed",
            original_text="treinta y nueve punto dos",
            source_turn_id="t2",
        ),
    ]
    decisions = [
        {
            "level": "HARD_RED_FLAG",
            "should_escalate": True,
            "trigger_codes": ["HIGH_FEVER"],
            "rationale": "fiebre alta",
            "created_at": "t3",
        }
    ]

    summary = build_call_summary(
        session=_session(),
        observations=observations,
        decisions=decisions,
        citations=[],
        escalations=[],
        patient_id="pac_1",
    )

    assert summary.followup_record is not None
    assert summary.followup_record.patient_id == "pac_1"
    assert summary.followup_record.dolor_nrs is not None
    assert summary.followup_record.dolor_nrs.value == 8
    assert summary.followup_record.fiebre_c is not None
    assert summary.followup_record.fiebre_c.value == 39.2
    assert summary.followup_record.alerta_equipo_medico is True


def test_citations_pass_through_unchanged() -> None:
    citation = CitationRef(
        citation_id="c1",
        document_id="d1",
        document_version=2,
        chunk_id="ch1",
        title="Guía de alta posoperatoria",
        section="Signos de alarma",
        page=4,
        knowledge_version=3,
    )
    summary = build_call_summary(
        session=_session(),
        observations=[],
        decisions=[],
        citations=[citation],
        escalations=[],
    )
    assert summary.citations == [citation]


def test_golden_snapshot_full_summary() -> None:
    """Snapshot estructural completo — si un campo cambia de forma o de
    bucketing sin querer, este test debe fallar explícitamente en vez de
    dejarlo pasar silenciosamente."""
    session = _session(closed_at="2026-08-08T10:10:00+00:00")
    observations = [
        Observation(
            code="FEVER",
            label="fiebre",
            certainty="confirmed",
            original_text="sí tuvo fiebre alta anoche",
            source_turn_id="t1",
        ),
        Observation(
            code="WOUND_DISCHARGE",
            label="secreción de la herida",
            certainty="confirmed",
            original_text="sale un líquido amarillento y huele feo",
            source_turn_id="t2",
        ),
        Observation.not_assessed(code="INTAKE", label="tolerancia a líquidos"),
    ]
    decisions = [
        {
            "level": "HARD_RED_FLAG",
            "should_escalate": True,
            "trigger_codes": ["FEVER_WITH_WOUND_DISCHARGE"],
            "rationale": "Señal(es) de alarma determinista(s) activa(s); precedencia máxima, "
            "no degradable por el modelo.",
            "created_at": "2026-08-08T10:03:00+00:00",
        }
    ]
    citations = [
        CitationRef(
            citation_id="c1",
            document_id="d1",
            document_version=1,
            chunk_id="ch1",
            title="Guía de alta posoperatoria",
            section="Signos de alarma",
            page=4,
            knowledge_version=3,
        )
    ]
    escalations = [
        EscalationRecord(
            id="e1",
            session_id=_SESSION_ID,
            decision_level=DecisionLevel.HARD_RED_FLAG,
            reasons=[
                "Señal(es) de alarma determinista(s) activa(s); precedencia máxima, "
                "no degradable por el modelo."
            ],
            trigger_codes=["FEVER_WITH_WOUND_DISCHARGE"],
            idempotency_key="k1",
            created_at="2026-08-08T10:03:00+00:00",
        )
    ]
    usage = UsageMetrics(
        input_tokens=42, output_tokens=17, latency_ms=123.4, provider="fake-scripted"
    )

    summary = build_call_summary(
        session=session,
        observations=observations,
        decisions=decisions,
        citations=citations,
        escalations=escalations,
        usage=usage,
        ended_at=None,
    )

    golden = {
        "schema_version": "1.2",
        "case_id": "demo-case-001",
        "procedure": None,
        "patient_reported": [
            {
                "code": "FEVER",
                "label": "fiebre",
                "value": None,
                "certainty": "confirmed",
                "original_text": "sí tuvo fiebre alta anoche",
                "normalized_text": None,
                "source_turn_id": "t1",
            },
            {
                "code": "WOUND_DISCHARGE",
                "label": "secreción de la herida",
                "value": None,
                "certainty": "confirmed",
                "original_text": "sale un líquido amarillento y huele feo",
                "normalized_text": None,
                "source_turn_id": "t2",
            },
        ],
        "explicit_denials": [],
        "not_assessed": [
            {
                "code": "INTAKE",
                "label": "tolerancia a líquidos",
                "value": None,
                "certainty": "not_assessed",
                "original_text": "",
                "normalized_text": None,
                "source_turn_id": None,
            },
        ],
        "clarifications": [],
        "follow_up_items": [],
        "risk": {
            "level": "HARD_RED_FLAG",
            "should_escalate": True,
            "trigger_codes": ["FEVER_WITH_WOUND_DISCHARGE"],
        },
        "handoff": {
            "status": "created",
            "reason": "Señal(es) de alarma determinista(s) activa(s); precedencia máxima, "
            "no degradable por el modelo.",
        },
        "knowledge_version": 3,
    }

    dumped = summary.model_dump(mode="json")
    for key, expected in golden.items():
        assert dumped[key] == expected, key
    assert dumped["citations"] == [citations[0].model_dump(mode="json")]
    assert dumped["usage"]["input_tokens"] == 42
    assert dumped["usage"]["provider"] == "fake-scripted"
    assert dumped["session_id"] == session["id"]
    assert dumped["ended_at"] is None
