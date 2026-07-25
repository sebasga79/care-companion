"""CORS: el frontend corre en otro puerto (cross-origin) y necesita las
cabeceras CORS para que el navegador no bloquee los fetch."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_cors_allows_localhost_frontend_origin(client: TestClient) -> None:
    r = client.get("/api/v1/cases", headers={"Origin": "http://localhost:49318"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:49318"


def test_cors_preflight_allows_methods(client: TestClient) -> None:
    r = client.options(
        "/api/v1/sessions",
        headers={
            "Origin": "http://localhost:49318",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:49318"


def test_cors_ignores_non_local_origin(client: TestClient) -> None:
    # Un origen no-local no recibe la cabecera de permiso.
    r = client.get("/api/v1/cases", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"
