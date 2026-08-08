from app.domain.clinical_values import (
    normalize_appetite,
    normalize_mobility,
    normalize_sleep,
    normalize_wound,
    parse_pain_nrs,
    parse_temperature_c,
)


def test_spanish_pain_word_becomes_numeric_dataset_value() -> None:
    assert parse_pain_nrs("siete") == 7


def test_fever_phrase_without_grados_becomes_numeric_temperature() -> None:
    assert parse_temperature_c(None, "tengo fiebre de 38") == 38.0


def test_liquids_ok_but_cannot_eat_keeps_both_facts() -> None:
    assert (
        normalize_appetite("puedo tomar líquidos normalmente pero no puedo comer")
        == "tolera_liquidos_no_alimentos"
    )


def test_red_and_swollen_wound_uses_dataset_category() -> None:
    assert normalize_wound("está roja y un poco inflamada") == "enrojecida_inflamada"


def test_unrelated_emergency_phrases_do_not_contaminate_dataset_axes() -> None:
    assert normalize_mobility("yo quiero que me hospitalicen ya") is None
    assert normalize_sleep("me duele mucho, necesito una ambulancia") is None
