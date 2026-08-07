"""`ChallengeCasePort` — aísla la fuente de casos del reto (spec.md §11.3).

Dos adapters: `FixtureCaseAdapter` (3 casos sintéticos propios, ADR-001,
usado si el dataset real no está descargado) y `DatasetCaseAdapter`
(dataset real del kit oficial — `.xlsx`, no Delta Share, ver
docs/auditoria-kit-oficial-2026-08-07.md §4.2/§9.2 — la construcción
anticipada asumió Delta Share; el reto real entrega 4 `.xlsx` + PDFs)."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class CaseFilters(BaseModel):
    procedure: str | None = None
    limit: int = 20


class CaseSummary(BaseModel):
    case_id: str
    patient_display_name: str
    procedure: str
    # `procedure_category` es el identificador corto/en inglés (p. ej.
    # "appendicitis") que mapea 1:1 a una carpeta de `dataset/textos/` del
    # corpus oficial — es lo que el RAG usa para acotar la búsqueda al
    # material clínico relevante para ESTE procedimiento (`applicability`
    # de un documento, ver app/services/ingestion.py). `procedure` es el
    # nombre clínico en español para mostrar ("Apendicectomía").
    procedure_category: str
    phase: str
    days_since_procedure: int


class ReferenceTrajectory(BaseModel):
    """Cuadro clínico real de este caso (`trayectorias_postop_silver.xlsx`
    del dataset oficial) — SOLO contexto de referencia para quien actúa de
    paciente/cuidador en la demo (una persona hablando por el micrófono).
    El `InterviewAgent` NUNCA recibe esto en su prompt: debe indagarlo
    conversando, igual que en la evaluación real del jurado — pasarlo
    directo sería literalmente lo que `spec.md` prohíbe ("el agente solo
    puede averiguar conversando", docs/auditoria-kit-oficial-2026-08-07.md
    §1.2)."""

    arquetipo: str
    dolor_nrs: int
    fiebre_c: float
    movilidad: str
    herida: str
    apetito: str
    sueno: str


class ChallengeCase(BaseModel):
    case_id: str
    patient_display_name: str
    procedure: str
    procedure_category: str
    phase: str
    days_since_procedure: int
    caregiver_role: str
    notes: str | None = None
    # Campos reales del dataset oficial (perfiles_clinicos_pacientes_
    # silver_contest.xlsx / perfiles_pacientes_co.xlsx) — `None` en
    # `FixtureCaseAdapter` (los 3 casos inventados no tienen esta
    # profundidad; no se fabrica el dato, se declara ausente).
    age: int | None = None
    gender: str | None = None
    comorbidities: list[str] = Field(default_factory=list)
    city: str | None = None
    department: str | None = None
    reference_trajectory: ReferenceTrajectory | None = None


class ChallengeCasePort(Protocol):
    async def list_cases(self, filters: CaseFilters) -> list[CaseSummary]: ...

    async def get_case(self, case_id: str) -> ChallengeCase | None: ...
