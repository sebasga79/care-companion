"""Punto de entrada FastAPI — monolito modular (architecture.md §5.2).

`create_app()` es una factory pura (sin estado de módulo compartido) para
que los tests puedan construir instancias aisladas con su propia
`DATABASE_PATH`. `app` al final del archivo es el objeto que usa
`uvicorn app.main:app`."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.dataset_case_source import DatasetCaseAdapter, DatasetFilesMissingError
from app.adapters.fake_embeddings import FakeEmbeddings
from app.adapters.fake_llm import FakeLLM
from app.adapters.fallback_llm import FallbackLLM
from app.adapters.fixture_cases import FixtureCaseAdapter
from app.adapters.openai_compat_embeddings import OpenAICompatEmbeddings
from app.adapters.openai_compat_llm import OpenAICompatLLM
from app.api.routes import audit, cases, health, knowledge, sessions, ws
from app.core.config import EmbeddingsProvider, LLMProvider, Settings, get_settings
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.orchestrator.call_cycle import CallCycleOrchestrator
from app.ports.challenge_case import ChallengeCasePort
from app.ports.embeddings import EmbeddingsPort
from app.ports.llm import LLMPort
from app.repositories.audit import AuditRepository
from app.repositories.db import apply_schema, get_connection
from app.repositories.decisions import DecisionRepository
from app.repositories.documents import DocumentRepository
from app.repositories.escalations import EscalationRepository
from app.repositories.events import EventRepository
from app.repositories.observations import ObservationRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository
from app.services.embeddings_cache import EmbeddingsCache
from app.services.ingestion import KnowledgeIngestionService

logger = logging.getLogger("care_companion.main")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    conn = get_connection(settings.database_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()

    app = FastAPI(
        title="Care Companion API",
        version="0.1.0",
        description=(
            "Backend del agente de voz postoperatorio Care Companion "
            "(fase C1 — vertical slice, ver docs/plan.md)."
        ),
    )

    app.state.settings = settings
    app.state.case_port = _build_case_port(settings)
    app.state.session_repo = SessionRepository(settings.database_path)
    app.state.turn_repo = TurnRepository(settings.database_path)
    app.state.event_repo = EventRepository(settings.database_path)

    # RAG (Sprint C2, Epic RAG). `EMBEDDINGS_PROVIDER` es independiente de
    # `LLM_PROVIDER` (dos puertos distintos) — decisión de embeddings reales
    # en docs/auditoria-kit-oficial-2026-08-07.md §3/§9 (Ollama/BGE-M3).
    app.state.document_repo = DocumentRepository(settings.database_path)
    app.state.embeddings_cache = EmbeddingsCache(_build_embeddings_adapter(settings))
    app.state.ingestion_service = KnowledgeIngestionService(
        settings.database_path,
        embeddings_cache=app.state.embeddings_cache,
        settings=settings,
        document_repo=app.state.document_repo,
    )

    # Sprint C2 (CON-001/SAFE-00x/ORC-002). `observation_repo`/`decision_repo`/
    # `escalation_repo` no tenían wiring en `app.state` todavía (los routers
    # REST no los necesitaban hasta que `CallCycleOrchestrator` los consume).
    app.state.observation_repo = ObservationRepository(settings.database_path)
    app.state.decision_repo = DecisionRepository(settings.database_path)
    app.state.escalation_repo = EscalationRepository(settings.database_path)
    app.state.audit_repo = AuditRepository(settings.database_path)

    app.state.llm = _build_llm_adapter(settings)
    app.state.call_cycle_orchestrator = CallCycleOrchestrator(
        database_path=settings.database_path,
        llm=app.state.llm,
        embeddings=app.state.embeddings_cache,
        case_port=app.state.case_port,
        evidence_score_threshold=settings.rag_evidence_score_threshold,
        candidate_pool_size=settings.rag_candidate_pool_size,
        retrieval_top_k=settings.rag_retrieval_top_k,
    )

    # CORS: el frontend corre en otro puerto (cross-origin) y el navegador
    # exige cabeceras CORS para fetch. En dev permitimos cualquier origen
    # localhost/127.0.0.1 en cualquier puerto (regex), sin credenciales (no se
    # usan cookies; el auth futuro irá por header). En T0/despliegue real se
    # restringe a los orígenes concretos vía CORS_ALLOW_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(CorrelationIdMiddleware, event_repo=app.state.event_repo)

    app.include_router(health.router)
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(ws.router)

    logger.info(
        "care_companion_app_ready env=%s db=%s llm_provider=%s case_port=%s",
        settings.app_env,
        settings.database_path,
        settings.llm_provider.value,
        type(app.state.case_port).__name__,
    )
    return app


def _build_case_port(settings: Settings) -> ChallengeCasePort:
    """Dataset real si está descargado (`scripts/fetch_dataset.py`),
    fixtures ficticios si no. A diferencia de LLM/embeddings, esto NUNCA
    impide el arranque: un caso claramente ficticio (`demo-case-001`,
    "Camila (paciente ficticia)") no engaña a nadie sobre qué está viendo,
    así que fallar rápido aquí solo rompería el gate de instalación de 15
    minutos (G2) para quien todavía no descargó el dataset — se loguea un
    warning explícito en vez de fingir silencio (spec.md §11.2)."""
    try:
        return DatasetCaseAdapter(settings.dataset_dir)
    except DatasetFilesMissingError as exc:
        logger.warning(
            "dataset_case_adapter_unavailable_using_fixtures reason=%s", exc
        )
        return FixtureCaseAdapter()


def _build_llm_adapter(settings: Settings) -> LLMPort:
    """Único punto de construcción del `LLMPort` real usado por los agentes
    (ADR-001/ADR-005): el dominio nunca importa un SDK de proveedor, solo
    este adapter concreto. Decisión de modelo y arquitectura de resguardo en
    `docs/auditoria-kit-oficial-2026-08-07.md` §3 — Groq (Llama 3.1 70B)
    primario, Ollama local (Phi-3.5 Mini) de resguardo si `LLM_FALLBACK_
    PROVIDER` está configurado."""
    primary = _build_single_adapter(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    if settings.llm_fallback_provider is None:
        return primary

    fallback = _build_single_adapter(
        provider=settings.llm_fallback_provider,
        base_url=settings.llm_fallback_base_url,
        api_key=settings.llm_fallback_api_key,
        model=settings.llm_fallback_model,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
    return FallbackLLM(primary, fallback)


def _build_single_adapter(
    *,
    provider: LLMProvider,
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    timeout_seconds: float,
) -> LLMPort:
    if provider is LLMProvider.FAKE:
        return FakeLLM(model=model or "fake-model-v1")
    # `Settings._apply_llm_defaults_and_validate` ya garantizó que
    # base_url/model son valores reales para GROQ/OLLAMA antes de que la
    # app pueda arrancar — nunca llegamos aquí con placeholders.
    assert base_url is not None and model is not None
    return OpenAICompatLLM(
        base_url=base_url,
        api_key=api_key,
        model=model,
        provider_name=provider.value,
        timeout_seconds=timeout_seconds,
    )


def _build_embeddings_adapter(settings: Settings) -> EmbeddingsPort:
    """Único punto de construcción del `EmbeddingsPort` real (mismo
    principio que `_build_llm_adapter`: el dominio nunca importa un SDK de
    proveedor). Decisión en docs/auditoria-kit-oficial-2026-08-07.md §3/§9
    — `ollama` sirve BGE-M3 localmente; sin `EMBEDDINGS_PROVIDER` configurado
    se mantiene `FakeEmbeddings` (cero dependencias, comportamiento de
    siempre)."""
    if settings.embeddings_provider is EmbeddingsProvider.FAKE:
        return FakeEmbeddings(dimensions=settings.rag_embedding_dimensions)
    # `Settings._apply_llm_defaults_and_validate` ya garantizó valores
    # reales para OLLAMA antes de que la app pueda arrancar.
    assert settings.embeddings_base_url is not None and settings.embeddings_model is not None
    return OpenAICompatEmbeddings(
        base_url=settings.embeddings_base_url,
        api_key=settings.embeddings_api_key,
        model=settings.embeddings_model,
        provider_name=settings.embeddings_provider.value,
        timeout_seconds=settings.embeddings_request_timeout_seconds,
    )


app = create_app()
