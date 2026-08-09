"""`FixtureCaseAdapter` — implementación de `ChallengeCasePort` sobre casos
sintéticos propios (ADR-001, hasta que exista el adapter Delta Share real
en DATA-001).

Los tres casos son ficticios, inventados para esta fase, y usan el
procedimiento genérico ya establecido en `docs/fixtures/conversational-
scenarios.md` ("cirugía ambulatoria general X") para no anticipar ni
copiar el caso real del reto. No derivan de ningún dataset ni de
`caregaps-agent`.

Hasta el 9 ago sólo se usaban como resguardo de arranque si faltaba el
dataset real (`main.py::_build_case_port`). Desde entonces también se
exponen SIEMPRE, vía `CombinedCaseAdapter`, como los "pacientes de
prueba" de `/knowledge` — sin historial ni protocolo de seguimiento
longitudinal, para no forzar las 4 llamadas previas de un caso real sólo
para probar G5 (aprender/olvidar) o hacer un smoke-test de voz. `/call`
los excluye a propósito de su selector (`is_synthetic_demo`)."""

from __future__ import annotations

from app.ports.challenge_case import CaseFilters, CaseSummary, ChallengeCase, ChallengeCasePort

# Identificador interno para el filtro de aplicabilidad del RAG (nunca se
# muestra). Ningún documento del corpus oficial declara este valor, así
# que el retrieval sólo ve contenido "general" (sin `applicability.
# procedure`) más lo que el evaluador suba sin restricción — que es
# justamente el flujo de G5.
_GENERIC_PROCEDURE_CATEGORY = "cirugia_ambulatoria_general_x"
_GENERIC_PROCEDURE_LABEL = "Seguimiento general (paciente de prueba)"

_FIXTURE_CASES: dict[str, ChallengeCase] = {
    "demo-case-001": ChallengeCase(
        case_id="demo-case-001",
        patient_id="demo-patient-001",
        patient_display_name="Camila (paciente de prueba)",
        procedure=_GENERIC_PROCEDURE_LABEL,
        procedure_category=_GENERIC_PROCEDURE_CATEGORY,
        phase="post_discharge_day_2",
        days_since_procedure=2,
        caregiver_role="madre",
        notes="Caso sintético de demostración sin señales de alarma reportadas.",
        is_synthetic_demo=True,
    ),
    "demo-case-002": ChallengeCase(
        case_id="demo-case-002",
        patient_id="demo-patient-002",
        patient_display_name="Julián (paciente de prueba)",
        procedure=_GENERIC_PROCEDURE_LABEL,
        procedure_category=_GENERIC_PROCEDURE_CATEGORY,
        phase="post_discharge_day_1",
        days_since_procedure=1,
        caregiver_role="padre",
        notes="Caso sintético de demostración pensado para ejercitar aclaración de ambigüedad.",
        is_synthetic_demo=True,
    ),
    "demo-case-003": ChallengeCase(
        case_id="demo-case-003",
        patient_id="demo-patient-003",
        patient_display_name="Sofía (paciente de prueba)",
        procedure=_GENERIC_PROCEDURE_LABEL,
        procedure_category=_GENERIC_PROCEDURE_CATEGORY,
        phase="post_discharge_day_3",
        days_since_procedure=3,
        caregiver_role="madre",
        notes="Caso sintético de demostración pensado para ejercitar el camino de escalamiento.",
        is_synthetic_demo=True,
    ),
    # Dedicado al botón "Probar en una llamada" de `/knowledge` (auditoría
    # §9.23, 9 ago). Deliberadamente un 4º caso, no reutiliza Camila/Julián/
    # Sofía: esos tres alimentan `test_gates.py`, que SÍ necesita el
    # checklist clínico completo activo. Mezclar ambos propósitos en el
    # mismo `is_synthetic_demo` rompía esos tests la primera vez que se
    # intentó.
    "demo-case-quicktest": ChallengeCase(
        case_id="demo-case-quicktest",
        patient_id="demo-patient-quicktest",
        patient_display_name="Paciente de prueba",
        procedure=_GENERIC_PROCEDURE_LABEL,
        procedure_category=_GENERIC_PROCEDURE_CATEGORY,
        phase="post_discharge_day_1",
        days_since_procedure=1,
        caregiver_role="paciente",
        notes=(
            "Caso dedicado a pruebas ad-hoc (G5, smoke-test de voz) desde /knowledge. "
            "No conduce el checklist clínico: responde lo que se le pregunte y nada más."
        ),
        is_synthetic_demo=True,
        skip_interview_checklist=True,
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
                procedure_category=case.procedure_category,
                phase=case.phase,
                days_since_procedure=case.days_since_procedure,
                is_synthetic_demo=case.is_synthetic_demo,
                skip_interview_checklist=case.skip_interview_checklist,
            )
            for case in cases
        ]

    async def get_case(self, case_id: str) -> ChallengeCase | None:
        return _FIXTURE_CASES.get(case_id)
