"""Tests de las lecturas de auditoría y métricas (UX-005 / PERF)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.repositories.audit import _normalize_followup_payload
from app.repositories.events import EventRepository


def test_audit_sessions_empty(client: TestClient) -> None:
    r = client.get("/api/v1/audit/sessions")
    assert r.status_code == 200
    assert r.json() == {"sessions": []}


def test_metrics_honest_pending_without_samples(client: TestClient) -> None:
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    body = r.json()
    # Sin instrumentar, todo debe reportarse pendiente — nunca inventar cifras.
    assert body["tokens"]["status"] == "pendiente"
    assert body["cost"]["status"] == "pendiente"
    assert body["latency_voice"]["status"] == "pendiente"
    assert body["measured"] is False


def test_metrics_voice_latency_percentiles_with_multiple_samples(
    client: TestClient,
) -> None:
    """`voice_latency_percentiles` (rúbrica §5, definición literal) usa la
    misma fórmula de percentil que `latency_percentiles`, sobre
    `client.voice_latency_reported` en vez de `turn.response_sent` — aquí se
    prueba con varias muestras para que P50 y P95 no coincidan."""
    created = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"}).json()
    for ms in (500, 1000, 1500, 2000, 9000):
        r = client.post(
            f"/api/v1/sessions/{created['id']}/voice-latency", json={"latency_ms": ms}
        )
        assert r.status_code == 204

    body = client.get("/api/v1/metrics").json()
    assert body["latency_voice"]["status"] == "medido"
    assert body["latency_voice"]["value"] == "1500 ms P50"
    assert "9000 ms" in body["latency_voice"]["detail"]  # p95 con 5 muestras = la mayor
    assert "n=5" in body["latency_voice"]["detail"]


def test_cost_only_counts_primary_provider_tokens_not_fallback(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, db_path: str
) -> None:
    """Regresión real (auditoría §9.34): la corrida de benchmark del 9 de
    agosto agotó la cuota diaria de Groq a mitad de una conversación y
    `FallbackLLM` degradó 3 de 36 invocaciones a Ollama (gratis). Antes de
    esta corrección, `_cost_metric` sumaba TODOS los tokens de
    `agent.*.completed` sin mirar el proveedor real de cada llamada — habría
    cobrado precio de Groq por tokens que sirvió gratis el modelo local.
    Aquí se simulan ambos proveedores en la misma sesión y se verifica que
    sólo los tokens de `LLM_PROVIDER` (groq) entran al cálculo."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "unit-test-credential-not-a-secret")
    monkeypatch.setenv("LLM_COST_PER_MILLION_INPUT_TOKENS", "1.0")
    monkeypatch.setenv("LLM_COST_PER_MILLION_OUTPUT_TOKENS", "2.0")
    local_client = TestClient(create_app())

    created = local_client.post(
        "/api/v1/sessions", json={"case_id": "demo-case-001"}
    ).json()
    session_id = created["id"]

    settings = get_settings()
    event_repo = EventRepository(settings.database_path)
    # Llamada real a Groq: 1000 in / 100 out.
    event_repo.add_event(
        session_id=session_id,
        correlation_id="corr-groq",
        component="agents",
        event_type="agent.response.completed",
        payload={
            "input_tokens": 1000,
            "output_tokens": 100,
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
        },
    )
    # Llamada degradada al resguardo local: 500 in / 50 out — NO debe costar nada.
    event_repo.add_event(
        session_id=session_id,
        correlation_id="corr-ollama",
        component="agents",
        event_type="agent.response.completed",
        payload={
            "input_tokens": 500,
            "output_tokens": 50,
            "provider": "ollama",
            "model": "phi3.5",
        },
    )
    assert local_client.post(f"/api/v1/sessions/{session_id}/finish").status_code == 200

    body = local_client.get("/api/v1/metrics").json()
    assert body["cost"]["status"] == "medido"
    # Sólo los 1000 in / 100 out de groq: (1000/1e6*1.0 + 100/1e6*2.0) / 1 llamada.
    expected = (1000 / 1_000_000 * 1.0 + 100 / 1_000_000 * 2.0) / 1
    assert body["cost"]["value"] == f"${expected:.4f} USD/llamada"
    assert "1000 in + 100 out tokens de groq" in body["cost"]["detail"]
    assert "550 tokens de otros modelos/resguardo excluidos" in body["cost"]["detail"]


def test_usage_excludes_open_and_non_real_sessions(client: TestClient) -> None:
    """El denominador por llamada no mezcla sesiones incompletas ni
    registros históricos de dobles de prueba."""
    completed = client.post(
        "/api/v1/sessions", json={"case_id": "demo-case-001"}
    ).json()["id"]
    open_session = client.post(
        "/api/v1/sessions", json={"case_id": "demo-case-002"}
    ).json()["id"]
    event_repo = EventRepository(get_settings().database_path)
    event_repo.add_event(
        session_id=completed,
        correlation_id="corr-real",
        component="agents",
        event_type="agent.response.completed",
        payload={
            "input_tokens": 100,
            "output_tokens": 20,
            "provider": "ollama",
            "model": "llama3.2:3b",
        },
    )
    event_repo.add_event(
        session_id=completed,
        correlation_id="corr-test-double",
        component="agents",
        event_type="agent.response.completed",
        payload={
            "input_tokens": 9000,
            "output_tokens": 9000,
            "provider": "fake",
            "model": "test-double",
        },
    )
    event_repo.add_event(
        session_id=open_session,
        correlation_id="corr-open",
        component="agents",
        event_type="agent.response.completed",
        payload={
            "input_tokens": 7000,
            "output_tokens": 7000,
            "provider": "ollama",
            "model": "llama3.2:3b",
        },
    )
    assert client.post(f"/api/v1/sessions/{completed}/finish").status_code == 200

    body = client.get("/api/v1/metrics").json()
    assert body["tokens"]["status"] == "medido"
    assert body["tokens"]["value"] == "120 tokens"
    assert "n=1 llamadas cerradas" in body["tokens"]["detail"]
    assert body["tokens"]["scope"]["closed_calls"] == 1
    assert body["tokens"]["scope"]["provider"] == "ollama"
    assert body["tokens"]["scope"]["model"] == "llama3.2:3b"


def test_metrics_latency_stays_pending_despite_unrelated_http_traffic(
    client: TestClient,
) -> None:
    """Regresión (docs/auditoria-kit-oficial-2026-08-07.md §9): antes de la
    corrección, `/metrics` promediaba latencia de CUALQUIER request HTTP
    (uploads, listados de /audit), no la del turno conversacional real. Solo
    un turno real de voz/texto por WebSocket (`turn.response_sent`, ver
    test_ws.py) debe alimentar latency_p50/p95 — tráfico HTTP administrativo
    por sí solo debe seguir "pendiente"."""
    client.get("/api/v1/cases")
    client.get("/api/v1/audit/sessions")
    client.get("/health")

    body = client.get("/api/v1/metrics").json()
    assert body["latency_p50"]["status"] == "pendiente"
    assert body["latency_p95"]["status"] == "pendiente"


def test_audit_trace_404_for_unknown_session(client: TestClient) -> None:
    r = client.get("/api/v1/audit/sessions/does-not-exist/trace")
    assert r.status_code == 404


def test_audit_session_appears_after_creation(client: TestClient) -> None:
    cases = client.get("/api/v1/cases").json()
    case_id = cases[0]["case_id"]
    session = client.post("/api/v1/sessions", json={"case_id": case_id}).json()

    listing = client.get("/api/v1/audit/sessions").json()["sessions"]
    assert len(listing) == 1
    row = listing[0]
    assert row["session_id"] == session["id"]
    assert row["case_id"] == case_id
    assert row["citation_count"] == 0
    assert row["escalated"] is False

    trace = client.get(f"/api/v1/audit/sessions/{session['id']}/trace").json()
    assert trace["session_id"] == session["id"]
    assert isinstance(trace["events"], list)
    assert trace["contacts"] == []


def test_legacy_followup_values_are_normalized_for_audit_display() -> None:
    payload = {
        "dolor_nrs": {"value": "siete", "original_text": "siete"},
        "fiebre_c": {"value": "tengo fiebre de 38", "original_text": "tengo fiebre de 38"},
        "herida": {
            "value": "está roja y un poco inflamada",
            "original_text": "está roja y un poco inflamada",
        },
        "movilidad": {
            "value": "yo quiero que me hospitalicen ya",
            "original_text": "yo quiero que me hospitalicen ya",
        },
    }
    normalized = _normalize_followup_payload(payload)
    assert normalized["dolor_nrs"]["value"] == 7
    assert normalized["fiebre_c"]["value"] == 38.0
    assert normalized["herida"]["value"] == "enrojecida_inflamada"
    assert normalized["movilidad"] is None
