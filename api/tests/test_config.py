"""REP-002 — settings con pydantic-settings, allowlist y validación al
arranque."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import LLMProvider, get_settings


def test_default_settings_use_fake_provider(clean_env: None) -> None:
    settings = get_settings()
    assert settings.llm_provider == LLMProvider.FAKE
    assert settings.llm_model == "fake-model-v1"
    assert settings.api_port == 8000


def test_database_path_env_override(clean_env: None, db_path: str) -> None:
    settings = get_settings()
    assert settings.database_path == db_path


def test_openai_compat_requires_base_url_and_model(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        get_settings()


def test_openai_compat_rejects_changeme_base_url(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "changeme")
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        get_settings()


def test_openai_compat_succeeds_with_real_values(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    settings = get_settings()
    assert settings.llm_provider == LLMProvider.OPENAI_COMPAT
    assert settings.llm_base_url == "http://localhost:11434/v1"


def test_llm_provider_allowlist_rejects_unknown_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic-direct-sdk")
    with pytest.raises(ValidationError):
        get_settings()
