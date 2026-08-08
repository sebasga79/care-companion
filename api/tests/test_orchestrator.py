"""ORC-002 — `CallCycleOrchestrator`: cobertura de estados del ciclo
completo (clarify, rutina sin escalar, hard red flag, evidence-insufficient-
with-risk, fail_safe, sesión no encontrada / que no acepta turnos)."""

from __future__ import annotations

import json

import pytest

from app.adapters.fake_embeddings import FakeEmbeddings
from app.adapters.fake_llm import ScriptedFakeLLM
from app.adapters.fixture_cases import FixtureCaseAdapter
from app.core.config import Settings
from app.domain.decision import DecisionLevel
from app.domain.observation import Observation
from app.domain.session_fsm import SessionState
from app.orchestrator.call_cycle import (
    CallCycleOrchestrator,
    SessionNotAcceptingTurnsError,
    SessionNotFoundError,
    _case_context,
    _history_aware_pain_question,
)
from app.ports.challenge_case import ChallengeCase, HistoricalFollowup, ReferenceTrajectory
from app.repositories.db import apply_schema, get_connection
from app.repositories.events import EventRepository
from app.repositories.knowledge import get_current_knowledge_version
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository
from app.services.embeddings_cache import EmbeddingsCache
from app.services.ingestion import KnowledgeIngestionService

_INTERVIEW_MARKER = "extraer observaciones estructuradas del último turno"
_TRIAGE_MARKER = "evaluador de riesgo estructurado"
_RESPONSE_MARKER = "asistente de voz de seguimiento postoperatorio"


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()


def _orchestrator(db_path: str, llm: ScriptedFakeLLM) -> CallCycleOrchestrator:
    settings = Settings(DATABASE_PATH=db_path)
    embeddings = EmbeddingsCache(FakeEmbeddings(dimensions=settings.rag_embedding_dimensions))
    return CallCycleOrchestrator(
        database_path=db_path,
        llm=llm,
        embeddings=embeddings,
        case_port=FixtureCaseAdapter(),
        evidence_score_threshold=settings.rag_evidence_score_threshold,
        candidate_pool_size=settings.rag_candidate_pool_size,
        retrieval_top_k=settings.rag_retrieval_top_k,
    )


def _new_session(db_path: str) -> str:
    repo = SessionRepository(db_path)
    record = repo.create(
        case_id="demo-case-001",
        state=SessionState.CREATED.value,
        knowledge_version=get_current_knowledge_version(db_path),
    )
    return record["id"]


def _interview_json(
    *,
    needs_clarification: bool = False,
    clarification_question: str | None = None,
    next_question: str | None = None,
    observations: list[dict] | None = None,
) -> str:
    return json.dumps(
        {
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "next_question": next_question,
            "observations": observations or [],
        }
    )


def _triage_json(*, model_level: str, missing_information: list[str] | None = None) -> str:
    return json.dumps(
        {
            "model_level": model_level,
            "rationale": "evaluación programada de test",
            "missing_information": missing_information or [],
            "patient_message_intent": "explain_routine_follow_up",
        }
    )


def _script(
    llm: ScriptedFakeLLM, *, interview_json: str, triage_json: str, response_text: str
) -> None:
    llm._scripted = [  # noqa: SLF001 - reasignación deliberada entre turnos de test
        (_INTERVIEW_MARKER, interview_json),
        (_TRIAGE_MARKER, triage_json),
        (_RESPONSE_MARKER, response_text),
    ]


_ALL_OBJECTIVES_HARMLESS = [
    {
        "code": "PAIN",
        "label": "dolor",
        "certainty": "denied",
        "original_text": "no tiene dolor",
        "normalized_text": None,
    },
    {
        "code": "PAIN_LOCATION",
        "label": "lugar del dolor",
        "certainty": "denied",
        "original_text": "no aplica porque no tiene dolor",
        "normalized_text": None,
    },
    {
        "code": "PAIN_SEVERITY",
        "label": "intensidad",
        "certainty": "denied",
        "original_text": "no aplica porque no tiene dolor",
        "normalized_text": None,
    },
    {
        "code": "PAIN_EVOLUTION",
        "label": "evolución",
        "certainty": "denied",
        "original_text": "no aplica porque no tiene dolor",
        "normalized_text": None,
    },
    {
        "code": "GENERAL_STATE",
        "label": "ánimo",
        "certainty": "confirmed",
        "original_text": "bien, jugando",
        "normalized_text": None,
    },
    {
        "code": "INTAKE",
        "label": "líquidos y comida",
        "certainty": "confirmed",
        "original_text": "comió arroz sin problema",
        "normalized_text": None,
    },
    {
        "code": "FEVER",
        "label": "fiebre",
        "certainty": "denied",
        "original_text": "no, fresquito",
        "normalized_text": None,
    },
    {
        "code": "WOUND_APPEARANCE",
        "label": "aspecto de la herida",
        "certainty": "confirmed",
        "original_text": "se ve limpia y seca",
        "normalized_text": None,
    },
    {
        "code": "MOBILITY",
        "label": "movilidad",
        "certainty": "confirmed",
        "original_text": "camina sin problema",
        "normalized_text": None,
    },
    {
        "code": "SLEEP",
        "label": "sueño",
        "certainty": "confirmed",
        "original_text": "durmió bien",
        "normalized_text": None,
    },
]


async def test_handle_turn_raises_for_unknown_session(db_path: str) -> None:
    _init_db(db_path)
    orchestrator = _orchestrator(db_path, ScriptedFakeLLM(default="x"))
    with pytest.raises(SessionNotFoundError):
        await orchestrator.handle_turn("00000000-0000-0000-0000-000000000000", "hola")


async def test_agent_opens_call_with_purpose_and_persists_first_turn(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    orchestrator = _orchestrator(db_path, ScriptedFakeLLM(default="x"))

    opening = await orchestrator.start_session(session_id)

    assert "seguimiento postoperatorio" in opening.lower()
    assert "cirugia ambulatoria general x" in opening.lower()
    assert "cómo se ha sentido desde el último seguimiento" in opening.lower()
    assert SessionRepository(db_path).get(session_id)["state"] == "interviewing"
    turns = TurnRepository(db_path).list_for_session(session_id)
    assert [(turn["speaker"], turn["text"]) for turn in turns] == [("agent", opening)]


async def test_agent_opening_acknowledges_prior_followup_for_same_patient(db_path: str) -> None:
    _init_db(db_path)
    previous_session_id = _new_session(db_path)
    SessionRepository(db_path).update_state(previous_session_id, state=SessionState.CLOSED.value)
    current_session_id = _new_session(db_path)
    orchestrator = _orchestrator(db_path, ScriptedFakeLLM(default="x"))

    opening = await orchestrator.start_session(current_session_id)

    assert "seguimientos anteriores" in opening.lower()
    assert "confirmar cómo se encuentra hoy" in opening.lower()


def test_case_context_never_exposes_hidden_reference_trajectory() -> None:
    case = ChallengeCase(
        case_id="case-1",
        patient_id="patient-1",
        patient_display_name="Paciente demo",
        procedure="Apendicectomía",
        procedure_category="appendicitis",
        phase="post_discharge_day_1",
        days_since_procedure=1,
        caregiver_role="paciente",
        reference_trajectory=ReferenceTrajectory(
            arquetipo="complicacion",
            dolor_nrs=9,
            fiebre_c=40.0,
            movilidad="mala",
            herida="secrecion",
            apetito="malo",
            sueno="malo",
        ),
    )

    context = _case_context(case)

    assert context["procedure"] == "Apendicectomía"
    assert "reference_trajectory" not in context
    assert "dolor_nrs" not in context


async def test_longitudinal_history_is_available_to_agents_as_prior_followups(
    db_path: str,
) -> None:
    _init_db(db_path)
    orchestrator = _orchestrator(db_path, ScriptedFakeLLM(default="x"))
    case = ChallengeCase(
        case_id="paciente_patient-1",
        patient_id="patient-1",
        patient_display_name="Paciente demo",
        procedure="Apendicectomía",
        procedure_category="appendicitis",
        phase="longitudinal_follow_up",
        days_since_procedure=14,
        caregiver_role="paciente",
        historical_followups=[
            HistoricalFollowup(
                trajectory_id="tray-1",
                day=1,
                archetype="recuperacion_normal",
                pain_nrs=5,
                temperature_c=37.2,
                mobility="limitada_esperada",
                wound="normal",
                appetite="normal",
                sleep="levemente_alterado",
            ),
            HistoricalFollowup(
                trajectory_id="tray-14",
                day=14,
                archetype="recuperacion_normal",
                pain_nrs=1,
                temperature_c=36.8,
                mobility="normal",
                wound="normal",
                appetite="normal",
                sleep="normal",
            ),
        ],
    )

    history = await orchestrator._prior_followups(  # noqa: SLF001 - contrato longitudinal
        case, exclude_session_id="current"
    )

    assert [item["days_since_procedure"] for item in history] == [1, 14]
    assert history[0]["pain_nrs"] == 5
    assert history[1]["pain_nrs"] == 1
    assert all(item["source"] == "official_longitudinal_history" for item in history)


def test_history_objection_acknowledges_baseline_and_current_pain() -> None:
    case = ChallengeCase(
        case_id="patient-1",
        patient_id="patient-1",
        patient_display_name="Paciente demo",
        procedure="Colectomía",
        procedure_category="colorectal_cancer",
        phase="longitudinal_follow_up",
        days_since_procedure=14,
        caregiver_role="paciente",
        historical_followups=[
            HistoricalFollowup(
                trajectory_id="tray-14",
                day=14,
                archetype="recuperacion_normal",
                pain_nrs=0,
                temperature_c=36.2,
                mobility="normal",
                wound="normal",
                appetite="normal",
                sleep="normal",
            )
        ],
    )
    observations = [
        Observation(
            code="PAIN_SEVERITY",
            label="intensidad del dolor",
            value="siete",
            certainty="confirmed",
            original_text="siete",
            source_turn_id="turn-1",
        )
    ]

    question = _history_aware_pain_question(case, observations)
    assert "último seguimiento el dolor estaba en 0 de 10" in question
    assert "hoy me reporta 7 de 10" in question
    assert "aumentando, sigue igual o disminuye" in question


async def test_handle_turn_rejects_closed_session(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    SessionRepository(db_path).update_state(session_id, state=SessionState.CLOSED.value)
    orchestrator = _orchestrator(db_path, ScriptedFakeLLM(default="x"))
    with pytest.raises(SessionNotAcceptingTurnsError) as exc_info:
        await orchestrator.handle_turn(session_id, "hola")
    assert exc_info.value.state is SessionState.CLOSED


async def test_clarify_loop_keeps_session_in_interviewing(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(
            needs_clarification=True,
            clarification_question="¿A qué se refiere con 'maluca'? ¿Dolor, decaimiento, algo más?",
            observations=[
                {
                    "code": "GENERAL_STATE",
                    "label": "ánimo",
                    "certainty": "uncertain",
                    "original_text": "la vi maluca",
                    "normalized_text": None,
                }
            ],
        ),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="no debería usarse",
    )

    result = await orchestrator.handle_turn(session_id, "la vi maluca")

    assert result.needs_clarification is True
    assert result.state is SessionState.INTERVIEWING
    message = (result.agent_message or "").lower()
    assert "maluca" in message or "aclar" in message

    session_after = SessionRepository(db_path).get(session_id)
    assert session_after["state"] == "interviewing"


async def test_routine_cycle_covers_objectives_and_closes_automatically(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(observations=_ALL_OBJECTIVES_HARMLESS),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Qué bueno escuchar eso, todo se ve dentro de lo esperado.",
    )

    result = await orchestrator.handle_turn(session_id, "hoy amaneció jugando, comió normal")

    assert result.state is SessionState.CLOSED
    assert result.intent == "close"
    assert "finalizar la llamada" in (result.agent_message or "").lower()
    assert result.decision_level == DecisionLevel.ROUTINE_FOLLOW_UP
    assert result.should_escalate is False
    assert result.escalated is False


async def test_hard_red_flag_escalates_even_if_model_tries_to_downgrade(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(
            observations=[
                {
                    "code": "FEVER",
                    "label": "fiebre",
                    "certainty": "confirmed",
                    "original_text": "amaneció con fiebre alta",
                    "normalized_text": None,
                },
                {
                    "code": "WOUND_DISCHARGE",
                    "label": "secreción de la herida",
                    "certainty": "confirmed",
                    "original_text": "sale un líquido amarillento y huele feo",
                    "normalized_text": None,
                },
            ]
        ),
        # el modelo intenta rebajar a rutina — no debe poder.
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Con lo que me cuenta, esto requiere atención prioritaria; voy a escalar.",
    )

    result = await orchestrator.handle_turn(
        session_id, "amaneció con fiebre alta y la herida enrojecida con líquido amarillento"
    )

    assert result.decision_level == DecisionLevel.HARD_RED_FLAG
    assert result.should_escalate is True
    assert result.escalated is True
    assert result.intent == "handoff"
    assert result.state is SessionState.ESCALATED

    session_after = SessionRepository(db_path).get(session_id)
    assert session_after["state"] == "escalated"

    primary = await orchestrator.handle_turn(session_id, "Me pueden llamar al 300 123 4567")
    assert primary.state is SessionState.ESCALATED
    assert "número adicional" in (primary.agent_message or "").lower()

    completed = await orchestrator.handle_turn(
        session_id, "El número de emergencia es 604 555 1234"
    )
    assert completed.state is SessionState.CLOSED
    assert "finalizar la llamada" in (completed.agent_message or "").lower()
    session_after = SessionRepository(db_path).get(session_id)
    assert session_after["state"] == "closed"
    assert session_after["closed_at"] is not None

    summary = await orchestrator.build_summary(session_id)
    contact_codes = {item["code"] for item in summary.patient_reported}
    assert {"CONTACT_PRIMARY", "CONTACT_EMERGENCY"} <= contact_codes


async def test_raw_40_degrees_overrides_agent_denial_and_clarification(db_path: str) -> None:
    """Regresión del falso negativo real: la seguridad no depende de que el
    InterviewAgent reconozca la temperatura ni de que evite pedir aclaración."""
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(
            needs_clarification=True,
            clarification_question="¿Puede repetir la temperatura?",
            observations=[
                {
                    "code": "FEVER",
                    "label": "fiebre",
                    "certainty": "denied",
                    "original_text": "salida incorrecta del modelo",
                    "normalized_text": None,
                }
            ],
        ),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="NO DEBE USARSE: todo está normal",
    )

    result = await orchestrator.handle_turn(session_id, "Sí tengo fiebre, tengo 40 grados")

    assert result.decision_level is DecisionLevel.HARD_RED_FLAG
    assert result.should_escalate is True
    assert result.needs_clarification is False
    assert "valoración médica urgente" in result.agent_message
    assert "todo está normal" not in result.agent_message


async def test_evidence_insufficient_with_risk_escalates_without_calling_triage(
    db_path: str,
) -> None:
    """Falta un dato que casi dispara una regla determinista (WOUND_DISCHARGE
    sin evaluar) Y no hay evidencia cargada que compense esa falta — debe
    escalar por EVIDENCE_INSUFFICIENT_WITH_RISK sin siquiera invocar a
    TriageAgent (arco Retrieve->Escalate de architecture.md §7)."""
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(
            observations=[
                {
                    "code": "FEVER",
                    "label": "fiebre",
                    "certainty": "confirmed",
                    "original_text": "tiene fiebre",
                    "normalized_text": None,
                },
            ]
        ),
        triage_json="NO DEBERÍA LLAMARSE",
        response_text="Voy a dejar esto registrado para que lo revise el equipo médico.",
    )

    result = await orchestrator.handle_turn(session_id, "tiene fiebre")

    assert result.decision_level == DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK
    assert result.should_escalate is True
    triage_calls = [call for call in llm.calls if any(_TRIAGE_MARKER in m.content for m in call)]
    assert triage_calls == []


async def test_agent_error_triggers_fail_safe_and_still_escalates(db_path: str) -> None:
    """Si `InterviewAgent` agota reintentos (salida del LLM que nunca
    matchea el guion), el ciclo debe caer a FAIL_SAFE y escalar por
    DATA_INTEGRITY_FAILURE — nunca fingir que "todo salió bien" (BR-027)."""
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(scripted=[], default=None)  # sin guion -> ValueError en cada intento
    orchestrator = _orchestrator(db_path, llm)

    result = await orchestrator.handle_turn(session_id, "cualquier cosa")

    assert result.state is SessionState.FAIL_SAFE
    assert result.decision_level == DecisionLevel.DATA_INTEGRITY_FAILURE
    assert result.should_escalate is True
    assert result.escalated is True
    assert result.warnings

    session_after = SessionRepository(db_path).get(session_id)
    assert session_after["state"] == "fail_safe"


async def test_escalated_session_only_accepts_contact_flow_until_auto_close(
    db_path: str,
) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)
    _script(
        llm,
        interview_json=_interview_json(
            observations=[
                {
                    "code": "FEVER",
                    "label": "fiebre",
                    "certainty": "confirmed",
                    "original_text": "fiebre alta",
                    "normalized_text": None,
                },
                {
                    "code": "WOUND_DISCHARGE",
                    "label": "secreción",
                    "certainty": "confirmed",
                    "original_text": "secreción amarilla",
                    "normalized_text": None,
                },
            ]
        ),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Escalando de inmediato.",
    )
    escalated = await orchestrator.handle_turn(session_id, "fiebre alta y secreción amarilla")
    assert escalated.state is SessionState.ESCALATED

    clarification = await orchestrator.handle_turn(session_id, "no lo recuerdo")
    assert clarification.needs_clarification is True
    assert "dígitos" in (clarification.agent_message or "")

    await orchestrator.handle_turn(session_id, "300 123 4567")
    closed = await orchestrator.handle_turn(session_id, "604 555 1234")
    assert closed.state is SessionState.CLOSED

    with pytest.raises(SessionNotAcceptingTurnsError):
        await orchestrator.handle_turn(session_id, "otra cosa")


async def test_follow_up_loop_returns_to_interviewing_when_objectives_pending(
    db_path: str,
) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(
            next_question="¿Ha tenido fiebre?",
            observations=[
                {
                    "code": "GENERAL_STATE",
                    "label": "ánimo",
                    "certainty": "confirmed",
                    "original_text": "bien, jugando",
                    "normalized_text": None,
                },
            ],
        ),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Qué bueno. ¿Ha tenido fiebre?",
    )
    result = await orchestrator.handle_turn(session_id, "hoy amaneció jugando")

    assert result.state is SessionState.INTERVIEWING
    assert result.decision_level == DecisionLevel.ROUTINE_FOLLOW_UP


async def test_retrieval_is_scoped_to_case_procedure_via_applicability(db_path: str) -> None:
    """Regresión (docs/auditoria-kit-oficial-2026-08-07.md §9.2): antes,
    `hybrid_search` nunca recibía `applicability_filter` — con el corpus
    real del reto (5 procedimientos en la misma base de conocimiento), un
    documento de OTRO procedimiento podía aparecer como evidencia de una
    sesión que no lo cubre. `demo-case-001` (FixtureCaseAdapter) tiene
    `procedure_category="cirugia_ambulatoria_general_x"`."""
    _init_db(db_path)
    settings = Settings(DATABASE_PATH=db_path)
    embeddings = EmbeddingsCache(FakeEmbeddings(dimensions=settings.rag_embedding_dimensions))
    ingestion = KnowledgeIngestionService(db_path, embeddings_cache=embeddings, settings=settings)

    await ingestion.learn(
        raw_filename="guia_relevante.md",
        content=(
            b"Si presenta fiebre alta o calor en la zona de la cirugia general, "
            b"contacte al equipo medico de inmediato."
        ),
        applicability={"procedure": "cirugia_ambulatoria_general_x"},
    )
    await ingestion.learn(
        raw_filename="guia_no_relacionada.md",
        content=(
            b"Si presenta fiebre alta o calor en la zona de la cirugia general, "
            b"avise al personal a cargo cuanto antes."
        ),
        applicability={"procedure": "otro_procedimiento_no_relacionado"},
    )

    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = CallCycleOrchestrator(
        database_path=db_path,
        llm=llm,
        embeddings=embeddings,
        case_port=FixtureCaseAdapter(),
        evidence_score_threshold=settings.rag_evidence_score_threshold,
        candidate_pool_size=settings.rag_candidate_pool_size,
        retrieval_top_k=settings.rag_retrieval_top_k,
    )
    _script(
        llm,
        interview_json=_interview_json(observations=_ALL_OBJECTIVES_HARMLESS),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Respuesta anclada en la guía.",
    )

    result = await orchestrator.handle_turn(session_id, "tiene fiebre alta y calor en la herida")

    titles = {c.title for c in result.citations}
    assert "guia_relevante.md" in titles
    assert "guia_no_relacionada.md" not in titles

    events = EventRepository(db_path).list_for_session(session_id)
    retrieval_events = [e for e in events if e["event_type"] == "rag.retrieval.completed"]
    assert len(retrieval_events) == 1
    payload = json.loads(retrieval_events[0]["payload"])
    assert payload["applicability_filter"] == {"procedure": "cirugia_ambulatoria_general_x"}
