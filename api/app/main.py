"""Punto de entrada FastAPI — monolito modular (architecture.md §5.2).

`create_app()` es una factory pura (sin estado de módulo compartido) para
que los tests puedan construir instancias aisladas con su propia
`DATABASE_PATH`. `app` al final del archivo es el objeto que usa
`uvicorn app.main:app`."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.adapters.fake_embeddings import FakeEmbeddings
from app.adapters.fake_llm import FakeLLM
from app.adapters.fixture_cases import FixtureCaseAdapter
from app.api.routes import cases, health, knowledge, sessions, ws
from app.core.config import LLMProvider, get_settings
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.orchestrator.call_cycle import CallCycleOrchestrator
from app.ports.llm import LLMPort
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
    app.state.case_port = FixtureCaseAdapter()
    app.state.session_repo = SessionRepository(settings.database_path)
    app.state.turn_repo = TurnRepository(settings.database_path)
    app.state.event_repo = EventRepository(settings.database_path)

    # RAG (Sprint C2, Epic RAG). El adapter de embeddings real llega detrás
    # del mismo `EmbeddingsPort` en T0 (RAG-004) — hoy siempre es
    # `FakeEmbeddings`, sin condicionar por `LLM_PROVIDER` (son puertos
    # independientes; no existe todavía un `EMBEDDINGS_PROVIDER`).
    app.state.document_repo = DocumentRepository(settings.database_path)
    app.state.embeddings_cache = EmbeddingsCache(
        FakeEmbeddings(dimensions=settings.rag_embedding_dimensions)
    )
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

    app.state.llm = _build_llm_adapter(settings.llm_provider, model=settings.llm_model)
    app.state.call_cycle_orchestrator = CallCycleOrchestrator(
        database_path=settings.database_path,
        llm=app.state.llm,
        embeddings=app.state.embeddings_cache,
        evidence_score_threshold=settings.rag_evidence_score_threshold,
        candidate_pool_size=settings.rag_candidate_pool_size,
        retrieval_top_k=settings.rag_retrieval_top_k,
    )

    app.add_middleware(CorrelationIdMiddleware, event_repo=app.state.event_repo)

    app.include_router(health.router)
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(ws.router)

    logger.info(
        "care_companion_app_ready env=%s db=%s llm_provider=%s",
        settings.app_env,
        settings.database_path,
        settings.llm_provider.value,
    )
    return app


def _build_llm_adapter(provider: LLMProvider, *, model: str) -> LLMPort:
    """Único punto de construcción del `LLMPort` real usado por los
    agentes (ADR-001/ADR-005): el dominio nunca importa un SDK de
    proveedor, solo este adapter concreto. `openai_compat` (el modelo
    obligatorio del 7 de agosto) todavía no tiene adapter — se falla rápido
    y explícito en el arranque en vez de degradar silenciosamente a un
    fake, para no fingir que el modelo obligatorio está conectado cuando no
    lo está (spec.md §11.2, "no defaults inseguros")."""
    if provider is LLMProvider.FAKE:
        return FakeLLM(model=model)
    raise RuntimeError(
        f"LLM_PROVIDER={provider.value!r} todavía no tiene adapter implementado "
        "(pendiente del modelo obligatorio del 7 de agosto, ADR-005/ADR-008); "
        "usa LLM_PROVIDER=fake mientras tanto."
    )


app = create_app()
