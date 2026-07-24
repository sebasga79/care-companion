"""Punto de entrada FastAPI — monolito modular (architecture.md §5.2).

`create_app()` es una factory pura (sin estado de módulo compartido) para
que los tests puedan construir instancias aisladas con su propia
`DATABASE_PATH`. `app` al final del archivo es el objeto que usa
`uvicorn app.main:app`."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.adapters.fixture_cases import FixtureCaseAdapter
from app.api.routes import cases, health, sessions
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.repositories.db import apply_schema, get_connection
from app.repositories.events import EventRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository

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

    app.add_middleware(CorrelationIdMiddleware, event_repo=app.state.event_repo)

    app.include_router(health.router)
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")

    logger.info(
        "care_companion_app_ready env=%s db=%s llm_provider=%s",
        settings.app_env,
        settings.database_path,
        settings.llm_provider.value,
    )
    return app


app = create_app()
