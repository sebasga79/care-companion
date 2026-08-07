"""`DatasetCaseAdapter` — `ChallengeCasePort` real sobre el dataset oficial
del reto (docs/auditoria-kit-oficial-2026-08-07.md §4.2/§9.2: no es Delta
Share, son 4 `.xlsx` — descargados por `scripts/fetch_dataset.py` a
`DATASET_DIR`, nunca commiteados al repo, ver `.gitignore`).

Lee `trayectorias_postop_silver.xlsx` (una fila = un caso: paciente × día
postoperatorio), `perfiles_clinicos_pacientes_silver_contest.xlsx`
(procedimiento/edad/género/comorbilidades) y `perfiles_pacientes_co.xlsx`
(demografía colombiana). `dataset_final.xlsx` (las 3.991 conversaciones
guionizadas) NO se usa aquí — no hace falta para poblar el selector de
casos de `/call`; es material para un futuro arnés de evaluación
automatizada (fuera de alcance de este adapter).

Join real del dataset (no inventado, confirmado inspeccionando los
archivos con `openpyxl`): `paciente_id` conecta los tres archivos;
`caso_id = "caso_" + trayectoria_id`."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.ports.challenge_case import (
    CaseFilters,
    CaseSummary,
    ChallengeCase,
    ChallengeCasePort,
    ReferenceTrajectory,
)

logger = logging.getLogger("care_companion.dataset")

TRAYECTORIAS_FILE = "trayectorias_postop_silver.xlsx"
PERFILES_CLINICOS_FILE = "perfiles_clinicos_pacientes_silver_contest.xlsx"
PERFILES_DEMOGRAFICOS_FILE = "perfiles_pacientes_co.xlsx"

REQUIRED_FILES = (TRAYECTORIAS_FILE, PERFILES_CLINICOS_FILE, PERFILES_DEMOGRAFICOS_FILE)


class DatasetFilesMissingError(Exception):
    """Falta alguno de los `.xlsx` requeridos en `dataset_dir`. El caller
    (`main.py`) decide qué hacer — hoy, caer a `FixtureCaseAdapter` con un
    warning explícito en el log, nunca fingir que el dataset real está
    cargado cuando no lo está (spec.md §11.2)."""

    def __init__(self, dataset_dir: Path, missing: list[str]) -> None:
        self.dataset_dir = dataset_dir
        self.missing = missing
        super().__init__(
            f"Faltan archivos del dataset en {dataset_dir}: {', '.join(missing)} "
            "— correr `uv run python scripts/fetch_dataset.py`."
        )


def _read_rows(path: Path) -> list[dict[str, Any]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)
        header = [str(cell) for cell in next(rows)]
        return [dict(zip(header, row, strict=True)) for row in rows if any(row)]
    finally:
        wb.close()


def _parse_json_cell(value: Any) -> list[str]:
    """`comorbilidades` viene como una lista JSON dentro de una celda de
    texto (README oficial del kit, sección "Antes de que empieces"). Si el
    valor no es JSON válido, se registra vacío en vez de romper la carga
    completa por una fila con datos sucios — un caso con metadata
    incompleta es preferible a que el selector de casos entero no cargue."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("dataset_comorbilidades_json_invalido valor=%r", value)
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


@dataclass(frozen=True)
class _PatientClinicalProfile:
    procedure: str
    procedure_category: str
    age: int | None
    gender: str | None
    comorbidities: list[str]


@dataclass(frozen=True)
class _PatientDemographics:
    display_name: str
    city: str | None
    department: str | None


def _load_clinical_profiles(dataset_dir: Path) -> dict[str, _PatientClinicalProfile]:
    profiles: dict[str, _PatientClinicalProfile] = {}
    for row in _read_rows(dataset_dir / PERFILES_CLINICOS_FILE):
        paciente_id = row["paciente_id"]
        profiles[paciente_id] = _PatientClinicalProfile(
            procedure=row.get("procedimiento") or "",
            procedure_category=row.get("modulo_synthea") or "",
            age=row.get("edad"),
            gender=row.get("genero"),
            comorbidities=_parse_json_cell(row.get("comorbilidades")),
        )
    return profiles


def _load_demographics(dataset_dir: Path) -> dict[str, _PatientDemographics]:
    demographics: dict[str, _PatientDemographics] = {}
    for row in _read_rows(dataset_dir / PERFILES_DEMOGRAFICOS_FILE):
        paciente_id = row["paciente_id"]
        demographics[paciente_id] = _PatientDemographics(
            display_name=row.get("nombre_completo") or paciente_id,
            city=row.get("ciudad"),
            department=row.get("departamento"),
        )
    return demographics


def _build_cases(dataset_dir: Path) -> dict[str, ChallengeCase]:
    clinical = _load_clinical_profiles(dataset_dir)
    demographics = _load_demographics(dataset_dir)

    cases: dict[str, ChallengeCase] = {}
    for row in _read_rows(dataset_dir / TRAYECTORIAS_FILE):
        trayectoria_id = row["trayectoria_id"]
        paciente_id = row["paciente_id"]
        case_id = f"caso_{trayectoria_id}"
        dia_postop = int(row["dia_postop"])

        profile = clinical.get(paciente_id)
        demo = demographics.get(paciente_id)
        if profile is None or demo is None:
            # Fila de trayectoria sin perfil clínico/demográfico asociado —
            # dato incompleto, se omite ese caso en vez de fabricar
            # valores por defecto que parecerían reales.
            logger.warning(
                "dataset_trayectoria_sin_perfil paciente_id=%s trayectoria_id=%s",
                paciente_id, trayectoria_id,
            )
            continue

        cases[case_id] = ChallengeCase(
            case_id=case_id,
            patient_display_name=demo.display_name,
            procedure=profile.procedure,
            procedure_category=profile.procedure_category,
            phase=f"post_discharge_day_{dia_postop}",
            days_since_procedure=dia_postop,
            caregiver_role="paciente o acompañante",
            notes=(
                "Caso del dataset oficial del reto (sintético, adaptado a "
                "Colombia) — no corresponde a una persona real."
            ),
            age=profile.age,
            gender=profile.gender,
            comorbidities=profile.comorbidities,
            city=demo.city,
            department=demo.department,
            reference_trajectory=ReferenceTrajectory(
                arquetipo=row.get("arquetipo_trayectoria") or "",
                dolor_nrs=int(row["dolor_nrs"]) if row.get("dolor_nrs") is not None else 0,
                fiebre_c=float(row["fiebre_c"]) if row.get("fiebre_c") is not None else 0.0,
                movilidad=row.get("movilidad") or "",
                herida=row.get("herida") or "",
                apetito=row.get("apetito") or "",
                sueno=row.get("sueno") or "",
            ),
        )
    return cases


def check_dataset_files_present(dataset_dir: Path) -> list[str]:
    """Devuelve la lista de archivos requeridos que faltan (vacía si están
    todos) — el caller decide si eso es fatal o si cae a fixtures."""
    return [name for name in REQUIRED_FILES if not (dataset_dir / name).is_file()]


class DatasetCaseAdapter(ChallengeCasePort):
    """Carga los 3 `.xlsx` una sola vez en memoria al construirse (160
    casos, trivial en tamaño) — no hay necesidad de releer disco por
    request; los archivos no cambian en caliente durante una sesión del
    reto."""

    def __init__(self, dataset_dir: str | Path) -> None:
        dataset_dir = Path(dataset_dir)
        missing = check_dataset_files_present(dataset_dir)
        if missing:
            raise DatasetFilesMissingError(dataset_dir, missing)
        self._cases = _build_cases(dataset_dir)
        logger.info("dataset_case_adapter_loaded case_count=%d", len(self._cases))

    async def list_cases(self, filters: CaseFilters) -> list[CaseSummary]:
        cases = list(self._cases.values())
        if filters.procedure:
            needle = filters.procedure.strip().lower()
            cases = [
                c
                for c in cases
                if c.procedure.lower() == needle or c.procedure_category.lower() == needle
            ]
        cases = cases[: filters.limit]
        return [
            CaseSummary(
                case_id=c.case_id,
                patient_display_name=c.patient_display_name,
                procedure=c.procedure,
                procedure_category=c.procedure_category,
                phase=c.phase,
                days_since_procedure=c.days_since_procedure,
            )
            for c in cases
        ]

    async def get_case(self, case_id: str) -> ChallengeCase | None:
        return self._cases.get(case_id)


__all__ = [
    "DatasetCaseAdapter",
    "DatasetFilesMissingError",
    "check_dataset_files_present",
]
