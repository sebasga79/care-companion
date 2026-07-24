"""Repositorio de eventos de traza (OBS-001).

Escritura pensada para ser fail-open desde el punto de vista del llamador
cuando el evento es telemetría no clínica (architecture.md §13.1): quien
use este repositorio para telemetría secundaria debe envolver la llamada
en su propio try/except y solo loguear, nunca dejar que un fallo de
escritura de evento tumbe una ruta clínica. Este repositorio en sí mismo no
oculta errores — deja que la excepción se propague al llamador."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.repositories.db import session_scope


class EventRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def add_event(
        self,
        *,
        correlation_id: str,
        component: str,
        event_type: str,
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
        latency_ms: float | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with session_scope(self._database_path) as conn:
            conn.execute(
                """
                INSERT INTO events
                    (id, session_id, correlation_id, component, event_type,
                     payload, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    correlation_id,
                    component,
                    event_type,
                    json.dumps(payload) if payload is not None else None,
                    latency_ms,
                    now,
                ),
            )
        return event_id

    def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_by_correlation(self, correlation_id: str) -> list[dict[str, Any]]:
        with session_scope(self._database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE correlation_id = ? ORDER BY created_at ASC",
                (correlation_id,),
            ).fetchall()
        return [dict(row) for row in rows]
