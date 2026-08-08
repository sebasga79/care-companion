"""SAFE-001 — `evaluate_rules` (motor de reglas deterministas)."""

from __future__ import annotations

import pytest

from app.domain.observation import Observation
from app.services.rule_engine import RULESET_VERSION, evaluate_rules


def _obs(code: str, certainty: str, *, turn_id: str = "t1") -> Observation:
    if certainty == "not_assessed":
        return Observation.not_assessed(code=code, label=code)
    return Observation(
        code=code,
        label=code,
        certainty=certainty,
        original_text=f"texto de {code}",
        source_turn_id=turn_id,
    )


def test_no_observations_flags_every_required_code_as_missing() -> None:
    """Sin ninguna observación, ninguna regla puede evaluarse de forma
    concluyente: todos los códigos que requiere el ruleset quedan como
    "falta el dato", nunca como "todo bien" implícito (spec.md §11.2)."""
    result = evaluate_rules([])
    assert result.hard_red_flag is False
    assert result.trigger_codes == []
    assert result.fired_rules == []
    assert set(result.missing_info) == {
        "BLEEDING",
        "BREATHING_DIFFICULTY",
        "ALTERED_CONSCIOUSNESS",
        "EMERGENCY_CONCERN",
        "FEVER",
        "HIGH_FEVER",
        "PAIN_WORSENING",
        "VOMITING",
        "WOUND_DISCHARGE",
        "WOUND_INFLAMMATION",
        "PAIN_SEVERE",
        "ORAL_INTAKE_INTOLERANCE",
    }
    assert result.ruleset_version == RULESET_VERSION


def test_rf001_fires_when_fever_and_wound_discharge_both_confirmed() -> None:
    result = evaluate_rules([_obs("FEVER", "confirmed"), _obs("WOUND_DISCHARGE", "confirmed")])
    assert result.hard_red_flag is True
    assert "RF-001" in result.fired_rules
    assert "FEVER_WITH_WOUND_DISCHARGE" in result.trigger_codes


def test_rf001_does_not_fire_with_only_one_condition_confirmed() -> None:
    result = evaluate_rules([_obs("FEVER", "confirmed")])
    assert result.hard_red_flag is False
    assert "WOUND_DISCHARGE" in result.missing_info
    assert "HIGH_FEVER" in result.missing_info


def test_rf001_does_not_fire_when_one_condition_explicitly_denied() -> None:
    """Negación explícita descarta RF-001 de forma concluyente: ni FEVER ni
    WOUND_DISCHARGE aparecen en `missing_info` (ya no faltan, se resolvieron
    a 'no'/'sí'). RF-002 (PAIN_WORSENING) sigue sin dato, así que sí falta."""
    result = evaluate_rules([_obs("FEVER", "denied"), _obs("WOUND_DISCHARGE", "confirmed")])
    assert result.hard_red_flag is False
    assert "FEVER" not in result.missing_info
    assert "WOUND_DISCHARGE" not in result.missing_info
    assert "PAIN_WORSENING" in result.missing_info


def test_rf001_uncertain_or_not_assessed_counts_as_missing_never_as_confirmed() -> None:
    for certainty in ("uncertain", "not_assessed"):
        result = evaluate_rules([_obs("FEVER", certainty), _obs("WOUND_DISCHARGE", "confirmed")])
        assert result.hard_red_flag is False, certainty
        assert "FEVER" in result.missing_info, certainty


def test_rf002_any_combine_fires_on_single_confirmed_condition() -> None:
    result = evaluate_rules([_obs("PAIN_WORSENING", "confirmed")])
    assert result.hard_red_flag is True
    assert "RF-002" in result.fired_rules
    assert "PAIN_WORSENING" in result.trigger_codes


def test_rf002_does_not_fire_when_denied() -> None:
    """PAIN_WORSENING negado descarta RF-002 de forma concluyente; RF-001
    sigue sin datos de FEVER/WOUND_DISCHARGE, así que ambos faltan."""
    result = evaluate_rules([_obs("PAIN_WORSENING", "denied")])
    assert result.hard_red_flag is False
    assert {"FEVER", "HIGH_FEVER", "WOUND_DISCHARGE"}.issubset(result.missing_info)


def test_rf002_missing_when_no_observation_at_all() -> None:
    """Sin ninguna observación de `PAIN_WORSENING`, RF-002 no puede
    evaluarse de forma concluyente — se reporta como dato faltante, nunca
    como "sin dolor" implícito (spec.md §11.2)."""
    result = evaluate_rules([_obs("GENERAL_STATE", "confirmed")])
    assert result.hard_red_flag is False
    assert "PAIN_WORSENING" in result.missing_info


def test_rf003_high_reported_temperature_is_a_hard_red_flag() -> None:
    result = evaluate_rules([_obs("HIGH_FEVER", "confirmed")])
    assert result.hard_red_flag is True
    assert "RF-003" in result.fired_rules
    assert "HIGH_FEVER" in result.trigger_codes


@pytest.mark.parametrize(
    ("observations", "rule_id", "trigger_code"),
    [
        ([_obs("BREATHING_DIFFICULTY", "confirmed")], "RF-004", "BREATHING_DIFFICULTY"),
        ([_obs("BLEEDING", "confirmed")], "RF-005", "BLEEDING"),
        ([_obs("EMERGENCY_CONCERN", "confirmed")], "RF-006", "EMERGENCY_CONCERN"),
        (
            [_obs("VOMITING", "confirmed"), _obs("PAIN_WORSENING", "confirmed")],
            "RF-007",
            "VOMITING_WITH_PAIN",
        ),
        (
            [_obs("ALTERED_CONSCIOUSNESS", "confirmed")],
            "RF-008",
            "ALTERED_CONSCIOUSNESS",
        ),
        (
            [
                _obs("FEVER", "confirmed"),
                _obs("PAIN_SEVERE", "confirmed"),
                _obs("WOUND_INFLAMMATION", "confirmed"),
            ],
            "RF-009",
            "POSTOP_DETERIORATION_WITH_WOUND",
        ),
        (
            [
                _obs("FEVER", "confirmed"),
                _obs("PAIN_SEVERE", "confirmed"),
                _obs("ORAL_INTAKE_INTOLERANCE", "confirmed"),
            ],
            "RF-010",
            "POSTOP_DETERIORATION_WITH_INTAKE",
        ),
    ],
)
def test_rules_v2_critical_signals_fire(
    observations: list[Observation], rule_id: str, trigger_code: str
) -> None:
    result = evaluate_rules(observations)
    assert result.hard_red_flag is True
    assert rule_id in result.fired_rules
    assert trigger_code in result.trigger_codes


def test_last_observation_wins_per_code() -> None:
    """`by_code` se resuelve por la última observación del código en la
    lista (orden = created_at ASC, ya garantizado por el repositorio)."""
    result = evaluate_rules(
        [
            _obs("FEVER", "denied", turn_id="t1"),
            _obs("WOUND_DISCHARGE", "confirmed", turn_id="t2"),
            _obs("FEVER", "confirmed", turn_id="t3"),  # corrección posterior
        ]
    )
    assert result.hard_red_flag is True
    assert "RF-001" in result.fired_rules


def test_multiple_rules_fire_independently_and_merge_trigger_codes() -> None:
    result = evaluate_rules(
        [
            _obs("FEVER", "confirmed"),
            _obs("WOUND_DISCHARGE", "confirmed"),
            _obs("PAIN_WORSENING", "confirmed"),
        ]
    )
    assert result.hard_red_flag is True
    assert set(result.fired_rules) == {"RF-001", "RF-002"}
    assert set(result.trigger_codes) == {"FEVER_WITH_WOUND_DISCHARGE", "PAIN_WORSENING"}
