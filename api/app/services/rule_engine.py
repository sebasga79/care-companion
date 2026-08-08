"""`RuleEngine` — reglas deterministas de red flag (SAFE-001, architecture.md
§6.1 `SafetyPolicyEngine`).

NO es un agente LLM: no importa `LLMPort`, no llama a ningún proveedor. Es
lógica pura sobre `Observation` estructuradas, versionada, con precedencia
absoluta sobre la clasificación del modelo (BR-020, spec.md §8.1). Un dato
ausente o ambiguo (`certainty` in {`uncertain`, `not_assessed`}) NUNCA
activa "todo bien": si una regla no puede evaluarse de forma concluyente
por falta de datos, sus observaciones pendientes se reportan en
`missing_info` — nunca se asume silenciosamente que el paciente está bien
(spec.md §11.2, "no interpretar silencio ... como negación")."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.observation import Observation

RULESET_VERSION = "rules-v2"


class RuleCondition(BaseModel):
    observation_code: str


class Rule(BaseModel):
    id: str
    version: str = RULESET_VERSION
    description: str
    trigger_codes: list[str]
    requires: list[RuleCondition]
    combine: Literal["all", "any"] = "all"


class RuleEngineResult(BaseModel):
    hard_red_flag: bool
    trigger_codes: list[str] = Field(default_factory=list)
    fired_rules: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    ruleset_version: str = RULESET_VERSION


# Reglas conservadoras de seguimiento postoperatorio, versionadas como
# datos. Las combinaciones se apoyan en las guías del corpus oficial y se
# mantienen separadas del LLM para que una alerta no sea degradable.
RULESET_V2: tuple[Rule, ...] = (
    Rule(
        id="RF-001",
        description=(
            "Fiebre confirmada combinada con secreción/enrojecimiento de la "
            "herida quirúrgica — combinación clásica de posible infección de "
            "sitio operatorio."
        ),
        trigger_codes=["FEVER_WITH_WOUND_DISCHARGE"],
        requires=[
            RuleCondition(observation_code="FEVER"),
            RuleCondition(observation_code="WOUND_DISCHARGE"),
        ],
        combine="all",
    ),
    Rule(
        id="RF-002",
        description="Dolor reportado explícitamente en aumento marcado.",
        trigger_codes=["PAIN_WORSENING"],
        requires=[RuleCondition(observation_code="PAIN_WORSENING")],
        combine="any",
    ),
    # Reglas añadidas tras una prueba en vivo donde el paciente reportó
    # "40 grados de fiebre", dolor persistente y pidió ser hospitalizado, y
    # el sistema respondió "todo se ve dentro de lo esperado": ninguna regla
    # cubría esas señales por sí solas (RF-001 exige fiebre Y secreción a la
    # vez). Ver `app/domain/safety_signals.py` para el detector que las
    # alimenta sin depender del LLM.
    Rule(
        id="RF-003",
        description=(
            "Temperatura reportada superior a 38 °C en seguimiento "
            "postoperatorio. El valor numérico se detecta sobre el texto crudo "
            "sin depender de la extracción del LLM."
        ),
        trigger_codes=["HIGH_FEVER"],
        requires=[RuleCondition(observation_code="HIGH_FEVER")],
        combine="any",
    ),
    Rule(
        id="RF-004",
        description="Dificultad respiratoria reportada — urgencia potencial.",
        trigger_codes=["BREATHING_DIFFICULTY"],
        requires=[RuleCondition(observation_code="BREATHING_DIFFICULTY")],
        combine="any",
    ),
    Rule(
        id="RF-005",
        description="Sangrado reportado sobre el sitio quirúrgico o general.",
        trigger_codes=["BLEEDING"],
        requires=[RuleCondition(observation_code="BLEEDING")],
        combine="any",
    ),
    Rule(
        id="RF-006",
        description=(
            "El paciente pide atención urgente, menciona hospitalización o "
            "expresa temor por su vida. Un pedido explícito de ayuda urgente "
            "nunca se responde con tranquilización automática — se escala y "
            "que una persona valore."
        ),
        trigger_codes=["EMERGENCY_CONCERN"],
        requires=[RuleCondition(observation_code="EMERGENCY_CONCERN")],
        combine="any",
    ),
    Rule(
        id="RF-007",
        description=(
            "Intolerancia a la vía oral / vómito persistente combinado con "
            "dolor que empeora — riesgo de complicación abdominal."
        ),
        trigger_codes=["VOMITING_WITH_PAIN"],
        requires=[
            RuleCondition(observation_code="VOMITING"),
            RuleCondition(observation_code="PAIN_WORSENING"),
        ],
        combine="all",
    ),
    Rule(
        id="RF-008",
        description="Desmayo, pérdida de conciencia o confusión reportada.",
        trigger_codes=["ALTERED_CONSCIOUSNESS"],
        requires=[RuleCondition(observation_code="ALTERED_CONSCIOUSNESS")],
        combine="any",
    ),
    Rule(
        id="RF-009",
        description=(
            "Deterioro posoperatorio combinado: fiebre, dolor actual alto y "
            "enrojecimiento o inflamación de la herida."
        ),
        trigger_codes=["POSTOP_DETERIORATION_WITH_WOUND"],
        requires=[
            RuleCondition(observation_code="FEVER"),
            RuleCondition(observation_code="PAIN_SEVERE"),
            RuleCondition(observation_code="WOUND_INFLAMMATION"),
        ],
        combine="all",
    ),
    Rule(
        id="RF-010",
        description=(
            "Deterioro posoperatorio combinado: fiebre, dolor actual alto e "
            "intolerancia a alimentos o líquidos."
        ),
        trigger_codes=["POSTOP_DETERIORATION_WITH_INTAKE"],
        requires=[
            RuleCondition(observation_code="FEVER"),
            RuleCondition(observation_code="PAIN_SEVERE"),
            RuleCondition(observation_code="ORAL_INTAKE_INTOLERANCE"),
        ],
        combine="all",
    ),
)


def evaluate_rules(
    observations: list[Observation],
    *,
    ruleset: tuple[Rule, ...] | None = None,
) -> RuleEngineResult:
    active_ruleset = ruleset if ruleset is not None else RULESET_V2

    # "Último gana" por código: el `InterviewAgent` ya resuelve
    # contradicciones dentro de una llamada (CON-002/CON-003) antes de que
    # la observación llegue aquí — si persiste una contradicción no
    # resuelta, llega como `certainty="uncertain"`, que este motor trata
    # igual que "dato faltante" (ni confirma ni descarta la regla).
    by_code: dict[str, Observation] = {}
    for observation in observations:
        by_code[observation.code] = observation

    fired_rule_ids: list[str] = []
    trigger_codes: set[str] = set()
    missing_info: set[str] = set()

    for rule in active_ruleset:
        condition_states: list[str] = []
        for condition in rule.requires:
            obs = by_code.get(condition.observation_code)
            if obs is None or obs.certainty in ("uncertain", "not_assessed"):
                condition_states.append("missing")
            elif obs.certainty == "confirmed":
                condition_states.append("true")
            else:  # denied
                condition_states.append("false")

        if rule.combine == "all":
            if "false" in condition_states:
                # Al menos una condición fue negada explícitamente: la
                # combinación AND ya no puede cumplirse, sin importar el
                # resto — regla descartada de forma concluyente, no "missing".
                continue
            if all(state == "true" for state in condition_states):
                fired_rule_ids.append(rule.id)
                trigger_codes.update(rule.trigger_codes)
                continue
            for condition, state in zip(rule.requires, condition_states, strict=True):
                if state == "missing":
                    missing_info.add(condition.observation_code)
        else:  # "any"
            if "true" in condition_states:
                fired_rule_ids.append(rule.id)
                trigger_codes.update(rule.trigger_codes)
                continue
            if all(state == "false" for state in condition_states):
                # Todas las condiciones negadas explícitamente: descartada
                # de forma concluyente.
                continue
            for condition, state in zip(rule.requires, condition_states, strict=True):
                if state == "missing":
                    missing_info.add(condition.observation_code)

    return RuleEngineResult(
        hard_red_flag=bool(fired_rule_ids),
        trigger_codes=sorted(trigger_codes),
        fired_rules=fired_rule_ids,
        missing_info=sorted(missing_info),
        ruleset_version=RULESET_VERSION,
    )


__all__ = [
    "RULESET_V2",
    "RULESET_VERSION",
    "Rule",
    "RuleCondition",
    "RuleEngineResult",
    "evaluate_rules",
]
