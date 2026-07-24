"""RAG-004 — `FakeEmbeddings` (n-gramas, no hash de texto completo) y
`EmbeddingsCache` (batching + cache por checksum de texto)."""

from __future__ import annotations

import math

from app.adapters.fake_embeddings import FakeEmbeddings
from app.services.embeddings_cache import EmbeddingsCache


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def test_fake_embeddings_similar_texts_are_closer_than_unrelated() -> None:
    embeddings = FakeEmbeddings(dimensions=128)
    related_a = "siento calor en la herida y esta enrojecida"
    related_b = "la herida presenta calor y enrojecimiento"
    unrelated = "el clima de hoy esta soleado y agradable"

    vectors = await embeddings.embed([related_a, related_b, unrelated])
    sim_related = _cosine(vectors[0], vectors[1])
    sim_unrelated = _cosine(vectors[0], vectors[2])

    assert sim_related > sim_unrelated


async def test_fake_embeddings_identical_text_has_cosine_one() -> None:
    embeddings = FakeEmbeddings(dimensions=64)
    text = "misma frase exacta"
    vectors = await embeddings.embed([text, text])
    assert abs(_cosine(vectors[0], vectors[1]) - 1.0) < 1e-6


async def test_embeddings_cache_reuses_vector_for_repeated_text() -> None:
    class CountingEmbeddings:
        def __init__(self) -> None:
            self.calls = 0
            self._inner = FakeEmbeddings(dimensions=32)

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls += 1
            return await self._inner.embed(texts)

    inner = CountingEmbeddings()
    cache = EmbeddingsCache(inner)

    first = await cache.embed_batch(["hola mundo", "adios mundo"])
    assert inner.calls == 1
    second = await cache.embed_batch(["hola mundo", "otro texto nuevo"])
    assert inner.calls == 2  # solo se pide el texto nuevo, "hola mundo" viene de caché
    assert first[0] == second[0]


async def test_embeddings_cache_deduplicates_within_same_batch() -> None:
    class CountingEmbeddings:
        def __init__(self) -> None:
            self.requested_texts: list[str] = []
            self._inner = FakeEmbeddings(dimensions=32)

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.requested_texts.extend(texts)
            return await self._inner.embed(texts)

    inner = CountingEmbeddings()
    cache = EmbeddingsCache(inner)

    vectors = await cache.embed_batch(["repetido", "repetido", "distinto"])
    assert inner.requested_texts == ["repetido", "distinto"]
    assert vectors[0] == vectors[1]


async def test_embeddings_cache_evict_removes_entry() -> None:
    cache = EmbeddingsCache(FakeEmbeddings(dimensions=16))
    await cache.embed_batch(["texto a olvidar", "texto a conservar"])
    assert len(cache) == 2

    removed = cache.evict(["texto a olvidar"])
    assert removed == 1
    assert len(cache) == 1

    # evict de algo que no está en caché es un no-op informativo, no un error
    assert cache.evict(["nunca estuvo aquí"]) == 0
