"""RAG-004 ampliado — adapter real de `EmbeddingsPort` sobre el protocolo
de embeddings estilo OpenAI (Ollama/BGE-M3,
docs/auditoria-kit-oficial-2026-08-07.md §3/§9).

Sin red real: `httpx.MockTransport`, mismo patrón que
`test_llm_adapters.py`."""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.openai_compat_embeddings import (
    EmbeddingsProviderError,
    OpenAICompatEmbeddings,
)


def _adapter(handler) -> OpenAICompatEmbeddings:
    return OpenAICompatEmbeddings(
        base_url="https://ollama.example.test/v1",
        api_key=None,
        model="bge-m3",
        provider_name="ollama",
        transport=httpx.MockTransport(handler),
    )


async def test_embed_returns_vectors_in_request_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "bge-m3"
        assert body["input"] == ["hola", "fiebre"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2, 0.3]},
                    {"index": 0, "embedding": [0.1, 0.1]},
                ]
            },
        )

    vectors = await _adapter(handler).embed(["hola", "fiebre"])
    assert vectors == [[0.1, 0.1], [0.2, 0.3]]


async def test_embed_empty_list_short_circuits_without_http_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería llamar a la red con lista vacía")

    assert await _adapter(handler).embed([]) == []


async def test_embed_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    with pytest.raises(EmbeddingsProviderError, match="HTTP 500"):
        await _adapter(handler).embed(["hola"])


async def test_embed_raises_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    with pytest.raises(EmbeddingsProviderError, match="red/timeout"):
        await _adapter(handler).embed(["hola"])


async def test_embed_raises_on_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(EmbeddingsProviderError, match="forma inesperada"):
        await _adapter(handler).embed(["hola"])


async def test_embed_raises_when_vector_count_mismatches_input() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}]})

    with pytest.raises(EmbeddingsProviderError, match="se pidieron 2"):
        await _adapter(handler).embed(["hola", "fiebre"])
