"""AI-001 — adapter real de `LLMPort` sobre el protocolo OpenAI-compatible
(Groq/Ollama, docs/auditoria-kit-oficial-2026-08-07.md §3) y `FallbackLLM`.

Sin red real: `httpx.MockTransport` sustituye la conexión HTTP por un
handler determinista, siguiendo el mismo principio que el resto de adapters
del proyecto (`FakeLLM`, `FakeEmbeddings`) — comportamiento real del
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
