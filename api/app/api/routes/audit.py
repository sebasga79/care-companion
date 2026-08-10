"""Lecturas de auditoría y métricas (UX-005 / PERF).

`GET /api/v1/audit/sessions` — timeline de sesiones para la vista `/audit`.
`GET /api/v1/audit/sessions/{id}/trace` — traza de una sesión.
`GET /api/v1/metrics` — snapshot honesto de métricas (pendiente donde no se
instrumentó todavía).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_audit_repo, get_case_port, get_settings_dep
from app.core.config import Settings
from app.ports.challenge_case import ChallengeCasePort
from app.repositories.audit import AuditRepository

router = APIRouter(tags=["audit"])


@router.get("/audit/sessions")
async def list_audit_sessions(
    audit_repo: AuditRepository = Depends(get_audit_repo),
    case_port: ChallengeCasePort = Depends(get_case_port),
) -> dict[str, Any]:
    rows = audit_repo.list_sessions()
    for row in rows:
        case = await case_port.get_case(row["case_id"])
        row["patient_display_name"] = case.patient_display_name if case else None
        row["procedure"] = case.procedure if case else None
        row["surgery_date"] = case.surgery_date.isoformat() if case and case.surgery_date else None
    return {"sessions": rows}


@router.get("/audit/sessions/{session_id}/trace")
async def get_audit_trace(
    session_id: str,
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> dict[str, Any]:
    trace = audit_repo.get_trace(session_id)
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión no encontrada")
    return trace


@router.get("/metrics")
async def get_metrics(
    audit_repo: AuditRepository = Depends(get_audit_repo),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:
    latency = audit_repo.latency_percentiles()
    voice_latency = audit_repo.voice_latency_percentiles()
    usage = audit_repo.usage_summary(
        provider_filter=settings.llm_provider.value,
        model_filter=settings.llm_model,
    )
    measured_latency = latency["sample_size"] > 0
    measured_usage = usage["sample_size"] > 0

    def latency_metric(value: float | None, unit: str, *, sample_size: int) -> dict[str, Any]:
        if value is None:
            return {"status": "pendiente", "value": "—", "detail": "Sin muestras instrumentadas"}
        return {
            "status": "medido",
            "value": f"{value:.0f} {unit}",
            "detail": f"n={sample_size}",
        }

    return {
        "latency_p50": latency_metric(latency["p50"], "ms", sample_size=latency["sample_size"]),
        "latency_p95": latency_metric(latency["p95"], "ms", sample_size=latency["sample_size"]),
        "latency_voice": _voice_latency_metric(voice_latency),
        "tokens": _tokens_metric(usage, measured_usage),
        "cost": _cost_metric(usage, measured_usage, settings),
        "measured": measured_latency and measured_usage,
    }


def _voice_latency_metric(voice_latency: dict[str, Any]) -> dict[str, Any]:
    """Rúbrica §5, definición literal (ver `AuditRepository.voice_latency_percentiles`):
    medida real en el navegador, alimentada por
    `POST /sessions/{id}/voice-latency` — distinta del proxy de servidor en
    `latency_p50`/`latency_p95`."""
    if voice_latency["sample_size"] == 0:
        return {
            "status": "pendiente",
            "value": "—",
            "detail": "Requiere una llamada real con micrófono — STT/TTS son del navegador",
        }
    return {
        "status": "medido",
        "value": f"{voice_latency['p50']:.0f} ms P50",
        "detail": (
            f"P95 {voice_latency['p95']:.0f} ms · n={voice_latency['sample_size']} · "
            "fin de habla del paciente → inicio de audio del agente"
        ),
    }


def _tokens_metric(usage: dict[str, Any], measured: bool) -> dict[str, Any]:
    """Rúbrica §5: tokens de entrada/salida por turno y por llamada,
    invocaciones al modelo por turno, consultas al RAG por llamada. Todas
    las cifras vienen de `AuditRepository.usage_summary()`, que lee
    `events` reales — nunca se fabrica un número aquí."""
    if not measured:
        return {
            "status": "pendiente",
            "value": "—",
            "detail": "Sin llamadas cerradas con uso de un modelo real instrumentado",
        }
    turns = max(usage["turn_count"], 1)
    calls = max(usage["session_count"], 1)
    total = usage["input_tokens_total"] + usage["output_tokens_total"]
    input_per_turn = usage["input_tokens_total"] / turns
    output_per_turn = usage["output_tokens_total"] / turns
    input_per_call = usage["input_tokens_total"] / calls
    output_per_call = usage["output_tokens_total"] / calls
    return {
        "status": "medido",
        "value": f"{total:,} tokens",
        "detail": (
            f"{usage['input_tokens_total']:,} entrada · {usage['output_tokens_total']:,} salida · "
            f"{input_per_turn:.1f}/{output_per_turn:.1f} tokens entrada/salida por turno · "
            f"{input_per_call:.1f}/{output_per_call:.1f} por llamada · "
            f"{usage['llm_calls_total'] / turns:.1f} llamadas LLM/turno · "
            f"{usage['rag_queries_total'] / calls:.1f} consultas RAG/llamada · "
            f"n={calls} llamadas cerradas · hasta {usage['window_ended_at']}"
            f" · {usage['provider_filter']}/{usage['model_filter']}"
        ),
        "scope": {
            "provider": usage["provider_filter"],
            "model": usage["model_filter"],
            "closed_calls": usage["session_count"],
            "patient_turns": usage["turn_count"],
            "llm_calls": usage["llm_calls_total"],
            "rag_queries": usage["rag_queries_total"],
            "input_tokens": usage["input_tokens_total"],
            "output_tokens": usage["output_tokens_total"],
            "excluded_other_model_tokens": usage["excluded_tokens_total"],
            "window_started_at": usage["window_started_at"],
            "window_ended_at": usage["window_ended_at"],
        },
    }


def _cost_metric(usage: dict[str, Any], measured: bool, settings: Settings) -> dict[str, Any]:
    """Rúbrica §5: costo estimado por llamada; si corre local, extrapolar a
    precios de producción con el cálculo explicado. Sin precio configurado
    (`LLM_COST_PER_MILLION_*_TOKENS`) se reporta "pendiente" — un número
    fabricado es peor que uno ausente (rúbrica §5, in extenso).

    Usa sólo `usage["by_provider"][settings.llm_provider]` — NO el total
    combinado. Hallazgo real (auditoría §9.34): cuando `FallbackLLM`
    degrada una llamada individual al resguardo local (cuota agotada, 429,
    etc.), esos tokens los sirvió gratis un modelo distinto al configurado
    — cobrarlos al precio del proveedor primario sobreestima el costo real
    y es exactamente el tipo de número que "no se sostiene" frente a los
    logs que la rúbrica penaliza."""
    if not measured:
        return {
            "status": "pendiente",
            "value": "—",
            "detail": "Sin llamadas al modelo instrumentadas",
        }
    price_in = settings.llm_cost_per_million_input_tokens
    price_out = settings.llm_cost_per_million_output_tokens
    if price_in is None or price_out is None:
        return {
            "status": "pendiente",
            "value": "No configurado",
            "detail": ("Hay tokens medidos; faltan las tarifas de entrada y salida del modelo."),
        }
    primary_bucket = usage["by_provider"].get(
        settings.llm_provider.value, {"input_tokens": 0, "output_tokens": 0}
    )
    primary_in = primary_bucket["input_tokens"]
    primary_out = primary_bucket["output_tokens"]
    calls = max(primary_bucket.get("session_count", 0), 1)
    total_cost = primary_in / 1_000_000 * price_in + primary_out / 1_000_000 * price_out
    excluded_tokens = usage.get("excluded_tokens_total", 0)
    fallback_note = (
        f" ({excluded_tokens} tokens de otros modelos/resguardo excluidos)"
        if excluded_tokens > 0
        else ""
    )
    return {
        "status": "medido",
        "value": f"${total_cost / calls:.4f} USD/llamada",
        "detail": (
            f"({primary_in} in + {primary_out} out tokens de {settings.llm_provider.value}) "
            f"× (${price_in}/1M in, ${price_out}/1M out) ÷ {calls} llamadas cerradas "
            f"del proveedor · modelos={','.join(primary_bucket.get('models', []))}"
            f"{fallback_note}"
        ),
    }
