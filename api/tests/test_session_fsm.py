"""ORC-001 — tests exhaustivos de `CallOrchestrator` (FSM) y `shortest_path`."""

from __future__ import annotations

import pytest

from app.domain.session_fsm import (
    CallOrchestrator,
    InvalidTransitionError,
    SessionState,
    shortest_path,
)


def test_happy_path_full_cycle() -> None:
    orchestrator = CallOrchestrator("s1")
    sequence = [
        SessionState.CONSENT,
        SessionState.INTERVIEWING,
        SessionState.RETRIEVING,
        SessionState.DECIDING,
        SessionState.RESPONDING,
        SessionState.SUMMARIZING,
        SessionState.CLOSED,
    ]
    for target in sequence:
        orchestrator.transition(target)
    assert orchestrator.state is SessionState.CLOSED
    assert orchestrator.is_terminal()
    assert [record.to_state for record in orchestrator.history] == sequence


def test_consent_declined_closes_directly() -> None:
    orchestrator = CallOrchestrator("s1")
    orchestrator.transition(SessionState.CONSENT)
    orchestrator.transition(SessionState.CLOSED, event="declined")
    assert orchestrator.state is SessionState.CLOSED


def test_retrieve_can_escalate_on_insufficient_evidence() -> None:
    orchestrator = CallOrchestrator("s1")
    orchestrator.transition(SessionState.CONSENT)
    orchestrator.transition(SessionState.INTERVIEWING)
    orchestrator.transition(SessionState.RETRIEVING)
    orchestrator.transition(SessionState.ESCALATED, event="evidence_insufficient_with_risk")
    orchestrator.transition(SessionState.SUMMARIZING)
    orchestrator.transition(SessionState.CLOSED)
    assert orchestrator.state is SessionState.CLOSED


def test_deciding_can_escalate_on_hard_red_flag() -> None:
    orchestrator = CallOrchestrator("s1")
    for target in (
        SessionState.CONSENT,
        SessionState.INTERVIEWING,
        SessionState.RETRIEVING,
        SessionState.DECIDING,
    ):
        orchestrator.transition(target)
    orchestrator.transition(SessionState.ESCALATED, event="hard_red_flag")
    assert orchestrator.state is SessionState.ESCALATED
    orchestrator.transition(SessionState.SUMMARIZING)
    orchestrator.transition(SessionState.CLOSED)


def test_responding_can_loop_back_to_interviewing_for_follow_up() -> None:
    orchestrator = CallOrchestrator("s1")
    for target in (
        SessionState.CONSENT,
        SessionState.INTERVIEWING,
        SessionState.RETRIEVING,
        SessionState.DECIDING,
        SessionState.RESPONDING,
    ):
        orchestrator.transition(target)
    orchestrator.transition(SessionState.INTERVIEWING, event="needs_follow_up")
    assert orchestrator.state is SessionState.INTERVIEWING
    # y puede volver a completar el ciclo
    for target in (
        SessionState.RETRIEVING,
        SessionState.DECIDING,
        SessionState.RESPONDING,
        SessionState.SUMMARIZING,
        SessionState.CLOSED,
    ):
        orchestrator.transition(target)
    assert orchestrator.state is SessionState.CLOSED


@pytest.mark.parametrize(
    "start",
    [
        SessionState.CREATED,
        SessionState.CONSENT,
        SessionState.INTERVIEWING,
        SessionState.RETRIEVING,
        SessionState.DECIDING,
        SessionState.RESPONDING,
        SessionState.ESCALATED,
        SessionState.SUMMARIZING,
    ],
)
def test_fail_safe_reachable_from_every_non_terminal_state(start: SessionState) -> None:
    orchestrator = CallOrchestrator("s1", initial_state=start)
    orchestrator.transition(SessionState.FAIL_SAFE, event="unexpected_failure")
    assert orchestrator.state is SessionState.FAIL_SAFE


def test_fail_safe_can_only_reach_summarizing_or_closed() -> None:
    orchestrator = CallOrchestrator("s1", initial_state=SessionState.FAIL_SAFE)
    assert orchestrator.allowed_transitions() == frozenset(
        {SessionState.SUMMARIZING, SessionState.CLOSED}
    )


def test_closed_is_terminal_with_no_outgoing_transitions() -> None:
    orchestrator = CallOrchestrator("s1", initial_state=SessionState.CLOSED)
    assert orchestrator.allowed_transitions() == frozenset()
    assert orchestrator.is_terminal()
    with pytest.raises(InvalidTransitionError):
        orchestrator.transition(SessionState.SUMMARIZING)


@pytest.mark.parametrize(
    ("start", "illegal_target"),
    [
        (SessionState.CREATED, SessionState.INTERVIEWING),  # salta CONSENT
        (SessionState.CREATED, SessionState.CLOSED),  # salta todo el flujo
        (SessionState.CONSENT, SessionState.RETRIEVING),  # salta INTERVIEWING
        (SessionState.INTERVIEWING, SessionState.CLOSED),  # sin resumen
        (SessionState.INTERVIEWING, SessionState.DECIDING),  # salta RETRIEVING
        (SessionState.RETRIEVING, SessionState.RESPONDING),  # salta DECIDING
        (SessionState.DECIDING, SessionState.CLOSED),  # salta RESPONDING/SUMMARIZING
        (SessionState.SUMMARIZING, SessionState.INTERVIEWING),  # retrocede tras resumir
        (SessionState.ESCALATED, SessionState.RESPONDING),  # escalado no vuelve a respuesta normal
        (SessionState.CLOSED, SessionState.CREATED),  # terminal no reabre
    ],
)
def test_illegal_transitions_are_rejected(
    start: SessionState, illegal_target: SessionState
) -> None:
    orchestrator = CallOrchestrator("s1", initial_state=start)
    with pytest.raises(InvalidTransitionError) as exc_info:
        orchestrator.transition(illegal_target)
    assert exc_info.value.current is start
    assert exc_info.value.target is illegal_target
    # una transición rechazada no debe mutar el estado
    assert orchestrator.state is start


def test_history_is_a_defensive_copy() -> None:
    orchestrator = CallOrchestrator("s1")
    orchestrator.transition(SessionState.CONSENT)
    history = orchestrator.history
    history.append(history[0])  # mutar la copia no debe afectar al interno
    assert len(orchestrator.history) == 1


def test_shortest_path_same_state_is_trivial() -> None:
    assert shortest_path(SessionState.CREATED, SessionState.CREATED) == [SessionState.CREATED]


def test_shortest_path_from_created_to_closed_has_length_two_hops() -> None:
    path = shortest_path(SessionState.CREATED, SessionState.CLOSED)
    assert path is not None
    assert path[0] is SessionState.CREATED
    assert path[-1] is SessionState.CLOSED
    # Dos caminos de 2 saltos son igualmente válidos como "más corto":
    # CREATED->CONSENT->CLOSED (declinar) o CREATED->FAIL_SAFE->CLOSED
    # (estado seguro). BFS no garantiza desempate entre ambos; solo importa
    # que la longitud sea la mínima posible y termine en CLOSED.
    assert len(path) == 3
    assert path[1] in {SessionState.CONSENT, SessionState.FAIL_SAFE}


@pytest.mark.parametrize(
    "start",
    [
        SessionState.CREATED,
        SessionState.CONSENT,
        SessionState.INTERVIEWING,
        SessionState.RETRIEVING,
        SessionState.DECIDING,
        SessionState.RESPONDING,
        SessionState.ESCALATED,
        SessionState.SUMMARIZING,
        SessionState.FAIL_SAFE,
    ],
)
def test_shortest_path_to_closed_always_exists(start: SessionState) -> None:
    path = shortest_path(start, SessionState.CLOSED)
    assert path is not None
    assert path[-1] is SessionState.CLOSED


def test_shortest_path_no_path_from_closed_elsewhere() -> None:
    assert shortest_path(SessionState.CLOSED, SessionState.CREATED) is None
