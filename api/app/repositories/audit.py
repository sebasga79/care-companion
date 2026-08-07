"""Lecturas de auditoría (UX-005) — agregan sesiones, decisiones,
escalamientos, citas y eventos para las vistas `/audit` y `/metrics`.

Solo lectura: no muta estado. Toda cifra es trazable a una fila real; cuando
un dato no se ha instrumentado todavía (p. ej. latencia P95 sin PERF-001) el
llamador debe reportarlo como "pendiente", nunca inventarlo.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.repositories.db import session_scope

_LLM_CALL_EVENT_TYPES = (
    "agent.interview.completed",
    "agent.triage.completed",
    "agent.response.completed",
)


def _duration_seconds(created_at: str, closed_at: str | None) -> float | None:
    if not closed_at:
        return None
    try:
        start = datetime.fromisoformat(created_at)
        end = datetime.fromisoformat(closed_at)
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())


class AuditRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def list_sessions(self) -> list[dict[str, Any]]:
        """Una fila por sesión con la última decisión, conteo de citas y
        si tuvo escalamiento. Orden: más reciente primero."""
        with session_scope(self._database_path) as conn:
            sessions = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            ).fetchall()

            rows: list[dict[str, Any]] = []
            for s in sessions:
                sid = s["id"]
                last_decision = conn.execute(
                    """
                    SELECT level, should_escalate FROM decisions
                    WHERE session_id = ? ORDER BY created_at DESC LIMIT 1
                    """,
                    (sid,),
                ).fetchone()
                citation_count = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM citations c
                    JOIN turns t ON t.id = c.turn_id
                    WHERE t.session_id = ?
                    """,
                    (sid,),
                ).fetchone()["n"]
                escalated = conn.execute(
                    "SELECT COUNT(*) AS n FROM escalations WHERE session_id = ?",
                    (sid,),
                ).fetchone()["n"]

                rows.append(
                    {
                        "session_id": sid,
                        "case_id": s["case_id"],
                        "state": s["state"],
                        "knowledge_version": s["knowledge_version"],
                        "started_at": s["created_at"],
                        "closed_at": s["closed_at"],
                        "duration_seconds": _duration_seconds(s["created_at"], s["closed_at"]),
                        "decision_level": last_decision["level"] if last_decision else None,
                        "citation_count": citation_count,
                        "escalated": escalated > 0,
                    }
                )
            return rows

    def get_trace(self, session_id: str) -> dict[str, Any] | None:
        """Timeline de una sesión: eventos instrumentados + decisiones +
        escalamientos, ordenados cronológicamente."""
        with session_scope(self._database_path) as conn:
            session = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                return None

            events = conn.execute(
                """
                SELECT correlation_id, component, event_type, latency_ms, created_at
                FROM events WHERE session_id = ? ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            decisions = conn.execute(
                """
                SELECT level, should_escalate, trigger_codes, rationale, created_at
                FROM decisions WHERE session_id = ? ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            escalations = conn.execute(
                """
                SELECT decision_level, reasons, trigger_codes, created_at
                FROM escalations WHERE session_id = ? ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()

            return {
                "session_id": session_id,
                "state": session["state"],
                "knowledge_version": session["knowledge_version"],
                "events": [dict(e) for e in events],
                "decisions": [dict(d) for d in decisions],
                "escalations": [dict(e) for e in escalations],
            }

    def latency_percentiles(self) -> dict[str, float | None]:
        """P50/P95 de latencia por evento instrumentado. Devuelve None si no
        hay muestras (PERF-001 aún no corrió) — el llamador reporta 'pendiente'."""
        with session_scope(self._database_path) as conn:
            values = [
                r["latency_ms"]
                for r in conn.execute(
                    "SELECT latency_ms FROM events WHERE latency_ms IS NOT NULL"
                ).fetchall()
            ]
        if not values:
            return {"p50": None, "p95": None, "sample_size": 0}
        values.sort()

        def pct(p: float) -> float:
            k = max(0, min(len(values) - 1, int(round(p * (len(values) - 1)))))
            return values[k]

        return {"p50": pct(0.50), "p95": pct(0.95), "sample_size": len(values)}

    def usage_summary(self) -> dict[str, Any]:
        """Agrega tokens/invocaciones LLM/consultas RAG desde `events`
        (rúbrica §5: "tokens de entrada y salida por turno y por llamada,
        invocaciones al modelo por turno, consultas al RAG por llamada").

        Cada `agent.*.completed` ya trae `usage.model_dump()` como payload
        (`app/orchestrator/call_cycle.py`); cada `rag.retrieval.completed`
        se loguea una vez por turno. Ninguna cifra se inventa: si no hay
        eventos instrumentados todavía (p. ej. `LLM_PROVIDER=fake` recién
        arrancado sin sesiones), se devuelve `sample_size=0` y el caller
        reporta "pendiente" — mismo patrón que `latency_percentiles`."""
        placeholders = ",".join("?" for _ in _LLM_CALL_EVENT_TYPES)
        with session_scope(self._database_path) as conn:
            llm_rows = conn.execute(
                f"SELECT payload FROM events WHERE event_type IN ({placeholders})",  # noqa: S608
                _LLM_CALL_EVENT_TYPES,
            ).fetchall()
            rag_call_count = conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE event_type = 'rag.retrieval.completed'"
            ).fetchone()["n"]
            turn_count = conn.execute(
                "SELECT COUNT(*) AS n FROM turns WHERE speaker = 'patient'"
            ).fetchone()["n"]
            session_count = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

        if not llm_rows:
            return {
                "sample_size": 0,
                "input_tokens_total": 0,
                "output_tokens_total": 0,
                "llm_calls_total": 0,
                "rag_queries_total": 0,
                "turn_count": turn_count,
                "session_count": session_count,
            }

        input_tokens_total = 0
        output_tokens_total = 0
        for row in llm_rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            input_tokens_total += int(payload.get("input_tokens", 0))
            output_tokens_total += int(payload.get("output_tokens", 0))

        return {
            "sample_size": len(llm_rows),
            "input_tokens_total": input_tokens_total,
            "output_tokens_total": output_tokens_total,
            "llm_calls_total": len(llm_rows),
            "rag_queries_total": rag_call_count,
            "turn_count": turn_count,
            "session_count": session_count,
        }
