"""Modelos REST específicos de request/response (API-001).

Los contratos de dominio (CallSummary, CaseSummary, etc.) viven en
`domain/`/`ports/` y se reutilizan directamente como `response_model`
donde aplica; aquí solo lo que es puramente de transporte HTTP."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str


class SessionCreateRequest(BaseModel):
    case_id: str


class SessionResponse(BaseModel):
    id: str
    case_id: str
    state: str
    knowledge_version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
