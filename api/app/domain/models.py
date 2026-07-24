"""Contratos base de agente (architecture.md §6.2).

Puro Pydantic, sin dependencias de proveedor. Todo agente (aún no
implementado en esta fase — llega en C2) deberá aceptar `AgentRequest` y
devolver `AgentResult`."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UsageMetrics(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    provider: str = "fake"
    model: str = "fake-model-v1"


class CitationRef(BaseModel):
    """spec.md §8.2 — una cita debe señalar documento, versión y ubicación."""

    citation_id: str
    document_id: str
    document_version: int
    chunk_id: str
    title: str
    section: str | None = None
    page: int | None = None
    knowledge_version: int


class AgentRequest(BaseModel):
    session_id: UUID
    correlation_id: UUID
    knowledge_version: int
    payload: dict[str, Any] = Field(default_factory=dict)
    deadline_ms: int = 5000


class AgentResult(BaseModel):
    status: Literal["ok", "abstain", "error"]
    output: dict[str, Any] = Field(default_factory=dict)
    evidence: list[CitationRef] = Field(default_factory=list)
    confidence: float | None = None
    usage: UsageMetrics
    warnings: list[str] = Field(default_factory=list)
