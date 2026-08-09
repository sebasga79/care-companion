"""`CombinedCaseAdapter` — une el dataset real con los casos sintéticos de
`FixtureCaseAdapter` bajo un único `ChallengeCasePort` (auditoría §9.22,
9 ago).

Antes de esto, `FixtureCaseAdapter` sólo se usaba como resguardo de
arranque cuando faltaba el dataset (`main.py::_build_case_port`) — con el
dataset cargado, los 3 casos de prueba quedaban completamente
inalcanzables desde la API. Pedido explícito del usuario: `/knowledge`
necesita poder abrir una llamada de prueba sin forzar el protocolo
completo de un paciente longitudinal (4 seguimientos previos, historial
clínico) sólo para verificar G5 (aprender/olvidar) o hacer un smoke-test
de voz.

Composición simple sobre el mismo puerto — ningún cambio en el dominio,
consistente con el resto de la arquitectura de adapters."""

from __future__ import annotations

from app.ports.challenge_case import CaseFilters, CaseSummary, ChallengeCase, ChallengeCasePort


class CombinedCaseAdapter(ChallengeCasePort):
    def __init__(self, primary: ChallengeCasePort, extra: ChallengeCasePort) -> None:
        self._primary = primary
        self._extra = extra

    async def list_cases(self, filters: CaseFilters) -> list[CaseSummary]:
        # El `limit` de `filters` ya lo aplica cada adapter sobre su propia
        # colección; concatenar después no lo vuelve a recortar a propósito
        # — los 3 casos de prueba no deben desaparecer por quedar después
        # del límite de 200 del dataset real (hoy son 160, sin colisión,
        # pero la garantía queda explícita en vez de accidental).
        primary_cases = await self._primary.list_cases(filters)
        extra_cases = await self._extra.list_cases(filters)
        return [*primary_cases, *extra_cases]

    async def get_case(self, case_id: str) -> ChallengeCase | None:
        case = await self._primary.get_case(case_id)
        if case is not None:
            return case
        return await self._extra.get_case(case_id)
