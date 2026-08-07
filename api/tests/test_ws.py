"""API-002 — `WS /ws/sessions/{session_id}`: envelopes versionados, `seq`
monotónico, errores recuperables sin cerrar la conexión."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.adapters.fake_llm import ScriptedFakeLLM
from app.main import create_app
from app.orchestrator.call_cycle import CallCycleOrchestrator

_INTERVIEW_MARKER = "extraer observaciones estructuradas del último turno"
_TRIAGE_MARKER = "evaluador de riesgo estructurado"
_RESPONSE_MARKER = "asistente de voz de seguimiento postoperatorio"

_ROUTINE_OBSERVATIONS = [
    {"code": "GENERAL_STATE", "label": "ánimo", "certainty": "confirmed",
     "original_text": "bien, jugando", "normalized_text": None},
    {"code": "FEVER", "label": "fiebre", "certainty": "denied",
     "original_text": "no, fresquito", "normalized_text": None},
    {"code": "WOUND_APPEARANCE", "label": "aspecto de la herida", "certainty": "confirmed",
     "original_text": "se ve limpia y seca", "normalized_text": None},
    {"code": "INTAKE", "label": "líquidos y comida", "certainty": "confirmed",
     "original_text": "comió arroz sin problema", "normalized_text": None},
]


def _client_with_scripted_llm(clean_env: None) -> tuple[TestClient, ScriptedFakeLLM]:
    app = create_app()
    llm = ScriptedFakeLLM(default="placeholder")
    llm._scripted = [  # noqa: SLF001 - reasignación deliberada en el test
        (
            _INTERVIEW_MARKER,
            json.dumps(
                {"needs_clarification": False, "clarification_question": None,
                 "next_question": None, "observations": _ROUTINE_OBSERVATIONS}
            ),
        ),
        (
            _TRIAGE_MARKER,
            json.dumps(
                {"model_level": "ROUTINE_FOLLOW_UP", "rationale": "sin hallazgos",
                 "missing_information": [], "patient_message_intent": "explain_routine_follow_up"}
            ),
        ),
        (_RESPONSE_MARKER, "Qué bueno escuchar eso, todo se ve dentro de lo esperado."),
    ]
    app.state.call_cycle_orchestrator = CallCycleOrchestrator(
        database_path=app.state.settings.database_path,
        llm=llm,
        embeddings=app.state.embeddings_cache,
        evidence_score_threshold=app.state.settings.rag_evidence_score_threshold,
        candidate_pool_size=app.state.settings.rag_candidate_pool_size,
        retrieval_top_k=app.state.settings.rag_retrieval_top_k,
    )
    return TestClient(app), llm


def _create_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"})
    assert response.status_code == 201
    return response.json()["id"]


def test_ws_full_turn_cycle_sends_versioned_envelopes_with_monotonic_seq(
    clean_env: None,
) -> None:
    client, _llm = _client_with_scripted_llm(clean_env)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {
                "v": 1, "type": "client.turn_text", "seq": 1,
                "payload": {"text": "hoy amaneció jugando, comió normal"},
                "correlation_id": "corr-turn-1",
            }
        )

        state_env = ws.receive_json()
        response_env = ws.receive_json()
        decision_env = ws.receive_json()
        summary_env = ws.receive_json()

    for env in (state_env, response_env, decision_env, summary_env):
        assert env["v"] == 1
        assert env["correlation_id"] == "corr-turn-1"

    assert [e["seq"] for e in (state_env, response_env, decision_env, summary_env)] == [1, 2, 3, 4]

    assert state_env["type"] == "server.state"
    assert state_env["payload"]["state"] == "summarizing"

    assert response_env["type"] == "server.agent_response"
    assert response_env["payload"]["message"]
    assert response_env["payload"]["needs_clarification"] is False

    assert decision_env["type"] == "server.decision"
    assert decision_env["payload"]["level"] == "ROUTINE_FOLLOW_UP"
    assert decision_env["payload"]["should_escalate"] is False

    assert summary_env["type"] == "server.summary"
    assert summary_env["payload"]["session_id"] == session_id
    assert summary_env["payload"]["risk"]["level"] == "ROUTINE_FOLLOW_UP"


def test_ws_turn_persists_conversational_latency_event(clean_env: None) -> None:
    """La latencia real del turno (no HTTP genérico) queda en `events` como
    `turn.response_sent` y alimenta `/metrics` — corrección de la auditoría
    del 7 de agosto (docs/auditoria-kit-oficial-2026-08-07.md §9): antes,
    `/metrics` promediaba latencia de cualquier request HTTP."""
    client, _llm = _client_with_scripted_llm(clean_env)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {
                "v": 1, "type": "client.turn_text", "seq": 1,
                "payload": {"text": "hoy amaneció jugando, comió normal"},
                "correlation_id": "corr-latency-1",
            }
        )
        for _ in range(4):
            ws.receive_json()

    trace = client.get(f"/api/v1/audit/sessions/{session_id}/trace").json()
    turn_events = [e for e in trace["events"] if e["event_type"] == "turn.response_sent"]
    assert len(turn_events) == 1
    assert turn_events[0]["latency_ms"] >= 0
    assert turn_events[0]["component"] == "ws"

    metrics = client.get("/api/v1/metrics").json()
    assert metrics["latency_p50"]["status"] == "medido"
    assert metrics["latency_p95"]["status"] == "medido"


def test_ws_unsupported_message_type_errors_without_closing_connection(
    clean_env: None,
) -> None:
    client, _llm = _client_with_scripted_llm(clean_env)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json({"v": 1, "type": "client.bogus", "seq": 1, "payload": {}})
        error_env = ws.receive_json()
        assert error_env["type"] == "server.error"
        assert error_env["seq"] == 1

        # la conexión sigue viva: un turno válido después del error funciona.
        ws.send_json(
            {
                "v": 1, "type": "client.turn_text", "seq": 2,
                "payload": {"text": "hoy amaneció jugando, comió normal"},
            }
        )
        state_env = ws.receive_json()
        assert state_env["type"] == "server.state"
        assert state_env["seq"] == 2  # el contador de seq es del SERVIDOR, sigue tras el error


def test_ws_invalid_payload_returns_server_error(clean_env: None) -> None:
    client, _llm = _client_with_scripted_llm(clean_env)
    session_id = _create_session(client)

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json({"v": 1, "type": "client.turn_text", "seq": 1, "payload": {}})
        error_env = ws.receive_json()
        assert error_env["type"] == "server.error"
        assert "payload inválido" in error_env["payload"]["reason"]


def test_ws_unknown_session_returns_server_error(clean_env: None) -> None:
    client, _llm = _client_with_scripted_llm(clean_env)

    with client.websocket_connect(
        "/ws/sessions/00000000-0000-0000-0000-000000000000"
    ) as ws:
        ws.send_json({"v": 1, "type": "client.turn_text", "seq": 1, "payload": {"text": "hola"}})
        error_env = ws.receive_json()
        assert error_env["type"] == "server.error"
        assert "no encontrada" in error_env["payload"]["reason"]


def test_ws_clarification_turn_does_not_emit_summary(clean_env: None) -> None:
    client, llm = _client_with_scripted_llm(clean_env)
    session_id = _create_session(client)
    llm._scripted = [  # noqa: SLF001
        (
            _INTERVIEW_MARKER,
            json.dumps(
                {
                    "needs_clarification": True,
                    "clarification_question": "¿A qué se refiere con 'maluca'?",
                    "next_question": None,
                    "observations": [
                        {"code": "GENERAL_STATE", "label": "ánimo", "certainty": "uncertain",
                         "original_text": "la vi maluca", "normalized_text": None}
                    ],
                }
            ),
        ),
    ]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {"v": 1, "type": "client.turn_text", "seq": 1, "payload": {"text": "la vi maluca"}}
        )
        state_env = ws.receive_json()
        response_env = ws.receive_json()
        decision_env = ws.receive_json()

    assert state_env["payload"]["state"] == "interviewing"
    assert response_env["payload"]["needs_clarification"] is True
    assert decision_env["type"] == "server.decision"
