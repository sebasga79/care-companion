"""TST-003 — Aserciones consolidadas de las 5 compuertas eliminatorias.

Cada test corresponde a un gate del reto (plan.md §10). Es la evidencia única
"verde/rojo" de que ningún gate está roto; los tests de detalle viven en sus
módulos (test_ingestion, test_orchestrator, test_ws, etc.).
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import LLMProvider
from app.domain.decision import DecisionInputs, DecisionLevel, reduce_decision

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Gate: aprendizaje/olvido (learn/forget) demostrable sin reinicio
# ---------------------------------------------------------------------------
def test_gate_learn_forget(client: TestClient) -> None:
    content = b"El vendaje posoperatorio se cambia cada 24 horas segun indicacion."
    files = {"file": ("cuidado.txt", io.BytesIO(content), "text/plain")}
    up = client.post("/api/v1/knowledge/documents", files=files)
    assert up.status_code in (200, 201)
    doc_id = up.json()["document"]["id"]

    # Canaria positiva: el contenido nuevo es recuperable.
    found = client.get("/api/v1/knowledge/search", params={"q": "vendaje 24 horas"})
    assert found.status_code == 200
    assert len(found.json()["results"]) >= 1

    # Olvido transaccional.
    deleted = client.delete(f"/api/v1/knowledge/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["document"]["status"] == "deleted"

    # Canaria negativa: el contenido borrado ya no es recuperable.
    gone = client.get("/api/v1/knowledge/search", params={"q": "vendaje 24 horas"})
    assert len(gone.json()["results"]) == 0


# ---------------------------------------------------------------------------
# Gate: decisión no degradable (el modelo nunca rebaja una regla determinista)
# ---------------------------------------------------------------------------
def test_gate_decision_not_degradable() -> None:
    # El modelo reporta el nivel más bajo posible, pero hay un red flag duro.
    result = reduce_decision(
        DecisionInputs(hard_red_flag=True, model_level=DecisionLevel.ROUTINE_FOLLOW_UP)
    )
    assert result.level == DecisionLevel.HARD_RED_FLAG
    assert result.should_escalate is True

    # El tipo impide que el modelo se autodeclare un nivel no reportable.
    for forbidden in (
        DecisionLevel.HARD_RED_FLAG,
        DecisionLevel.DATA_INTEGRITY_FAILURE,
        DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK,
    ):
        try:
            DecisionInputs(model_level=forbidden)
        except ValueError:
            continue
        raise AssertionError(f"model_level={forbidden} no debería ser construible")


# ---------------------------------------------------------------------------
# Gate: un solo modelo (allowlist de proveedores; sin adapters clandestinos)
# ---------------------------------------------------------------------------
def test_gate_single_model_allowlist() -> None:
    # Runtime solo permite proveedores reales: `groq` (primario, familia
    # Meta Llama) y `ollama` (resguardo local, Phi-3.5 Mini) — decisión en
    # docs/auditoria-kit-oficial-2026-08-07.md §3, ambos dentro de la
    # allowlist de modelos permitidos del reto (G3).
    assert {p.value for p in LLMProvider} == {"groq", "ollama"}


# ---------------------------------------------------------------------------
# Gate: voz realtime — contrato WebSocket con envelopes versionados y seq
# ---------------------------------------------------------------------------
def test_gate_websocket_realtime_contract(client: TestClient) -> None:
    """El fixture inyecta un doble determinista únicamente dentro de la
    suite. El arranque del producto no ofrece ese proveedor: este test
    conserva la regresión del contrato WebSocket sin consumir cuota Groq."""
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {"v": 1, "type": "client.turn_text", "seq": 1, "payload": {"text": "tiene fiebre"}}
        )
        # Un turno SIEMPRE produce exactamente estos tres envelopes, en este
        # orden (app/api/routes/ws.py); `server.summary` solo aparece si el
        # turno dejó la sesión en un estado terminal. Se leen los tres de
        # forma explícita en vez de "hasta 6 o hasta ver summary": ese bucle
        # bloqueaba indefinidamente cuando el turno NO es terminal, porque
        # `receive_json()` no tiene timeout.
        envs = [ws.receive_json() for _ in range(3)]
        for env in envs:
            assert env["v"] == 1
            assert "correlation_id" in env
        seqs = [env["seq"] for env in envs]
        types = [env["type"] for env in envs]
        decision_envs = [env for env in envs if env["type"] == "server.decision"]

        state = envs[0]["payload"]["state"]
        if state in ("summarizing", "fail_safe"):
            summary_env = ws.receive_json()
            assert summary_env["type"] == "server.summary"
            seqs.append(summary_env["seq"])
            types.append(summary_env["type"])

    # Envelopes versionados, seq del servidor estrictamente creciente.
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    assert "server.decision" in types

    # El PRIMER turno de una llamada nueva nunca debe fallar por un problema
    # técnico interno del doble de prueba (parsing/contrato), no
    # una decisión clínica legítima. `DATA_INTEGRITY_FAILURE` es
    # exactamente la señal de ese tipo de fallo (app/domain/decision.py).
    assert decision_envs[0]["payload"]["level"] != "DATA_INTEGRITY_FAILURE"


def test_agent_asks_the_next_checklist_question(client: TestClient) -> None:
    """Regresión de un fallo de producto real visto en `/call`: el agente
    respondía siempre lo mismo y NUNCA preguntaba nada — una llamada de
    seguimiento que no recolecta información. Causa: `next_question` del
    `InterviewAgent` sólo se usaba como consulta de retrieval y se
    descartaba; nunca llegaba al `ResponseAgent` ni al paciente. La rúbrica
    evalúa "cómo abre, conduce y cierra el agente la conversación"."""
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {"v": 1, "type": "client.turn_text", "seq": 1, "payload": {"text": "hola, buenas"}}
        )
        ws.receive_json()  # server.state
        response_env = ws.receive_json()

    message = response_env["payload"]["message"]
    assert "?" in message, f"el agente debe conducir la entrevista preguntando; dijo: {message!r}"
    assert "gracias por contarme" not in message.lower()
    assert message.lower().startswith("buenas tardes")


def test_greeting_alone_does_not_escalate_the_call(client: TestClient) -> None:
    """Regresión de un falso positivo real visto en `/call` en vivo: saludar
    ("aló, buenas tardes") escalaba la llamada a revisión humana en dos
    turnos. Causa: `FakeLLM` marcaba el siguiente objetivo del checklist
    como `uncertain` sin mirar el contenido del turno, y el segundo objetivo
    es FEVER (código de regla clínica) — "fiebre incierta" sin evidencia
    dispara `evidence_insufficient_with_risk`. La rúbrica evalúa
    explícitamente el comportamiento "en situaciones donde escalar
    claramente NO es lo correcto"."""
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    greetings = ["Aló, buenas tardes", "Sí, con él habla", "Bien, gracias"]
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        for seq, text in enumerate(greetings, start=1):
            ws.send_json(
                {"v": 1, "type": "client.turn_text", "seq": seq, "payload": {"text": text}}
            )
            state_env = ws.receive_json()
            ws.receive_json()  # server.agent_response
            decision_env = ws.receive_json()

            assert decision_env["payload"]["escalated"] is False, (
                f"un saludo no debe escalar la llamada (turno {seq}: {text!r})"
            )
            if state_env["payload"]["state"] in ("summarizing", "fail_safe", "escalated"):
                raise AssertionError(
                    f"la llamada terminó en {state_env['payload']['state']} tras un saludo "
                    f"(turno {seq}: {text!r})"
                )


def test_denied_pain_skips_irrelevant_location_questions(client: TestClient) -> None:
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {
                "v": 1,
                "type": "client.turn_text",
                "seq": 1,
                "payload": {"text": "No tengo dolor"},
            }
        )
        ws.receive_json()
        response = ws.receive_json()
        ws.receive_json()

    message = response["payload"]["message"].lower()
    assert "parte exacta" not in message
    assert "sentido en general" in message


def test_plain_pain_is_characterized_before_general_checklist(client: TestClient) -> None:
    """Dolor sin adjetivos también exige localización antes de avanzar."""
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {
                "v": 1,
                "type": "client.turn_text",
                "seq": 1,
                "payload": {"text": "Un poco mejor, pero tengo dolor"},
            }
        )
        ws.receive_json()
        response = ws.receive_json()
        decision = ws.receive_json()

    message = response["payload"]["message"].lower()
    assert "parte exacta" in message
    assert "estado general" not in message
    assert decision["payload"]["escalated"] is False


def test_unspecified_distress_gets_one_urgent_screen_before_decision(
    client: TestClient,
) -> None:
    """ "Muy mal" no inventa una urgencia; una señal concreta sí escala."""
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json({"v": 1, "type": "client.turn_text", "seq": 1, "payload": {"text": "Muy mal"}})
        vague_state = ws.receive_json()
        vague_response = ws.receive_json()
        vague_decision = ws.receive_json()

        assert vague_state["payload"]["state"] == "interviewing"
        assert vague_response["payload"]["needs_clarification"] is True
        screen = vague_response["payload"]["message"].lower()
        assert "qué siente exactamente" in screen
        assert "dificultad para respirar" in screen
        assert vague_decision["payload"]["escalated"] is False

        ws.send_json(
            {
                "v": 1,
                "type": "client.turn_text",
                "seq": 2,
                "payload": {"text": "No puedo respirar y siento que me voy a desmayar"},
            }
        )
        escalated_state = ws.receive_json()
        escalated_response = ws.receive_json()
        escalated_decision = ws.receive_json()

    assert escalated_state["payload"]["state"] == "escalated"
    assert escalated_decision["payload"]["level"] == "HARD_RED_FLAG"
    assert escalated_decision["payload"]["escalated"] is True
    assert "reporte" in escalated_response["payload"]["message"].lower()


def test_wound_description_without_repeating_subject_advances(client: TestClient) -> None:
    """ "Está roja e inflamada" responde la pregunta sobre la herida.

    Regresión de un bucle observado en vivo: el adapter solo reconocía la
    respuesta si el paciente volvía a decir literalmente "herida".
    """
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    turns = (
        "No tengo dolor",
        "Me siento normal",
        "Puedo tomar líquidos y estoy comiendo alimentos licuados",
        "Estoy en temperatura normal, sin fiebre",
        "Está un poco roja y tiene un poquito de inflamación, no sé si sea normal",
    )

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        responses: list[str] = []
        for seq, text in enumerate(turns, start=1):
            ws.send_json(
                {"v": 1, "type": "client.turn_text", "seq": seq, "payload": {"text": text}}
            )
            ws.receive_json()
            responses.append(ws.receive_json()["payload"]["message"])
            decision = ws.receive_json()
            assert decision["payload"]["escalated"] is False

    wound_response = responses[-1].lower()
    assert "cómo se ve la herida" not in wound_response
    assert "aspecto de la herida" not in wound_response
    assert "movilidad" in wound_response
    opening_phrases = {message.split(".", maxsplit=1)[0] for message in responses}
    assert len(opening_phrases) >= 3, "el agente no debe repetir el mismo acuse en cada turno"


def test_pain_is_characterized_then_handoff_collects_contacts_and_closes(
    client: TestClient,
) -> None:
    """Dolor fuerte aislado se caracteriza; empeoramiento explícito escala.

    Tras el handoff se confirman dos teléfonos y la llamada se cierra sola.
    """
    case_id = client.get("/api/v1/cases").json()[0]["case_id"]
    session_id = client.post("/api/v1/sessions", json={"case_id": case_id}).json()["id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json(
            {"v": 1, "type": "client.turn_text", "seq": 1, "payload": {"text": "buenas tardes"}}
        )
        ws.receive_json()  # server.state
        ws.receive_json()  # server.agent_response
        greeting_decision = ws.receive_json()
        assert greeting_decision["payload"]["should_escalate"] is False

        def send_turn(seq: int, text: str) -> tuple[dict, dict, dict]:
            ws.send_json(
                {"v": 1, "type": "client.turn_text", "seq": seq, "payload": {"text": text}}
            )
            return ws.receive_json(), ws.receive_json(), ws.receive_json()

        pain_state, pain_response, pain_decision = send_turn(
            2, "Sigo muy inflamado y me duele mucho, tengo mucho dolor"
        )
        assert pain_state["payload"]["state"] == "interviewing"
        assert "parte exacta" in pain_response["payload"]["message"].lower()
        assert pain_decision["payload"]["should_escalate"] is False

        _, location_response, _ = send_turn(3, "En el lado derecho del abdomen")
        assert "0 a 10" in location_response["payload"]["message"]

        _, severity_response, _ = send_turn(4, "Es un nueve de diez")
        assert "mejorando" in severity_response["payload"]["message"].lower()

        state_env, response_env, decision_env = send_turn(5, "Ha empeorado, cada vez está peor")
        assert state_env["payload"]["state"] == "escalated"
        assert response_env["payload"]["intent"] == "handoff"
        assert "número principal" in response_env["payload"]["message"].lower()

        primary_state, primary_response, _ = send_turn(6, "300 123 4567")
        assert primary_state["payload"]["state"] == "escalated"
        assert "número adicional" in primary_response["payload"]["message"].lower()

        ws.send_json(
            {
                "v": 1,
                "type": "client.turn_text",
                "seq": 7,
                "payload": {"text": "604 555 1234"},
            }
        )
        closed_state = ws.receive_json()
        closed_response = ws.receive_json()
        ws.receive_json()  # server.decision
        summary_env = ws.receive_json()

    message = response_env["payload"]["message"].lower()
    assert decision_env["payload"] == {
        "level": "HARD_RED_FLAG",
        "should_escalate": True,
        "escalated": True,
    }
    assert "valoración médica urgente" in message
    assert "dentro de lo esperado" not in message
    assert closed_state["payload"]["state"] == "closed"
    assert "finalizar la llamada" in closed_response["payload"]["message"].lower()
    assert summary_env["type"] == "server.summary"
    assert summary_env["payload"]["handoff"]["status"] == "created"
    contact_codes = {item["code"] for item in summary_env["payload"]["patient_reported"]}
    assert {"CONTACT_PRIMARY", "CONTACT_EMERGENCY"} <= contact_codes

    trace = client.get(f"/api/v1/audit/sessions/{session_id}/trace").json()
    assert {contact["code"] for contact in trace["contacts"]} == {
        "CONTACT_PRIMARY",
        "CONTACT_EMERGENCY",
    }


# ---------------------------------------------------------------------------
# Gate: repositorio/entregables — artefactos obligatorios presentes
# ---------------------------------------------------------------------------
def test_gate_repo_deliverables_present() -> None:
    assert (REPO_ROOT / "README.md").is_file()
    assert (REPO_ROOT / "LICENSE").is_file()
    assert (REPO_ROOT / "docker-compose.yml").is_file()
    assert (REPO_ROOT / "docs" / "architecture-diagram.md").is_file()
    license_text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
