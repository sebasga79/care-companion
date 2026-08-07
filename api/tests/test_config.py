"""REP-002 — settings con pydantic-settings, allowlist y validación al
arranque. Allowlist real (G3, docs/auditoria-kit-oficial-2026-08-07.md
§3): `groq` primario, `ollama` de resguardo local."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import EmbeddingsProvider, LLMProvider, get_settings


def test_default_settings_use_fake_provider(clean_env: None) -> None:
    settings = get_settings()
    assert settings.llm_provider == LLMProvider.FAKE
    assert settings.llm_model == "fake-model-v1"
    assert settings.api_port == 8000


def test_database_path_env_override(clean_env: None, db_path: str) -> None:
    settings = get_settings()
    assert settings.database_path == db_path


def test_groq_requires_api_key(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        get_settings()


def test_groq_rejects_changeme_api_key(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "changeme")
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        get_settings()


def test_groq_applies_known_defaults_with_only_api_key_set(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Menos variables que declarar en el README de instalación de 15 min
    (G2): con `LLM_API_KEY` alcanza, `base_url`/`model` se completan con
    los defaults conocidos de Groq."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "gsk_real_key")
    settings = get_settings()
    assert settings.llm_provider == LLMProvider.GROQ
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.llm_model == "llama-3.1-70b-versatile"


def test_ollama_does_not_require_api_key(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama local no exige credencial (no es un servicio de nube)."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    settings = get_settings()
    assert settings.llm_provider == LLMProvider.OLLAMA
    assert settings.llm_base_url == "http://localhost:11434/v1"
    assert settings.llm_model == "phi3.5"
    assert settings.llm_api_key is None


def test_llm_base_url_explicit_value_overrides_provider_default(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://otro-host:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    settings = get_settings()
    assert settings.llm_base_url == "http://otro-host:11434/v1"
    assert settings.llm_model == "llama3.2"


def test_llm_provider_allowlist_rejects_unknown_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic-direct-sdk")
    with pytest.raises(ValidationError):
        get_settings()


def test_fallback_disabled_by_default(clean_env: None) -> None:
    settings = get_settings()
    assert settings.llm_fallback_provider is None


def test_fallback_ollama_applies_defaults(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "gsk_real_key")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    settings = get_settings()
    assert settings.llm_fallback_base_url == "http://localhost:11434/v1"
    assert settings.llm_fallback_model == "phi3.5"


def test_fallback_groq_without_api_key_fails(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "groq")
    with pytest.raises(ValidationError, match="LLM_FALLBACK_API_KEY"):
        get_settings()


def test_embeddings_default_is_fake(clean_env: None) -> None:
    settings = get_settings()
    assert settings.embeddings_provider == EmbeddingsProvider.FAKE
    assert settings.embeddings_base_url is None


def test_embeddings_ollama_applies_known_defaults(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decisión (auditoría §3/§9): Ollama + BGE-M3, sin necesitar API key
    (no es un servicio de nube) — solo EMBEDDINGS_PROVIDER=ollama alcanza."""
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "ollama")
    settings = get_settings()
    assert settings.embeddings_base_url == "http://localhost:11434/v1"
    assert settings.embeddings_model == "bge-m3"
    assert settings.embeddings_api_key is None


def test_embeddings_ollama_explicit_values_override_defaults(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDINGS_BASE_URL", "http://otro-host:11434/v1")
    monkeypatch.setenv("EMBEDDINGS_MODEL", "nomic-embed-text")
    settings = get_settings()
    assert settings.embeddings_base_url == "http://otro-host:11434/v1"
    assert settings.embeddings_model == "nomic-embed-text"


def test_embeddings_provider_allowlist_rejects_unknown_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai-direct-sdk")
    with pytest.raises(ValidationError):
        get_settings()
