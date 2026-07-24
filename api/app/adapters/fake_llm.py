"""`FakeLLM` — adapter determinista de `LLMPort` para tests y desarrollo sin
credenciales (REP-002/ORC-001). No es el modelo obligatorio del reto; se
reemplaza en AI-001 sin tocar dominio (ADR-001)."""

from __future__ import annotations

from app.ports.llm import LLMMessage, LLMPort, LLMResult


class FakeLLM(LLMPort):
    def __init__(self, model: str = "fake-model-v1") -> None:
        self._model = model

    async def generate(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: dict | None = None,
    ) -> LLMResult:
        last_user_message = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        text = f"[fake-llm] respuesta determinista a: {last_user_message[:80]}"
        return LLMResult(
            text=text,
            input_tokens=len(last_user_message.split()),
            output_tokens=len(text.split()),
            model=self._model,
            provider="fake",
        )
