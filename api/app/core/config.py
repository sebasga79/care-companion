"""Configuración tipada de la aplicación (REP-002).

Fuente única de verdad para variables de entorno. Validación estricta al
arranque: un `LLM_PROVIDER` fuera de la allowlist o una configuración
incompleta para `openai_compat` deben impedir que el proceso arranque, no
degradar silenciosamente (spec.md §11 — no defaults inseguros).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Allowlist de proveedores LLM. El adapter concreto vive en `adapters/`;
    el dominio nunca importa un SDK de proveedor directamente (ADR-001)."""

    FAKE = "fake"
    OPENAI_COMPAT = "openai_compat"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")

    database_path: str = Field(default="./data/care_companion.db", alias="DATABASE_PATH")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    llm_provider: LLMProvider = Field(default=LLMProvider.FAKE, alias="LLM_PROVIDER")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="fake-model-v1", alias="LLM_MODEL")

    @model_validator(mode="after")
    def _validate_llm_provider_config(self) -> Settings:
        if self.llm_provider == LLMProvider.OPENAI_COMPAT:
            missing = []
            if not self.llm_base_url or self.llm_base_url.strip().lower() == "changeme":
                missing.append("LLM_BASE_URL")
            if not self.llm_model:
                missing.append("LLM_MODEL")
            if missing:
                raise ValueError(
                    "LLM_PROVIDER=openai_compat requiere valores reales para: "
                    + ", ".join(missing)
                )
        return self


def get_settings() -> Settings:
    """Construye `Settings` leyendo el entorno en cada llamada (sin cache),
    para que los tests puedan variar env vars entre casos sin recargar
    módulos."""
    return Settings()
