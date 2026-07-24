"""`GET /api/v1/cases` — casos disponibles vía `ChallengeCasePort` (API-001)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_case_port
from app.ports.challenge_case import CaseFilters, CaseSummary, ChallengeCasePort

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[CaseSummary])
async def list_cases(
    case_port: ChallengeCasePort = Depends(get_case_port),
) -> list[CaseSummary]:
    return await case_port.list_cases(CaseFilters())
