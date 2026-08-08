"""SAFE-001 — red de seguridad determinista sobre texto crudo."""

from __future__ import annotations

import pytest

from app.domain.observation import Observation
from app.domain.safety_signals import (
    detect_safety_signals,
    is_unspecified_severe_distress,
    merge_with_safety_precedence,
)


def _by_code(text: str) -> dict[str, Observation]:
    return {obs.code: obs for obs in detect_safety_signals(text, source_turn_id="turn-1")}


def test_40_degrees_is_confirmed_fever_and_high_fever() -> None:
    observations = _by_code("Sí, tengo fiebre, tengo 40 grados de fiebre")
    assert observations["FEVER"].certainty == "confirmed"
    assert observations["HIGH_FEVER"].certainty == "confirmed"
    assert observations["HIGH_FEVER"].value == "40.0 °C (reportado por el paciente)"


def test_normal_temperature_does_not_create_high_fever() -> None:
    observations = _by_code("Me medí y tengo 36,5 grados")
    assert observations["FEVER"].certainty == "denied"
    assert "HIGH_FEVER" not in observations


def test_exact_threshold_is_not_promoted_beyond_corpus_wording() -> None:
    observations = _by_code("Tengo exactamente 38 grados")
    assert observations["FEVER"].certainty == "denied"
    assert "HIGH_FEVER" not in observations


def test_explicit_fever_at_exact_threshold_is_not_contradicted() -> None:
    observations = _by_code("Tengo fiebre de 38 grados")
    assert observations["FEVER"].certainty == "confirmed"
    assert "HIGH_FEVER" not in observations


def test_explicit_negation_is_not_converted_into_an_alarm() -> None:
    observations = _by_code("No tengo fiebre y tampoco he sangrado")
    assert observations["FEVER"].certainty == "denied"
    assert observations["BLEEDING"].certainty == "denied"


def test_resolution_after_symptom_is_respected() -> None:
    observations = _by_code("Tuve fiebre, pero ya no")
    assert observations["FEVER"].certainty == "denied"
    assert "HIGH_FEVER" not in observations


def test_negation_stops_at_adversative_connector() -> None:
    observations = _by_code("No tengo fiebre, pero el dolor empeora cada vez más")
    assert observations["FEVER"].certainty == "denied"
    assert observations["PAIN_WORSENING"].certainty == "confirmed"


def test_exact_reported_pain_and_emergency_phrases_are_detected() -> None:
    observations = _by_code(
        "Me duele mucho el estómago, es un dolor persistente y creo que tengo que "
        "volver a ser hospitalizado; me voy a morir"
    )
    assert observations["PAIN_SEVERE"].certainty == "confirmed"
    assert observations["EMERGENCY_CONCERN"].certainty == "confirmed"


def test_severe_pain_alone_is_characterized_before_hard_escalation() -> None:
    observations = _by_code("Sigo inflamado y me duele mucho, tengo mucho dolor")
    assert observations["PAIN_SEVERE"].certainty == "confirmed"
    assert "PAIN_WORSENING" not in observations


def test_hospitalicen_is_detected_as_explicit_urgent_request() -> None:
    observations = _by_code("Yo quiero que me hospitalicen ya")
    assert observations["EMERGENCY_CONCERN"].certainty == "confirmed"


def test_inability_to_eat_is_not_mislabeled_as_vomiting() -> None:
    observations = _by_code("Puedo tomar líquidos normalmente, pero no puedo comer")
    assert observations["ORAL_INTAKE_INTOLERANCE"].certainty == "confirmed"
    assert "VOMITING" not in observations


def test_wound_redness_without_repeating_wound_is_detected() -> None:
    observations = _by_code("Está roja y un poco inflamada")
    assert observations["WOUND_INFLAMMATION"].certainty == "confirmed"


def test_unspecified_distress_is_not_an_explicit_emergency_request() -> None:
    observations = _by_code("Muy mal")
    assert "EMERGENCY_CONCERN" not in observations
    assert is_unspecified_severe_distress("Muy mal") is True
    assert is_unspecified_severe_distress("Me siento realmente terrible") is True


def test_concrete_alarm_with_distress_keeps_the_alarm() -> None:
    observations = _by_code("Estoy muy mal, no puedo respirar")
    assert observations["BREATHING_DIFFICULTY"].certainty == "confirmed"
    assert is_unspecified_severe_distress("Estoy muy mal, no puedo respirar") is False


def test_urgent_screen_consciousness_signals_are_detected() -> None:
    observations = _by_code("Estoy confundido y siento que me voy a desmayar")
    assert observations["ALTERED_CONSCIOUSNESS"].certainty == "confirmed"


def test_deterministic_confirmation_cannot_be_downgraded_by_agent() -> None:
    agent = Observation(
        code="FEVER",
        label="fiebre",
        certainty="denied",
        source_turn_id="turn-1",
        original_text="salida incorrecta del modelo",
    )
    safety = _by_code("Tengo 40 grados")["FEVER"]
    merged = {obs.code: obs for obs in merge_with_safety_precedence([agent], [safety])}
    assert merged["FEVER"].certainty == "confirmed"
    assert merged["FEVER"].normalized_by.startswith("safety-signal-detector")


# --------------------------------------------------------------------- #
# El paciente PREGUNTA, no reporta (falso positivo real visto en /call)
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "pregunta",
    [
        # Caso exacto de la prueba en vivo: escaló a urgencia porque el
        # paciente pronunció "empeorado" DENTRO de una pregunta.
        "no sé Usted dígame porque yo no me acuerdo cómo estaba y cómo había "
        "reportado la vez pasada entonces Quiero que me digas si sigue igual "
        "o mejorado o empeorado",
        "dígame usted si he mejorado o empeorado",
        "no me acuerdo si el dolor empeoró",
    ],
)
def test_question_about_a_symptom_is_not_a_report(pregunta: str) -> None:
    confirmed = [
        o.code for o in detect_safety_signals(pregunta, source_turn_id="t1")
        if o.certainty == "confirmed"
    ]
    assert confirmed == [], f"una pregunta no puede escalar la llamada: {confirmed}"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        # Contrapeso: suprimir preguntas NO puede introducir falsos
        # negativos, que la rúbrica marca como la falla catastrófica.
        ("el dolor ha empeorado bastante desde ayer", "PAIN_WORSENING"),
        ("no sé qué hacer, estoy sangrando mucho", "BLEEDING"),
        # "no puedo respirar" contiene su propia negación: aplicarle el
        # chequeo de negación previa la invertía ante un "no sé" delante.
        ("no sé, no puedo respirar bien", "BREATHING_DIFFICULTY"),
        ("no puedo respirar", "BREATHING_DIFFICULTY"),
    ],
)
def test_real_report_still_fires_after_question_suppression(texto: str, esperado: str) -> None:
    confirmed = [
        o.code for o in detect_safety_signals(texto, source_turn_id="t1")
        if o.certainty == "confirmed"
    ]
    assert esperado in confirmed, f"falso negativo en {texto!r}: {confirmed}"
