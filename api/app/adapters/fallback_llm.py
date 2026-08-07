"""`FallbackLLM` — envuelve un `LLMPort` primario y uno de resguardo.

Decisión de arquitectura (`docs/auditoria-kit-oficial-2026-08-07.md` §3):
Groq es el modelo primario (nube, free tier) y Ollama el de resguardo local.
Si la sesión de evaluación en vivo (gates G2/G4) no tiene red, o Groq
responde con error/rate-limit/timeout, la llamada sigue con el modelo local
en vez de que el agente se quede sin `LLMPort` — un resguardo nunca
ejercitado no es, en la práctica, un resguardo (auditoría §8)."""

from __future__ import annotations

import logging

from app.adapters.openai_compat_llm import LLMProviderError
from app.ports.llm import LLMMessage, LLMPort, LLMResult

logger = logging.getLogger("care_companion.llm")


class FallbackLLM(LLMPort):
    def __init__(self, primary: LLMPort, fallback: LLMPort) -> None:
        self._primary = primary
        self._fallback = fallback

    async def generate(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: dict | None = None,
    ) -> LLMResult:
        try:
            return await self._primary.generate(
                messages=messages, response_schema=response_schema
            )
        except LLMProviderError:
            logger.warning(
                "llm_primary_failed_falling_back_to_secondary", exc_info=True
            )
            return await self._fallback.generate(
                messages=messages, response_schema=response_schema
            )
