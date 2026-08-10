"""`EmbeddingsCache` — batching + cache por checksum de texto sobre
`EmbeddingsPort` (RAG-004).

Envuelve cualquier adapter (`LocalHashEmbeddings` u Ollama/BGE-M3)
llega detrás del mismo puerto) para que la ingestión no vuelva a llamar al
proveedor por un chunk cuyo texto exacto ya fue embebido antes — clave del
caché es `sha256(texto)`, no el `chunk_id` (dos chunks distintos con texto
idéntico comparten entrada de caché; determinista con `LocalHashEmbeddings` y
razonable para proveedores reales también).

`evict()` es lo que usa el flujo de borrado (RAG-009 — "purga de ...
caché de embeddings") para no dejar vectores de contenido olvidado
disponibles en memoria del proceso más tiempo del necesario."""

from __future__ import annotations

import hashlib

from app.ports.embeddings import EmbeddingsPort


def text_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingsCache:
    def __init__(self, port: EmbeddingsPort) -> None:
        self._port = port
        self._cache: dict[str, list[float]] = {}

    def __len__(self) -> int:
        return len(self._cache)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Alias de `embed_batch` que satisface `EmbeddingsPort` (Protocol
        estructural): permite pasar el caché donde se espera un puerto de
        embeddings sin puentes adicionales, p. ej. `retrieval.hybrid_search`
        y la consulta canaria del pipeline de ingestión."""
        return await self.embed_batch(texts)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        checksums = [text_checksum(text) for text in texts]

        # Deduplicar dentro del propio batch: si dos chunks del mismo
        # documento comparten texto exacto, el adapter solo se llama una vez.
        pending: dict[str, str] = {}
        for checksum, text in zip(checksums, texts, strict=True):
            if checksum not in self._cache and checksum not in pending:
                pending[checksum] = text

        if pending:
            pending_checksums = list(pending.keys())
            vectors = await self._port.embed([pending[c] for c in pending_checksums])
            for checksum, vector in zip(pending_checksums, vectors, strict=True):
                self._cache[checksum] = vector

        return [self._cache[checksum] for checksum in checksums]

    def evict(self, texts: list[str]) -> int:
        """Elimina las entradas de caché para `texts`. Devuelve cuántas
        entradas existían y fueron removidas (0 si ya no estaban — no es un
        error, solo informativo)."""
        removed = 0
        for text in texts:
            if self._cache.pop(text_checksum(text), None) is not None:
                removed += 1
        return removed
