"""`ChallengeCasePort` — aísla la fuente de casos del reto (spec.md §11.3).

Hasta que exista el Delta Share real (ticket DATA-001), el único adapter es
`FixtureCaseAdapter` sobre fixtures sintéticos propios (ADR-001)."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class CaseFilters(BaseModel):
    procedure: str | None = None
    limit: int = 20


class CaseSummary(BaseModel):
    case_id: str
    patient_display_name: str
    procedure: str
    phase: str
    days_since_procedure: int


class ChallengeCase(BaseModel):
    case_id: str
    patient_display_name: str
    procedure: str
    phase: str
    days_since_procedure: int
    caregiver_role: str
    notes: str | None = None


class ChallengeCasePort(Protocol):
    async def list_cases(self, filters: CaseFilters) -> list[CaseSummary]: ...

    async def get_case(self, case_id: str) -> ChallengeCase | None: ...
