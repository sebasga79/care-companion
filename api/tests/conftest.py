from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "care_companion_test.db")


@pytest.fixture(autouse=True)
def _ignore_developer_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Impide que `api/.env` contamine los tests.

    `Settings` declara `env_file=".env"`, así que pydantic-settings lo lee
    del directorio de trabajo. En cuanto alguien configura un proveedor real
    para probar a mano (`LLM_PROVIDER=groq`, `LLM_PROVIDER=ollama`…), ese
    archivo se filtraba a TODA la suite y 8 tests fallaban por un estado de
    la máquina, no por el código. Le pasaría igual al jurado en cuanto
    siguiera el README para conectar Groq y luego corriera `make verify`.

    `autouse` a propósito: no depende de que cada test recuerde pedir
    `clean_env`.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)


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
        "DATASET_DIR",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_PATH", db_path)
    # `DATASET_DIR` por defecto es relativo a cwd (`./data/dataset`) y este
    # fixture hace `chdir` a `api/` más abajo — si quien corre los tests ya
    # descargó el dataset real ahí (`scripts/fetch_dataset.py`), la app
    # levantaría `DatasetCaseAdapter` en vez de `FixtureCaseAdapter` y todo
    # test que asume `demo-case-001`/`demo-case-002`/`demo-case-003` (los 3
    # casos fijos) fallaría — el estado del filesystem del desarrollador no
    # debe filtrarse a los tests. Se fija a una ruta bajo `tmp_path` que
    # nunca existe, así los tests SIEMPRE ven fixtures salvo que un test
    # puntual (test_dataset_case_source.py) construya su propio adapter
    # directo, sin pasar por `clean_env`.
    monkeypatch.setenv("DATASET_DIR", str(Path(db_path).parent / "no-dataset-in-tests"))
    monkeypatch.chdir(Path(__file__).resolve().parent.parent)
    yield


@pytest.fixture
def client(clean_env: None) -> TestClient:
    """Shared TestClient over an isolated app (its own temp DB)."""
    return TestClient(create_app())
