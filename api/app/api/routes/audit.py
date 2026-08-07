"""Lecturas de auditoría y métricas (UX-005 / PERF).

`GET /api/v1/audit/sessions` — timeline de sesiones para la vista `/audit`.
`GET /api/v1/audit/sessions/{id}/trace` — traza de una sesión.
`GET /api/v1/metrics` — snapshot honesto de métricas (pendiente donde no se
instrumentó todavía).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_audit_repo, get_settings_dep
from app.core.config import Settings
from app.repositories.audit import AuditRepository

router = APIRouter(tags=["audit"])


@router.get("/audit/sessions")
async def list_audit_sessions(
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> dict[str, Any]:
    return {"sessions": audit_repo.list_sessions()}


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
    usage = audit_repo.usage_summary()
    measured_latency = latency["sample_size"] > 0
    measured_usage = usage["sample_size"] > 0

    def latency_metric(value: float | None, unit: str) -> dict[str, Any]:
        if value is None:
            return {"status": "pendiente", "value": "—", "detail": "Sin muestras instrumentadas"}
        return {
            "status": "medido",
            "value": f"{value:.0f} {unit}",
            "detail": f"n={latency['sample_size']}",
        }

    return {
        "latency_p50": latency_metric(latency["p50"], "ms"),
        "latency_p95": latency_metric(latency["p95"], "ms"),
        "tokens": _tokens_metric(usage, measured_usage),
        "cost": _cost_metric(usage, measured_usage, settings),
        "measured": measured_latency and measured_usage,
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
            "detail": "Sin llamadas al modelo instrumentadas (LLM_PROVIDER=fake o sin sesiones)",
        }
    turns = max(usage["turn_count"], 1)
    calls = max(usage["session_count"], 1)
    return {
        "status": "medido",
        "value": (
            f"in={usage['input_tokens_total']} out={usage['output_tokens_total']} tokens "
            f"totales"
        ),
        "detail": (
            f"por turno: in={usage['input_tokens_total'] / turns:.0f} "
            f"out={usage['output_tokens_total'] / turns:.0f}, "
            f"{usage['llm_calls_total'] / turns:.1f} invocaciones LLM/turno, "
            f"{usage['rag_queries_total'] / calls:.1f} consultas RAG/llamada "
            f"(n={usage['sample_size']} invocaciones, {usage['session_count']} llamadas)"
        ),
    }


def _cost_metric(usage: dict[str, Any], measured: bool, settings: Settings) -> dict[str, Any]:
    """Rúbrica §5: costo estimado por llamada; si corre local, extrapolar a
    precios de producción con el cálculo explicado. Sin precio configurado
    (`LLM_COST_PER_MILLION_*_TOKENS`) se reporta "pendiente" — un número
    fabricado es peor que uno ausente (rúbrica §5, in extenso)."""
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
            "value": "—",
            "detail": (
                f"Tokens medidos (in={usage['input_tokens_total']} "
                f"out={usage['output_tokens_total']}) pero sin precio configurado — fijar "
                "LLM_COST_PER_MILLION_INPUT_TOKENS/LLM_COST_PER_MILLION_OUTPUT_TOKENS"
            ),
        }
    calls = max(usage["session_count"], 1)
    total_cost = (
        usage["input_tokens_total"] / 1_000_000 * price_in
        + usage["output_tokens_total"] / 1_000_000 * price_out
    )
    return {
        "status": "medido",
        "value": f"${total_cost / calls:.4f} USD/llamada",
        "detail": (
            f"({usage['input_tokens_total']} in + {usage['output_tokens_total']} out tokens) "
            f"× (${price_in}/1M in, ${price_out}/1M out) ÷ {calls} llamadas"
        ),
    }
