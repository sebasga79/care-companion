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
    # `fake` es solo para tests/desarrollo sin credenciales; los dos
    # proveedores reales son `groq` (primario, Llama 3.1 70B) y `ollama`
    # (resguardo local, Phi-3.5 Mini) — decisión en
    # docs/auditoria-kit-oficial-2026-08-07.md §3, ambos dentro de la
    # allowlist de modelos permitidos del reto (G3).
    assert {p.value for p in LLMProvider} == {"fake", "groq", "ollama"}


# ---------------------------------------------------------------------------
# Gate: voz realtime — contrato WebSocket con envelopes versionados y seq
# ---------------------------------------------------------------------------
def test_gate_websocket_realtime_contract(client: TestClient) -> None:
    """`client` usa el `LLM_PROVIDER=fake` DEFAULT del proyecto (el mismo
    con el que arranca `./levantar_app.sh`/`docker compose up` sin ningún
    `.env`) — a propósito, no un `ScriptedFakeLLM` a medida. Regresión
    (docs/auditoria-kit-oficial-2026-08-07.md §9.2): hasta el 7 de agosto,
    `FakeLLM` devolvía texto plano no-JSON y CUALQUIER turno con el
    proveedor por defecto caía en fail-safe con
    `DATA_INTEGRITY_FAILURE` en el primer intento — el camino "sin
    credenciales" que el README anuncia como funcional nunca completaba una
    llamada real. Este test falla si eso vuelve a pasar."""
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

    # El PRIMER turno de una llamada nueva, con el proveedor fake por
    # defecto, nunca debe fallar por un problema técnico interno del propio
    # adapter (parsing/contrato) — eso es un bug del proveedor `fake`, no
    # una decisión clínica legítima. `DATA_INTEGRITY_FAILURE` es
    # exactamente la señal de ese tipo de fallo (app/domain/decision.py).
    assert decision_envs[0]["payload"]["level"] != "DATA_INTEGRITY_FAILURE"


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
