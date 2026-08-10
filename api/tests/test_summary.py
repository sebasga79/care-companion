"""SUM-001 — validación del schema `CallSummary`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.decision import DecisionLevel
from app.domain.summary import CallSummary


def test_minimal_valid_summary() -> None:
    summary = CallSummary(
        session_id=uuid4(),
        case_id="demo-case-001",
        started_at=datetime.now(UTC),
        knowledge_version=1,
    )
    assert summary.schema_version == "1.2"
    assert summary.risk.level == DecisionLevel.ROUTINE_FOLLOW_UP
    assert summary.risk.should_escalate is False
    assert summary.handoff.status == "none"
    assert summary.citations == []
    assert summary.usage.provider == "not_invoked"


def test_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        CallSummary(case_id="demo-case-001", started_at=datetime.now(UTC), knowledge_version=1)  # type: ignore[call-arg]


def test_handoff_status_is_restricted_to_allowed_values() -> None:
    with pytest.raises(ValidationError):
        CallSummary(
            session_id=uuid4(),
            case_id="demo-case-001",
            started_at=datetime.now(UTC),
            knowledge_version=1,
            handoff={"status": "not-a-real-status"},
        )


def test_round_trip_serialization() -> None:
    summary = CallSummary(
        session_id=uuid4(),
        case_id="demo-case-001",
        started_at=datetime.now(UTC),
        knowledge_version=3,
    )
    dumped = summary.model_dump_json()
    restored = CallSummary.model_validate_json(dumped)
    assert restored == summary
