"""`LLMPort` — interfaz del modelo de lenguaje (ADR-001, ADR-005).

Ningún módulo de `domain/` importa esto directamente con un SDK concreto;
solo `adapters/` implementa el puerto. El modelo obligatorio del 7 de
agosto se conecta implementando esta misma interfaz sin tocar dominio."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResult(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class LLMPort(Protocol):
    async def generate(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: dict | None = None,
    ) -> LLMResult: ...
