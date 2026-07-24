"""`FakeEmbeddings` — adapter determinista de `EmbeddingsPort` (RAG-004).

Sin llamadas externas. Usa una bolsa de n-gramas de caracteres con
"feature hashing" (truco de hashing, à la scikit-learn `HashingVectorizer`):
cada n-grama se hashea a una dimensión fija y a un signo (+1/-1) derivados
del mismo hash, se acumulan las contribuciones y se normaliza L2 al final.

Esto da tres propiedades necesarias para que el coseno sea significativo en
tests (RAG-005/006), no solo "estable":

- mismo texto -> mismo vector (determinismo, hash puro sobre el texto);
- textos que comparten vocabulario/n-gramas -> vectores cercanos en
  coseno (a diferencia de un hash de texto completo, donde un solo
  carácter distinto cambia todo el vector sin relación con el anterior);
- textos sin relación -> vectores casi ortogonales en expectativa (las
  contribuciones de n-gramas no compartidos caen en dimensiones distintas
  o se cancelan por el signo aleatorio-mas-determinista).

Sin dependencias nuevas (hashlib + math, stdlib) — el propio proyecto usa
NumPy para el cómputo de coseno sobre embeddings ya materializados
(RAG-005), pero generar el vector aquí no lo requiere."""

from __future__ import annotations

import hashlib
import math

from app.ports.embeddings import EmbeddingsPort

DEFAULT_DIMENSIONS = 128
_NGRAM_SIZE = 3
_BOUNDARY = ""  # marcador de inicio/fin, para pesar bordes de palabra


class FakeEmbeddings(EmbeddingsPort):
    """`dimensions` debe coincidir entre todas las llamadas que se vayan a
    comparar por coseno (documentos indexados y queries) — normalmente
    `Settings.rag_embedding_dimensions`."""

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for ngram in _char_ngrams(text, _NGRAM_SIZE):
            index, sign = _hash_feature(ngram, self._dimensions)
            vector[index] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            # Texto vacío/degenerado (p. ej. solo espacios tras strip): sin
            # n-gramas que aportar. Vector cero es una representación
            # honesta de "sin contenido" — no se inventa una dirección
            # aleatoria (eso rompería el determinismo).
            return vector
        return [component / norm for component in vector]


def _char_ngrams(text: str, n: int) -> list[str]:
    normalized = _BOUNDARY + " ".join(text.lower().split()) + _BOUNDARY
    if len(normalized) < n:
        return [normalized] if normalized else []
    return [normalized[i : i + n] for i in range(len(normalized) - n + 1)]


def _hash_feature(ngram: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.sha256(ngram.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % dimensions
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return index, sign
