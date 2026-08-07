"""Wiring de `create_app()` — qué `ChallengeCasePort` se activa según
`DATASET_DIR` (`app/main.py::_build_case_port`).

Regresión directa de un bug real encontrado en esta sesión: al descargar
el dataset oficial a `api/data/dataset/` (`scripts/fetch_dataset.py`), los
tests que corren desde `api/` con `DATASET_DIR` sin fijar empezaron a
recoger accidentalmente el dataset real del filesystem del desarrollador
en vez de los fixtures — rompiendo cualquier test que asuma
`demo-case-001`. `clean_env` (conftest.py) ahora fija `DATASET_DIR` a una
ruta que nunca existe; este archivo verifica el comportamiento de
`_build_case_port` en ambos sentidos explícitamente."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.adapters.dataset_case_source import (
    PERFILES_CLINICOS_FILE,
    PERFILES_DEMOGRAFICOS_FILE,
    TRAYECTORIAS_FILE,
    DatasetCaseAdapter,
)
from app.adapters.fixture_cases import FixtureCaseAdapter
from app.main import create_app


def _write_xlsx(path: Path, header: list[str], rows: list[tuple]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(path)


def _write_minimal_dataset(dataset_dir: Path) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    _write_xlsx(
        dataset_dir / TRAYECTORIAS_FILE,
        [
            "trayectoria_id", "paciente_id", "dia_postop", "arquetipo_trayectoria",
            "dolor_nrs", "fiebre_c", "movilidad", "herida", "apetito", "sueno",
        ],
        [
            (
                "tray_x_1", "pac_x", 1, "recuperacion_normal",
                1, 36.8, "normal", "normal", "normal", "normal",
            )
        ],
    )
    _write_xlsx(
        dataset_dir / PERFILES_CLINICOS_FILE,
        ["paciente_id", "modulo_synthea", "procedimiento", "edad", "genero", "comorbilidades"],
        [("pac_x", "appendicitis", "Apendicectomía", 40, "M", "[]")],
    )
    _write_xlsx(
        dataset_dir / PERFILES_DEMOGRAFICOS_FILE,
        ["paciente_id", "nombre_completo", "ciudad", "departamento"],
        [("pac_x", "Paciente X", "Cali", "Valle del Cauca")],
    )


def test_create_app_uses_fixture_case_adapter_by_default(clean_env: None) -> None:
    app = create_app()
    assert isinstance(app.state.case_port, FixtureCaseAdapter)


def test_create_app_uses_dataset_case_adapter_when_dataset_present(
    clean_env: None, monkeypatch, tmp_path: Path
) -> None:
    dataset_dir = tmp_path / "real-dataset"
    _write_minimal_dataset(dataset_dir)
    monkeypatch.setenv("DATASET_DIR", str(dataset_dir))

    app = create_app()
    assert isinstance(app.state.case_port, DatasetCaseAdapter)
