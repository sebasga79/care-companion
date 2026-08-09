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

from app.adapters.combined_cases import CombinedCaseAdapter
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
            "trayectoria_id",
            "paciente_id",
            "dia_postop",
            "arquetipo_trayectoria",
            "dolor_nrs",
            "fiebre_c",
            "movilidad",
            "herida",
            "apetito",
            "sueno",
        ],
        [
            (
                "tray_x_1",
                "pac_x",
                1,
                "recuperacion_normal",
                1,
                36.8,
                "normal",
                "normal",
                "normal",
                "normal",
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


def test_agent_deadline_grows_when_a_fallback_is_configured(
    clean_env: None, monkeypatch
) -> None:
    """Regresión de un resguardo que no podía dispararse. El deadline por
    intento envuelve `LLMPort.generate`, y con `FallbackLLM` eso cubre
    primario + resguardo. Con el valor fijo de 5.000 ms y un modelo local
    medido en ~5.600 ms, el resguardo se cancelaba antes de contestar:
    estaba configurado pero era inalcanzable."""
    from app.orchestrator.call_cycle import (
        AGENT_DEADLINE_MS,
        AGENT_DEADLINE_WITH_FALLBACK_MS,
        default_agent_deadline_ms,
    )

    assert default_agent_deadline_ms(has_fallback=False) == AGENT_DEADLINE_MS
    assert default_agent_deadline_ms(has_fallback=True) == AGENT_DEADLINE_WITH_FALLBACK_MS
    # El resguardo local medido tarda ~5,6 s: el presupuesto tiene que
    # dejarle margen real, no apenas alcanzarlo.
    assert AGENT_DEADLINE_WITH_FALLBACK_MS >= 15000

    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    app = create_app()
    orchestrator = app.state.call_cycle_orchestrator
    assert orchestrator._agent_deadline_ms == AGENT_DEADLINE_WITH_FALLBACK_MS  # noqa: SLF001


def test_create_app_uses_dataset_case_adapter_when_dataset_present(
    clean_env: None, monkeypatch, tmp_path: Path
) -> None:
    dataset_dir = tmp_path / "real-dataset"
    _write_minimal_dataset(dataset_dir)
    monkeypatch.setenv("DATASET_DIR", str(dataset_dir))

    app = create_app()
    # Con dataset presente, `_build_case_port` envuelve el adapter real en
    # `CombinedCaseAdapter` (auditoría §9.22): los 3 casos de prueba de
    # `FixtureCaseAdapter` siguen alcanzables para `/knowledge`, no
    # desaparecen sólo porque el dataset real cargó.
    assert isinstance(app.state.case_port, CombinedCaseAdapter)
    assert isinstance(app.state.case_port._primary, DatasetCaseAdapter)  # noqa: SLF001
