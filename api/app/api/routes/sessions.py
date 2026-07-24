"""`/api/v1/sessions` — crear, consultar y cerrar sesiones (API-001, SUM-001).

`finish_session` usa `shortest_path` sobre `CallOrchestrator` para cerrar
la sesión de forma segura sin importar en qué estado se encuentre: la FSM
siempre tiene una salida hacia `closed` (vía `fail_safe` si el estado no
tiene un camino "feliz" directo hacia `summarizing`). Nunca se finge un
cierre exitoso si la transición es ilegal — un error real produce 500, no
una respuesta silenciosamente incorrecta (spec.md §11.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_case_port, get_event_repo, get_session_repo, get_settings_dep
from app.api.schemas import SessionCreateRequest, SessionResponse
from app.core.config import Settings
from app.core.correlation_id import get_correlation_id
from app.domain.session_fsm import (
    CallOrchestrator,
    InvalidTransitionError,
    SessionState,
    shortest_path,
)
from app.domain.summary import CallSummary
from app.ports.challenge_case import ChallengeCasePort
from app.repositories.events import EventRepository
from app.repositories.knowledge import get_current_knowledge_version
from app.repositories.sessions import SessionRepository

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_response(record: dict) -> SessionResponse:
    return SessionResponse(**record)


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreateRequest,
    case_port: ChallengeCasePort = Depends(get_case_port),
    session_repo: SessionRepository = Depends(get_session_repo),
    settings: Settings = Depends(get_settings_dep),
) -> SessionResponse:
    case = await case_port.get_case(body.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Caso no encontrado: {body.case_id}")

    knowledge_version = get_current_knowledge_version(settings.database_path)
    record = session_repo.create(
        case_id=body.case_id,
        state=SessionState.CREATED.value,
        knowledge_version=knowledge_version,
    )
    return _to_response(record)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    session_repo: SessionRepository = Depends(get_session_repo),
) -> SessionResponse:
    record = session_repo.get(str(session_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return _to_response(record)


@router.post("/{session_id}/finish", response_model=CallSummary)
async def finish_session(
    session_id: UUID,
    session_repo: SessionRepository = Depends(get_session_repo),
    event_repo: EventRepository = Depends(get_event_repo),
) -> CallSummary:
    record = session_repo.get(str(session_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    orchestrator = CallOrchestrator(str(session_id), initial_state=SessionState(record["state"]))
    if orchestrator.state is SessionState.CLOSED:
        raise HTTPException(status_code=409, detail="La sesión ya está cerrada")

    path = shortest_path(orchestrator.state, SessionState.CLOSED)
    if path is None:
        # No debería ocurrir nunca: fail_safe siempre tiene salida a closed.
        # Si ocurriera, es un error real y explícito, no un cierre falso.
        raise HTTPException(
            status_code=500,
            detail="No existe una transición segura hacia 'closed' desde el estado actual",
        )

    try:
        for target in path[1:]:
            orchestrator.transition(target, event="finish_requested")
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=500, detail=f"Estado inconsistente: {exc}") from exc

    now = datetime.now(UTC)
    updated = session_repo.update_state(
        str(session_id), state=orchestrator.state.value, closed_at=now.isoformat()
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="No se pudo persistir el cierre de la sesión")

    correlation_id = get_correlation_id() or str(session_id)
    event_repo.add_event(
        session_id=str(session_id),
        correlation_id=correlation_id,
        component="orchestrator",
        event_type="session.finished",
        payload={
            "final_state": orchestrator.state.value,
            "path": [state.value for state in path],
        },
    )

    started_at = datetime.fromisoformat(record["created_at"])
    return CallSummary(
        session_id=session_id,
        case_id=updated["case_id"],
        started_at=started_at,
        ended_at=now,
        knowledge_version=updated["knowledge_version"],
    )
