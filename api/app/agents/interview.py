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
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.support import AgentInvocationError, extract_json_payload, invoke_structured
from app.domain.models import AgentRequest, AgentResult, UsageMetrics
from app.domain.observation import Certainty, Observation
from app.ports.llm import LLMMessage, LLMPort

# Checklist mínimo de seguimiento postoperatorio (conocimiento de diseño,
# spec.md US-001/FR-020: "la siguiente pregunta depende de observaciones y
# datos faltantes"). Cada código corresponde a un `Observation.code` que el
# `CallCycleOrchestrator` considera "cubierto" en cuanto exista una
# observación con ese código y certainty != not_assessed.
INTERVIEW_OBJECTIVES: tuple[tuple[str, str], ...] = (
    ("GENERAL_STATE", "ánimo y actividad general"),
    ("FEVER", "fiebre o sensación de calor corporal"),
    ("WOUND_APPEARANCE", "aspecto de la herida (color, secreción, olor)"),
    ("INTAKE", "tolerancia a líquidos y alimentos"),
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
    "4. Responde EXCLUSIVAMENTE con un objeto JSON válido con esta forma: "
    '{"needs_clarification": bool, "clarification_question": str|null, '
    '"next_question": str|null, "observations": '
    '[{"code": str, "label": str, "value": bool|str|null, '
    '"certainty": "confirmed"|"uncertain"|"denied"|"not_assessed", '
    '"original_text": str, "normalized_text": str|null}]}. '
    "Sin texto adicional fuera del JSON."
)


class _ObservationDraft(BaseModel):
    code: str
    label: str
    value: bool | str | None = None
    certainty: Certainty
    original_text: str = ""
    normalized_text: str | None = None


class InterviewLLMOutput(BaseModel):
    needs_clarification: bool = False
    clarification_question: str | None = None
    next_question: str | None = None
    observations: list[_ObservationDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def _clarification_requires_question(self) -> InterviewLLMOutput:
        if self.needs_clarification and not (self.clarification_question or "").strip():
            raise ValueError(
                "needs_clarification=true requiere clarification_question no vacía"
            )
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

        observations = [
            Observation(
                code=draft.code,
                label=draft.label,
                value=draft.value,
                certainty=draft.certainty,
                original_text=draft.original_text,
                normalized_text=draft.normalized_text,
                source_turn_id=(
                    None
                    if draft.certainty == "not_assessed"
                    else turn_input.last_patient_turn_id
                ),
                normalized_by="interview-agent-v1",
            ).model_dump(mode="json")
            for draft in parsed.observations
        ]

        return AgentResult(
            status="ok",
            output={
                "needs_clarification": parsed.needs_clarification,
                "clarification_question": parsed.clarification_question,
                "next_question": parsed.next_question,
                "observations": observations,
            },
            usage=usage,
        )


def _build_user_prompt(turn_input: InterviewTurnInput) -> str:
    lines = ["## Objetivos pendientes del checklist"]
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
