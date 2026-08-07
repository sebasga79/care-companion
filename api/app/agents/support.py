"""Soporte compartido de invocación LLM para agentes (architecture.md §6.2).

Reglas del contrato de agente que vive aquí, en un único lugar, para que
`InterviewAgent`/`TriageAgent`/`ResponseAgent` no reimplementen cada uno su
propia política de reintento/presupuesto:

- tiempo máximo por intento (`deadline_ms`, viene de `AgentRequest`);
- máximo UN reintento ante timeout o salida inválida (2 intentos totales);
- ante el segundo fallo, se lanza `AgentInvocationError` — el agente
  llamador la atrapa y construye un `AgentResult(status="error")`
  estructurado (fallback determinista, spec.md §9.3 política de error);
  nunca se deja una excepción sin manejar escapar hacia el orquestador
  como un fallo "silencioso".

Este módulo NO llama a otro agente ni conoce el dominio clínico — es
exclusivamente el mecanismo de invocación del `LLMPort` inyectado."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import ValidationError

from app.domain.models import UsageMetrics
from app.ports.llm import LLMMessage, LLMPort

T = TypeVar("T")

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_payload(text: str) -> str:
    """Pela el envoltorio más común que un LLM real agrega alrededor de un
    objeto JSON pese a que el prompt pida "solo JSON": fences de markdown
    (```json ... ```) o una frase antes/después del objeto. No es un parser
    laxo — solo recorta hasta el primer `{`/último `}` plausible; `parse`
    (Pydantic) sigue validando la forma real. `FakeLLM`/`ScriptedFakeLLM`
    siempre devuelven JSON limpio, así que esto solo importa con un
    proveedor real (Groq/Ollama) que no respete el formato al 100 % pese a
    `response_format=json_object`."""
    stripped = text.strip()
    match = _JSON_FENCE_RE.search(stripped)
    if match:
        return match.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


class AgentInvocationError(Exception):
    """Se agotaron los intentos permitidos (1 llamada + 1 reintento) sin
    obtener una salida válida del LLM inyectado. `usage` refleja el último
    intento realizado (puede ser `UsageMetrics()` en blanco si todos los
    intentos fueron timeout antes de recibir respuesta)."""

    def __init__(self, reason: str, *, attempts: int, usage: UsageMetrics) -> None:
        self.reason = reason
        self.attempts = attempts
        self.usage = usage
        super().__init__(reason)


async def invoke_structured(
    llm: LLMPort,
    *,
    messages: list[LLMMessage],
    response_schema: dict | None,
    deadline_ms: int,
    parse: Callable[[str], T],
    max_retries: int = 1,
) -> tuple[T, UsageMetrics]:
    """Llama a `llm.generate`, valida/parsea la salida con `parse` y
    reintenta como máximo `max_retries` veces ante timeout, error del
    proveedor o salida inválida (JSON mal formado / no cumple el schema
    Pydantic que `parse` aplica). Si el último intento también falla,
    lanza `AgentInvocationError` en vez de devolver un resultado a medias
    o inventado — "no defaults inseguros" (spec.md §11.2)."""
    last_reason = "no se realizó ningún intento"
    usage = UsageMetrics()
    attempts = 0
    deadline_s = max(deadline_ms, 1) / 1000

    for _attempt in range(max_retries + 1):
        attempts += 1
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                llm.generate(messages=messages, response_schema=response_schema),
                timeout=deadline_s,
            )
        except TimeoutError:
            last_reason = f"timeout del LLM tras {deadline_ms}ms (intento {attempts})"
            continue
        except Exception as exc:  # el adapter concreto puede lanzar errores de proveedor
            last_reason = f"error del proveedor LLM en intento {attempts}: {exc}"
            continue

        latency_ms = (time.monotonic() - start) * 1000
        usage = UsageMetrics(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency_ms,
            provider=result.provider,
            model=result.model,
        )
        try:
            parsed = parse(result.text)
        except (ValueError, ValidationError) as exc:
            last_reason = f"salida inválida en intento {attempts}: {exc}"
            continue

        return parsed, usage

    raise AgentInvocationError(last_reason, attempts=attempts, usage=usage)


__all__ = ["AgentInvocationError", "extract_json_payload", "invoke_structured"]
