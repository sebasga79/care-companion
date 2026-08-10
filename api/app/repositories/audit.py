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

from app.domain.clinical_values import (
    normalize_appetite,
    normalize_mobility,
    normalize_sleep,
    normalize_wound,
    parse_pain_nrs,
    parse_temperature_c,
)
from app.repositories.db import session_scope

_LLM_CALL_EVENT_TYPES = (
    "agent.interview.completed",
    "agent.triage.completed",
    "agent.response.completed",
)
_REAL_LLM_PROVIDERS = frozenset({"groq", "ollama"})


def _percentile_stats(values: list[float]) -> dict[str, float | None]:
    """P50/P95 por percentil-por-rango (nearest-rank), compartido entre
    `latency_percentiles()` (proxy de servidor) y `voice_latency_percentiles()`
    (medición real del navegador) — misma fórmula, distinta fuente de
    `event_type`. Devuelve `None`/`sample_size=0` sin muestras: el llamador
    reporta "pendiente", nunca inventa un número."""
    if not values:
        return {"p50": None, "p95": None, "sample_size": 0}
    values = sorted(values)

    def pct(p: float) -> float:
        k = max(0, min(len(values) - 1, int(round(p * (len(values) - 1)))))
        return values[k]

    return {"p50": pct(0.50), "p95": pct(0.95), "sample_size": len(values)}


def _normalize_followup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Proyecta registros v1.1 existentes al vocabulario clínico actual.

    No altera la evidencia original; solo corrige el valor mostrado en la
    vista de auditoría usando el ``original_text`` conservado en cada campo.
    Las llamadas nuevas ya se persisten normalizadas por ``summary.py``.
    """
    normalizers = {
        "dolor_nrs": lambda value, text: parse_pain_nrs(value, text),
        "fiebre_c": lambda value, text: parse_temperature_c(value, text),
        "movilidad": lambda _value, text: normalize_mobility(text),
        "herida": lambda _value, text: normalize_wound(text),
        "apetito": lambda _value, text: normalize_appetite(text),
        "sueno": lambda _value, text: normalize_sleep(text),
    }
    for key, normalizer in normalizers.items():
        field = payload.get(key)
        if not isinstance(field, dict):
            continue
        normalized = normalizer(field.get("value"), field.get("original_text", ""))
        if normalized is None:
            payload[key] = None
        else:
            field["value"] = normalized
    return payload


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
            sessions = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()

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
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
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
            contact_rows = conn.execute(
                """
                SELECT code, label, value, created_at
                FROM observations
                WHERE session_id = ?
                  AND code IN ('CONTACT_PRIMARY', 'CONTACT_EMERGENCY')
                  AND certainty = 'confirmed'
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            contacts = []
            for row in contact_rows:
                record = dict(row)
                try:
                    record["value"] = json.loads(record["value"])
                except (json.JSONDecodeError, TypeError):
                    pass
                contacts.append(record)

            followup_row = conn.execute(
                "SELECT payload FROM followup_records WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            followup_record = None
            if followup_row is not None:
                try:
                    followup_record = _normalize_followup_payload(
                        json.loads(followup_row["payload"])
                    )
                except (json.JSONDecodeError, TypeError):
                    followup_record = None

            return {
                "session_id": session_id,
                "state": session["state"],
                "knowledge_version": session["knowledge_version"],
                "events": [dict(e) for e in events],
                "decisions": [dict(d) for d in decisions],
                "escalations": [dict(e) for e in escalations],
                "contacts": contacts,
                "followup_record": followup_record,
            }

    def latency_percentiles(self) -> dict[str, float | None]:
        """P50/P95 de la latencia conversacional real (rúbrica §5: "desde
        que el paciente termina de hablar hasta que empieza a sonar el
        audio del agente"), NO de cualquier request HTTP.

        Filtra estrictamente a `event_type = 'turn.response_sent'`
        (instrumentado en `app/api/routes/ws.py`, un evento por turno de
        `/ws/sessions/{id}`) — antes de esta corrección se agregaba
        `latency_ms` de CUALQUIER evento, lo que mezclaba HTTP
        administrativo (subir un documento, listar `/audit/sessions`) con
        latencia conversacional real y habría producido un P50/P95
        engañoso frente a los logs de la sesión de evaluación (spec.md §11,
        docs/auditoria-kit-oficial-2026-08-07.md §9).

        Devuelve None si no hay muestras — el llamador reporta 'pendiente'."""
        with session_scope(self._database_path) as conn:
            values = [
                r["latency_ms"]
                for r in conn.execute(
                    "SELECT latency_ms FROM events "
                    "WHERE event_type = 'turn.response_sent' AND latency_ms IS NOT NULL"
                ).fetchall()
            ]
        return _percentile_stats(values)

    def voice_latency_percentiles(self) -> dict[str, float | None]:
        """P50/P95 de la latencia voz-a-voz **real**, medida en el
        navegador (rúbrica §5, definición literal: "desde que el paciente
        termina de hablar hasta que empieza a sonar el audio del agente").

        A diferencia de `latency_percentiles()` (proxy del lado del
        servidor: desde que llega `client.turn_text` hasta que se envía la
        respuesta, sin tránsito de red ni arranque real del motor de TTS),
        ésta es la medición completa de punta a punta. STT y TTS corren
        enteramente en el navegador (Web Speech API) — no hay forma de
        producirla desde el servidor ni desde un script. Se alimenta de
        `POST /sessions/{id}/voice-latency`, que `CallModal.tsx` llama
        automáticamente después de cada turno hablado.

        Devuelve None si no hay muestras — el llamador reporta 'pendiente'
        hasta que exista al menos una llamada real con micrófono."""
        with session_scope(self._database_path) as conn:
            values = [
                r["latency_ms"]
                for r in conn.execute(
                    "SELECT latency_ms FROM events "
                    "WHERE event_type = 'client.voice_latency_reported' "
                    "AND latency_ms IS NOT NULL"
                ).fetchall()
            ]
        return _percentile_stats(values)

    def usage_summary(
        self, *, provider_filter: str | None = None, model_filter: str | None = None
    ) -> dict[str, Any]:
        """Agrega tokens/invocaciones LLM/consultas RAG desde `events`
        (rúbrica §5: "tokens de entrada y salida por turno y por llamada,
        invocaciones al modelo por turno, consultas al RAG por llamada").

        El universo es deliberadamente estricto: sesiones cerradas que
        contienen al menos una invocación de un proveedor real permitido.
        Sesiones abiertas, pruebas antiguas y eventos sin proveedor/modelo
        verificable no entran en tokens, RAG ni denominadores por llamada.

        Cuando se indican filtros, tokens e invocaciones corresponden
        exclusivamente al proveedor/modelo configurado. El total excluido
        se conserva por separado para hacer visible cualquier degradación
        real a otro modelo sin mezclar universos ni precios."""
        placeholders = ",".join("?" for _ in _LLM_CALL_EVENT_TYPES)
        with session_scope(self._database_path) as conn:
            llm_rows = conn.execute(
                f"""SELECT e.session_id, e.payload, s.created_at, s.closed_at
                FROM events e
                JOIN sessions s ON s.id = e.session_id
                WHERE e.event_type IN ({placeholders})
                  AND s.state = 'closed'
                  AND s.closed_at IS NOT NULL""",  # noqa: S608
                _LLM_CALL_EVENT_TYPES,
            ).fetchall()

            all_real_rows: list[tuple[Any, dict[str, Any]]] = []
            real_rows: list[tuple[Any, dict[str, Any]]] = []
            eligible_session_ids: set[str] = set()
            for row in llm_rows:
                try:
                    payload = json.loads(row["payload"]) if row["payload"] else {}
                except (json.JSONDecodeError, TypeError):
                    continue
                provider = str(payload.get("provider") or "")
                model = str(payload.get("model") or "")
                if provider not in _REAL_LLM_PROVIDERS or not model:
                    continue
                all_real_rows.append((row, payload))
                if provider_filter is not None and provider != provider_filter:
                    continue
                if model_filter is not None and model != model_filter:
                    continue
                real_rows.append((row, payload))
                eligible_session_ids.add(row["session_id"])

            if eligible_session_ids:
                session_placeholders = ",".join("?" for _ in eligible_session_ids)
                session_params = tuple(sorted(eligible_session_ids))
                rag_call_count = conn.execute(
                    f"""SELECT COUNT(*) AS n FROM events
                    WHERE event_type = 'rag.retrieval.completed'
                      AND session_id IN ({session_placeholders})""",  # noqa: S608
                    session_params,
                ).fetchone()["n"]
                turn_count = conn.execute(
                    f"""SELECT COUNT(*) AS n FROM turns
                    WHERE speaker = 'patient'
                      AND session_id IN ({session_placeholders})""",  # noqa: S608
                    session_params,
                ).fetchone()["n"]
            else:
                rag_call_count = 0
                turn_count = 0

        if not real_rows:
            return {
                "sample_size": 0,
                "input_tokens_total": 0,
                "output_tokens_total": 0,
                "llm_calls_total": 0,
                "rag_queries_total": 0,
                "turn_count": turn_count,
                "session_count": 0,
                "by_provider": {},
                "window_started_at": None,
                "window_ended_at": None,
                "provider_filter": provider_filter,
                "model_filter": model_filter,
                "excluded_tokens_total": 0,
            }

        input_tokens_total = 0
        output_tokens_total = 0
        by_provider_work: dict[str, dict[str, Any]] = {}
        for row, payload in real_rows:
            tokens_in = int(payload.get("input_tokens", 0))
            tokens_out = int(payload.get("output_tokens", 0))
            input_tokens_total += tokens_in
            output_tokens_total += tokens_out
            provider = str(payload["provider"])
            model = str(payload["model"])
            bucket = by_provider_work.setdefault(
                provider,
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "session_ids": set(),
                    "models": set(),
                },
            )
            bucket["input_tokens"] += tokens_in
            bucket["output_tokens"] += tokens_out
            bucket["session_ids"].add(row["session_id"])
            bucket["models"].add(model)

        by_provider = {
            provider: {
                "input_tokens": bucket["input_tokens"],
                "output_tokens": bucket["output_tokens"],
                "session_count": len(bucket["session_ids"]),
                "models": sorted(bucket["models"]),
            }
            for provider, bucket in by_provider_work.items()
        }
        closed_rows = {row["session_id"]: row for row, _payload in real_rows}
        excluded_tokens_total = sum(
            int(payload.get("input_tokens", 0)) + int(payload.get("output_tokens", 0))
            for row, payload in all_real_rows
            if row["session_id"] in eligible_session_ids
            and (
                (provider_filter is not None and payload.get("provider") != provider_filter)
                or (model_filter is not None and payload.get("model") != model_filter)
            )
        )

        return {
            "sample_size": len(real_rows),
            "input_tokens_total": input_tokens_total,
            "output_tokens_total": output_tokens_total,
            "llm_calls_total": len(real_rows),
            "rag_queries_total": rag_call_count,
            "turn_count": turn_count,
            "session_count": len(eligible_session_ids),
            "by_provider": by_provider,
            "window_started_at": min(row["created_at"] for row in closed_rows.values()),
            "window_ended_at": max(row["closed_at"] for row in closed_rows.values()),
            "provider_filter": provider_filter,
            "model_filter": model_filter,
            "excluded_tokens_total": excluded_tokens_total,
        }
