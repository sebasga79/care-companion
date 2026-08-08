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

import asyncio
import logging
import re

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



# Groq responde 429 indicando exactamente cuánto esperar, en la cabecera
# `retry-after` y también en el texto ("Please try again in 3.73s"). Antes
# se ignoraba: el 429 se trataba como cualquier error y la llamada degradaba
# al resguardo local, 20 veces más lento y con otro modelo. Esperar los
# segundos que el propio proveedor pide es lo correcto — y para medir
# (`scripts/benchmark.py`) es la diferencia entre medir el modelo declarado
# o medir el resguardo.
_RETRY_AFTER_TEXT_RE = re.compile(r"try again in\s+(?P<seconds>\d+(?:\.\d+)?)\s*s", re.I)


def _parse_retry_after_seconds(response: httpx.Response) -> float | None:
    """Segundos que el proveedor pide esperar, o `None` si no lo indica."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    match = _RETRY_AFTER_TEXT_RE.search(response.text or "")
    return float(match.group("seconds")) if match else None


class OpenAICompatLLM(LLMPort):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        provider_name: str,
        timeout_seconds: float = 20.0,
        rate_limit_max_retries: int = 0,
        rate_limit_max_wait_seconds: float = 10.0,
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
        # 0 por defecto: en una conversación en vivo, hacer esperar al
        # paciente varios segundos es peor que responder con el modelo de
        # resguardo. El benchmark sí los sube, porque ahí lo que importa
        # es medir el modelo declarado y no el resguardo.
        self._rate_limit_max_retries = rate_limit_max_retries
        self._rate_limit_max_wait_seconds = rate_limit_max_wait_seconds
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

        attempt = 0
        while True:
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

            # 429 es distinto de un error real: el proveedor dice "vuelve en
            # N segundos". Si el llamador autorizó esperar (y la espera es
            # razonable), se respeta en vez de degradar al resguardo.
            if response.status_code == 429 and attempt < self._rate_limit_max_retries:
                wait_seconds = _parse_retry_after_seconds(response)
                if wait_seconds is not None and wait_seconds <= self._rate_limit_max_wait_seconds:
                    attempt += 1
                    logger.info(
                        "llm_rate_limited_waiting provider=%s wait_s=%.2f attempt=%d",
                        self._provider_name,
                        wait_seconds,
                        attempt,
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

            if response.status_code >= 400:
                raise LLMProviderError(
                    f"{self._provider_name}: HTTP {response.status_code} — {response.text[:300]}"
                )
            break

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
