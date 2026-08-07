"""DATA-001 (real) — `DatasetCaseAdapter` sobre el dataset oficial del reto.

Los `.xlsx` de prueba se escriben con `openpyxl` en el propio test (mismo
esquema de columnas confirmado inspeccionando el dataset real con
`openpyxl` — ver docs/auditoria-kit-oficial-2026-08-07.md §9.2), no
fixtures binarias ni el dataset real (que no se commitea, ver
`scripts/fetch_dataset.py` y `.gitignore`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.dataset_case_source import (
    PERFILES_CLINICOS_FILE,
    PERFILES_DEMOGRAFICOS_FILE,
    TRAYECTORIAS_FILE,
    DatasetCaseAdapter,
    DatasetFilesMissingError,
    check_dataset_files_present,
)
from app.ports.challenge_case import CaseFilters


def _write_xlsx(path: Path, header: list[str], rows: list[tuple]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(path)


def _write_full_dataset(
    tmp_path: Path,
    *,
    trayectorias: list[tuple] | None = None,
    perfiles_clinicos: list[tuple] | None = None,
    perfiles_demograficos: list[tuple] | None = None,
) -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()

    _write_xlsx(
        dataset_dir / TRAYECTORIAS_FILE,
        [
            "trayectoria_id", "paciente_id", "dia_postop", "arquetipo_trayectoria",
            "dolor_nrs", "fiebre_c", "movilidad", "herida", "apetito", "sueno",
        ],
        trayectorias
        if trayectorias is not None
        else [
            (
                "tray_pac_1_00000_1", "pac_1_00000", 1, "recuperacion_normal",
                2, 37.5, "normal", "normal", "normal", "normal",
            ),
            (
                "tray_pac_1_00000_3", "pac_1_00000", 3, "recuperacion_normal",
                1, 36.9, "normal", "normal", "normal", "normal",
            ),
        ],
    )
    _write_xlsx(
        dataset_dir / PERFILES_CLINICOS_FILE,
        ["paciente_id", "modulo_synthea", "procedimiento", "edad", "genero", "comorbilidades"],
        perfiles_clinicos
        if perfiles_clinicos is not None
        else [
            ("pac_1_00000", "appendicitis", "Apendicectomía", 34, "F", '["hipertension"]'),
        ],
    )
    _write_xlsx(
        dataset_dir / PERFILES_DEMOGRAFICOS_FILE,
        ["paciente_id", "nombre_completo", "ciudad", "departamento"],
        perfiles_demograficos
        if perfiles_demograficos is not None
        else [
            ("pac_1_00000", "María Fernanda Rodríguez", "Medellín", "Antioquia"),
        ],
    )
    return dataset_dir


def test_check_dataset_files_present_reports_missing(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    missing = check_dataset_files_present(empty_dir)
    assert set(missing) == {TRAYECTORIAS_FILE, PERFILES_CLINICOS_FILE, PERFILES_DEMOGRAFICOS_FILE}


def test_adapter_raises_when_files_missing(tmp_path: Path) -> None:
    with pytest.raises(DatasetFilesMissingError):
        DatasetCaseAdapter(tmp_path / "does-not-exist")


async def test_adapter_builds_case_id_from_trayectoria_id(tmp_path: Path) -> None:
    dataset_dir = _write_full_dataset(tmp_path)
    adapter = DatasetCaseAdapter(dataset_dir)

    cases = await adapter.list_cases(CaseFilters())
    case_ids = {c.case_id for c in cases}
    assert case_ids == {"caso_tray_pac_1_00000_1", "caso_tray_pac_1_00000_3"}


async def test_adapter_joins_clinical_and_demographic_profiles(tmp_path: Path) -> None:
    dataset_dir = _write_full_dataset(tmp_path)
    adapter = DatasetCaseAdapter(dataset_dir)

    case = await adapter.get_case("caso_tray_pac_1_00000_1")
    assert case is not None
    assert case.patient_display_name == "María Fernanda Rodríguez"
    assert case.procedure == "Apendicectomía"
    assert case.procedure_category == "appendicitis"
    assert case.age == 34
    assert case.gender == "F"
    assert case.comorbidities == ["hipertension"]
    assert case.city == "Medellín"
    assert case.department == "Antioquia"
    assert case.days_since_procedure == 1
    assert case.phase == "post_discharge_day_1"


async def test_adapter_exposes_reference_trajectory_never_fed_to_agents(tmp_path: Path) -> None:
    """El campo existe para que un humano actuando de paciente sepa qué
    describir en la demo — nunca se pasa al prompt de InterviewAgent
    (contrato del port, no algo que este test pueda verificar en
    aislamiento, pero sí que el dato llega completo hasta acá)."""
    dataset_dir = _write_full_dataset(tmp_path)
    adapter = DatasetCaseAdapter(dataset_dir)

    case = await adapter.get_case("caso_tray_pac_1_00000_1")
    assert case is not None
    assert case.reference_trajectory is not None
    assert case.reference_trajectory.dolor_nrs == 2
    assert case.reference_trajectory.fiebre_c == 37.5
    assert case.reference_trajectory.arquetipo == "recuperacion_normal"


async def test_adapter_skips_trajectory_rows_without_matching_profile(tmp_path: Path) -> None:
    """Fila de trayectoria de un paciente que no aparece en los perfiles —
    se omite ese caso (dato incompleto) en vez de fabricar un perfil vacío
    que parecería real."""
    dataset_dir = _write_full_dataset(
        tmp_path,
        trayectorias=[
            (
                "tray_huerfana_1", "pac_sin_perfil", 1, "recuperacion_normal",
                2, 37.0, "normal", "normal", "normal", "normal",
            ),
        ],
    )
    adapter = DatasetCaseAdapter(dataset_dir)
    cases = await adapter.list_cases(CaseFilters())
    assert cases == []


async def test_list_cases_filters_by_procedure_category(tmp_path: Path) -> None:
    dataset_dir = _write_full_dataset(
        tmp_path,
        trayectorias=[
            (
                "tray_pac_1_00000_1", "pac_1_00000", 1, "recuperacion_normal",
                2, 37.5, "normal", "normal", "normal", "normal",
            ),
            (
                "tray_pac_2_00000_1", "pac_2_00000", 1, "recuperacion_normal",
                1, 36.8, "normal", "normal", "normal", "normal",
            ),
        ],
        perfiles_clinicos=[
            ("pac_1_00000", "appendicitis", "Apendicectomía", 34, "F", "[]"),
            ("pac_2_00000", "cholecystitis", "Colecistectomía", 30, "F", "[]"),
        ],
        perfiles_demograficos=[
            ("pac_1_00000", "Paciente Uno", "Medellín", "Antioquia"),
            ("pac_2_00000", "Paciente Dos", "Bogotá D.C.", "Bogotá D.C."),
        ],
    )
    adapter = DatasetCaseAdapter(dataset_dir)

    cases = await adapter.list_cases(CaseFilters(procedure="cholecystitis"))
    assert len(cases) == 1
    assert cases[0].procedure_category == "cholecystitis"


async def test_list_cases_respects_limit(tmp_path: Path) -> None:
    dataset_dir = _write_full_dataset(tmp_path)
    adapter = DatasetCaseAdapter(dataset_dir)
    cases = await adapter.list_cases(CaseFilters(limit=1))
    assert len(cases) == 1


async def test_get_case_returns_none_for_unknown_id(tmp_path: Path) -> None:
    dataset_dir = _write_full_dataset(tmp_path)
    adapter = DatasetCaseAdapter(dataset_dir)
    assert await adapter.get_case("caso_no_existe") is None


async def test_invalid_comorbilidades_json_defaults_to_empty_list(tmp_path: Path) -> None:
    dataset_dir = _write_full_dataset(
        tmp_path,
        perfiles_clinicos=[
            ("pac_1_00000", "appendicitis", "Apendicectomía", 34, "F", "esto no es json"),
        ],
    )
    adapter = DatasetCaseAdapter(dataset_dir)
    case = await adapter.get_case("caso_tray_pac_1_00000_1")
    assert case is not None
    assert case.comorbidities == []
