"""Tests de las lecturas de auditoría y métricas (UX-005 / PERF)."""

from __future__ import annotations

from fastapi.testclient import TestClient


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
    assert body["measured"] is False


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
