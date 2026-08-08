"""`OpenAICompatEmbeddings` — adapter de `EmbeddingsPort` sobre el
protocolo de embeddings estilo OpenAI (`POST {base_url}/embeddings`).

Decisión (docs/auditoria-kit-oficial-2026-08-07.md §3/§9): Ollama sirve
BGE-M3 localmente vía este mismo protocolo — reusa la infraestructura que
ya vamos a tener encendida como resguardo del LLM (`app/adapters/
openai_compat_llm.py`), sin sumar un segundo proveedor de nube. BGE-M3 es
el modelo de embeddings que el propio kit del reto sugiere para español
(`docs/stack-tecnico.md` §4: "entiende sinónimos médicos y conceptos
complejos en nuestro idioma")."""

from __future__ import annotations

import httpx

from app.ports.embeddings import EmbeddingsPort


class EmbeddingsProviderError(Exception):
    """Fallo al invocar el proveedor de embeddings (red/timeout/HTTP
    no-2xx/forma inesperada). A diferencia del LLM, no hay resguardo
    automático aquí: si el proveedor configurado falla, es mejor fallar
    fuerte y visible que indexar contenido con un vector degradado o
    inventado en silencio (spec.md §11, "no defaults inseguros")."""


class OpenAICompatEmbeddings(EmbeddingsPort):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        provider_name: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`transport` solo se usa desde tests (`httpx.MockTransport`)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._provider_name = provider_name
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    json={"model": self._model, "input": texts},
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise EmbeddingsProviderError(
                f"{self._provider_name}: fallo de red/timeout llamando a embeddings: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise EmbeddingsProviderError(
                f"{self._provider_name}: HTTP {response.status_code} — {response.text[:300]}"
            )

        try:
            data = response.json()
            items = sorted(data["data"], key=lambda item: item.get("index", 0))
            vectors = [item["embedding"] for item in items]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise EmbeddingsProviderError(
                f"{self._provider_name}: respuesta con forma inesperada: {exc}"
            ) from exc

        if len(vectors) != len(texts):
            raise EmbeddingsProviderError(
                f"{self._provider_name}: se pidieron {len(texts)} vectores, llegaron {len(vectors)}"
            )
        return vectors
