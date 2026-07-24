"""Logging estructurado (OBS-001).

Cada línea de log lleva `correlation_id` inyectado vía filtro, sin requerir
que cada call site lo pase explícitamente. No se registra chain-of-thought
ni payloads clínicos completos por defecto (spec.md §11.2)."""

from __future__ import annotations

import logging
import sys

from app.core.correlation_id import get_correlation_id

_LOG_FORMAT = (
    '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
    '"correlation_id":"%(correlation_id)s","message":"%(message)s"}'
)


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT))
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
