"""`FakeEmbeddings` — adapter determinista de `EmbeddingsPort` para
tests/desarrollo. Genera vectores estables a partir de un hash del texto
(mismo texto -> mismo vector), sin llamar a ningún proveedor externo."""

from __future__ import annotations

import hashlib

from app.ports.embeddings import EmbeddingsPort

_DIMENSIONS = 16


class FakeEmbeddings(EmbeddingsPort):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[:_DIMENSIONS]]
