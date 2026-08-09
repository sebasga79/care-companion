"""API-001 / SUM-001 — tests REST con httpx.TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(clean_env: None) -> TestClient:
    app = create_app()
    return TestClient(app)


def test_health_reports_ok_and_db_status(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"] == "0.1.0"


def test_list_cases_returns_fixture_cases(client: TestClient) -> None:
    response = client.get("/api/v1/cases")
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) >= 2
    ids = {case["case_id"] for case in cases}
    assert "demo-case-001" in ids
    for case in cases:
        assert case["procedure"]
        assert case["phase"]


def test_create_session_for_known_case(client: TestClient) -> None:
    response = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"})
    assert response.status_code == 201
    body = response.json()
    assert body["case_id"] == "demo-case-001"
    assert body["state"] == "interviewing"
    assert "seguimiento" in body["opening_message"].lower()
    assert "seguimiento general (paciente de prueba)" in body["opening_message"].lower()
    assert body["knowledge_version"] == 1
    assert body["closed_at"] is None


def test_create_session_for_unknown_case_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/sessions", json={"case_id": "does-not-exist"})
    assert response.status_code == 404


def test_get_session_roundtrip(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"case_id": "demo-case-002"}).json()
    response = client.get(f"/api/v1/sessions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_session_missing_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_finish_session_returns_valid_empty_summary(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"}).json()

    response = client.post(f"/api/v1/sessions/{created['id']}/finish")
    assert response.status_code == 200
    summary = response.json()

    assert summary["schema_version"] == "1.2"
    assert summary["session_id"] == created["id"]
    assert summary["case_id"] == "demo-case-001"
    assert summary["procedure"] == "Seguimiento general (paciente de prueba)"
    assert summary["patient_reported"] == []
    assert summary["explicit_denials"] == []
    assert summary["not_assessed"] == []
    assert summary["risk"]["level"] == "ROUTINE_FOLLOW_UP"
    assert summary["risk"]["should_escalate"] is False
    assert summary["citations"] == []
    assert summary["handoff"]["status"] == "none"
    assert summary["knowledge_version"] == 1
    assert summary["ended_at"] is not None

    # el estado de la sesión debe reflejar el cierre
    session_after = client.get(f"/api/v1/sessions/{created['id']}").json()
    assert session_after["state"] == "closed"
    assert session_after["closed_at"] is not None


def test_finish_session_twice_returns_409(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"}).json()
    first = client.post(f"/api/v1/sessions/{created['id']}/finish")
    assert first.status_code == 200
    second = client.post(f"/api/v1/sessions/{created['id']}/finish")
    assert second.status_code == 409


def test_finish_missing_session_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/sessions/00000000-0000-0000-0000-000000000000/finish")
    assert response.status_code == 404


def test_report_voice_latency_persists_event_and_returns_204(client: TestClient) -> None:
    """Rúbrica §5: latencia voz-a-voz real, medida en el navegador
    (`CallModal.tsx`) y persistida aquí como evento auditable — antes vivía
    sólo en memoria del navegador (auditoría §9.34)."""
    created = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"}).json()

    response = client.post(
        f"/api/v1/sessions/{created['id']}/voice-latency", json={"latency_ms": 1200}
    )
    assert response.status_code == 204
    assert response.content == b""

    metrics = client.get("/api/v1/metrics").json()
    assert metrics["latency_voice"]["status"] == "medido"
    assert metrics["latency_voice"]["value"] == "1200 ms P50"
    assert "n=1" in metrics["latency_voice"]["detail"]

    trace = client.get(f"/api/v1/audit/sessions/{created['id']}/trace").json()
    event_types = {e["event_type"] for e in trace["events"]}
    assert "client.voice_latency_reported" in event_types


def test_report_voice_latency_missing_session_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/voice-latency",
        json={"latency_ms": 900},
    )
    assert response.status_code == 404


def test_report_voice_latency_rejects_non_positive_value(client: TestClient) -> None:
    created = client.post("/api/v1/sessions", json={"case_id": "demo-case-001"}).json()
    response = client.post(
        f"/api/v1/sessions/{created['id']}/voice-latency", json={"latency_ms": 0}
    )
    assert response.status_code == 422


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/cases" in schema["paths"]
    assert "/api/v1/sessions" in schema["paths"]
    assert "/api/v1/sessions/{session_id}/finish" in schema["paths"]
