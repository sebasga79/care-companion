"""`EmbeddingsPort` — interfaz de embeddings para RAG (RAG-004, Sprint C2)."""

from __future__ import annotations

from typing import Protocol


class EmbeddingsPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
