"""`InterviewAgent` (CON-002, CON-003) — formula/interpreta preguntas
conversacionales y extrae observaciones (architecture.md §6.1).

Puede usar: contexto mínimo de sesión + "glosario regional" como
conocimiento de diseño. No puede: diagnosticar, decidir riesgo final,
consultar datos arbitrarios, ni llamar a otro agente — solo usa el
`LLMPort` inyectado (vía `app.agents.support.invoke_structured`).

CON-003 (ambigüedad colombiana): el system prompt incluye un pequeño
conjunto de expresiones coloquiales ambiguas, tomado como CONOCIMIENTO DE
DISEÑO a partir de `docs/fixtures/colombian-glossary.md` (no se lee ese
archivo en tiempo de ejecución — el ticket pide explícitamente no
hardcodear el fixture, solo usarlo como referencia de diseño). La regla
transversal del glosario (nunca mapear una expresión ambigua directo a un
síntoma) se traduce aquí en una instrucción explícita del prompt."""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agents.support import (
    AgentInvocationError,
    extract_json_payload,
    format_prior_followup,
    invoke_structured,
)
from app.domain.models import AgentRequest, AgentResult, UsageMetrics
from app.domain.observation import Certainty, Observation
from app.ports.llm import LLMMessage, LLMPort

logger = logging.getLogger("care_companion.agents.interview")

# Checklist mínimo de seguimiento postoperatorio (conocimiento de diseño,
# spec.md US-001/FR-020: "la siguiente pregunta depende de observaciones y
# datos faltantes"). Cada código corresponde a un `Observation.code` que el
# `CallCycleOrchestrator` considera "cubierto" en cuanto exista una
# observación con ese código y certainty != not_assessed.
INTERVIEW_OBJECTIVES: tuple[tuple[str, str], ...] = (
    ("PAIN", "dolor actual y si ha cambiado"),
    ("PAIN_LOCATION", "lugar exacto del dolor"),
    ("PAIN_SEVERITY", "intensidad del dolor de 0 a 10"),
    ("PAIN_EVOLUTION", "evolución del dolor: mejora, sigue igual o empeora"),
    ("GENERAL_STATE", "estado general y ánimo"),
    ("INTAKE", "tolerancia a líquidos y alimentos"),
    ("FEVER", "fiebre o sensación de calor corporal"),
    ("WOUND_APPEARANCE", "aspecto de la herida (color, secreción, olor)"),
    ("MOBILITY", "movilidad y actividad"),
    ("SLEEP", "descanso y sueño"),
)

# Ejemplos de expresiones ambiguas (conocimiento de diseño derivado de
# docs/fixtures/colombian-glossary.md, NO una carga en tiempo de ejecución
# del archivo) — se inyectan como guía del prompt, nunca como mapeo directo
# a un síntoma.
_AMBIGUOUS_PATTERN_EXAMPLES: tuple[str, ...] = (
    "maluco/a",
    "decaído/a",
    "le dio duro",
    "guayabo de la anestesia",
    "aporreado/a",
    "está como ido/a",
    "más quietico/a de lo normal",
    "amaneció torcido/a",
    "tiene la carita rara",
    "está caliente (sin termómetro)",
    "le da vueltas la cabeza",
    "tiene el estómago revuelto",
    "está muy sentido/a",
    "tiene mal cuerpo",
    "está bajoneado/a",
    "amaneció rendido/a",
    "no se le quita lo llorón/llorona",
)

# Qué NO va en este prompt, y por qué (revisado 9 ago tras la prueba en vivo
# del jurado): toda regla que el orquestador ya impone de forma determinista
# se elimina de aquí. No es sólo ahorro de tokens — el orquestador
# SOBREESCRIBE la decisión del modelo en esos puntos, así que pedirle que
# razone sobre ellos gasta atención en algo que después se descarta, y con un
# modelo pequeño ese gasto se notaba en preguntas básicas mal manejadas.
#
# Movido a código (no repetir aquí):
#   - elegir el siguiente objetivo / no repetir lo ya respondido
#     -> `_resolve_next_question` valida el objetivo propuesto contra las
#        observaciones reales y lo reemplaza si no corresponde.
#   - no repetir una aclaración casi idéntica
#     -> `_is_near_duplicate_question` en el orquestador.
#   - "ya tienes mis registros" no es una respuesta clínica
#     -> `_references_known_history` intercepta antes y descarta lo que el
#        modelo hubiera extraído en ese turno.
#   - priorizar lugar/intensidad/evolución cuando hay dolor sin caracterizar
#     -> `_resolve_next_question` lo hace explícitamente.
#
# Lo que SÍ se queda: conocimiento de dominio que sólo el modelo aplica
# (glosario coloquial, contradicciones entre turnos, silencio != negación) y
# el contrato de salida JSON.
_SYSTEM_PROMPT = (
    "Eres el asistente de entrevista de seguimiento postoperatorio de Care "
    "Companion. Hablas en español, tono cálido y breve. Tu única función es "
    "formular la siguiente pregunta del checklist o extraer observaciones "
    "estructuradas del último turno del cuidador/paciente. NO diagnosticas, "
    "NO decides el riesgo final, NO inventas datos.\n\n"
    "Reglas obligatorias:\n"
    "1. Si el cuidador usa una expresión coloquial ambigua (ejemplos: "
    + ", ".join(_AMBIGUOUS_PATTERN_EXAMPLES)
    + "), NUNCA la traduzcas directamente a un síntoma. Responde con "
    "needs_clarification=true, una clarification_question abierta que ofrezca "
    "categorías amplias sin sugerir la respuesta, y conserva el texto "
    "original tal cual en original_text de cualquier observación relacionada.\n"
    "2. Si detectas que el cuidador se contradice respecto a algo que dijo "
    "en un turno anterior de esta misma llamada, señala la contradicción de "
    "forma explícita en clarification_question (citando lo dicho antes) y "
    "pide aclaración dirigida. Si tras la aclaración la incertidumbre "
    "persiste, registra la observación con certainty='uncertain' y una nota "
    "en normalized_text que explique la falta de confirmación — nunca "
    "fuerces 'confirmed' ni 'denied' cuando la evidencia conversacional es "
    "mixta.\n"
    "3. El silencio, la falta de respuesta o un turno vacío NUNCA se "
    "registra como certainty='denied'; usa 'not_assessed'.\n"
    "4. Un saludo o una fórmula social sin información clínica NO cubre un "
    "objetivo y NO crea observaciones. Responde al saludo con naturalidad y "
    "continúa con el primer objetivo pendiente.\n"
    "5. Extrae TODA la información explícita del último turno, aunque no "
    "corresponda a la pregunta anterior.\n"
    "6. Usa los seguimientos anteriores para reconocer la evolución y no "
    "hacer repetir antecedentes ya registrados. Nunca presentes un "
    "antecedente como síntoma actual ni contestes por el paciente.\n"
    "7. Responde EXCLUSIVAMENTE con un objeto JSON válido con esta forma: "
    '{"needs_clarification": bool, "clarification_question": str|null, '
    '"next_objective_code": str|null, "next_question": str|null, "observations": '
    '[{"code": str, "label": str, "value": bool|number|str|null, '
    '"certainty": "confirmed"|"uncertain"|"denied"|"not_assessed", '
    '"original_text": str, "normalized_text": str|null}]}. '
    "Sin texto adicional fuera del JSON."
)


class _ObservationDraft(BaseModel):
    code: str
    label: str
    value: bool | int | float | str | None = None
    certainty: Certainty
    original_text: str = ""
    normalized_text: str | None = None


class InterviewLLMOutput(BaseModel):
    needs_clarification: bool = False
    clarification_question: str | None = None
    next_objective_code: str | None = None
    next_question: str | None = None
    observations: list[_ObservationDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def _clarification_requires_question(self) -> InterviewLLMOutput:
        if self.needs_clarification and not (self.clarification_question or "").strip():
            raise ValueError("needs_clarification=true requiere clarification_question no vacía")
        return self


def _parse_interview_output(text: str) -> InterviewLLMOutput:
    data = json.loads(extract_json_payload(text))
    return InterviewLLMOutput.model_validate(data)


class InterviewTurnInput(BaseModel):
    """`payload` esperado en el `AgentRequest` de este agente."""

    turns: list[dict] = Field(default_factory=list)
    remaining_objectives: list[dict] = Field(default_factory=list)
    last_patient_utterance: str = ""
    last_patient_turn_id: str | None = None
    case_context: dict = Field(default_factory=dict)
    prior_followups: list[dict] = Field(default_factory=list)


Speaker = Literal["patient", "agent", "system"]


class InterviewAgent:
    """Ver docstring del módulo. `run()` es la única entrada pública."""

    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    async def run(self, request: AgentRequest) -> AgentResult:
        turn_input = InterviewTurnInput.model_validate(request.payload)

        messages = [
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=_build_user_prompt(turn_input)),
        ]

        try:
            parsed, usage = await invoke_structured(
                self._llm,
                messages=messages,
                # No-None: hace que OpenAICompatLLM pida response_format
                # json_object a Groq/Ollama — el prompt ya menciona "JSON"
                # explícitamente, requisito del proveedor para ese modo.
                response_schema={"type": "object"},
                deadline_ms=request.deadline_ms,
                parse=_parse_interview_output,
            )
        except AgentInvocationError as exc:
            return AgentResult(
                status="error",
                output={"reason": exc.reason},
                usage=exc.usage,
                warnings=[f"InterviewAgent: {exc.reason}"],
            )

        observations = _build_observations(parsed.observations, turn_input)

        return AgentResult(
            status="ok",
            output={
                "needs_clarification": parsed.needs_clarification,
                "clarification_question": parsed.clarification_question,
                "next_objective_code": parsed.next_objective_code,
                "next_question": parsed.next_question,
                "observations": observations,
            },
            usage=usage,
        )


def _build_observations(
    drafts: list[_ObservationDraft], turn_input: InterviewTurnInput
) -> list[dict]:
    """Construye las `Observation` finales tolerando salidas incompletas del
    modelo.

    Bug real encontrado probando G3 contra un modelo permitido de verdad
    (llama3.2:3b vía Ollama): el modelo devolvió una observación con
    `certainty="uncertain"` pero `original_text` vacío. `Observation` lo
    rechaza a propósito (BR-006: toda afirmación conserva su texto
    verbatim), pero la `ValidationError` se lanzaba AQUÍ — fuera del
    `try/except AgentInvocationError`, que sólo cubre la invocación — y
    escapaba hasta el orquestador como excepción no anticipada. Resultado:
    `DATA_INTEGRITY_FAILURE` y escalamiento en el PRIMER turno ante un
    simple "buenas tardes". Los tests no lo detectaban porque los fakes
    siempre rellenan `original_text`.

    Dos defensas, en este orden:

    1. Si el modelo no citó el texto, se usa el turno literal del paciente
       — que es la fuente verbatim real y satisface BR-006 sin inventar
       nada (no se fabrica una cita: se usa lo que el paciente dijo).
    2. Si aun así la observación no valida (código vacío, certeza no
       reconocida, etc.), se descarta ESA observación y se sigue. Perder
       una observación malformada del modelo es preferible a tumbar el
       turno completo: las señales críticas no dependen de esta ruta, las
       detecta `app/domain/safety_signals.py` sobre el texto crudo.
    """
    fallback_text = (turn_input.last_patient_utterance or "").strip()
    observations: list[dict] = []

    for draft in drafts:
        original_text = (draft.original_text or "").strip() or fallback_text
        try:
            observation = Observation(
                code=draft.code,
                label=draft.label,
                value=draft.value,
                certainty=draft.certainty,
                original_text=original_text,
                normalized_text=draft.normalized_text,
                source_turn_id=(
                    None if draft.certainty == "not_assessed" else turn_input.last_patient_turn_id
                ),
                normalized_by="interview-agent-v1",
            )
        except ValidationError:
            logger.warning(
                "interview_observation_descartada code=%r certainty=%r "
                "(salida del modelo no cumple el contrato de Observation)",
                draft.code,
                draft.certainty,
            )
            continue
        observations.append(observation.model_dump(mode="json"))

    return observations


def _build_user_prompt(turn_input: InterviewTurnInput) -> str:
    lines = ["## Contexto conocido del caso (no es respuesta del paciente)"]
    if turn_input.case_context:
        for key, value in turn_input.case_context.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("(sin contexto de caso)")

    lines.append("\n## Seguimientos anteriores estructurados (no asumir vigencia hoy)")
    if turn_input.prior_followups:
        for followup in turn_input.prior_followups:
            lines.append(f"- {format_prior_followup(followup)}")
    else:
        lines.append("(ninguno)")

    lines.append("\n## Objetivos pendientes del checklist")
    if turn_input.remaining_objectives:
        for objective in turn_input.remaining_objectives:
            lines.append(f"- {objective['code']}: {objective['label']}")
    else:
        lines.append("(ninguno — todos los objetivos ya fueron cubiertos)")

    lines.append("\n## Historial de la llamada (más reciente al final)")
    for turn in turn_input.turns[-8:]:
        lines.append(f"- [{turn.get('speaker')}] {turn.get('text')}")

    lines.append("\n## Último turno del cuidador/paciente a interpretar")
    lines.append(turn_input.last_patient_utterance or "(sin respuesta / silencio)")

    return "\n".join(lines)


__all__ = [
    "INTERVIEW_OBJECTIVES",
    "InterviewAgent",
    "InterviewLLMOutput",
    "InterviewTurnInput",
    "UsageMetrics",
]
