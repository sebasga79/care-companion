"""`CallOrchestrator` — máquina de estados tipada del ciclo de vida de una
llamada (ORC-001).

Estados y happy path mínimos exigidos por el ticket:

    created -> consent -> interviewing -> retrieving -> deciding
             -> responding -> summarizing -> closed

más los caminos de architecture.md §7 (Retrieve->Escalate, Assess->Escalate,
Respond->Interview loop, Consent->Closed por rechazo) y los estados
transversales `fail_safe`/`escalated` de spec.md §9.1 y BR-027.

`transition()` es la única forma de cambiar de estado y rechaza cualquier
transición fuera de `_TRANSITIONS` — la orquestación es código, no un
"superprompt" (architecture.md principio 5)."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class SessionState(str, Enum):
    CREATED = "created"
    CONSENT = "consent"
    INTERVIEWING = "interviewing"
    RETRIEVING = "retrieving"
    DECIDING = "deciding"
    RESPONDING = "responding"
    SUMMARIZING = "summarizing"
    CLOSED = "closed"
    FAIL_SAFE = "fail_safe"
    ESCALATED = "escalated"


TERMINAL_STATES: frozenset[SessionState] = frozenset({SessionState.CLOSED})

# Tabla de transiciones válidas. `fail_safe` es alcanzable desde cualquier
# estado no terminal (BR-027: ante fallo de modelo/parser/RAG/persistencia
# con riesgo, el estado seguro es abstenerse/escalar) y siempre tiene una
# salida hacia `closed` (directa o vía `summarizing`), de modo que ninguna
# sesión puede quedar atascada sin camino de cierre.
_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.CREATED: frozenset({SessionState.CONSENT, SessionState.FAIL_SAFE}),
    SessionState.CONSENT: frozenset(
        {SessionState.INTERVIEWING, SessionState.CLOSED, SessionState.FAIL_SAFE}
    ),
    SessionState.INTERVIEWING: frozenset({SessionState.RETRIEVING, SessionState.FAIL_SAFE}),
    SessionState.RETRIEVING: frozenset(
        {SessionState.DECIDING, SessionState.ESCALATED, SessionState.FAIL_SAFE}
    ),
    SessionState.DECIDING: frozenset(
        {SessionState.RESPONDING, SessionState.ESCALATED, SessionState.FAIL_SAFE}
    ),
    SessionState.RESPONDING: frozenset(
        {SessionState.INTERVIEWING, SessionState.SUMMARIZING, SessionState.FAIL_SAFE}
    ),
    SessionState.ESCALATED: frozenset({SessionState.SUMMARIZING, SessionState.FAIL_SAFE}),
    SessionState.SUMMARIZING: frozenset({SessionState.CLOSED, SessionState.FAIL_SAFE}),
    SessionState.FAIL_SAFE: frozenset({SessionState.SUMMARIZING, SessionState.CLOSED}),
    SessionState.CLOSED: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, current: SessionState, target: SessionState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Transición no permitida: {current.value} -> {target.value}")


class TransitionRecord(BaseModel):
    from_state: SessionState
    to_state: SessionState
    event: str | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CallOrchestrator:
    """FSM tipada que gobierna el estado de una sesión de llamada."""

    def __init__(
        self, session_id: str, *, initial_state: SessionState = SessionState.CREATED
    ) -> None:
        self._session_id = session_id
        self._state = initial_state
        self._history: list[TransitionRecord] = []

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def history(self) -> list[TransitionRecord]:
        return list(self._history)

    def allowed_transitions(self) -> frozenset[SessionState]:
        return _TRANSITIONS.get(self._state, frozenset())

    def can_transition(self, target: SessionState) -> bool:
        return target in self.allowed_transitions()

    def transition(self, target: SessionState, *, event: str | None = None) -> SessionState:
        if not self.can_transition(target):
            raise InvalidTransitionError(self._state, target)
        self._history.append(
            TransitionRecord(from_state=self._state, to_state=target, event=event)
        )
        self._state = target
        return self._state

    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES


def shortest_path(start: SessionState, goal: SessionState) -> list[SessionState] | None:
    """BFS sobre `_TRANSITIONS`. Devuelve la secuencia de estados
    (incluyendo `start` y `goal`) más corta, o `None` si no existe camino.
    Usado por la API para cerrar una sesión de forma segura desde
    cualquier estado en el que se encuentre (ver `POST .../finish`)."""
    if start == goal:
        return [start]

    visited = {start}
    queue: deque[list[SessionState]] = deque([[start]])
    while queue:
        path = queue.popleft()
        current = path[-1]
        for next_state in _TRANSITIONS.get(current, frozenset()):
            if next_state in visited:
                continue
            new_path = [*path, next_state]
            if next_state == goal:
                return new_path
            visited.add(next_state)
            queue.append(new_path)
    return None
