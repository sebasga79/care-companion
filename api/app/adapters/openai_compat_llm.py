"""`OpenAICompatLLM` — adapter de `LLMPort` sobre cualquier proveedor que
hable el protocolo de Chat Completions estilo OpenAI en `/chat/completions`
(ADR-001/ADR-005: el dominio nunca importa un SDK de proveedor concreto,
solo este adapter).

Groq y Ollama —los dos proveedores reales de este proyecto, ver
`docs/auditoria-kit-oficial-2026-08-07.md` §3— exponen exactamente ese
protocolo, así que un solo adapter HTTP (`httpx`, ya es dependencia) basta
para ambos: lo único que cambia entre "Groq" y "Ollama" es `base_url`,
`api_key` y `model` (`app/core/config.py`)."""

from __future__ import annotations

import logging

import httpx

from app.ports.llm import LLMMessage, LLMPort, LLMResult

logger = logging.getLogger("care_companion.llm")


class LLMProviderError(Exception):
    """Fallo al invocar el proveedor: red/timeout, HTTP no-2xx, o respuesta
    sin el shape esperado. `FallbackLLM` (`app/adapters/fallback_llm.py`)
    la usa como señal de "probar el adapter de resguardo"; sin resguardo
    configurado, se propaga tal cual hasta el caller (spec.md §11 — ante
    fallo de modelo con riesgo, el estado seguro es abstenerse/escalar, no
    fingir una respuesta)."""


class OpenAICompatLLM(LLMPort):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        provider_name: str,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`transport` solo se usa desde tests (`httpx.MockTransport`) para
        no golpear red real; en producción se deja `None` y `httpx` arma su
        transporte real de conexión."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._provider_name = provider_name
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def generate(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: dict | None = None,
    ) -> LLMResult:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if response_schema is not None:
            # Subconjunto de proveedores soporta JSON mode estricto por este
            # campo (Groq, compatible con el shape de OpenAI); el que no lo
            # reconozca simplemente lo ignora — degradación aceptable, el
            # caller (app/agents/support.py) ya valida/reintenta sobre texto.
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"{self._provider_name}: fallo de red/timeout llamando al modelo: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise LLMProviderError(
                f"{self._provider_name}: HTTP {response.status_code} — {response.text[:300]}"
            )

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMProviderError(
                f"{self._provider_name}: respuesta con forma inesperada: {exc}"
            ) from exc

        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            model=data.get("model") or self._model,
            provider=self._provider_name,
        )
