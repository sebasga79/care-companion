"""ORC-001 — tests exhaustivos y adversariales de `reduce_decision`.

La regla no negociable (spec.md §8.1, BR-020/BR-021): una decisión de
mayor severidad NUNCA es rebajada por el modelo. Los tests adversariales
intentan exactamente eso — hacer que el modelo "gane" sobre una bandera
determinista — y verifican que nunca lo logra."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.decision import (
    PRECEDENCE_ORDER,
    DecisionInputs,
    DecisionLevel,
    reduce_decision,
)


def test_no_signals_defaults_to_routine_follow_up() -> None:
    result = reduce_decision(DecisionInputs())
    assert result.level == DecisionLevel.ROUTINE_FOLLOW_UP
    assert result.should_escalate is False
    assert result.trigger_codes == []


def test_hard_red_flag_alone_escalates() -> None:
    result = reduce_decision(
        DecisionInputs(hard_red_flag=True, trigger_codes=["WOUND_HEAT", "PAIN_WORSENING"])
    )
    assert result.level == DecisionLevel.HARD_RED_FLAG
    assert result.should_escalate is True
    assert result.trigger_codes == ["WOUND_HEAT", "PAIN_WORSENING"]


# --- Adversarial: el modelo intenta rebajar cada bandera determinista ---


@pytest.mark.parametrize("model_level", list(DecisionLevel))
def test_model_cannot_downgrade_hard_red_flag(model_level: DecisionLevel) -> None:
    if model_level not in {
        DecisionLevel.MODEL_HIGH_RISK,
        DecisionLevel.MODEL_MODERATE_RISK,
        DecisionLevel.ROUTINE_FOLLOW_UP,
    }:
        pytest.skip("nivel no reportable por el modelo; cubierto en otro test")
    result = reduce_decision(
        DecisionInputs(hard_red_flag=True, trigger_codes=["X"], model_level=model_level)
    )
    assert result.level == DecisionLevel.HARD_RED_FLAG, (
        f"el modelo reportando {model_level} no debe poder rebajar HARD_RED_FLAG"
    )
    assert result.should_escalate is True


def test_model_cannot_downgrade_data_integrity_failure_even_with_routine_model() -> None:
    result = reduce_decision(
        DecisionInputs(data_integrity_failure=True, model_level=DecisionLevel.ROUTINE_FOLLOW_UP)
    )
    assert result.level == DecisionLevel.DATA_INTEGRITY_FAILURE
    assert result.should_escalate is True


def test_model_cannot_downgrade_evidence_insufficient_with_risk() -> None:
    result = reduce_decision(
        DecisionInputs(
            evidence_insufficient_with_risk=True, model_level=DecisionLevel.MODEL_HIGH_RISK
        )
    )
    # EVIDENCE_INSUFFICIENT_WITH_RISK supera a MODEL_HIGH_RISK en precedencia.
    assert result.level == DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK
    assert result.should_escalate is True


def test_hard_red_flag_beats_data_integrity_failure_when_both_present() -> None:
    result = reduce_decision(
        DecisionInputs(
            hard_red_flag=True,
            trigger_codes=["A"],
            data_integrity_failure=True,
            evidence_insufficient_with_risk=True,
            model_level=DecisionLevel.MODEL_HIGH_RISK,
        )
    )
    assert result.level == DecisionLevel.HARD_RED_FLAG
    assert result.trigger_codes == ["A"]


def test_data_integrity_failure_beats_evidence_insufficient_and_model() -> None:
    result = reduce_decision(
        DecisionInputs(
            data_integrity_failure=True,
            evidence_insufficient_with_risk=True,
            model_level=DecisionLevel.MODEL_HIGH_RISK,
        )
    )
    assert result.level == DecisionLevel.DATA_INTEGRITY_FAILURE


def test_model_high_risk_wins_over_model_moderate_when_no_deterministic_flags() -> None:
    result = reduce_decision(DecisionInputs(model_level=DecisionLevel.MODEL_HIGH_RISK))
    assert result.level == DecisionLevel.MODEL_HIGH_RISK
    assert result.should_escalate is True


def test_model_moderate_risk_does_not_auto_escalate() -> None:
    result = reduce_decision(DecisionInputs(model_level=DecisionLevel.MODEL_MODERATE_RISK))
    assert result.level == DecisionLevel.MODEL_MODERATE_RISK
    assert result.should_escalate is False


def test_trigger_codes_only_populated_for_hard_red_flag_result() -> None:
    result = reduce_decision(
        DecisionInputs(
            data_integrity_failure=True,
            trigger_codes=["SHOULD_NOT_APPEAR"],
        )
    )
    assert result.level == DecisionLevel.DATA_INTEGRITY_FAILURE
    assert result.trigger_codes == []


def test_model_level_cannot_be_constructed_as_hard_red_flag() -> None:
    with pytest.raises(ValidationError, match="model_level"):
        DecisionInputs(model_level=DecisionLevel.HARD_RED_FLAG)


def test_model_level_cannot_be_constructed_as_data_integrity_failure() -> None:
    with pytest.raises(ValidationError, match="model_level"):
        DecisionInputs(model_level=DecisionLevel.DATA_INTEGRITY_FAILURE)


def test_model_level_cannot_be_constructed_as_evidence_insufficient_with_risk() -> None:
    with pytest.raises(ValidationError, match="model_level"):
        DecisionInputs(model_level=DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK)


def test_precedence_order_matches_spec_exactly() -> None:
    assert PRECEDENCE_ORDER == (
        DecisionLevel.HARD_RED_FLAG,
        DecisionLevel.DATA_INTEGRITY_FAILURE,
        DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK,
        DecisionLevel.MODEL_HIGH_RISK,
        DecisionLevel.MODEL_MODERATE_RISK,
        DecisionLevel.ROUTINE_FOLLOW_UP,
    )


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (
            {"hard_red_flag": True, "data_integrity_failure": True},
            DecisionLevel.HARD_RED_FLAG,
        ),
        (
            {"data_integrity_failure": True, "evidence_insufficient_with_risk": True},
            DecisionLevel.DATA_INTEGRITY_FAILURE,
        ),
        (
            {"evidence_insufficient_with_risk": True},
            DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK,
        ),
    ],
)
def test_combinations_always_yield_highest_precedence_active_signal(
    flags: dict[str, bool], expected: DecisionLevel
) -> None:
    result = reduce_decision(DecisionInputs(**flags))
    assert result.level == expected


def test_rationale_is_non_empty_for_every_level() -> None:
    for level in (
        DecisionLevel.MODEL_HIGH_RISK,
        DecisionLevel.MODEL_MODERATE_RISK,
        DecisionLevel.ROUTINE_FOLLOW_UP,
    ):
        result = reduce_decision(DecisionInputs(model_level=level))
        assert result.rationale
