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


class ScriptedFakeLLM(LLMPort):
    """`LLMPort` determinista y CONFIGURABLE POR ESCENARIO, para tests de
    agentes (C2) — no aleatorio, no depende de red ni credenciales.

    `scripted` es una lista ordenada de pares `(needle, response_text)`: en
    cada llamada, se concatena el contenido de todos los mensajes (system +
    user) y se devuelve la respuesta del primer `needle` que aparezca como
    substring — así un test puede "programar" con precisión qué debe
    responder el modelo ante un turno de paciente concreto (p. ej. una
    expresión ambigua del glosario) sin acoplar el agente a un mock
    específico. Si ningún `needle` matchea, se usa `default` (o se lanza un
    error explícito si no hay default, para que un prompt no cubierto por
    el guion falle rápido y visible en el test, no en silencio).

    `fail_first_n_calls` simula fallos transitorios del proveedor (para
    probar la política de "máximo 1 reintento" de `app.agents.support`):
    las primeras N llamadas lanzan una excepción antes de intentar
    matchear el guion."""

    def __init__(
        self,
        scripted: list[tuple[str, str]] | None = None,
        *,
        default: str | None = None,
        model: str = "scripted-fake-v1",
        fail_first_n_calls: int = 0,
    ) -> None:
        self._scripted = scripted or []
        self._default = default
        self._model = model
        self._fail_first_n_calls = fail_first_n_calls
        self.calls: list[list[LLMMessage]] = []

    async def generate(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: dict | None = None,
    ) -> LLMResult:
        self.calls.append(messages)

        if self._fail_first_n_calls > 0:
            self._fail_first_n_calls -= 1
            raise RuntimeError("ScriptedFakeLLM: fallo transitorio simulado del proveedor")

        full_text = "\n".join(message.content for message in messages)
        text: str | None = None
        for needle, response in self._scripted:
            if needle in full_text:
                text = response
                break
        if text is None:
            if self._default is None:
                last_user = next(
                    (m.content for m in reversed(messages) if m.role == "user"), ""
                )
                raise ValueError(
                    "ScriptedFakeLLM: ningún guion coincide y no hay `default` — "
                    f"último mensaje de usuario: {last_user[:200]!r}"
                )
            text = self._default

        return LLMResult(
            text=text,
            input_tokens=len(full_text.split()),
            output_tokens=len(text.split()),
            model=self._model,
            provider="fake-scripted",
        )
