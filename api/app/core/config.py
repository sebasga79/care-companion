"""Configuración tipada de la aplicación (REP-002).

Fuente única de verdad para variables de entorno. Validación estricta al
arranque: un `LLM_PROVIDER` fuera de la allowlist o una configuración
incompleta para `groq`/`ollama` deben impedir que el proceso arranque, no
degradar silenciosamente (spec.md §11 — no defaults inseguros).

Allowlist de modelos (G3, docs/auditoria-kit-oficial-2026-08-07.md §3):
`groq` (Llama 3.1 70B, nube) es el proveedor primario elegido; `ollama`
(Phi-3.5 Mini / Llama 3.2 local) es el de resguardo si el primario no
responde en la sesión de evaluación en vivo. Ambos hablan el mismo
protocolo de Chat Completions estilo OpenAI — un solo adapter HTTP basta
para los dos (`app/adapters/openai_compat_llm.py`).

Embeddings de RAG (no restringidos por G3, decisión propia): `ollama`
sirve BGE-M3 localmente por el mismo protocolo HTTP (`app/adapters/
openai_compat_embeddings.py`), reusando la infraestructura de Ollama que
ya corre como resguardo del LLM."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Allowlist de proveedores LLM. El adapter concreto vive en `adapters/`;
    el dominio nunca importa un SDK de proveedor directamente (ADR-001).

    Los únicos modelos permitidos por la rúbrica del reto (G3) son Gemini
    1.5 Flash, Llama 3.1 70B vía Groq, Llama 3.2 (1B/3B) local y Phi-3.5
    Mini local. Este proyecto usa `groq` como primario y `ollama` como
    resguardo local — Gemini queda fuera de la allowlist de *este* código
    porque no habla el protocolo OpenAI-compatible que ya soportamos (haría
    falta un SDK/adapter aparte, ver auditoría §3)."""

    FAKE = "fake"
    GROQ = "groq"
    OLLAMA = "ollama"


# Defaults conocidos por proveedor — así `LLM_PROVIDER=groq` + `LLM_API_KEY`
# ya alcanza para arrancar (menos variables que declarar en el README de
# instalación de 15 min, gate G2). Se aplican solo si el env no fijó un
# valor explícito (Settings los deja en `None`/placeholder).
_DEFAULT_BASE_URLS: dict[LLMProvider, str] = {
    LLMProvider.GROQ: "https://api.groq.com/openai/v1",
    LLMProvider.OLLAMA: "http://localhost:11434/v1",
}
_DEFAULT_MODELS: dict[LLMProvider, str] = {
    # Nombre de modelo tal como lo expone la API de Groq para Llama 3.1 70B.
    LLMProvider.GROQ: "llama-3.1-70b-versatile",
    # Decisión (auditoría §3): Phi-3.5 Mini como resguardo local por defecto;
    # Llama 3.2 3B es la alternativa si se prefiere (LLM_FALLBACK_MODEL=llama3.2).
    LLMProvider.OLLAMA: "phi3.5",
}
_PLACEHOLDER_VALUES = {"", "changeme"}


def _is_placeholder(value: str | None) -> bool:
    return not value or value.strip().lower() in _PLACEHOLDER_VALUES


class EmbeddingsProvider(str, Enum):
    """Allowlist de proveedores de embeddings para RAG. A diferencia del
    LLM (G3), los embeddings NO están restringidos por la rúbrica del reto
    — esta allowlist es una decisión propia, no un requisito del kit.

    Decisión (docs/auditoria-kit-oficial-2026-08-07.md §3/§9): `ollama`
    sirve BGE-M3 localmente vía el mismo protocolo HTTP que ya usa el
    resguardo del LLM — sin sumar un segundo proveedor de nube (se
    descartó explícitamente usar embeddings de Gemini por esto: hubiera
    significado una segunda dependencia de red/API key en la sesión de
    evaluación en vivo, sin necesidad, ya que Ollama corre local)."""

    FAKE = "fake"
    OLLAMA = "ollama"


_EMBEDDINGS_DEFAULT_BASE_URLS: dict[EmbeddingsProvider, str] = {
    EmbeddingsProvider.OLLAMA: "http://localhost:11434/v1",
}
_EMBEDDINGS_DEFAULT_MODELS: dict[EmbeddingsProvider, str] = {
    # BGE-M3: sugerido explícitamente por docs/stack-tecnico.md §4 por su
    # desempeño en español ("entiende sinónimos médicos y conceptos
    # complejos"). Se instala con `ollama pull bge-m3`.
    EmbeddingsProvider.OLLAMA: "bge-m3",
}


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
    llm_request_timeout_seconds: float = Field(
        default=20.0, alias="LLM_REQUEST_TIMEOUT_SECONDS"
    )

    # Resguardo (docs/auditoria-kit-oficial-2026-08-07.md §3): si el
    # primario (Groq, nube) falla o no responde durante la sesión de
    # evaluación en vivo, `FallbackLLM` reintenta contra este segundo
    # `LLMPort` (Ollama local). `None` desactiva el resguardo por completo
    # — es el comportamiento por defecto y el de todos los tests que no lo
    # configuran explícitamente.
    llm_fallback_provider: LLMProvider | None = Field(
        default=None, alias="LLM_FALLBACK_PROVIDER"
    )
    llm_fallback_base_url: str | None = Field(default=None, alias="LLM_FALLBACK_BASE_URL")
    llm_fallback_api_key: str | None = Field(default=None, alias="LLM_FALLBACK_API_KEY")
    llm_fallback_model: str | None = Field(default=None, alias="LLM_FALLBACK_MODEL")

    # Costo estimado por llamada (rúbrica §5: "si tu solución corre local,
    # extrapola a precios de API de producción y explica el cálculo"). Sin
    # configurar, `/metrics` reporta el costo como "pendiente" en vez de
    # inventar un precio — la vigencia de precios de proveedores cambia y
    # un número fabricado es peor que uno ausente (mismo principio que
    # honestidad de latencia P50/P95).
    llm_cost_per_million_input_tokens: float | None = Field(
        default=None, alias="LLM_COST_PER_MILLION_INPUT_TOKENS"
    )
    llm_cost_per_million_output_tokens: float | None = Field(
        default=None, alias="LLM_COST_PER_MILLION_OUTPUT_TOKENS"
    )

    # Embeddings reales para RAG (decisión post-auditoría, §3/§9): `fake`
    # (n-gramas hasheados, sin dependencias, el default de siempre) u
    # `ollama` (BGE-M3 local). Cambiar de proveedor invalida los vectores ya
    # indexados (dimensiones distintas) — requiere reingestión completa del
    # conocimiento cargado (`--clean` en `levantar_app.sh` o borrar la BD).
    embeddings_provider: EmbeddingsProvider = Field(
        default=EmbeddingsProvider.FAKE, alias="EMBEDDINGS_PROVIDER"
    )
    embeddings_base_url: str | None = Field(default=None, alias="EMBEDDINGS_BASE_URL")
    embeddings_api_key: str | None = Field(default=None, alias="EMBEDDINGS_API_KEY")
    embeddings_model: str | None = Field(default=None, alias="EMBEDDINGS_MODEL")
    embeddings_request_timeout_seconds: float = Field(
        default=30.0, alias="EMBEDDINGS_REQUEST_TIMEOUT_SECONDS"
    )

    # RAG (Sprint C2, Epic RAG). Defaults conservadores para un corpus
    # pequeño/mediano de reto (architecture.md §9.1); todos overrideables
    # por entorno para tests y ajuste sin tocar código.
    rag_allowed_extensions: str = Field(default="txt,md,pdf", alias="RAG_ALLOWED_EXTENSIONS")
    rag_max_upload_bytes: int = Field(default=2_000_000, alias="RAG_MAX_UPLOAD_BYTES")
    rag_chunk_size_chars: int = Field(default=800, alias="RAG_CHUNK_SIZE_CHARS")
    rag_chunk_overlap_chars: int = Field(default=150, alias="RAG_CHUNK_OVERLAP_CHARS")
    rag_embedding_dimensions: int = Field(default=128, alias="RAG_EMBEDDING_DIMENSIONS")
    rag_rrf_k: int = Field(default=60, alias="RAG_RRF_K")
    rag_retrieval_top_k: int = Field(default=5, alias="RAG_RETRIEVAL_TOP_K")
    rag_candidate_pool_size: int = Field(default=200, alias="RAG_CANDIDATE_POOL_SIZE")
    rag_evidence_score_threshold: float = Field(default=0.2, alias="RAG_EVIDENCE_SCORE_THRESHOLD")

    @property
    def rag_allowed_extensions_set(self) -> frozenset[str]:
        return frozenset(
            ext.strip().lower().lstrip(".")
            for ext in self.rag_allowed_extensions.split(",")
            if ext.strip()
        )

    @model_validator(mode="after")
    def _apply_llm_defaults_and_validate(self) -> Settings:
        self.llm_base_url = self._resolved_base_url(self.llm_provider, self.llm_base_url)
        self.llm_model = self._resolved_model(self.llm_provider, self.llm_model)
        _require_real_values(
            provider=self.llm_provider,
            base_url=self.llm_base_url,
            model=self.llm_model,
            api_key=self.llm_api_key,
            env_prefix="LLM",
        )

        if self.llm_fallback_provider is not None:
            self.llm_fallback_base_url = self._resolved_base_url(
                self.llm_fallback_provider, self.llm_fallback_base_url
            )
            self.llm_fallback_model = self._resolved_model(
                self.llm_fallback_provider, self.llm_fallback_model
            )
            _require_real_values(
                provider=self.llm_fallback_provider,
                base_url=self.llm_fallback_base_url,
                model=self.llm_fallback_model,
                api_key=self.llm_fallback_api_key,
                env_prefix="LLM_FALLBACK",
            )

        if self.embeddings_provider is not EmbeddingsProvider.FAKE:
            self.embeddings_base_url = (
                self.embeddings_base_url
                if not _is_placeholder(self.embeddings_base_url)
                else _EMBEDDINGS_DEFAULT_BASE_URLS.get(self.embeddings_provider)
            )
            self.embeddings_model = (
                self.embeddings_model
                if not _is_placeholder(self.embeddings_model)
                else _EMBEDDINGS_DEFAULT_MODELS.get(self.embeddings_provider)
            )
            missing: list[str] = []
            if _is_placeholder(self.embeddings_base_url):
                missing.append("EMBEDDINGS_BASE_URL")
            if _is_placeholder(self.embeddings_model):
                missing.append("EMBEDDINGS_MODEL")
            if missing:
                raise ValueError(
                    f"EMBEDDINGS_PROVIDER={self.embeddings_provider.value!r} requiere "
                    "valores reales para: " + ", ".join(missing)
                )
        return self

    @staticmethod
    def _resolved_base_url(provider: LLMProvider, base_url: str | None) -> str | None:
        if not _is_placeholder(base_url):
            return base_url
        return _DEFAULT_BASE_URLS.get(provider, base_url)

    @staticmethod
    def _resolved_model(provider: LLMProvider, model: str | None) -> str | None:
        # "fake-model-v1" es el default genérico del campo; si el proveedor
        # real no trae su propio modelo declarado, se interpreta igual que
        # "no declarado" y se completa con el default conocido del proveedor.
        if model and model not in ("fake-model-v1", *_PLACEHOLDER_VALUES):
            return model
        return _DEFAULT_MODELS.get(provider, model)


def _require_real_values(
    *,
    provider: LLMProvider,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    env_prefix: str,
) -> None:
    if provider is LLMProvider.FAKE:
        return
    missing: list[str] = []
    if _is_placeholder(base_url):
        missing.append(f"{env_prefix}_BASE_URL")
    if _is_placeholder(model):
        missing.append(f"{env_prefix}_MODEL")
    if provider is LLMProvider.GROQ and _is_placeholder(api_key):
        # Ollama local no exige credencial; Groq sí (es un servicio de nube).
        missing.append(f"{env_prefix}_API_KEY")
    if missing:
        raise ValueError(
            f"{env_prefix}_PROVIDER={provider.value!r} requiere valores reales para: "
            + ", ".join(missing)
        )


def get_settings() -> Settings:
    """Construye `Settings` leyendo el entorno en cada llamada (sin cache),
    para que los tests puedan variar env vars entre casos sin recargar
    módulos."""
    return Settings()
