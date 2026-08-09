"""`CombinedCaseAdapter` — une dataset real + casos de prueba sin tocar
ninguno de los dos adapters (auditoría §9.22, 9 ago)."""

from __future__ import annotations

from app.adapters.combined_cases import CombinedCaseAdapter
from app.adapters.fixture_cases import FixtureCaseAdapter
from app.ports.challenge_case import CaseFilters, CaseSummary, ChallengeCase, ChallengeCasePort


class _StubPrimary(ChallengeCasePort):
    """Sustituto mínimo de `DatasetCaseAdapter` — no hace falta el dataset
    real de 160 casos para probar la composición."""

    async def list_cases(self, filters: CaseFilters) -> list[CaseSummary]:
        return [
            CaseSummary(
                case_id="real-001",
                patient_display_name="Paciente real",
                procedure="Apendicectomía",
                procedure_category="appendicitis",
                phase="post_discharge_day_7",
                days_since_procedure=7,
            )
        ]

    async def get_case(self, case_id: str) -> ChallengeCase | None:
        if case_id != "real-001":
            return None
        return ChallengeCase(
            case_id="real-001",
            patient_id="patient-real-001",
            patient_display_name="Paciente real",
            procedure="Apendicectomía",
            procedure_category="appendicitis",
            phase="post_discharge_day_7",
            days_since_procedure=7,
            caregiver_role="madre",
        )


def _adapter() -> CombinedCaseAdapter:
    return CombinedCaseAdapter(_StubPrimary(), FixtureCaseAdapter())


async def test_list_cases_includes_both_real_and_synthetic() -> None:
    cases = await _adapter().list_cases(CaseFilters())
    ids = {c.case_id for c in cases}
    assert "real-001" in ids
    assert {"demo-case-001", "demo-case-002", "demo-case-003"} <= ids


async def test_synthetic_cases_are_flagged_and_real_ones_are_not() -> None:
    cases = await _adapter().list_cases(CaseFilters())
    by_id = {c.case_id: c for c in cases}
    assert by_id["real-001"].is_synthetic_demo is False
    assert by_id["demo-case-001"].is_synthetic_demo is True


async def test_get_case_checks_primary_first_then_falls_through_to_extra() -> None:
    adapter = _adapter()
    real = await adapter.get_case("real-001")
    assert real is not None and real.patient_display_name == "Paciente real"

    synthetic = await adapter.get_case("demo-case-001")
    assert synthetic is not None and synthetic.is_synthetic_demo is True

    missing = await adapter.get_case("no-existe")
    assert missing is None
