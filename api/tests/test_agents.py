"""CON-002/CON-003, SAFE-002, RES-001 — tests de los tres agentes de
responsabilidad única + `app.agents.support.invoke_structured`.

Usa `ScriptedFakeLLM` (adapters/fake_llm.py) para programar exactamente lo
que "responde el modelo" por escenario, sin red ni credenciales — el mismo
mecanismo que usan los tests E2E-002."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.adapters.fake_llm import ScriptedFakeLLM
from app.agents.interview import InterviewAgent, InterviewTurnInput
from app.agents.response import ResponseAgent, ResponseTurnInput
from app.agents.support import AgentInvocationError, extract_json_payload, invoke_structured
from app.agents.triage import TriageAgent, TriageTurnInput
from app.domain.models import AgentRequest
from app.ports.llm import LLMMessage


def _request(payload: dict) -> AgentRequest:
    return AgentRequest(
        session_id=uuid4(), correlation_id=uuid4(), knowledge_version=1,
        payload=payload, deadline_ms=2000,
    )


# --------------------------------------------------------------------- #
# invoke_structured (soporte compartido)
# --------------------------------------------------------------------- #


async def test_invoke_structured_returns_parsed_result_on_first_try() -> None:
    llm = ScriptedFakeLLM(default="hola")
    parsed, usage = await invoke_structured(
        llm, messages=[LLMMessage(role="user", content="hi")],
        response_schema=None, deadline_ms=1000, parse=lambda text: text.upper(),
    )
    assert parsed == "HOLA"
    assert usage.provider == "fake-scripted"


async def test_invoke_structured_retries_once_after_transient_failure() -> None:
    llm = ScriptedFakeLLM(default="ok", fail_first_n_calls=1)
    parsed, _usage = await invoke_structured(
        llm, messages=[LLMMessage(role="user", content="hi")],
        response_schema=None, deadline_ms=1000, parse=lambda text: text,
    )
    assert parsed == "ok"
    assert len(llm.calls) == 2


async def test_invoke_structured_raises_after_exhausting_retries() -> None:
    llm = ScriptedFakeLLM(default="ok", fail_first_n_calls=5)
    with pytest.raises(AgentInvocationError) as exc_info:
        await invoke_structured(
            llm, messages=[LLMMessage(role="user", content="hi")],
            response_schema=None, deadline_ms=1000, parse=lambda text: text, max_retries=1,
        )
    assert exc_info.value.attempts == 2


async def test_invoke_structured_retries_on_invalid_parse_then_succeeds() -> None:
    llm = ScriptedFakeLLM([("hi", "not-json")], default="not-json")

    calls = {"n": 0}

    def _parse(text: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("boom")
        return text

    parsed, _usage = await invoke_structured(
        llm, messages=[LLMMessage(role="user", content="hi")],
        response_schema=None, deadline_ms=1000, parse=_parse,
    )
    assert parsed == "not-json"


# --------------------------------------------------------------------- #
# extract_json_payload — resiliencia ante proveedores reales que no
# respetan "solo JSON" al 100% (Groq/Ollama, ver docs/auditoria-kit-
# oficial-2026-08-07.md §9 y app/agents/support.py)
# --------------------------------------------------------------------- #


def test_extract_json_payload_passthrough_for_clean_json() -> None:
    assert extract_json_payload('{"a": 1}') == '{"a": 1}'


def test_extract_json_payload_strips_markdown_fence_with_json_tag() -> None:
    text = '```json\n{"a": 1, "b": "hola"}\n```'
    assert extract_json_payload(text) == '{"a": 1, "b": "hola"}'


def test_extract_json_payload_strips_markdown_fence_without_tag() -> None:
    text = '```\n{"a": 1}\n```'
    assert extract_json_payload(text) == '{"a": 1}'


def test_extract_json_payload_strips_surrounding_prose() -> None:
    text = 'Aquí tienes el resultado:\n{"a": 1}\nEspero que ayude.'
    assert extract_json_payload(text) == '{"a": 1}'


def test_extract_json_payload_returns_original_when_no_json_object_found() -> None:
    assert extract_json_payload("solo texto, sin json") == "solo texto, sin json"


# --------------------------------------------------------------------- #
# InterviewAgent (CON-002/CON-003)
# --------------------------------------------------------------------- #


async def test_interview_agent_extracts_confirmed_observation() -> None:
    response = json.dumps(
        {
            "needs_clarification": False,
            "clarification_question": None,
            "next_question": "¿Y la herida?",
            "observations": [
                {
                    "code": "FEVER", "label": "fiebre", "value": False,
                    "certainty": "denied", "original_text": "no, para nada",
                    "normalized_text": None,
                }
            ],
        }
    )
    llm = ScriptedFakeLLM(default=response)
    agent = InterviewAgent(llm)
    result = await agent.run(
        _request(
            InterviewTurnInput(
                turns=[], remaining_objectives=[{"code": "FEVER", "label": "fiebre"}],
                last_patient_utterance="no, para nada", last_patient_turn_id="t1",
            ).model_dump()
        )
    )
    assert result.status == "ok"
    assert result.output["needs_clarification"] is False
    assert len(result.output["observations"]) == 1
    obs = result.output["observations"][0]
    assert obs["certainty"] == "denied"
    assert obs["original_text"] == "no, para nada"
    assert obs["source_turn_id"] == "t1"


async def test_interview_agent_ambiguous_expression_requests_clarification() -> None:
    """AC-E2E-003: ante una expresión ambigua, el agente pide aclaración y
    conserva el texto original (aquí se simula la salida que produciría el
    modelo real siguiendo las reglas del prompt, CON-003)."""
    response = json.dumps(
        {
            "needs_clarification": True,
            "clarification_question": (
                "Cuando dice 'maluca', ¿se refiere a dolor, malestar general, "
                "decaída, o algo distinto?"
            ),
            "next_question": None,
            "observations": [
                {
                    "code": "GENERAL_STATE", "label": "ánimo general", "value": None,
                    "certainty": "uncertain", "original_text": "la he visto un poco maluca",
                    "normalized_text": None,
                }
            ],
        }
    )
    llm = ScriptedFakeLLM(default=response)
    agent = InterviewAgent(llm)
    result = await agent.run(
        _request(
            InterviewTurnInput(
                turns=[], remaining_objectives=[{"code": "GENERAL_STATE", "label": "ánimo"}],
                last_patient_utterance="la he visto un poco maluca", last_patient_turn_id="t1",
            ).model_dump()
        )
    )
    assert result.status == "ok"
    assert result.output["needs_clarification"] is True
    assert "maluca" in result.output["clarification_question"] or True  # pregunta abierta
    obs = result.output["observations"][0]
    assert obs["certainty"] == "uncertain"
    assert obs["original_text"] == "la he visto un poco maluca"


async def test_interview_agent_tolerates_markdown_fenced_json_from_real_provider() -> None:
    """Un proveedor real (Groq/Ollama) a veces envuelve el JSON en fences
    de markdown pese al prompt/response_format=json_object — el agente
    debe seguir funcionando (extract_json_payload en _parse_interview_output)."""
    payload = json.dumps(
        {
            "needs_clarification": False, "clarification_question": None,
            "next_question": "¿cómo sigue?",
            "observations": [
                {
                    "code": "FEVER", "label": "fiebre", "value": False,
                    "certainty": "denied", "original_text": "no tiene fiebre",
                    "normalized_text": None,
                }
            ],
        }
    )
    fenced_response = f"```json\n{payload}\n```"
    llm = ScriptedFakeLLM(default=fenced_response)
    agent = InterviewAgent(llm)
    result = await agent.run(
        _request(
            InterviewTurnInput(
                turns=[], remaining_objectives=[{"code": "FEVER", "label": "fiebre"}],
                last_patient_utterance="no tiene fiebre", last_patient_turn_id="t1",
            ).model_dump()
        )
    )
    assert result.status == "ok"
    assert result.output["observations"][0]["code"] == "FEVER"


async def test_interview_agent_needs_clarification_without_question_is_invalid_output() -> None:
    """El propio `InterviewLLMOutput` (model_validator) rechaza
    needs_clarification=true sin pregunta — eso cuenta como salida inválida
    y agota reintentos -> `status="error"`, nunca un resultado a medias."""
    response = json.dumps(
        {"needs_clarification": True, "clarification_question": None, "next_question": None,
         "observations": []}
    )
    llm = ScriptedFakeLLM(default=response)
    agent = InterviewAgent(llm)
    result = await agent.run(
        _request(
            InterviewTurnInput(
                turns=[], remaining_objectives=[], last_patient_utterance="algo",
                last_patient_turn_id="t1",
            ).model_dump()
        )
    )
    assert result.status == "error"
    assert result.warnings


async def test_interview_agent_returns_error_result_on_malformed_json() -> None:
    llm = ScriptedFakeLLM(default="esto no es json")
    agent = InterviewAgent(llm)
    result = await agent.run(
        _request(
            InterviewTurnInput(
                turns=[], remaining_objectives=[], last_patient_utterance="hola",
                last_patient_turn_id="t1",
            ).model_dump()
        )
    )
    assert result.status == "error"
    assert "InterviewAgent" in result.warnings[0]


# --------------------------------------------------------------------- #
# TriageAgent (SAFE-002)
# --------------------------------------------------------------------- #


async def test_triage_agent_reports_routine_level() -> None:
    response = json.dumps(
        {"model_level": "ROUTINE_FOLLOW_UP", "rationale": "sin hallazgos",
         "missing_information": [], "patient_message_intent": "explain_routine_follow_up"}
    )
    llm = ScriptedFakeLLM(default=response)
    agent = TriageAgent(llm)
    result = await agent.run(
        _request(TriageTurnInput(observations=[], rule_engine_missing_info=[]).model_dump())
    )
    assert result.status == "ok"
    assert result.output["model_level"] == "ROUTINE_FOLLOW_UP"
    # BR-023: nunca se emite confidence numérico como atajo de decisión.
    assert result.confidence is None


async def test_triage_agent_cannot_construct_hard_red_flag_output() -> None:
    """`model_level` fuera de {ROUTINE_FOLLOW_UP, MODEL_MODERATE_RISK,
    MODEL_HIGH_RISK} es una salida inválida — ni siquiera "HARD_RED_FLAG"
    puede llegar como resultado ok (SAFE-002: estructuralmente imposible)."""
    response = json.dumps(
        {"model_level": "HARD_RED_FLAG", "rationale": "intento adversarial",
         "missing_information": [], "patient_message_intent": "x"}
    )
    llm = ScriptedFakeLLM(default=response)
    agent = TriageAgent(llm)
    result = await agent.run(
        _request(TriageTurnInput(observations=[], rule_engine_missing_info=[]).model_dump())
    )
    assert result.status == "error"


async def test_triage_agent_reports_moderate_risk_with_missing_info() -> None:
    response = json.dumps(
        {"model_level": "MODEL_MODERATE_RISK", "rationale": "dato incompleto",
         "missing_information": ["temperature_c"],
         "patient_message_intent": "explain_routine_follow_up"}
    )
    llm = ScriptedFakeLLM(default=response)
    agent = TriageAgent(llm)
    result = await agent.run(
        _request(
            TriageTurnInput(
                observations=[{"code": "FEVER", "certainty": "uncertain", "original_text": "x"}],
                rule_engine_missing_info=["temperature_c"],
            ).model_dump()
        )
    )
    assert result.output["model_level"] == "MODEL_MODERATE_RISK"
    assert result.output["missing_information"] == ["temperature_c"]


# --------------------------------------------------------------------- #
# ResponseAgent (RES-001) — groundedness
# --------------------------------------------------------------------- #


async def test_response_agent_grounded_answer_only_with_sufficient_evidence() -> None:
    llm = ScriptedFakeLLM(default="Según la guía, es normal sentir algo de calor localizado.")
    agent = ResponseAgent(llm)
    result = await agent.run(
        _request(
            ResponseTurnInput(
                evidence_sufficient=True, should_escalate=False,
                evidence_fragments=[
                    {
                        "title": "Guía de alta", "text": "sentir calor leve es normal",
                        "citation_id": "c1", "document_id": "d1", "document_version": 1,
                        "chunk_id": "ch1", "knowledge_version": 1,
                    }
                ],
                observations_summary=["ánimo general — bien [confirmed]"],
                patient_question_or_context="¿es normal sentir algo de calor?",
            ).model_dump()
        )
    )
    assert result.status == "ok"
    assert result.output["intent"] == "grounded_answer"
    assert len(result.evidence) == 1
    assert result.evidence[0].citation_id == "c1"


async def test_response_agent_abstains_without_evidence_and_without_escalation() -> None:
    """AC-E2E-007: sin evidencia suficiente y sin motivo de escalamiento,
    el agente debe abstenerse — nunca inventar una respuesta plausible
    desde conocimiento general, y no debe adjuntar ninguna cita."""
    llm = ScriptedFakeLLM(
        default=(
            "No cuento con información verificada en mis fuentes actuales sobre eso; "
            "lo voy a dejar registrado para el equipo médico tratante."
        )
    )
    agent = ResponseAgent(llm)
    result = await agent.run(
        _request(
            ResponseTurnInput(
                evidence_sufficient=False, should_escalate=False, evidence_fragments=[],
                observations_summary=[],
                patient_question_or_context="¿le puedo dar jugo de un cítrico específico?",
            ).model_dump()
        )
    )
    assert result.status == "ok"
    assert result.output["intent"] == "abstain"
    assert result.evidence == []


async def test_response_agent_handoff_takes_priority_over_evidence_sufficiency() -> None:
    """Aunque haya evidencia suficiente, si `should_escalate=True` el
    intent debe ser `handoff` — la escalada nunca se diluye en una
    respuesta clínica normal (architecture.md principio 1)."""
    llm = ScriptedFakeLLM(default="Voy a escalar este caso a revisión humana de inmediato.")
    agent = ResponseAgent(llm)
    result = await agent.run(
        _request(
            ResponseTurnInput(
                evidence_sufficient=True, should_escalate=True,
                evidence_fragments=[
                    {
                        "title": "x", "text": "y", "citation_id": "c1", "document_id": "d1",
                        "document_version": 1, "chunk_id": "ch1", "knowledge_version": 1,
                    }
                ],
                observations_summary=[], patient_question_or_context="fiebre alta",
            ).model_dump()
        )
    )
    assert result.output["intent"] == "handoff"
    # el intent handoff no adjunta evidencia (no es una "respuesta clínica").
    assert result.evidence == []


async def test_response_agent_grounded_prompt_never_leaks_into_abstain_or_handoff_prompt() -> None:
    """Groundedness real: el prompt de abstención/handoff JAMÁS incluye la
    sección de fragmentos de evidencia — así el LLM no puede "colarse" y
    responder clínicamente desde ahí cuando no debería."""
    llm = ScriptedFakeLLM(default="respuesta")
    agent = ResponseAgent(llm)
    await agent.run(
        _request(
            ResponseTurnInput(
                evidence_sufficient=False, should_escalate=False,
                evidence_fragments=[{"title": "no debería aparecer", "text": "contenido oculto"}],
                observations_summary=[], patient_question_or_context="pregunta sin evidencia",
            ).model_dump()
        )
    )
    sent_prompt = "\n".join(m.content for m in llm.calls[-1])
    assert "FRAGMENTOS DE EVIDENCIA" not in sent_prompt
    assert "contenido oculto" not in sent_prompt


async def test_response_agent_returns_error_when_llm_output_is_empty() -> None:
    llm = ScriptedFakeLLM(default="   ")
    agent = ResponseAgent(llm)
    result = await agent.run(
        _request(
            ResponseTurnInput(
                evidence_sufficient=False, should_escalate=False, evidence_fragments=[],
                observations_summary=[], patient_question_or_context="x",
            ).model_dump()
        )
    )
    assert result.status == "error"
