"""`FixtureCaseAdapter` — implementación de `ChallengeCasePort` sobre casos
sintéticos propios (ADR-001, hasta que exista el adapter Delta Share real
en DATA-001).

Los tres casos son ficticios, inventados para esta fase, y usan el
procedimiento genérico ya establecido en `docs/fixtures/conversational-
scenarios.md` ("cirugía ambulatoria general X") para no anticipar ni
copiar el caso real del reto. No derivan de ningún dataset ni de
`caregaps-agent`."""

from __future__ import annotations

from app.ports.challenge_case import CaseFilters, CaseSummary, ChallengeCase, ChallengeCasePort

_GENERIC_PROCEDURE = "cirugia_ambulatoria_general_x"

_FIXTURE_CASES: dict[str, ChallengeCase] = {
    "demo-case-001": ChallengeCase(
        case_id="demo-case-001",
        patient_display_name="Camila (paciente ficticia)",
        procedure=_GENERIC_PROCEDURE,
        phase="post_discharge_day_2",
        days_since_procedure=2,
        caregiver_role="madre",
        notes="Caso sintético de demostración sin señales de alarma reportadas.",
    ),
    "demo-case-002": ChallengeCase(
        case_id="demo-case-002",
        patient_display_name="Julián (paciente ficticio)",
        procedure=_GENERIC_PROCEDURE,
        phase="post_discharge_day_1",
        days_since_procedure=1,
        caregiver_role="padre",
        notes="Caso sintético de demostración pensado para ejercitar aclaración de ambigüedad.",
    ),
    "demo-case-003": ChallengeCase(
        case_id="demo-case-003",
        patient_display_name="Sofía (paciente ficticia)",
        procedure=_GENERIC_PROCEDURE,
        phase="post_discharge_day_3",
        days_since_procedure=3,
        caregiver_role="madre",
        notes="Caso sintético de demostración pensado para ejercitar el camino de escalamiento.",
    ),
}


class FixtureCaseAdapter(ChallengeCasePort):
    async def list_cases(self, filters: CaseFilters) -> list[CaseSummary]:
        cases = list(_FIXTURE_CASES.values())
        if filters.procedure:
            cases = [case for case in cases if case.procedure == filters.procedure]
        cases = cases[: filters.limit]
        return [
            CaseSummary(
                case_id=case.case_id,
                patient_display_name=case.patient_display_name,
                procedure=case.procedure,
                phase=case.phase,
                days_since_procedure=case.days_since_procedure,
            )
            for case in cases
        ]

    async def get_case(self, case_id: str) -> ChallengeCase | None:
        return _FIXTURE_CASES.get(case_id)
