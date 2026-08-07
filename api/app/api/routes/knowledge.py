"""`/api/v1/knowledge` — administración del corpus RAG (RAG-010).

Todas las escrituras (`POST`/`DELETE`) delegan en `KnowledgeIngestionService`
(RAG-008/009): esta capa solo traduce excepciones de dominio/servicio a
códigos HTTP explícitos, nunca esconde un fallo detrás de un 200 (health.py
sienta el mismo precedente: "reporta honestamente error, nunca finge
éxito"). El contenido de los documentos subidos es DATO, nunca se trata
como instrucción en esta capa ni en ninguna otra (spec.md §11, BR-015):
aquí solo se validan bytes/tamaño/tipo y se pasa el texto tal cual al
pipeline de fragmentación — no se interpola en ningún prompt."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.api.deps import (
    get_document_repo,
    get_embeddings_cache,
    get_ingestion_service,
    get_settings_dep,
)
from app.api.schemas import (
    CanaryStatus,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    SearchResponse,
    SearchResultItem,
)
from app.core.config import Settings
from app.repositories.db import session_scope
from app.repositories.documents import DocumentRepository
from app.repositories.knowledge import (
    get_current_knowledge_version,
    get_current_knowledge_version_conn,
)
from app.services.embeddings_cache import EmbeddingsCache
from app.services.ingestion import (
    DocumentAlreadyDeletedError,
    DocumentNotFoundError,
    KnowledgeCanaryError,
    KnowledgeIngestionService,
    UploadRejected,
)
from app.services.retrieval import hybrid_search

logger = logging.getLogger("care_companion.knowledge")

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_UPLOAD_REJECTION_STATUS: dict[str, int] = {
    "invalid_filename": status.HTTP_400_BAD_REQUEST,
    "missing_extension": status.HTTP_400_BAD_REQUEST,
    "extension_not_allowed": status.HTTP_400_BAD_REQUEST,
    "empty_file": status.HTTP_400_BAD_REQUEST,
    "empty_after_chunking": status.HTTP_400_BAD_REQUEST,
    "file_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    "mime_mismatch": status.HTTP_400_BAD_REQUEST,
    "duplicate_checksum": status.HTTP_409_CONFLICT,
    "invalid_encoding": status.HTTP_400_BAD_REQUEST,
    "pdf_unreadable": status.HTTP_400_BAD_REQUEST,
    "pdf_encrypted": status.HTTP_400_BAD_REQUEST,
    "pdf_no_text_layer": status.HTTP_400_BAD_REQUEST,
}


def _to_document_response(record: dict[str, Any]) -> DocumentResponse:
    return DocumentResponse(
        id=record["id"],
        filename=record["filename"],
        checksum=record["checksum"],
        status=record["status"],
        mime=record["mime"],
        size_bytes=record["size_bytes"],
        applicability=record["applicability"],
        knowledge_version_added=record["knowledge_version"],
        knowledge_version_deleted=record["knowledge_version_deleted"],
        error_reason=record["error_reason"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        deleted_at=record["deleted_at"],
        deleted_by=record["deleted_by"],
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    document_repo: DocumentRepository = Depends(get_document_repo),
    settings: Settings = Depends(get_settings_dep),
) -> DocumentListResponse:
    records = document_repo.list_all()
    return DocumentListResponse(
        documents=[_to_document_response(r) for r in records],
        knowledge_version=get_current_knowledge_version(settings.database_path),
    )


@router.post(
    "/documents", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    file: UploadFile = File(...),
    applicability: str | None = Form(default=None),
    ingestion_service: KnowledgeIngestionService = Depends(get_ingestion_service),
) -> DocumentUploadResponse:
    parsed_applicability: dict[str, Any] = {}
    if applicability:
        try:
            parsed_applicability = json.loads(applicability)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"`applicability` no es JSON válido: {exc}",
            ) from exc
        if not isinstance(parsed_applicability, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="`applicability` debe ser un objeto JSON",
            )

    content = await file.read()
    try:
        result = await ingestion_service.learn(
            raw_filename=file.filename or "",
            content=content,
            applicability=parsed_applicability,
        )
    except UploadRejected as exc:
        raise HTTPException(
            status_code=_UPLOAD_REJECTION_STATUS.get(
                exc.code, status.HTTP_400_BAD_REQUEST
            ),
            detail={"code": exc.code, "message": exc.reason},
        ) from exc
    except KnowledgeCanaryError as exc:
        logger.exception("knowledge_learn_canary_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No se pudo verificar la carga del documento (consulta canaria falló); "
                "no se persistió ningún cambio. Inténtelo de nuevo."
            ),
        ) from exc

    return DocumentUploadResponse(
        document=_to_document_response(result.document),
        knowledge_version=result.knowledge_version,
        chunk_count=result.chunk_count,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    document_repo: DocumentRepository = Depends(get_document_repo),
    embeddings_cache: EmbeddingsCache = Depends(get_embeddings_cache),
    settings: Settings = Depends(get_settings_dep),
) -> DocumentDetailResponse:
    record = document_repo.get(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    canary: CanaryStatus | None = None
    if record["status"] == "ready":
        with session_scope(settings.database_path) as conn:
            current_version = get_current_knowledge_version_conn(conn)
            chunk_row = conn.execute(
                "SELECT text FROM document_chunks WHERE document_id = ? "
                "ORDER BY chunk_index ASC LIMIT 1",
                (document_id,),
            ).fetchone()
            if chunk_row is not None:
                query = " ".join(chunk_row["text"].split()[:8]) or chunk_row["text"]
                results = await hybrid_search(
                    conn,
                    query,
                    embeddings=embeddings_cache,
                    session_knowledge_version=current_version,
                    top_k=5,
                )
                found = any(r.document_id == document_id for r in results)
                canary = CanaryStatus(
                    query=query, found=found, checked_at=datetime.now(UTC)
                )

    return DocumentDetailResponse(document=_to_document_response(record), canary=canary)


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    ingestion_service: KnowledgeIngestionService = Depends(get_ingestion_service),
) -> DocumentDeleteResponse:
    try:
        result = await ingestion_service.forget(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from exc
    except DocumentAlreadyDeletedError as exc:
        raise HTTPException(
            status_code=409, detail="El documento ya está eliminado"
        ) from exc
    except KnowledgeCanaryError as exc:
        logger.exception("knowledge_forget_canary_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No se pudo verificar el borrado del documento (consulta canaria falló); "
                "se revirtió el borrado. Inténtelo de nuevo."
            ),
        ) from exc

    return DocumentDeleteResponse(
        document=_to_document_response(result.document),
        knowledge_version=result.knowledge_version,
        purged_chunk_count=result.purged_chunk_count,
    )


@router.get("/search", response_model=SearchResponse)
async def search_debug(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=5, ge=1, le=50),
    procedure: str | None = Query(default=None),
    phase: str | None = Query(default=None),
    embeddings_cache: EmbeddingsCache = Depends(get_embeddings_cache),
    settings: Settings = Depends(get_settings_dep),
) -> SearchResponse:
    applicability_filter: dict[str, str] = {}
    if procedure:
        applicability_filter["procedure"] = procedure
    if phase:
        applicability_filter["phase"] = phase

    with session_scope(settings.database_path) as conn:
        current_version = get_current_knowledge_version_conn(conn)
        results = await hybrid_search(
            conn,
            q,
            embeddings=embeddings_cache,
            session_knowledge_version=current_version,
            applicability_filter=applicability_filter or None,
            top_k=top_k,
            rrf_k=settings.rag_rrf_k,
            candidate_pool_size=settings.rag_candidate_pool_size,
        )

    return SearchResponse(
        query=q,
        knowledge_version=current_version,
        results=[
            SearchResultItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                document_title=r.document_title,
                document_version=r.document_version,
                section=r.section,
                page=r.page,
                text=r.text,
                lexical_rank=r.lexical_rank,
                lexical_score=r.lexical_score,
                semantic_rank=r.semantic_rank,
                semantic_score=r.semantic_score,
                rrf_score=r.rrf_score,
            )
            for r in results
        ],
    )
