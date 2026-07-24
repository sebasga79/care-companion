"""ORC-002 — `CallCycleOrchestrator`: cobertura de estados del ciclo
completo (clarify, rutina sin escalar, hard red flag, evidence-insufficient-
with-risk, fail_safe, sesión no encontrada / que no acepta turnos)."""

from __future__ import annotations

import json

import pytest

from app.adapters.fake_embeddings import FakeEmbeddings
from app.adapters.fake_llm import ScriptedFakeLLM
from app.core.config import Settings
from app.domain.decision import DecisionLevel
from app.domain.session_fsm import SessionState
from app.orchestrator.call_cycle import (
    CallCycleOrchestrator,
    SessionNotAcceptingTurnsError,
    SessionNotFoundError,
)
from app.repositories.db import apply_schema, get_connection
from app.repositories.knowledge import get_current_knowledge_version
from app.repositories.sessions import SessionRepository
from app.services.embeddings_cache import EmbeddingsCache

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
        database_path=db_path, llm=llm, embeddings=embeddings,
        evidence_score_threshold=settings.rag_evidence_score_threshold,
        candidate_pool_size=settings.rag_candidate_pool_size,
        retrieval_top_k=settings.rag_retrieval_top_k,
    )


def _new_session(db_path: str) -> str:
    repo = SessionRepository(db_path)
    record = repo.create(
        case_id="demo-case-001", state=SessionState.CREATED.value,
        knowledge_version=get_current_knowledge_version(db_path),
    )
    return record["id"]


def _interview_json(
    *, needs_clarification: bool = False, clarification_question: str | None = None,
    next_question: str | None = None, observations: list[dict] | None = None,
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
            "model_level": model_level, "rationale": "evaluación programada de test",
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
    {"code": "GENERAL_STATE", "label": "ánimo", "certainty": "confirmed",
     "original_text": "bien, jugando", "normalized_text": None},
    {"code": "FEVER", "label": "fiebre", "certainty": "denied",
     "original_text": "no, fresquito", "normalized_text": None},
    {"code": "WOUND_APPEARANCE", "label": "aspecto de la herida", "certainty": "confirmed",
     "original_text": "se ve limpia y seca", "normalized_text": None},
    {"code": "INTAKE", "label": "líquidos y comida", "certainty": "confirmed",
     "original_text": "comió arroz sin problema", "normalized_text": None},
]


async def test_handle_turn_raises_for_unknown_session(db_path: str) -> None:
    _init_db(db_path)
    orchestrator = _orchestrator(db_path, ScriptedFakeLLM(default="x"))
    with pytest.raises(SessionNotFoundError):
        await orchestrator.handle_turn("00000000-0000-0000-0000-000000000000", "hola")


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
                {"code": "GENERAL_STATE", "label": "ánimo", "certainty": "uncertain",
                 "original_text": "la vi maluca", "normalized_text": None}
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


async def test_routine_cycle_covers_objectives_and_reaches_summarizing(db_path: str) -> None:
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

    assert result.state is SessionState.SUMMARIZING
    assert result.decision_level == DecisionLevel.ROUTINE_FOLLOW_UP
    assert result.should_escalate is False
    assert result.escalated is False
    assert result.intent in {"abstain", "grounded_answer"}


async def test_hard_red_flag_escalates_even_if_model_tries_to_downgrade(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)

    _script(
        llm,
        interview_json=_interview_json(
            observations=[
                {"code": "FEVER", "label": "fiebre", "certainty": "confirmed",
                 "original_text": "amaneció con fiebre alta", "normalized_text": None},
                {"code": "WOUND_DISCHARGE", "label": "secreción de la herida",
                 "certainty": "confirmed",
                 "original_text": "sale un líquido amarillento y huele feo",
                 "normalized_text": None},
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
    assert result.state is SessionState.SUMMARIZING

    session_after = SessionRepository(db_path).get(session_id)
    assert session_after["state"] == "summarizing"


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
                {"code": "FEVER", "label": "fiebre", "certainty": "confirmed",
                 "original_text": "tiene fiebre", "normalized_text": None},
            ]
        ),
        triage_json="NO DEBERÍA LLAMARSE",
        response_text="Voy a dejar esto registrado para que lo revise el equipo médico.",
    )

    result = await orchestrator.handle_turn(session_id, "tiene fiebre")

    assert result.decision_level == DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK
    assert result.should_escalate is True
    triage_calls = [
        call for call in llm.calls if any(_TRIAGE_MARKER in m.content for m in call)
    ]
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


async def test_escalated_session_does_not_accept_further_turns(db_path: str) -> None:
    _init_db(db_path)
    session_id = _new_session(db_path)
    llm = ScriptedFakeLLM(default="placeholder")
    orchestrator = _orchestrator(db_path, llm)
    _script(
        llm,
        interview_json=_interview_json(
            observations=[
                {"code": "FEVER", "label": "fiebre", "certainty": "confirmed",
                 "original_text": "fiebre alta", "normalized_text": None},
                {"code": "WOUND_DISCHARGE", "label": "secreción", "certainty": "confirmed",
                 "original_text": "secreción amarilla", "normalized_text": None},
            ]
        ),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Escalando de inmediato.",
    )
    await orchestrator.handle_turn(session_id, "fiebre alta y secreción amarilla")

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
                {"code": "GENERAL_STATE", "label": "ánimo", "certainty": "confirmed",
                 "original_text": "bien, jugando", "normalized_text": None},
            ],
        ),
        triage_json=_triage_json(model_level="ROUTINE_FOLLOW_UP"),
        response_text="Qué bueno. ¿Ha tenido fiebre?",
    )
    result = await orchestrator.handle_turn(session_id, "hoy amaneció jugando")

    assert result.state is SessionState.INTERVIEWING
    assert result.decision_level == DecisionLevel.ROUTINE_FOLLOW_UP
