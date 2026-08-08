"""`CorrelationIdMiddleware` — correlation_id + timings estructurados por
request (OBS-001).

Toma `X-Correlation-ID` del request si viene, o genera uno nuevo. Lo
propaga vía contextvar (para que repositorios/handlers lo lean sin pasarlo
explícitamente), lo devuelve en la respuesta, loguea method/path/status/
duración, y persiste un evento en `events`. La persistencia del evento es
telemetría no clínica: si falla, se loguea pero NUNCA se deja que tumbe el
request (architecture.md §13.1, fail-open) — nunca un `except: pass`
silencioso, siempre queda rastro en el log."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.correlation_id import get_correlation_id, new_correlation_id, set_correlation_id
from app.repositories.events import EventRepository

logger = logging.getLogger("care_companion.http")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, event_repo: EventRepository) -> None:
        super().__init__(app)
        self._event_repo = event_repo

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
        set_correlation_id(correlation_id)

        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status_code = response.status_code if response is not None else 500

            logger.info(
                "http_request method=%s path=%s status=%s duration_ms=%.2f correlation_id=%s",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                get_correlation_id(),
            )

            if response is not None:
                response.headers["X-Correlation-ID"] = correlation_id

            try:
                self._event_repo.add_event(
                    correlation_id=correlation_id,
                    component="http",
                    event_type="request.completed",
                    payload={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                    },
                    latency_ms=duration_ms,
                )
            except Exception:
                # Fail-open intencional: telemetría no clínica. Se deja
                # constancia en el log; nunca se oculta en silencio.
                logger.exception("failed_to_persist_http_event correlation_id=%s", correlation_id)
