"""Correlation id por request/turno (OBS-001).

Usa un `ContextVar` para que cualquier código (repositorios, agentes,
middleware) pueda leer el correlation_id activo sin pasarlo explícitamente
por cada función, sin perder aislamiento entre requests concurrentes
(cada request de asyncio tiene su propio contexto)."""

from __future__ import annotations

import contextvars
import uuid

_correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def get_correlation_id() -> str | None:
    return _correlation_id_ctx.get()


def set_correlation_id(value: str) -> None:
    _correlation_id_ctx.set(value)
