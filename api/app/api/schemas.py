"""Modelos REST específicos de request/response (API-001).

Los contratos de dominio (CallSummary, CaseSummary, etc.) viven en
`domain/`/`ports/` y se reutilizan directamente como `response_model`
donde aplica; aquí solo lo que es puramente de transporte HTTP."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


# -- Conocimiento / RAG (RAG-010) --------------------------------------


class DocumentResponse(BaseModel):
    id: str
    filename: str
    checksum: str
    status: str
    mime: str
    size_bytes: int
    applicability: dict[str, Any] = Field(default_factory=dict)
    knowledge_version_added: int
    knowledge_version_deleted: int | None = None
    error_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    knowledge_version: int


class DocumentUploadResponse(BaseModel):
    document: DocumentResponse
    knowledge_version: int
    chunk_count: int


class DocumentDeleteResponse(BaseModel):
    document: DocumentResponse
    knowledge_version: int
    purged_chunk_count: int


class CanaryStatus(BaseModel):
    query: str
    found: bool
    checked_at: datetime


class DocumentDetailResponse(BaseModel):
    document: DocumentResponse
    canary: CanaryStatus | None = None


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    document_version: int
    section: str | None
    page: int | None
    text: str
    lexical_rank: int | None
    lexical_score: float | None
    semantic_rank: int | None
    semantic_score: float | None
    rrf_score: float


class SearchResponse(BaseModel):
    query: str
    knowledge_version: int
    results: list[SearchResultItem]
