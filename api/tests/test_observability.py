"""OBS-001 — correlation_id (header entrante/generado) + traza persistida
en `events` con timings por request."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.repositories.events import EventRepository


@pytest.fixture
def client(clean_env: None) -> TestClient:
    app = create_app()
    return TestClient(app)


def test_correlation_id_is_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    assert len(response.headers["X-Correlation-ID"]) > 0


def test_correlation_id_is_echoed_when_provided(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Correlation-ID": "test-corr-123"})
    assert response.headers["X-Correlation-ID"] == "test-corr-123"


def test_http_request_event_is_persisted_with_latency(client: TestClient) -> None:
    response = client.get("/api/v1/cases", headers={"X-Correlation-ID": "trace-abc"})
    assert response.status_code == 200

    settings = get_settings()
    event_repo = EventRepository(settings.database_path)
    events = event_repo.list_by_correlation("trace-abc")

    assert len(events) == 1
    event = events[0]
    assert event["component"] == "http"
    assert event["event_type"] == "request.completed"
    assert event["latency_ms"] is not None
    assert event["latency_ms"] >= 0

    import json

    payload = json.loads(event["payload"])
    assert payload["path"] == "/api/v1/cases"
    assert payload["status_code"] == 200


def test_each_request_gets_a_distinct_correlation_id_by_default(client: TestClient) -> None:
    first = client.get("/health")
    second = client.get("/health")
    assert first.headers["X-Correlation-ID"] != second.headers["X-Correlation-ID"]


def test_trace_correlates_across_session_creation_and_finish(client: TestClient) -> None:
    created = client.post(
        "/api/v1/sessions",
        json={"case_id": "demo-case-001"},
        headers={"X-Correlation-ID": "trace-session-1"},
    ).json()

    client.post(
        f"/api/v1/sessions/{created['id']}/finish",
        headers={"X-Correlation-ID": "trace-session-1"},
    )

    settings = get_settings()
    event_repo = EventRepository(settings.database_path)
    events = event_repo.list_by_correlation("trace-session-1")
    event_types = {event["event_type"] for event in events}

    assert "request.completed" in event_types
    assert "session.finished" in event_types
