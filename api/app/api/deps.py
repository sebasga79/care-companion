"""Dependencias FastAPI — leen instancias singleton desde `app.state`
(creadas una vez en `main.create_app`, no por request)."""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings
from app.ports.challenge_case import ChallengeCasePort
from app.repositories.documents import DocumentRepository
from app.repositories.events import EventRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository
from app.services.embeddings_cache import EmbeddingsCache
from app.services.ingestion import KnowledgeIngestionService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_case_port(request: Request) -> ChallengeCasePort:
    return request.app.state.case_port


def get_session_repo(request: Request) -> SessionRepository:
    return request.app.state.session_repo


def get_turn_repo(request: Request) -> TurnRepository:
    return request.app.state.turn_repo


def get_event_repo(request: Request) -> EventRepository:
    return request.app.state.event_repo


def get_document_repo(request: Request) -> DocumentRepository:
    return request.app.state.document_repo


def get_embeddings_cache(request: Request) -> EmbeddingsCache:
    return request.app.state.embeddings_cache


def get_ingestion_service(request: Request) -> KnowledgeIngestionService:
    return request.app.state.ingestion_service
