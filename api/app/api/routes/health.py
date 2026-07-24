"""`GET /health` — versión + estado de la base de datos (API-001)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.api.schemas import HealthResponse
from app.repositories.db import get_connection

logger = logging.getLogger("care_companion.health")

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    db_status = "ok"
    try:
        conn = get_connection(settings.database_path)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception:
        # El health check reporta honestamente "error"; nunca finge éxito.
        logger.exception("health_db_check_failed")
        db_status = "error"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=request.app.version,
        db=db_status,
    )
