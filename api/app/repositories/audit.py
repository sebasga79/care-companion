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

    def usage_summary(self) -> dict[str, Any]:
        """Agrega tokens/invocaciones LLM/consultas RAG desde `events`
        (rúbrica §5: "tokens de entrada y salida por turno y por llamada,
        invocaciones al modelo por turno, consultas al RAG por llamada").

        Cada `agent.*.completed` ya trae `usage.model_dump()` como payload
        (`app/orchestrator/call_cycle.py`), incluido `provider` — clave para
        `by_provider` (ver abajo). Cada `rag.retrieval.completed` se loguea
        una vez por turno. Ninguna cifra se inventa: si no hay eventos
        instrumentados todavía (p. ej. `LLM_PROVIDER=fake` recién arrancado
        sin sesiones), se devuelve `sample_size=0` y el caller reporta
        "pendiente" — mismo patrón que `latency_percentiles`.

        `by_provider`: desglose de tokens por proveedor real de cada
        llamada (`groq`, `ollama`, ...). Existe porque `FallbackLLM` puede
        degradar una llamada individual al resguardo local sin que la
        sesión se entere — un caso real, no hipotético: durante la corrida
        de benchmark del 9 de agosto, la cuota diaria de Groq se agotó a
        mitad de una conversación y 3 de 36 invocaciones cayeron a Ollama
        (gratis). Sin este desglose, `_cost_metric` habría cobrado precio
        de Groq por tokens que en realidad sirvió gratis el modelo local —
        exactamente el tipo de número que "no se sostiene" que la rúbrica
        penaliza. `input_tokens_total`/`output_tokens_total` siguen siendo
        el total real (incluye resguardo) para las cifras de consumo; sólo
        el costo debe mirar `by_provider`."""
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
                "by_provider": {},
            }

        input_tokens_total = 0
        output_tokens_total = 0
        by_provider: dict[str, dict[str, int]] = {}
        for row in llm_rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            tokens_in = int(payload.get("input_tokens", 0))
            tokens_out = int(payload.get("output_tokens", 0))
            input_tokens_total += tokens_in
            output_tokens_total += tokens_out
            provider = str(payload.get("provider") or "desconocido")
            bucket = by_provider.setdefault(provider, {"input_tokens": 0, "output_tokens": 0})
            bucket["input_tokens"] += tokens_in
            bucket["output_tokens"] += tokens_out

        return {
            "sample_size": len(llm_rows),
            "input_tokens_total": input_tokens_total,
            "output_tokens_total": output_tokens_total,
            "llm_calls_total": len(llm_rows),
            "rag_queries_total": rag_call_count,
            "turn_count": turn_count,
            "session_count": session_count,
            "by_provider": by_provider,
        }
