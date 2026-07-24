"""Precedencia de decisión clínica — función pura `reduce_decision` (ORC-001).

spec.md §8.1 fija la jerarquía completa:

    HARD_RED_FLAG
      > DATA_INTEGRITY_FAILURE
      > EVIDENCE_INSUFFICIENT_WITH_RISK
      > MODEL_HIGH_RISK
      > MODEL_MODERATE_RISK
      > ROUTINE_FOLLOW_UP

Regla no negociable (BR-020/BR-021, spec.md §11.2): una decisión de mayor
severidad NUNCA es rebajada por la salida del modelo. Este módulo no
importa ningún SDK de proveedor ni llama a un LLM — es lógica pura,
determinista y con 100% de cobertura de ramas exigido por NFR-011."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DecisionLevel(str, Enum):
    HARD_RED_FLAG = "HARD_RED_FLAG"
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    EVIDENCE_INSUFFICIENT_WITH_RISK = "EVIDENCE_INSUFFICIENT_WITH_RISK"
    MODEL_HIGH_RISK = "MODEL_HIGH_RISK"
    MODEL_MODERATE_RISK = "MODEL_MODERATE_RISK"
    ROUTINE_FOLLOW_UP = "ROUTINE_FOLLOW_UP"


# De mayor a menor severidad — fuente única de la jerarquía de spec.md §8.1.
PRECEDENCE_ORDER: tuple[DecisionLevel, ...] = (
    DecisionLevel.HARD_RED_FLAG,
    DecisionLevel.DATA_INTEGRITY_FAILURE,
    DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK,
    DecisionLevel.MODEL_HIGH_RISK,
    DecisionLevel.MODEL_MODERATE_RISK,
    DecisionLevel.ROUTINE_FOLLOW_UP,
)

_RANK: dict[DecisionLevel, int] = {level: index for index, level in enumerate(PRECEDENCE_ORDER)}

# Niveles que la evaluación estructurada del LLM puede reportar. HARD_RED_FLAG,
# DATA_INTEGRITY_FAILURE y EVIDENCE_INSUFFICIENT_WITH_RISK son exclusivamente
# deterministas (SafetyPolicyEngine/reglas versionadas) — el modelo nunca los
# produce ni los controla (architecture.md §6.1, spec.md BR-020).
MODEL_REPORTABLE_LEVELS: frozenset[DecisionLevel] = frozenset(
    {
        DecisionLevel.MODEL_HIGH_RISK,
        DecisionLevel.MODEL_MODERATE_RISK,
        DecisionLevel.ROUTINE_FOLLOW_UP,
    }
)

# Niveles que implican escalamiento (should_escalate=True). Decisión de
# diseño (no explícita en spec.md, ver reporte final): HARD_RED_FLAG,
# DATA_INTEGRITY_FAILURE y EVIDENCE_INSUFFICIENT_WITH_RISK escalan siempre
# por regla; MODEL_HIGH_RISK también escala; MODEL_MODERATE_RISK y
# ROUTINE_FOLLOW_UP no auto-escalan (BR-024: "no escalar" requiere ausencia
# de red flags, evidencia suficiente y datos mínimos completos).
_ESCALATING_LEVELS: frozenset[DecisionLevel] = frozenset(
    {
        DecisionLevel.HARD_RED_FLAG,
        DecisionLevel.DATA_INTEGRITY_FAILURE,
        DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK,
        DecisionLevel.MODEL_HIGH_RISK,
    }
)


class DecisionInputs(BaseModel):
    """Entradas a `reduce_decision`.

    Las tres primeras banderas son deterministas. `model_level` es la
    evaluación estructurada del LLM y está restringida por validación de
    Pydantic a `MODEL_REPORTABLE_LEVELS`: el modelo no puede ni siquiera
    *construir* una entrada que se autodeclare HARD_RED_FLAG — el tipo lo
    impide antes de llegar a la lógica de reducción.
    """

    hard_red_flag: bool = False
    trigger_codes: list[str] = Field(default_factory=list)
    data_integrity_failure: bool = False
    evidence_insufficient_with_risk: bool = False
    model_level: DecisionLevel = DecisionLevel.ROUTINE_FOLLOW_UP

    @field_validator("model_level")
    @classmethod
    def _model_level_must_be_reportable(cls, value: DecisionLevel) -> DecisionLevel:
        if value not in MODEL_REPORTABLE_LEVELS:
            allowed = ", ".join(sorted(level.value for level in MODEL_REPORTABLE_LEVELS))
            raise ValueError(
                f"model_level={value.value} no es un nivel que el modelo pueda reportar; "
                f"valores permitidos: {allowed}"
            )
        return value


class DecisionResult(BaseModel):
    level: DecisionLevel
    should_escalate: bool
    trigger_codes: list[str] = Field(default_factory=list)
    rationale: str


def reduce_decision(inputs: DecisionInputs) -> DecisionResult:
    """Combina señales deterministas y evaluación del modelo aplicando la
    precedencia completa. Toma el nivel de mayor severidad entre todas las
    señales activas — nunca el del modelo si hay una bandera determinista
    de mayor severidad presente, sin importar el orden de evaluación."""
    candidates: list[DecisionLevel] = []
    if inputs.hard_red_flag:
        candidates.append(DecisionLevel.HARD_RED_FLAG)
    if inputs.data_integrity_failure:
        candidates.append(DecisionLevel.DATA_INTEGRITY_FAILURE)
    if inputs.evidence_insufficient_with_risk:
        candidates.append(DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK)
    candidates.append(inputs.model_level)

    final_level = min(candidates, key=lambda level: _RANK[level])

    return DecisionResult(
        level=final_level,
        should_escalate=final_level in _ESCALATING_LEVELS,
        trigger_codes=(
            list(inputs.trigger_codes) if final_level == DecisionLevel.HARD_RED_FLAG else []
        ),
        rationale=_rationale_for(final_level),
    )


def _rationale_for(level: DecisionLevel) -> str:
    messages = {
        DecisionLevel.HARD_RED_FLAG: (
            "Señal(es) de alarma determinista(s) activa(s); precedencia máxima, "
            "no degradable por el modelo."
        ),
        DecisionLevel.DATA_INTEGRITY_FAILURE: (
            "Fallo de integridad de datos detectado; se prioriza sobre la evaluación del modelo."
        ),
        DecisionLevel.EVIDENCE_INSUFFICIENT_WITH_RISK: (
            "Evidencia insuficiente ante posible riesgo; se escala a revisión humana."
        ),
        DecisionLevel.MODEL_HIGH_RISK: (
            "El modelo reportó riesgo alto sin bandera determinista activa."
        ),
        DecisionLevel.MODEL_MODERATE_RISK: (
            "El modelo reportó riesgo moderado sin bandera determinista activa."
        ),
        DecisionLevel.ROUTINE_FOLLOW_UP: (
            "Sin señales de riesgo deterministas ni del modelo; seguimiento de rutina."
        ),
    }
    return messages[level]
