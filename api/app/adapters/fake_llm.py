"""`FakeLLM` — adapter determinista de `LLMPort` para tests y desarrollo sin
credenciales (REP-002/ORC-001, `LLM_PROVIDER=fake`, el default del proyecto
y el que anuncia el README como "no necesitas credenciales para correr el
prototipo"). No es uno de los modelos permitidos del reto (G3); se
reemplaza por un adapter real (Groq/Ollama, `app/adapters/
openai_compat_llm.py`) sin tocar dominio (ADR-001).

Contract-aware (corregido 7 ago, ver docs/auditoria-kit-oficial-2026-08-07.md
§9.2): antes, `generate()` devolvía siempre el mismo texto plano
`"[fake-llm] respuesta determinista a: ..."`, que NO es JSON válido. Como
`InterviewAgent`/`TriageAgent` (`app/agents/`) exigen JSON estricto y
agotan sus reintentos ante una respuesta no parseable, **cualquier llamada
real con el default `LLM_PROVIDER=fake` entraba en fail-safe/escalamiento
en el primer turno, siempre** — el camino "sin credenciales" que el README
anuncia como funcional nunca completaba una llamada de verdad. Esta clase
detecta, por el system prompt, a cuál de los tres agentes le está
respondiendo (mismo mecanismo de "needle" que ya usan los tests con
`ScriptedFakeLLM`) y devuelve una salida determinista que SÍ cumple el
contrato de cada uno — para que la demo sin credenciales atraviese
entrevista → retrieval → decisión → respuesta → resumen de verdad, no solo
la forma de los envelopes.

No importa nada de `app/agents/` (los adapters no dependen de agentes,
es al revés) — las formas JSON de abajo están hardcodeadas como los tests
que usan `ScriptedFakeLLM` ya hacen, no reutilizadas de un modelo Pydantic
importado."""

from __future__ import annotations

import json
import re

from app.ports.llm import LLMMessage, LLMPort, LLMResult

_INTERVIEW_MARKER = "extraer observaciones estructuradas del último turno"
_TRIAGE_MARKER = "evaluador de riesgo estructurado"
_RESPONSE_MARKER = "asistente de voz de seguimiento postoperatorio"
_RESPONSE_ABSTAIN_MARKER = "NO tienes evidencia verificada"
_RESPONSE_HANDOFF_MARKER = "Esta llamada se está escalando"

_FIRST_OBJECTIVE_RE = re.compile(r"^- (?P<code>[A-Z_]+):", re.MULTILINE)
_LAST_UTTERANCE_RE = re.compile(
    r"## Último turno del cuidador/paciente a interpretar\n(?P<text>.+)", re.DOTALL
)

_DEFAULT_OBJECTIVE_CODE = "GENERAL_STATE"


def _fake_interview_response(full_text: str) -> str:
    """Nunca declara `confirmed`/`denied` (no puede interpretar de verdad el
    lenguaje del cuidador) — registra `uncertain`, que cuenta como
    "objetivo cubierto" para el orchestrator (certainty != not_assessed) y
    permite que la entrevista avance hacia retrieval/decisión sin fingir
    una lectura clínica que este adapter no hace."""
    objective_match = _FIRST_OBJECTIVE_RE.search(full_text)
    code = objective_match.group("code") if objective_match else _DEFAULT_OBJECTIVE_CODE

    utterance_match = _LAST_UTTERANCE_RE.search(full_text)
    original_text = utterance_match.group("text").strip() if utterance_match else ""
    if not original_text or original_text.startswith("(sin respuesta"):
        original_text = ""

    payload = {
        "needs_clarification": False,
        "clarification_question": None,
        "next_question": "¿Hay algo más que quieras contarme sobre cómo se siente?",
        "observations": [
            {
                "code": code,
                "label": code.replace("_", " ").lower(),
                "value": None,
                "certainty": "uncertain",
                "original_text": original_text,
                "normalized_text": None,
            }
        ]
        if original_text
        else [],
    }
    return json.dumps(payload, ensure_ascii=False)


def _fake_triage_response() -> str:
    """Siempre `ROUTINE_FOLLOW_UP`: es el único nivel seguro que un
    proveedor fake puede declarar sin fingir criterio clínico. Las reglas
    deterministas (`app/services/rule_engine.py`) siguen operando en
    paralelo y son las únicas que pueden producir un `HARD_RED_FLAG` — este
    adapter nunca las rebaja ni las reemplaza (spec.md §11, "decisión no
    degradable")."""
    payload = {
        "model_level": "ROUTINE_FOLLOW_UP",
        "rationale": (
            "Evaluación de referencia del proveedor fake (sin credenciales "
            "configuradas, LLM_PROVIDER=fake) — no sustituye una evaluación real."
        ),
        "missing_information": [],
        "patient_message_intent": "explain_routine_follow_up",
    }
    return json.dumps(payload, ensure_ascii=False)


def _fake_response_text(full_text: str) -> str:
    if _RESPONSE_HANDOFF_MARKER in full_text:
        return (
            "Voy a dejar este caso registrado para que lo revise una persona del "
            "equipo; ya quedó anotado lo que me contaste."
        )
    if _RESPONSE_ABSTAIN_MARKER in full_text:
        return (
            "No tengo información verificada sobre eso en este momento, así que "
            "prefiero no responder directamente; lo voy a dejar registrado."
        )
    return (
        "Gracias por contarme. Con lo que conversamos hasta ahora, todo se ve "
        "dentro de lo esperado para esta etapa de la recuperación."
    )


class FakeLLM(LLMPort):
    def __init__(self, model: str = "fake-model-v1") -> None:
        self._model = model

    async def generate(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: dict | None = None,
    ) -> LLMResult:
        full_text = "\n".join(message.content for message in messages)

        if _INTERVIEW_MARKER in full_text:
            text = _fake_interview_response(full_text)
        elif _TRIAGE_MARKER in full_text:
            text = _fake_triage_response()
        elif _RESPONSE_MARKER in full_text:
            text = _fake_response_text(full_text)
        else:
            # Ningún agente conocido llamó — mantiene el comportamiento
            # anterior como fallback honesto (útil para tests de
            # `LLMPort` en aislamiento que no pasan un prompt real de
            # agente, p. ej. test_adapters.py).
            last_user_message = next(
                (m.content for m in reversed(messages) if m.role == "user"), ""
            )
            text = f"[fake-llm] respuesta determinista a: {last_user_message[:80]}"

        return LLMResult(
            text=text,
            input_tokens=len(full_text.split()),
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
