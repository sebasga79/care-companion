"""AI-001 — adapter real de `LLMPort` sobre el protocolo OpenAI-compatible
(Groq/Ollama, docs/auditoria-kit-oficial-2026-08-07.md §3) y `FallbackLLM`.

Sin red real: `httpx.MockTransport` sustituye la conexión HTTP por un
handler determinista, siguiendo el mismo principio que el resto de adapters
del proyecto (dobles deterministas de LLM y embeddings locales) — comportamiento real del
protocolo, sin credenciales ni servicios externos en CI."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.fallback_llm import FallbackLLM
from app.adapters.openai_compat_llm import LLMProviderError, OpenAICompatLLM
from app.ports.llm import LLMMessage, LLMResult


def _adapter(handler, *, provider_name: str = "groq") -> OpenAICompatLLM:
    return OpenAICompatLLM(
        base_url="https://api.example.test/openai/v1",
        api_key="test-key",
        model="test-model",
        provider_name=provider_name,
        transport=httpx.MockTransport(handler),
    )


async def test_generate_maps_text_and_token_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "hola, ¿cómo sigue?"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            },
        )

    result = await _adapter(handler).generate(
        messages=[LLMMessage(role="user", content="tengo fiebre")]
    )
    assert isinstance(result, LLMResult)
    assert result.text == "hola, ¿cómo sigue?"
    assert result.input_tokens == 42
    assert result.output_tokens == 7
    assert result.provider == "groq"
    assert result.model == "test-model"


async def test_generate_sends_json_response_format_when_schema_given() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}], "usage": {}},
        )

    await _adapter(handler).generate(
        messages=[LLMMessage(role="user", content="x")],
        response_schema={"type": "object"},
    )
    assert captured["body"]["response_format"] == {"type": "json_object"}


async def test_generate_raises_provider_error_on_http_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    with pytest.raises(LLMProviderError, match="HTTP 401"):
        await _adapter(handler).generate(messages=[LLMMessage(role="user", content="x")])


async def test_generate_raises_provider_error_on_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(LLMProviderError, match="forma inesperada"):
        await _adapter(handler).generate(messages=[LLMMessage(role="user", content="x")])


async def test_generate_raises_provider_error_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    with pytest.raises(LLMProviderError, match="red/timeout"):
        await _adapter(handler).generate(messages=[LLMMessage(role="user", content="x")])


async def test_generate_defaults_missing_usage_to_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    result = await _adapter(handler).generate(messages=[LLMMessage(role="user", content="x")])
    assert result.input_tokens == 0
    assert result.output_tokens == 0


async def test_fallback_uses_primary_when_healthy() -> None:
    def primary_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "respuesta primaria"}}], "usage": {}}
        )

    def fallback_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería llamarse al resguardo si el primario funciona")

    fallback_llm = FallbackLLM(
        _adapter(primary_handler, provider_name="groq"),
        _adapter(fallback_handler, provider_name="ollama"),
    )
    result = await fallback_llm.generate(messages=[LLMMessage(role="user", content="x")])
    assert result.text == "respuesta primaria"
    assert result.provider == "groq"


async def test_fallback_switches_to_secondary_when_primary_fails() -> None:
    def primary_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    def fallback_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "respuesta local"}}], "usage": {}}
        )

    fallback_llm = FallbackLLM(
        _adapter(primary_handler, provider_name="groq"),
        _adapter(fallback_handler, provider_name="ollama"),
    )
    result = await fallback_llm.generate(messages=[LLMMessage(role="user", content="x")])
    assert result.text == "respuesta local"
    assert result.provider == "ollama"


async def test_fallback_propagates_error_when_both_fail() -> None:
    def always_fails(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="down")

    fallback_llm = FallbackLLM(_adapter(always_fails), _adapter(always_fails))
    with pytest.raises(LLMProviderError):
        await fallback_llm.generate(messages=[LLMMessage(role="user", content="x")])


# --------------------------------------------------------------------- #
# 429: esperar lo que el proveedor pide, en vez de degradar al resguardo
# --------------------------------------------------------------------- #


async def test_rate_limit_is_not_retried_by_default() -> None:
    """En una conversación en vivo, hacer esperar al paciente es peor que
    responder con el resguardo: por defecto un 429 se propaga y
    `FallbackLLM` toma el relevo."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, text="Rate limit reached. Please try again in 0.01s")

    with pytest.raises(LLMProviderError, match="HTTP 429"):
        await _adapter(handler).generate(messages=[LLMMessage(role="user", content="x")])
    assert calls["n"] == 1, "sin reintentos configurados no debe reintentar"


async def test_rate_limit_waits_and_retries_when_configured() -> None:
    """Con reintentos autorizados (el benchmark), se respeta el tiempo que
    indica el proveedor y se vuelve a intentar con el MISMO modelo. Sin
    esto, medir contra Groq en el nivel gratuito medía en realidad el
    resguardo local: 20 veces más lento y con otro modelo."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="Rate limit reached. Please try again in 0.01s")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}}
        )

    adapter = OpenAICompatLLM(
        base_url="https://api.example.test/openai/v1",
        api_key="k",
        model="m",
        provider_name="groq",
        rate_limit_max_retries=2,
        rate_limit_max_wait_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    result = await adapter.generate(messages=[LLMMessage(role="user", content="x")])
    assert result.text == "ok"
    assert calls["n"] == 2


async def test_rate_limit_does_not_wait_longer_than_allowed() -> None:
    """Una espera desproporcionada (el proveedor pide minutos) no se
    acepta: mejor fallar y dejar que el resguardo responda."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit reached. Please try again in 600s")

    adapter = OpenAICompatLLM(
        base_url="https://api.example.test/openai/v1",
        api_key="k",
        model="m",
        provider_name="groq",
        rate_limit_max_retries=5,
        rate_limit_max_wait_seconds=10,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LLMProviderError, match="HTTP 429"):
        await adapter.generate(messages=[LLMMessage(role="user", content="x")])


async def test_retry_after_header_is_preferred_over_message_text() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429, headers={"retry-after": "0.01"}, text="sin texto parseable"
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}}
        )

    adapter = OpenAICompatLLM(
        base_url="https://api.example.test/openai/v1",
        api_key="k",
        model="m",
        provider_name="groq",
        rate_limit_max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    assert (await adapter.generate(messages=[LLMMessage(role="user", content="x")])).text == "ok"
