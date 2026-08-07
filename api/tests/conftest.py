from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "care_companion_test.db")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, db_path: str) -> Iterator[None]:
    """Aísla cada test de cualquier `.env` real y de env vars heredadas del
    shell, fijando solo lo necesario para levantar una app/Settings de
    prueba con una base de datos temporal."""
    for key in [
        "APP_ENV",
        "DATABASE_PATH",
        "API_HOST",
        "API_PORT",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_REQUEST_TIMEOUT_SECONDS",
        "LLM_FALLBACK_PROVIDER",
        "LLM_FALLBACK_BASE_URL",
        "LLM_FALLBACK_API_KEY",
        "LLM_FALLBACK_MODEL",
        "EMBEDDINGS_PROVIDER",
        "EMBEDDINGS_BASE_URL",
        "EMBEDDINGS_API_KEY",
        "EMBEDDINGS_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    yield


@pytest.fixture
def client(clean_env: None) -> TestClient:
    """Shared TestClient over an isolated app (its own temp DB)."""
    return TestClient(create_app())
