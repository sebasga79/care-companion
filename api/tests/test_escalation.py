"""SAFE-004 (BR-025) — `EscalationRecord`/`EscalationRepository`: idempotencia
por `session_id + trigger_set + decision_level`."""

from __future__ import annotations

from app.domain.decision import DecisionLevel, DecisionResult
from app.domain.escalation import compute_idempotency_key
from app.repositories.db import apply_schema, get_connection
from app.repositories.escalations import EscalationRepository
from app.repositories.sessions import SessionRepository


def _init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()


def test_idempotency_key_is_stable_regardless_of_trigger_code_order() -> None:
    key_a = compute_idempotency_key(
        session_id="s1",
        decision_level=DecisionLevel.HARD_RED_FLAG,
        trigger_codes=["B", "A"],
    )
    key_b = compute_idempotency_key(
        session_id="s1",
        decision_level=DecisionLevel.HARD_RED_FLAG,
        trigger_codes=["A", "B"],
    )
    assert key_a == key_b


def test_idempotency_key_differs_by_session_level_or_triggers() -> None:
    base = compute_idempotency_key(
        session_id="s1", decision_level=DecisionLevel.HARD_RED_FLAG, trigger_codes=["A"]
    )
    assert base != compute_idempotency_key(
        session_id="s2", decision_level=DecisionLevel.HARD_RED_FLAG, trigger_codes=["A"]
    )
    assert base != compute_idempotency_key(
        session_id="s1", decision_level=DecisionLevel.DATA_INTEGRITY_FAILURE, trigger_codes=["A"]
    )
    assert base != compute_idempotency_key(
        session_id="s1", decision_level=DecisionLevel.HARD_RED_FLAG, trigger_codes=["A", "B"]
    )


def test_create_if_absent_is_idempotent_for_the_same_condition(db_path: str) -> None:
    _init_db(db_path)
    session = SessionRepository(db_path).create(
        case_id="demo-case-001", state="deciding", knowledge_version=1
    )
    repo = EscalationRepository(db_path)
    decision = DecisionResult(
        level=DecisionLevel.HARD_RED_FLAG,
        should_escalate=True,
        trigger_codes=["FEVER_WITH_WOUND_DISCHARGE"],
        rationale="alarma determinista",
    )

    first = repo.create_if_absent(session_id=session["id"], decision=decision)
    second = repo.create_if_absent(session_id=session["id"], decision=decision)

    assert first.was_duplicate is False
    assert second.was_duplicate is True
    assert first.id == second.id
    assert len(repo.list_for_session(session["id"])) == 1


def test_create_if_absent_creates_new_row_for_different_condition(db_path: str) -> None:
    _init_db(db_path)
    session = SessionRepository(db_path).create(
        case_id="demo-case-001", state="deciding", knowledge_version=1
    )
    repo = EscalationRepository(db_path)

    first = repo.create_if_absent(
        session_id=session["id"],
        decision=DecisionResult(
            level=DecisionLevel.HARD_RED_FLAG,
            should_escalate=True,
            trigger_codes=["FEVER_WITH_WOUND_DISCHARGE"],
            rationale="r1",
        ),
    )
    second = repo.create_if_absent(
        session_id=session["id"],
        decision=DecisionResult(
            level=DecisionLevel.HARD_RED_FLAG,
            should_escalate=True,
            trigger_codes=["PAIN_WORSENING"],
            rationale="r2",
        ),
    )

    assert first.id != second.id
    assert len(repo.list_for_session(session["id"])) == 2
