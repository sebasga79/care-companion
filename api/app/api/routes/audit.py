"""Lecturas de auditoría y métricas (UX-005 / PERF).

`GET /api/v1/audit/sessions` — timeline de sesiones para la vista `/audit`.
`GET /api/v1/audit/sessions/{id}/trace` — traza de una sesión.
`GET /api/v1/metrics` — snapshot honesto de métricas (pendiente donde no se
instrumentó todavía).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_audit_repo
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
) -> dict[str, Any]:
    latency = audit_repo.latency_percentiles()
    measured = latency["sample_size"] > 0

    def metric(value: float | None, unit: str) -> dict[str, Any]:
        if value is None:
            return {"status": "pendiente", "value": "—", "detail": "Sin muestras instrumentadas"}
        return {
            "status": "medido",
            "value": f"{value:.0f} {unit}",
            "detail": f"n={latency['sample_size']}",
        }

    return {
        "latency_p50": metric(latency["p50"], "ms"),
        "latency_p95": metric(latency["p95"], "ms"),
        # Costo/tokens dependen del modelo obligatorio (T0) — honestos como
        # pendientes hasta COST-001 con el proveedor real.
        "tokens": {"status": "pendiente", "value": "—", "detail": "Depende del modelo de T0"},
        "cost": {"status": "pendiente", "value": "—", "detail": "Depende del modelo de T0"},
        "measured": measured,
    }
