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

_OBJECTIVE_RE = re.compile(r"^- (?P<code>[A-Z_]+): (?P<label>.+)$", re.MULTILINE)
_LAST_UTTERANCE_RE = re.compile(
    r"## Último turno del cuidador/paciente a interpretar\n(?P<text>.+)", re.DOTALL
)
_NEXT_QUESTION_RE = re.compile(
    r"## SIGUIENTE PREGUNTA DEL SEGUIMIENTO \(cierra tu respuesta con ella\)\n"
    r"(?P<question>.+?)(?:\n##|\Z)",
    re.DOTALL,
)
_CURRENT_CONTEXT_RE = re.compile(
    r"## Contexto del turno actual\n(?P<text>.+?)(?:\n##|\Z)", re.DOTALL
)

_DEFAULT_OBJECTIVE_CODE = "GENERAL_STATE"

# Códigos que alimentan reglas clínicas deterministas
# (`app/services/rule_engine.py` RULESET_V2). Este adapter NUNCA declara
# `confirmed`/`uncertain` sobre ellos: no entiende el lenguaje del
# cuidador, así que afirmar "fiebre incierta" porque alguien dijo "aló
# buenas tardes" es inventar una señal clínica.
#
# Bug real corregido (visto en `/call` en vivo): el fake marcaba el
# siguiente objetivo pendiente como `uncertain` sin mirar el contenido. El
# segundo objetivo del checklist es FEVER — así que un simple saludo
# producía "fiebre incierta" -> `evidence_insufficient_with_risk` ->
# ESCALADO en el segundo turno de CUALQUIER llamada de demostración. Un
# falso positivo así de burdo (saludar y que el sistema alerte a una
# persona) es exactamente lo que la rúbrica evalúa en "situaciones donde
# escalar claramente NO es lo correcto".
_RULE_CLINICAL_CODES = frozenset({"FEVER", "WOUND_APPEARANCE"})
_FORM_RESPONSE_CODES = frozenset({"PAIN_LOCATION", "PAIN_SEVERITY", "PAIN_EVOLUTION"})

_GREETING_ONLY_RE = re.compile(
    r"^(?:(?:alo|hola|buenas|buenos dias|buenas tardes|buenas noches|que tal)"
    r"[\s,.;:¡!¿?]*)+$"
)


def _normalized(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").strip()


def _semantic_objective(text: str) -> str | None:
    normalized = _normalized(text)
    signals: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("FEVER", ("fiebre", "calentura", "grados", "temperatura")),
        ("PAIN", ("dolor", "duele", "adolor")),
        ("INTAKE", ("comer", "comida", "alimento", "tomar", "liquido", "bebida")),
        (
            "WOUND_APPEARANCE",
            (
                "herida",
                "secrecion",
                "pus",
                "sangr",
                "olor",
                # Respuestas elípticas frecuentes a "¿cómo se ve la herida?":
                # el paciente no tiene por qué repetir el sustantivo de la
                # pregunta. Sin estas formas, "está roja e inflamada" no
                # cubría el objetivo y el agente preguntaba lo mismo en bucle.
                "roja",
                "rojo",
                "enrojec",
                "inflamada",
                "hinchada",
            ),
        ),
        ("MOBILITY", ("caminar", "mover", "movilidad", "actividad")),
        ("SLEEP", ("dormir", "duermo", "sueno", "descans")),
        (
            "GENERAL_STATE",
            (
                "me siento",
                "animo",
                "estoy bien",
                "estoy mal",
                "debil",
                "cansad",
                "maread",
            ),
        ),
    )
    for code, needles in signals:
        if any(needle in normalized for needle in needles):
            return code
    return None


def _is_explicit_denial(code: str, text: str) -> bool:
    normalized = _normalized(text)
    patterns: dict[str, tuple[str, ...]] = {
        "PAIN": ("no tengo dolor", "no siento dolor", "no me duele", "sin dolor"),
        "FEVER": ("no tengo fiebre", "no he tenido fiebre", "sin fiebre"),
        "WOUND_APPEARANCE": ("sin secrecion", "no tiene secrecion", "no sangra"),
    }
    return any(phrase in normalized for phrase in patterns.get(code, ()))


def _fake_interview_response(full_text: str) -> str:
    """Nunca declara `confirmed`/`denied` (no puede interpretar de verdad el
    lenguaje del cuidador). Registra `uncertain` sólo para objetivos NO
    clínicos —lo que cuenta como "objetivo cubierto" y deja avanzar la
    entrevista—; para los que alimentan reglas clínicas registra
    `not_assessed`, la representación honesta de "este adapter no evaluó
    esto" (y que por diseño no dispara reglas ni cuenta como cubierto).

    `next_question` rota por los objetivos pendientes según cuántos turnos
    lleva la llamada: sin esto el fake devolvía siempre la misma pregunta
    genérica y la demostración se veía como un bucle que no avanzaba."""
    objectives = [
        (m.group("code"), m.group("label").strip()) for m in _OBJECTIVE_RE.finditer(full_text)
    ]
    utterance_match = _LAST_UTTERANCE_RE.search(full_text)
    original_text = utterance_match.group("text").strip() if utterance_match else ""
    if not original_text or original_text.startswith("(sin respuesta"):
        original_text = ""

    greeting_only = bool(original_text and _GREETING_ONLY_RE.fullmatch(_normalized(original_text)))
    semantic_code = None if greeting_only else _semantic_objective(original_text)
    objective_labels = dict(objectives)

    if semantic_code and semantic_code in objective_labels:
        code = semantic_code
        label = objective_labels[code]
        certainty = "denied" if _is_explicit_denial(code, original_text) else "confirmed"
    elif objectives:
        code, label = objectives[0]
        if code in _RULE_CLINICAL_CODES:
            certainty = "not_assessed"
        elif code in _FORM_RESPONSE_CODES:
            certainty = "confirmed"
        else:
            certainty = "uncertain"
    else:
        code, label = _DEFAULT_OBJECTIVE_CODE, "cómo se siente en general"
        certainty = "not_assessed"

    covered_now = (
        code if original_text and not greeting_only and certainty != "not_assessed" else None
    )
    next_candidates = [
        (item_code, item_label) for item_code, item_label in objectives if item_code != covered_now
    ]
    next_code, next_label = next_candidates[0] if next_candidates else (None, None)

    payload = {
        "needs_clarification": False,
        "clarification_question": None,
        "next_objective_code": next_code,
        "next_question": f"¿Me puede contar sobre {next_label}?" if next_label else None,
        "observations": [
            {
                "code": code,
                "label": label,
                "value": original_text if code in _FORM_RESPONSE_CODES else None,
                "certainty": certainty,
                "original_text": original_text,
                "normalized_text": None,
            }
        ]
        if original_text and not greeting_only
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

    # El agente debe CONDUCIR la entrevista: si el orquestador mandó la
    # siguiente pregunta del checklist, cerrar con ella. Sin esto, el fake
    # repetía literalmente la misma frase en cada turno — visible en pruebas
    # en vivo como un bucle de "Gracias por contarme…" que no avanzaba.
    next_question = _extract_next_question(full_text)
    context_match = _CURRENT_CONTEXT_RE.search(full_text)
    current_text = context_match.group("text").strip() if context_match else ""
    normalized = _normalized(current_text)

    if current_text and _GREETING_ONLY_RE.fullmatch(normalized):
        return f"Buenas tardes. {next_question}".strip() if next_question else "Buenas tardes."

    asks_for_guidance = any(
        marker in normalized
        for marker in ("es normal", "que debo", "que hago", "puedo tomar", "puedo hacer")
    )
    if _RESPONSE_ABSTAIN_MARKER in full_text and asks_for_guidance:
        base = "No tengo una orientación verificada para responder eso; lo dejaré registrado."
    else:
        # ResponseAgent recibe el contexto actual, no todo el historial. La
        # variación se decide por lo que acaba de decir el paciente para no
        # anteponer la misma muletilla a cada pregunta.
        if any(marker in normalized for marker in ("sin fiebre", "no tengo", "no siento")):
            base = "De acuerdo."
        elif any(marker in normalized for marker in ("liquido", "comiendo", "alimento")):
            base = "Bien."
        elif any(
            marker in normalized
            for marker in ("herida", "roja", "enrojec", "inflamada", "secrecion", "olor")
        ):
            base = "Lo tengo presente."
        elif any(marker in normalized for marker in ("dolor", "duele")):
            base = "Entiendo."
        else:
            base = "De acuerdo."
    return f"{base} {next_question}".strip() if next_question else base


def _extract_next_question(full_text: str) -> str | None:
    match = _NEXT_QUESTION_RE.search(full_text)
    if not match:
        return None
    question = match.group("question").strip()
    return question or None


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
                last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
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
