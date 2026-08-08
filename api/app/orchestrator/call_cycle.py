"""`CallCycleOrchestrator` — coordinador único del ciclo turno-a-turno
(ORC-002, architecture.md §6.1/§6.2/§7, spec.md §9).

Secuencia por turno (architecture.md §7.1), toda en este módulo — NINGÚN
agente llama a otro agente ni al orquestador; este es el único punto que
importa `InterviewAgent`, `TriageAgent` y `ResponseAgent` a la vez y
decide el orden:

    turno del cuidador
      -> InterviewAgent (observaciones + ¿necesita aclaración?)
      -> RuleEngine (deterministas, SAFE-001)
      -> retrieval híbrido + evidence gate (RAG-005/006)
      -> TriageAgent (evaluación estructurada, restringida por tipo a
         niveles no-HARD_RED_FLAG — SAFE-002)
      -> reduce_decision (precedencia no negociable, SAFE-003)
      -> escalamiento idempotente si `should_escalate` (SAFE-004)
      -> ResponseAgent (mensaje breve; groundedness real vía evidence gate)
      -> persistencia (turnos, observaciones, decisión, citas, eventos)

Si el cuidador usa una expresión ambigua o se contradice, `InterviewAgent`
devuelve `needs_clarification=True` y el ciclo se corta ahí mismo (sin
reglas/retrieval/triage/decisión) — la sesión permanece en
`INTERVIEWING` hasta que el turno siguiente aclare (spec.md AC-E2E-003).

Fail-safe (spec.md §9.3, BR-027): cualquier `AgentResult(status="error")`
de un agente, o cualquier excepción no anticipada durante el ciclo (p. ej.
un fallo de retrieval/DB), se trata como riesgo — no como "todo bien" — y
produce `DecisionInputs(data_integrity_failure=True)`, que por precedencia
escala siempre, más una transición de la FSM a `FAIL_SAFE`. Nunca se deja
una excepción sin manejar "silenciosa": siempre se registra el motivo y se
persiste una decisión/escalamiento explícitos."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.agents.interview import INTERVIEW_OBJECTIVES, InterviewAgent, InterviewTurnInput
from app.agents.response import ResponseAgent, ResponseTurnInput
from app.agents.triage import TriageAgent, TriageTurnInput
from app.core.correlation_id import get_correlation_id, new_correlation_id
from app.domain.clinical_values import normalize_spanish, parse_pain_nrs
from app.domain.decision import DecisionInputs, DecisionLevel, reduce_decision
from app.domain.evidence import EvidenceStatus, evaluate_evidence
from app.domain.models import AgentRequest, CitationRef, UsageMetrics
from app.domain.observation import Observation
from app.domain.safety_signals import (
    derive_longitudinal_safety_signals,
    detect_safety_signals,
    is_unspecified_severe_distress,
    merge_with_safety_precedence,
)
from app.domain.session_fsm import CallOrchestrator, SessionState
from app.domain.summary import CallSummary, build_call_summary
from app.ports.challenge_case import ChallengeCase, ChallengeCasePort
from app.ports.embeddings import EmbeddingsPort
from app.ports.llm import LLMPort
from app.repositories.citations import CitationRepository
from app.repositories.db import get_connection, session_scope
from app.repositories.decisions import DecisionRepository
from app.repositories.escalations import EscalationRepository
from app.repositories.events import EventRepository
from app.repositories.followups import FollowupRecordRepository
from app.repositories.observations import ObservationRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository
from app.services.retrieval import hybrid_search
from app.services.rule_engine import evaluate_rules

logger = logging.getLogger("care_companion.orchestrator")

# Presupuesto por intento de agente. Es el `asyncio.wait_for` que envuelve
# `LLMPort.generate` (app/agents/support.py), así que con `FallbackLLM`
# cubre primario + resguardo dentro del MISMO intento.
#
# Por eso el default sube cuando hay resguardo configurado: medido en la
# máquina de desarrollo, Groq responde en ~0,7 s pero Ollama local tarda
# ~5,6 s. Con el antiguo valor fijo de 5.000 ms el resguardo **nunca podía
# activarse**: el deadline lo mataba antes de que el modelo local
# alcanzara a contestar. Un resguardo que no puede dispararse es no tener
# resguardo — justo el riesgo que la auditoría §8 marcó como abierto.
AGENT_DEADLINE_MS = 5000
AGENT_DEADLINE_WITH_FALLBACK_MS = 20000

# Cuántas llamadas ya cerradas en la app se adjuntan al contexto, además de
# los cuatro hitos oficiales del dataset. Ver `_prior_followups`.
_MAX_PRIOR_COMPLETED_CALLS = 2


def default_agent_deadline_ms(*, has_fallback: bool) -> int:
    return AGENT_DEADLINE_WITH_FALLBACK_MS if has_fallback else AGENT_DEADLINE_MS

_URGENT_SCREEN_QUESTION = (
    "Entiendo que se siente muy mal. Para saber si necesita atención inmediata: "
    "¿qué siente exactamente? ¿Tiene dificultad para respirar, desmayo o confusión, "
    "sangrado abundante, dolor insoportable, fiebre medida o vómitos persistentes?"
)

_VAGUE_WELLBEING_RE = re.compile(
    r"^(?:me siento\s+)?(?:mas o menos|regular|ahi voy|pues ahi|ni bien ni mal)[\s.!¡¿?]*$"
)
# El paciente remite su respuesta al historial que el agente ya tiene. No
# es una respuesta ni una evasiva: es una petición legítima de información
# que el sistema SÍ puede satisfacer (tiene los cuatro seguimientos).
#
# Se amplió tras una prueba en vivo: "no sé, usted dígame porque yo no me
# acuerdo cómo estaba… quiero que me diga si sigue igual o mejorado o
# empeorado" no coincidía con ninguna forma anterior, así que el turno se
# trataba como respuesta cualquiera y la pregunta del paciente quedaba sin
# contestar.
_HISTORY_REFERENCE_RE = re.compile(
    r"\b(?:usted|ustedes)\s+(?:debe|deben|deberia|deberian)\s+saber\b|"
    r"\b(?:ya\s+)?(?:tiene|tienen)\s+(?:todos\s+)?(?:mis|los)\s+registros\b|"
    r"\b(?:eso|esa informacion)\s+esta\s+en\s+(?:mis|los)\s+registros\b|"
    r"\b(?:usted\s+)?(?:digame|digamelo|dime|dimelo)\b|"
    r"\bquiero que me (?:diga|digas|cuente)\b|"
    r"\bno (?:me acuerdo|recuerdo)\b|"
    r"\b(?:me|nos) puede decir (?:usted|si)\b"
)

# Componentes aislados que sí justifican revisión humana cuando el corpus no
# ofrece evidencia suficiente. Dolor alto, enrojecimiento leve o dificultad
# para comer se caracterizan primero; solo sus combinaciones definidas en el
# ruleset escalan. Esto evita convertir cada síntoma posoperatorio en handoff.
_EVIDENCE_ESCALATION_SIGNAL_CODES: frozenset[str] = frozenset(
    {"FEVER", "WOUND_DISCHARGE", "VOMITING"}
)

# Estados en los que una sesión puede aceptar un nuevo turno de texto.
# CREATED/CONSENT se resuelven automáticamente al primer turno (ver
# docstring de `handle_turn` — no existe todavía un paso de consentimiento
# explícito en la API, se documenta como simplificación deliberada de esta
# fase). RETRIEVING/DECIDING nunca quedan persistidos como estado "en
# reposo" entre llamadas (son transiciones internas de un mismo
# `handle_turn`), así que no aparecen aquí.
_ACCEPTS_TURN: frozenset[SessionState] = frozenset(
    {
        SessionState.CREATED,
        SessionState.CONSENT,
        SessionState.INTERVIEWING,
        SessionState.RESPONDING,
        SessionState.ESCALATED,
    }
)

_USAGE_EVENT_TYPES: frozenset[str] = frozenset(
    {"agent.interview.completed", "agent.triage.completed", "agent.response.completed"}
)


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Sesión no encontrada: {session_id}")


class SessionNotAcceptingTurnsError(Exception):
    def __init__(self, session_id: str, state: SessionState) -> None:
        self.session_id = session_id
        self.state = state
        super().__init__(
            f"La sesión {session_id} está en estado {state.value!r} y no acepta turnos nuevos"
        )


@dataclass
class TurnCycleResult:
    """Resultado de un `handle_turn` — lo consume tanto el WS (API-002)
    como los tests de estado del orquestador."""

    session_id: str
    state: SessionState
    agent_message: str | None
    intent: str
    decision_level: DecisionLevel
    should_escalate: bool
    escalated: bool
    citations: list[CitationRef] = field(default_factory=list)
    needs_clarification: bool = False
    warnings: list[str] = field(default_factory=list)


def _obs_summary(observation: Observation) -> str:
    text = observation.original_text or "(sin texto)"
    return f"{observation.label} — {text} [{observation.certainty}]"


_CONTACT_NUMBER_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{5,}\d)(?!\d)")
_SPANISH_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _extract_contact_number(text: str) -> str | None:
    """Extrae un teléfono transcrito conservando el prefijo internacional."""
    for match in _CONTACT_NUMBER_RE.finditer(text):
        candidate = match.group(0).strip()
        digits = "".join(char for char in candidate if char.isdigit())
        if 7 <= len(digits) <= 15:
            return f"+{digits}" if candidate.startswith("+") else digits
    return None


def _format_spanish_date(value: date) -> str:
    return f"{value.day} de {_SPANISH_MONTHS[value.month - 1]} de {value.year}"


def _is_vague_wellbeing_response(text: str) -> bool:
    return bool(_VAGUE_WELLBEING_RE.fullmatch(normalize_spanish(text).strip()))


def _references_known_history(text: str) -> bool:
    return bool(_HISTORY_REFERENCE_RE.search(normalize_spanish(text)))


def _history_aware_pain_question(case: ChallengeCase, observations: list[Observation]) -> str:
    severity = next(
        (
            item
            for item in reversed(observations)
            if item.code == "PAIN_SEVERITY" and item.certainty == "confirmed"
        ),
        None,
    )
    current = (
        parse_pain_nrs(severity.value, severity.original_text) if severity is not None else None
    )
    previous = (
        max(case.historical_followups, key=lambda item: item.day)
        if case.historical_followups
        else None
    )
    if previous is not None and current is not None:
        return (
            f"Tiene razón. En su último seguimiento el dolor estaba en "
            f"{previous.pain_nrs} de 10 y hoy me reporta {current} de 10; es un "
            "cambio importante. Para entender lo que ocurre ahora, ¿el dolor "
            "apareció de repente o gradualmente, y está aumentando, sigue igual o disminuye?"
        )
    return (
        "Tiene razón, ya tengo presentes sus seguimientos anteriores. Necesito confirmar "
        "solo el cambio de hoy: ¿esto apareció de repente y está aumentando, sigue igual "
        "o disminuye?"
    )


def _case_context(case: ChallengeCase) -> dict[str, Any]:
    """Perfil longitudinal estable; la evolución histórica viaja aparte."""
    return {
        "patient_display_name": case.patient_display_name,
        "procedure": case.procedure,
        "procedure_category": case.procedure_category,
        "phase": case.phase,
        "surgery_date": case.surgery_date.isoformat() if case.surgery_date else None,
        "history_through_day": (
            max(item.day for item in case.historical_followups)
            if case.historical_followups
            else None
        ),
        "age": case.age,
        "gender": case.gender,
        "comorbidities": list(case.comorbidities),
    }


def _build_opening_message(case: ChallengeCase, prior_followups: list[dict[str, Any]]) -> str:
    display_name = case.patient_display_name.split(" (", maxsplit=1)[0].strip()
    first_name = display_name.split()[0] if display_name else ""
    greeting = f"Buenas tardes, {first_name}." if first_name else "Buenas tardes."
    history = (
        " Tengo a la vista la evolución registrada en sus seguimientos anteriores "
        "para continuar desde allí y confirmar cómo se encuentra hoy."
        if prior_followups
        else ""
    )
    procedure = case.procedure.replace("_", " ")
    surgery_reference = (
        f", realizada el {_format_spanish_date(case.surgery_date)}"
        if case.surgery_date is not None
        else ""
    )
    return (
        f"{greeting} Soy el asistente de seguimiento postoperatorio de Care Companion. "
        f"Esta llamada es para continuar el seguimiento de su recuperación después de "
        f"{procedure}{surgery_reference}.{history} ¿Cómo se ha sentido desde el último "
        "seguimiento?"
    )


_QUESTION_BY_CODE: dict[str, str] = {
    "PAIN": "¿Tiene dolor en este momento y ha cambiado desde ayer?",
    "PAIN_LOCATION": "¿En qué parte exacta siente el dolor?",
    "PAIN_SEVERITY": "En una escala de 0 a 10, ¿qué intensidad tiene el dolor?",
    "PAIN_EVOLUTION": "¿El dolor está mejorando, sigue igual o ha empeorado?",
    "GENERAL_STATE": "¿Cómo se ha sentido en general y cómo ha estado de ánimo?",
    "INTAKE": "¿Ha podido tomar líquidos y comer con normalidad?",
    "FEVER": "¿Ha tenido fiebre o sensación de calor corporal?",
    "WOUND_APPEARANCE": "¿Cómo se ve la herida: ha notado enrojecimiento, secreción u olor?",
    "MOBILITY": "¿Cómo está su movilidad y qué actividades ha podido hacer?",
    "SLEEP": "¿Cómo ha dormido y descansado?",
}


def _covered_objective_codes(observations: list[Observation]) -> set[str]:
    latest_by_code: dict[str, Observation] = {}
    for observation in observations:
        latest_by_code[observation.code] = observation
    covered = {
        code
        for code, observation in latest_by_code.items()
        if observation.certainty != "not_assessed"
    }
    # Los códigos de seguridad son más específicos que algunos objetivos
    # conversacionales, pero también los cubren semánticamente.
    if "PAIN_WORSENING" in covered or "PAIN_HISTORY_DETERIORATION" in covered:
        covered.add("PAIN")
    if "PAIN_SEVERE" in covered:
        covered.add("PAIN")
    if "WOUND_DISCHARGE" in covered or "WOUND_INFLAMMATION" in covered:
        covered.add("WOUND_APPEARANCE")
    if "VOMITING" in covered or "ORAL_INTAKE_INTOLERANCE" in covered:
        covered.add("INTAKE")
    pain_observation = latest_by_code.get("PAIN")
    if pain_observation is not None and pain_observation.certainty == "denied":
        covered.update({"PAIN_LOCATION", "PAIN_SEVERITY", "PAIN_EVOLUTION"})
    return covered


def _resolve_next_question(
    interview_output: dict[str, Any], observations: list[Observation]
) -> str | None:
    """Elige una pregunta realmente pendiente después de interpretar el turno.

    El modelo puede proponer la redacción, pero el orquestador valida el
    objetivo contra las observaciones ya persistidas y las recién extraídas.
    Así, si el paciente responde fiebre fuera del orden previsto, FEVER queda
    cubierto inmediatamente y no se vuelve a preguntar en el turno siguiente.
    """
    covered = _covered_objective_codes(observations)
    pending = [code for code, _ in INTERVIEW_OBJECTIVES if code not in covered]
    if not pending:
        return None

    pain_reported = bool({"PAIN", "PAIN_SEVERE", "PAIN_WORSENING"} & covered)
    if pain_reported:
        for code in ("PAIN_LOCATION", "PAIN_SEVERITY", "PAIN_EVOLUTION"):
            if code in pending:
                return _QUESTION_BY_CODE[code]

    proposed_code = interview_output.get("next_objective_code")
    proposed_question = (interview_output.get("next_question") or "").strip()
    if proposed_code in pending and proposed_question:
        return proposed_question
    return _QUESTION_BY_CODE[pending[0]]


def _to_correlation_uuid(value: str | None) -> uuid.UUID:
    if value:
        try:
            return uuid.UUID(value)
        except ValueError:
            pass
    return uuid.uuid4()


def _sum_usage_from_events(events: list[dict[str, Any]]) -> UsageMetrics:
    input_tokens = 0
    output_tokens = 0
    latency_ms = 0.0
    provider = "fake"
    model = "fake-model-v1"
    for event in events:
        if event.get("event_type") not in _USAGE_EVENT_TYPES:
            continue
        raw_payload = event.get("payload")
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except json.JSONDecodeError:
            continue
        input_tokens += int(payload.get("input_tokens", 0))
        output_tokens += int(payload.get("output_tokens", 0))
        latency_ms += float(payload.get("latency_ms", 0.0))
        provider = payload.get("provider", provider)
        model = payload.get("model", model)
    return UsageMetrics(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        provider=provider,
        model=model,
    )


class CallCycleOrchestrator:
    """Ver docstring del módulo. `handle_turn` es la única entrada para
    procesar un turno; `build_summary` construye el `CallSummary` (SUM-002)
    a partir de lo ya persistido, reutilizable por la API REST (`/finish`)
    y por el WebSocket (`server.summary`)."""

    def __init__(
        self,
        *,
        database_path: str,
        llm: LLMPort,
        embeddings: EmbeddingsPort,
        case_port: ChallengeCasePort,
        evidence_score_threshold: float,
        candidate_pool_size: int = 200,
        retrieval_top_k: int = 5,
        agent_deadline_ms: int = AGENT_DEADLINE_MS,
    ) -> None:
        self._database_path = database_path
        self._embeddings = embeddings
        self._case_port = case_port
        self._evidence_score_threshold = evidence_score_threshold
        self._candidate_pool_size = candidate_pool_size
        self._retrieval_top_k = retrieval_top_k
        self._agent_deadline_ms = agent_deadline_ms

        self._interview_agent = InterviewAgent(llm)
        self._triage_agent = TriageAgent(llm)
        self._response_agent = ResponseAgent(llm)

        self._session_repo = SessionRepository(database_path)
        self._turn_repo = TurnRepository(database_path)
        self._observation_repo = ObservationRepository(database_path)
        self._decision_repo = DecisionRepository(database_path)
        self._escalation_repo = EscalationRepository(database_path)
        self._event_repo = EventRepository(database_path)
        self._followup_repo = FollowupRecordRepository(database_path)
        self._citation_repo = CitationRepository()

    async def start_session(self, session_id: str) -> str:
        """Inicia la llamada desde el agente y devuelve su apertura.

        La interfaz representa la llamada de producción: después de que el
        demo selecciona un caso, el agente explica el propósito y abre la
        entrevista; no espera que el paciente/operador escriba primero.
        """
        session = self._session_repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        case = await self._case_port.get_case(session["case_id"])
        if case is None:
            raise SessionNotFoundError(session_id)

        existing_turns = self._turn_repo.list_for_session(session_id)
        if existing_turns:
            return existing_turns[0]["text"]

        prior_followups = await self._prior_followups(case, exclude_session_id=session_id)
        opening = _build_opening_message(case, prior_followups)
        self._turn_repo.add(session_id=session_id, speaker="agent", text=opening, sequence=1)

        fsm = CallOrchestrator(session_id, initial_state=SessionState(session["state"]))
        if fsm.state is SessionState.CREATED:
            fsm.transition(SessionState.CONSENT, event="agent_opened_call")
        if fsm.state is SessionState.CONSENT:
            fsm.transition(SessionState.INTERVIEWING, event="purpose_explained")
        self._session_repo.update_state(session_id, state=fsm.state.value)
        self._log_event(
            session_id=session_id,
            correlation_id=get_correlation_id() or new_correlation_id(),
            event_type="session.agent_opened",
            payload={
                "procedure": case.procedure,
                "days_since_procedure": case.days_since_procedure,
                "prior_followup_count": len(prior_followups),
            },
        )
        return opening

    async def _prior_followups(
        self, case: ChallengeCase, *, exclude_session_id: str
    ) -> list[dict[str, Any]]:
        """Memoria estructurada de llamadas anteriores del mismo paciente.

        Para una entidad longitudinal, los cuatro hitos 1/3/7/14 son
        historia clínica conocida antes de esta nueva llamada. Se combinan
        con observaciones realmente dichas y decisiones persistidas en
        sesiones anteriores de la aplicación. `reference_trajectory` sigue
        reservado a los episodios originales y nunca se expone directamente.
        """
        prior: list[dict[str, Any]] = [
            {
                "source": "official_longitudinal_history",
                "days_since_procedure": followup.day,
                "trajectory_id": followup.trajectory_id,
                "archetype": followup.archetype,
                "pain_nrs": followup.pain_nrs,
                "temperature_c": followup.temperature_c,
                "mobility": followup.mobility,
                "wound": followup.wound,
                "appetite": followup.appetite,
                "sleep": followup.sleep,
            }
            for followup in case.historical_followups
        ]
        eligible_states = {
            SessionState.SUMMARIZING.value,
            SessionState.CLOSED.value,
            SessionState.FAIL_SAFE.value,
        }
        for record in self._session_repo.list_all():
            if record["id"] == exclude_session_id or record["state"] not in eligible_states:
                continue
            prior_case = await self._case_port.get_case(record["case_id"])
            if prior_case is None or prior_case.patient_id != case.patient_id:
                continue
            if prior_case.days_since_procedure > case.days_since_procedure:
                continue

            observations = self._observation_repo.list_for_session(record["id"])
            decisions = self._decision_repo.list_for_session(record["id"])
            latest_by_code: dict[str, Observation] = {}
            for observation in observations:
                latest_by_code[observation.code] = observation
            prior.append(
                {
                    "source": "completed_call",
                    "days_since_procedure": prior_case.days_since_procedure,
                    "procedure": prior_case.procedure,
                    "observations": [
                        {
                            "code": observation.code,
                            "label": observation.label,
                            "certainty": observation.certainty,
                            "value": observation.value,
                        }
                        for observation in latest_by_code.values()
                        if observation.certainty != "not_assessed"
                    ],
                    "decision_level": decisions[-1]["level"] if decisions else None,
                }
            )

        # Los cuatro hitos oficiales (1/3/7/14) son la línea base clínica y
        # siempre viajan completos. Las llamadas ya cerradas EN LA APP, en
        # cambio, se acumulan sin techo: cada demo o prueba agrega una más y
        # todas terminaban en el prompt de tres agentes. Medido tras unas
        # pocas pruebas ya había ~17 entradas donde deberían ser 4.
        #
        # Se conservan sólo las más recientes: en un seguimiento
        # postoperatorio lo que importa es la evolución cercana, y el
        # historial oficial ya cubre el arco completo. Sin este techo, el
        # consumo por turno crece con el uso hasta agotar la cuota del
        # proveedor (6.000 TPM en el nivel gratuito de Groq).
        official = [f for f in prior if f.get("source") == "official_longitudinal_history"]
        completed = [f for f in prior if f.get("source") == "completed_call"]
        completed.sort(key=lambda f: f.get("days_since_procedure") or 0)
        return official + completed[-_MAX_PRIOR_COMPLETED_CALLS:]

    async def handle_turn(self, session_id: str, patient_text: str) -> TurnCycleResult:
        session = self._session_repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        fsm = CallOrchestrator(session_id, initial_state=SessionState(session["state"]))
        if fsm.state not in _ACCEPTS_TURN:
            raise SessionNotAcceptingTurnsError(session_id, fsm.state)

        correlation_id = get_correlation_id() or new_correlation_id()
        correlation_uuid = _to_correlation_uuid(correlation_id)
        knowledge_version = session["knowledge_version"]

        if fsm.state is SessionState.ESCALATED:
            try:
                result = self._handle_contact_turn(
                    session_id=session_id,
                    fsm=fsm,
                    patient_text=patient_text,
                    correlation_id=correlation_id,
                )
            except Exception as exc:  # noqa: BLE001 - fail-safe deliberado
                logger.exception(
                    "handoff_contact_failure session_id=%s correlation_id=%s",
                    session_id,
                    correlation_id,
                )
                result = self._fail_safe(
                    session_id=session_id,
                    fsm=fsm,
                    correlation_id=correlation_id,
                    reason=f"recolección de contacto: {exc}",
                )
            self._session_repo.update_state(session_id, state=fsm.state.value)
            return result

        # CREATED -> CONSENT -> INTERVIEWING en el primer turno. No existe
        # todavía un paso de consentimiento explícito y separado en la API
        # de esta fase (fuera del alcance de ORC-002); recibir un turno de
        # texto se trata como consentimiento implícito para el propósito de
        # esta demo — se documenta aquí explícitamente, no en silencio.
        if fsm.state is SessionState.CREATED:
            fsm.transition(SessionState.CONSENT, event="turn_received")
        if fsm.state is SessionState.CONSENT:
            fsm.transition(SessionState.INTERVIEWING, event="consent_confirmed")
        elif fsm.state is SessionState.RESPONDING:
            fsm.transition(SessionState.INTERVIEWING, event="follow_up_turn")

        try:
            result = await self._run_cycle(
                session_id=session_id,
                case_id=session["case_id"],
                fsm=fsm,
                patient_text=patient_text,
                knowledge_version=knowledge_version,
                correlation_id=correlation_id,
                correlation_uuid=correlation_uuid,
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe intencional, ver docstring
            logger.exception(
                "orchestrator_unexpected_failure session_id=%s correlation_id=%s",
                session_id,
                correlation_id,
            )
            result = self._fail_safe(
                session_id=session_id,
                fsm=fsm,
                correlation_id=correlation_id,
                reason=f"excepción no anticipada: {exc}",
            )

        self._session_repo.update_state(session_id, state=fsm.state.value)
        return result

    async def _run_cycle(
        self,
        *,
        session_id: str,
        case_id: str,
        fsm: CallOrchestrator,
        patient_text: str,
        knowledge_version: int,
        correlation_id: str,
        correlation_uuid: uuid.UUID,
    ) -> TurnCycleResult:
        case = await self._case_port.get_case(case_id)
        if case is None:
            raise SessionNotFoundError(session_id)
        case_context = _case_context(case)
        prior_followups = await self._prior_followups(case, exclude_session_id=session_id)

        existing_turns = self._turn_repo.list_for_session(session_id)
        next_sequence = len(existing_turns) + 1
        patient_turn = self._turn_repo.add(
            session_id=session_id, speaker="patient", text=patient_text, sequence=next_sequence
        )

        existing_observations = self._observation_repo.list_for_session(session_id)
        # Aplicar las mismas equivalencias que usa la selección final de la
        # pregunta. Antes, una negación de dolor omitía correctamente sus
        # detalles al responder el turno actual, pero PAIN_LOCATION/
        # PAIN_SEVERITY/PAIN_EVOLUTION reaparecían en el prompt del turno
        # siguiente. El adapter podía entonces atribuir una respuesta breve
        # sobre otro tema al primer detalle de dolor fantasma.
        covered_codes = _covered_objective_codes(existing_observations)
        remaining_objectives = [
            {"code": code, "label": label}
            for code, label in INTERVIEW_OBJECTIVES
            if code not in covered_codes
        ]
        turn_history = [{"speaker": t["speaker"], "text": t["text"]} for t in existing_turns]

        interview_request = AgentRequest(
            session_id=uuid.UUID(session_id),
            correlation_id=correlation_uuid,
            knowledge_version=knowledge_version,
            payload=InterviewTurnInput(
                turns=turn_history,
                remaining_objectives=remaining_objectives,
                last_patient_utterance=patient_text,
                last_patient_turn_id=patient_turn["id"],
                case_context=case_context,
                prior_followups=prior_followups,
            ).model_dump(),
            deadline_ms=self._agent_deadline_ms,
        )
        interview_result = await self._interview_agent.run(interview_request)
        self._log_event(
            session_id=session_id,
            correlation_id=correlation_id,
            event_type="agent.interview.completed",
            payload=interview_result.usage.model_dump(),
        )
        if interview_result.status == "error":
            return self._fail_safe(
                session_id=session_id,
                fsm=fsm,
                correlation_id=correlation_id,
                reason=f"InterviewAgent: {interview_result.output.get('reason')}",
            )

        needs_clarification = bool(interview_result.output.get("needs_clarification"))
        clarification_question = interview_result.output.get("clarification_question")
        raw_observations = interview_result.output.get("observations", [])
        agent_observations = [Observation.model_validate(item) for item in raw_observations]

        # Red de seguridad determinista (SAFE-001 ampliado): se analiza el
        # texto LITERAL del paciente sin pasar por el LLM. Antes, toda la
        # seguridad clínica dependía de que el modelo extrajera bien las
        # observaciones — si fallaba, el motor de reglas no veía nada y el
        # sistema respondía "todo dentro de lo esperado" ante un paciente
        # que reportaba 40 °C de fiebre (visto en vivo; ver
        # `app/domain/safety_signals.py`). Esto corre siempre, incluso si el
        # modelo no extrajo nada, y sus confirmaciones no son degradables.
        safety_observations = detect_safety_signals(patient_text, source_turn_id=patient_turn["id"])
        critical_safety_signal = any(obs.certainty == "confirmed" for obs in safety_observations)
        unspecified_distress = (
            is_unspecified_severe_distress(patient_text) and not critical_safety_signal
        )
        if (
            len(existing_turns) == 1
            and _is_vague_wellbeing_response(patient_text)
            and not critical_safety_signal
        ):
            agent_observations = [
                Observation(
                    code="GENERAL_STATE",
                    label="estado general ambiguo",
                    value=None,
                    certainty="uncertain",
                    source_turn_id=patient_turn["id"],
                    original_text=patient_text,
                    normalized_text="respuesta general sin síntoma identificable",
                    normalized_by="conversation-guard-v1",
                )
            ]
            needs_clarification = True
            clarification_question = (
                "Entiendo. ¿Qué es lo que no está del todo bien hoy: dolor, fiebre, "
                "náuseas, la herida u otra molestia?"
            )
        elif _references_known_history(patient_text) and not critical_safety_signal:
            # No convierte una objeción o una referencia a la historia en una
            # respuesta clínica. Usa la línea base real y pregunta únicamente
            # por el cambio que solo el paciente puede describir hoy.
            agent_observations = []
            needs_clarification = True
            clarification_question = _history_aware_pain_question(case, existing_observations)
        elif unspecified_distress:
            # Una frase puramente subjetiva como "muy mal" sí informa el
            # estado general, pero no identifica una alarma concreta. Se
            # descarta cualquier atribución especulativa del modelo (p. ej.
            # PAIN uncertain) y se ejecuta un tamizaje corto antes de decidir.
            agent_observations = [
                Observation(
                    code="GENERAL_STATE",
                    label="malestar general intenso sin especificar",
                    value="malestar intenso sin síntoma identificado",
                    certainty="confirmed",
                    source_turn_id=patient_turn["id"],
                    original_text=patient_text,
                    normalized_text="requiere tamizaje breve de señales de alarma",
                    normalized_by="urgent-screen-v1",
                )
            ]
            needs_clarification = True
            clarification_question = _URGENT_SCREEN_QUESTION
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type="interview.urgent_screen_requested",
                payload={"reason": "malestar intenso sin síntoma concreto"},
            )

        new_observations = merge_with_safety_precedence(agent_observations, safety_observations)
        longitudinal_observations = derive_longitudinal_safety_signals(
            existing_observations + new_observations,
            case.historical_followups,
            source_turn_id=patient_turn["id"],
        )
        new_observations = merge_with_safety_precedence(new_observations, longitudinal_observations)
        if safety_observations:
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type="safety.signals_detected",
                payload={
                    "confirmed": [
                        o.code for o in safety_observations if o.certainty == "confirmed"
                    ],
                    "denied": [o.code for o in safety_observations if o.certainty == "denied"],
                },
            )

        for observation in new_observations:
            self._observation_repo.add(session_id=session_id, observation=observation)

        # Una señal de alarma confirmada NUNCA se aplaza por una petición de
        # aclaración del modelo: si el paciente dijo algo crítico, el ciclo
        # completo (reglas -> decisión -> escalamiento) tiene que correr en
        # ESTE turno, no en el siguiente (spec.md §11, estado seguro).
        if needs_clarification and critical_safety_signal:
            needs_clarification = False
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type="safety.clarification_overridden",
                payload={
                    "reason": (
                        "señal de alarma confirmada por el detector determinista; "
                        "no se aplaza la evaluación de riesgo"
                    )
                },
            )

        if needs_clarification:
            clarification_text = (
                clarification_question
                or "¿Me puede contar un poco más para entender mejor lo que me describe?"
            )
            self._turn_repo.add(
                session_id=session_id,
                speaker="agent",
                text=clarification_text,
                sequence=next_sequence + 1,
            )
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type="interview.clarification_requested",
                payload={"question": clarification_text},
            )
            # Permanece en INTERVIEWING: la aclaración no consume
            # reglas/retrieval/decisión/respuesta todavía (AC-E2E-003).
            return TurnCycleResult(
                session_id=session_id,
                state=fsm.state,
                agent_message=clarification_text,
                intent="clarify",
                decision_level=DecisionLevel.ROUTINE_FOLLOW_UP,
                should_escalate=False,
                escalated=False,
                needs_clarification=True,
            )

        all_observations = existing_observations + new_observations
        next_question = _resolve_next_question(interview_result.output, all_observations)
        covered_after = _covered_objective_codes(all_observations)
        objectives_pending = any(code not in covered_after for code, _ in INTERVIEW_OBJECTIVES)
        rule_result = evaluate_rules(all_observations)

        fsm.transition(SessionState.RETRIEVING, event="observations_extracted")

        # Acota el retrieval al procedimiento del caso (RAG-005 ampliado,
        # docs/auditoria-kit-oficial-2026-08-07.md §9.2): el corpus real del
        # reto cubre 5 procedimientos distintos en la misma base de
        # conocimiento (apendicectomía, colecistectomía, mastectomía,
        # colectomía, artroplastia) — sin este filtro, una sesión sobre una
        # apendicectomía podría recibir evidencia de un reemplazo de cadera
        # si el ranking léxico/semántico las confunde. Un documento que no
        # declara `applicability.procedure` sigue aplicando a cualquier
        # caso (contenido general); solo se excluyen los que declaran
        # explícitamente OTRO procedimiento (app/services/retrieval.py
        # `_applicability_matches`).
        applicability_filter = (
            {"procedure": case.procedure_category} if case.procedure_category else None
        )

        # La evidencia debe responder a lo que el paciente acaba de decir,
        # no a la próxima pregunta del checklist. Consultar por la siguiente
        # pregunta mezclaba temas y podía dejar sin sustento un síntoma actual.
        retrieval_query = patient_text
        conn = get_connection(self._database_path)
        try:
            retrieval_results = await hybrid_search(
                conn,
                retrieval_query,
                embeddings=self._embeddings,
                session_knowledge_version=knowledge_version,
                top_k=self._retrieval_top_k,
                candidate_pool_size=self._candidate_pool_size,
                applicability_filter=applicability_filter,
            )
        finally:
            conn.close()
        # Rúbrica §5 exige reportar "consultas al RAG por llamada" de forma
        # verificable en logs, no solo inferida de la estructura del código
        # (una consulta por turno hoy) — se instrumenta igual que el uso de
        # tokens de los agentes, vía el mismo `_log_event` fail-open.
        self._log_event(
            session_id=session_id,
            correlation_id=correlation_id,
            event_type="rag.retrieval.completed",
            payload={
                "top_k": self._retrieval_top_k,
                "result_count": len(retrieval_results),
                "knowledge_version": knowledge_version,
                "applicability_filter": applicability_filter,
            },
        )

        evidence_decision = evaluate_evidence(
            retrieval_results,
            score_threshold=self._evidence_score_threshold,
            knowledge_version=knowledge_version,
        )
        text_by_chunk = {r.chunk_id: r.text for r in retrieval_results}
        evidence_sufficient = evidence_decision.status == EvidenceStatus.SUFFICIENT

        # Heurística de diseño (no explícita en spec.md, documentada aquí
        # como el resto de decisiones de diseño del proyecto — ver
        # app.domain.decision._ESCALATING_LEVELS): EVIDENCE_INSUFFICIENT_
        # WITH_RISK solo aplica cuando (a) este turno reportó una señal
        # parcial de especial preocupación (no basta con que
        # `missing_info` tenga códigos que NADIE mencionó — eso pasaría en
        # casi cualquier turno, dado que el checklist de entrevista no
        # cubre todos los códigos de todas las reglas), (b) esa regla no
        # pudo completarse por falta de otro dato, y (c) no hay evidencia
        # que compense esa falta. Una pregunta general sin evidencia
        # (SCEN-E) NO escala por sí sola, solo produce abstención en
        # ResponseAgent (AC-E2E-007). Si ya hay un `hard_red_flag`, el ciclo
        # normal (DECIDING -> TriageAgent) sigue su curso — la precedencia
        # de `reduce_decision` ya garantiza HARD_RED_FLAG sin necesidad de
        # este atajo.
        turn_touched_rule_relevant_signal = any(
            o.code in _EVIDENCE_ESCALATION_SIGNAL_CODES
            and o.certainty in ("confirmed", "uncertain")
            for o in new_observations
        )
        evidence_insufficient_with_risk = (
            not rule_result.hard_red_flag
            and not evidence_sufficient
            and bool(rule_result.missing_info)
            and turn_touched_rule_relevant_signal
        )

        triage_missing_info = list(rule_result.missing_info)
        model_level = DecisionLevel.ROUTINE_FOLLOW_UP

        if evidence_insufficient_with_risk:
            fsm.transition(SessionState.ESCALATED, event="evidence_insufficient_with_risk")
        else:
            fsm.transition(SessionState.DECIDING, event="evidence_evaluated")

            evidence_summaries = [
                text_by_chunk.get(citation.chunk_id, "") for citation in evidence_decision.citations
            ]
            triage_request = AgentRequest(
                session_id=uuid.UUID(session_id),
                correlation_id=correlation_uuid,
                knowledge_version=knowledge_version,
                payload=TriageTurnInput(
                    observations=[o.model_dump(mode="json") for o in all_observations],
                    rule_engine_missing_info=triage_missing_info,
                    evidence_summaries=evidence_summaries,
                    case_context=case_context,
                    prior_followups=prior_followups,
                ).model_dump(),
                deadline_ms=self._agent_deadline_ms,
            )
            triage_result = await self._triage_agent.run(triage_request)
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type="agent.triage.completed",
                payload=triage_result.usage.model_dump(),
            )
            if triage_result.status == "error":
                return self._fail_safe(
                    session_id=session_id,
                    fsm=fsm,
                    correlation_id=correlation_id,
                    reason=f"TriageAgent: {triage_result.output.get('reason')}",
                )
            model_level = DecisionLevel(triage_result.output["model_level"])

        decision_inputs = DecisionInputs(
            hard_red_flag=rule_result.hard_red_flag,
            trigger_codes=rule_result.trigger_codes,
            evidence_insufficient_with_risk=evidence_insufficient_with_risk,
            model_level=model_level,
        )
        decision = reduce_decision(decision_inputs)
        self._decision_repo.add(session_id=session_id, decision=decision)

        if fsm.state is SessionState.DECIDING:
            if decision.should_escalate:
                fsm.transition(SessionState.ESCALATED, event=decision.level.value.lower())
            else:
                fsm.transition(SessionState.RESPONDING, event="decision_routine_or_moderate")
        # si ya estamos en ESCALATED (camino evidence_insufficient_with_risk)
        # no hay transición adicional que hacer aquí.

        escalation_created = False
        if decision.should_escalate:
            escalation_record = self._escalation_repo.create_if_absent(
                session_id=session_id, decision=decision
            )
            escalation_created = True
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type=(
                    "escalation.duplicate_suppressed"
                    if escalation_record.was_duplicate
                    else "escalation.created"
                ),
                payload={
                    "decision_level": decision.level.value,
                    "trigger_codes": decision.trigger_codes,
                    "idempotency_key": escalation_record.idempotency_key,
                },
            )

        response_result = await self._response_agent.run(
            AgentRequest(
                session_id=uuid.UUID(session_id),
                correlation_id=correlation_uuid,
                knowledge_version=knowledge_version,
                payload=ResponseTurnInput(
                    evidence_sufficient=evidence_sufficient,
                    should_escalate=decision.should_escalate,
                    decision_level=decision.level,
                    trigger_codes=decision.trigger_codes,
                    # Bug real encontrado y corregido (docs/auditoria-kit-
                    # oficial-2026-08-07.md §9.2): antes solo se pasaba
                    # {title, text}, que NO alcanza para reconstruir un
                    # `CitationRef` válido (faltan citation_id/document_id/
                    # document_version/chunk_id/knowledge_version) —
                    # `ResponseAgent._parse` descartaba silenciosamente
                    # CADA fragmento (`except Exception: continue`), así que
                    # `result.citations` quedaba SIEMPRE vacío aunque
                    # `intent == "grounded_answer"`. Ahora se pasa el
                    # `CitationRef` completo (`model_dump`) más el campo
                    # extra `text` que necesita el prompt — Pydantic ignora
                    # el campo desconocido al revalidar, así que el
                    # round-trip ya no pierde nada.
                    evidence_fragments=[
                        {**c.model_dump(mode="json"), "text": text_by_chunk.get(c.chunk_id, "")}
                        for c in evidence_decision.citations
                    ],
                    observations_summary=[_obs_summary(o) for o in new_observations],
                    patient_question_or_context=patient_text,
                    case_context=case_context,
                    prior_followups=prior_followups,
                    # El agente debe CONDUCIR la entrevista, no solo
                    # reaccionar: la siguiente pregunta del checklist que
                    # decidió `InterviewAgent` llega hasta el paciente. Antes
                    # solo se usaba como consulta de retrieval y se
                    # descartaba, así que el agente nunca preguntaba nada.
                    next_question=next_question,
                ).model_dump(),
                deadline_ms=self._agent_deadline_ms,
            )
        )
        self._log_event(
            session_id=session_id,
            correlation_id=correlation_id,
            event_type="agent.response.completed",
            payload=response_result.usage.model_dump(),
        )
        if response_result.status == "error":
            return self._fail_safe(
                session_id=session_id,
                fsm=fsm,
                correlation_id=correlation_id,
                reason=f"ResponseAgent: {response_result.output.get('reason')}",
            )

        agent_message = response_result.output["message"]
        intent = response_result.output["intent"]
        if fsm.state is not SessionState.ESCALATED and not objectives_pending:
            agent_message = (
                "Gracias. Completamos el seguimiento de hoy y el reporte quedó "
                "registrado para el equipo de atención. Voy a finalizar la llamada ahora."
            )
            intent = "close"
        response_turn = self._turn_repo.add(
            session_id=session_id,
            speaker="agent",
            text=agent_message,
            sequence=next_sequence + 1,
        )

        if intent == "grounded_answer" and response_result.evidence:
            now = datetime.now(UTC).isoformat()
            with session_scope(self._database_path) as conn:
                for citation in response_result.evidence:
                    self._citation_repo.record(
                        conn, turn_id=response_turn["id"], citation=citation, created_at=now
                    )

        # Cierre del loop: si ya no quedan objetivos del checklist sin
        # cubrir, la sesión está lista para resumir (RESPONDING ->
        # SUMMARIZING); si faltan, vuelve a INTERVIEWING para el próximo
        # turno (architecture.md §7 "Respond->Interview: necesita
        # seguimiento"). ESCALATED permanece abierto únicamente para
        # confirmar teléfono principal y alternativo; ese subflujo cierra
        # automáticamente la llamada en `_handle_contact_turn`.
        if fsm.state is not SessionState.ESCALATED:
            if objectives_pending:
                fsm.transition(SessionState.INTERVIEWING, event="needs_follow_up")
            else:
                fsm.transition(SessionState.SUMMARIZING, event="objectives_covered")
                fsm.transition(SessionState.CLOSED, event="call_finished_automatically")
                self._session_repo.update_state(
                    session_id,
                    state=fsm.state.value,
                    closed_at=datetime.now(UTC).isoformat(),
                )

        return TurnCycleResult(
            session_id=session_id,
            state=fsm.state,
            agent_message=agent_message,
            intent=intent,
            decision_level=decision.level,
            should_escalate=decision.should_escalate,
            escalated=escalation_created,
            citations=list(response_result.evidence),
        )

    def _handle_contact_turn(
        self,
        *,
        session_id: str,
        fsm: CallOrchestrator,
        patient_text: str,
        correlation_id: str,
    ) -> TurnCycleResult:
        """Confirma teléfono principal y alternativo después del handoff."""
        existing_turns = self._turn_repo.list_for_session(session_id)
        patient_turn = self._turn_repo.add(
            session_id=session_id,
            speaker="patient",
            text=patient_text,
            sequence=len(existing_turns) + 1,
        )
        observations = self._observation_repo.list_for_session(session_id)
        confirmed_codes = {item.code for item in observations if item.certainty == "confirmed"}
        target_code = (
            "CONTACT_PRIMARY" if "CONTACT_PRIMARY" not in confirmed_codes else "CONTACT_EMERGENCY"
        )
        phone_number = _extract_contact_number(patient_text)
        decisions = self._decision_repo.list_for_session(session_id)
        if not decisions:
            raise RuntimeError("handoff sin decisión persistida")
        decision_level = DecisionLevel(decisions[-1]["level"])

        if phone_number is None:
            message = (
                "No alcancé a identificar el número. Por favor dígamelo nuevamente "
                "incluyendo todos los dígitos."
            )
            self._turn_repo.add(
                session_id=session_id,
                speaker="agent",
                text=message,
                sequence=len(existing_turns) + 2,
            )
            return TurnCycleResult(
                session_id=session_id,
                state=fsm.state,
                agent_message=message,
                intent="handoff_contact",
                decision_level=decision_level,
                should_escalate=True,
                escalated=True,
                needs_clarification=True,
            )

        label = (
            "teléfono principal de contacto"
            if target_code == "CONTACT_PRIMARY"
            else "teléfono alternativo de emergencia"
        )
        self._observation_repo.add(
            session_id=session_id,
            observation=Observation(
                code=target_code,
                label=label,
                value=phone_number,
                certainty="confirmed",
                source_turn_id=patient_turn["id"],
                original_text=patient_text.strip(),
                normalized_by="contact-capture-v1",
            ),
        )

        if target_code == "CONTACT_PRIMARY":
            message = (
                "Gracias. ¿Me comparte también un número adicional de emergencia, "
                "por si el equipo no logra comunicarse con usted en el principal?"
            )
        else:
            message = (
                "Gracias. El reporte y los dos números quedaron enviados al equipo de "
                "atención prioritaria. Una persona lo contactará para continuar la "
                "atención. Voy a finalizar la llamada ahora."
            )
            fsm.transition(SessionState.SUMMARIZING, event="contact_details_completed")
            fsm.transition(SessionState.CLOSED, event="call_finished_automatically")
            self._session_repo.update_state(
                session_id,
                state=fsm.state.value,
                closed_at=datetime.now(UTC).isoformat(),
            )
            self._log_event(
                session_id=session_id,
                correlation_id=correlation_id,
                event_type="handoff.contact_completed",
                payload={"primary": True, "emergency": True, "auto_closed": True},
            )

        self._turn_repo.add(
            session_id=session_id,
            speaker="agent",
            text=message,
            sequence=len(existing_turns) + 2,
        )
        return TurnCycleResult(
            session_id=session_id,
            state=fsm.state,
            agent_message=message,
            intent="handoff_contact",
            decision_level=decision_level,
            should_escalate=True,
            escalated=True,
        )

    def _fail_safe(
        self, *, session_id: str, fsm: CallOrchestrator, correlation_id: str, reason: str
    ) -> TurnCycleResult:
        if fsm.can_transition(SessionState.FAIL_SAFE):
            fsm.transition(SessionState.FAIL_SAFE, event="agent_error")

        decision = reduce_decision(DecisionInputs(data_integrity_failure=True))
        self._decision_repo.add(session_id=session_id, decision=decision)
        escalation_record = self._escalation_repo.create_if_absent(
            session_id=session_id, decision=decision
        )

        self._log_event(
            session_id=session_id,
            correlation_id=correlation_id,
            event_type="orchestrator.fail_safe",
            payload={"reason": reason, "idempotency_key": escalation_record.idempotency_key},
        )

        safe_message = (
            "Tuvimos un inconveniente técnico procesando este turno. Por seguridad, "
            "voy a dejar este caso registrado para que lo revise una persona del equipo."
        )
        existing_turns = self._turn_repo.list_for_session(session_id)
        self._turn_repo.add(
            session_id=session_id,
            speaker="agent",
            text=safe_message,
            sequence=len(existing_turns) + 1,
        )

        # La sesión queda en FAIL_SAFE (no se auto-avanza): `shortest_path`
        # (session_fsm.py, ya usado por `/finish`) garantiza que siempre hay
        # camino hacia `closed` desde aquí — el cierre explícito decide
        # cuándo completar FAIL_SAFE -> SUMMARIZING -> CLOSED, igual que ya
        # hace `finish_session`. `build_summary`/el WS tratan FAIL_SAFE como
        # un estado "listo para resumir" (ver `_SUMMARY_STATES` en
        # `app.api.routes.ws`), así que el resumen se comunica igual.
        return TurnCycleResult(
            session_id=session_id,
            state=fsm.state,
            agent_message=safe_message,
            intent="handoff",
            decision_level=decision.level,
            should_escalate=True,
            escalated=True,
            warnings=[reason],
        )

    async def build_summary(self, session_id: str) -> CallSummary:
        """SUM-002: ensambla el `CallSummary` de una sesión a partir de lo
        ya persistido (observaciones, decisiones, citas, escalamientos,
        uso agregado desde los eventos `agent.*.completed`) y materializa
        idempotentemente su `FollowupRecord` longitudinal. No cambia el
        estado de la FSM ni ejecuta acciones clínicas externas."""
        session = self._session_repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        observations = self._observation_repo.list_for_session(session_id)
        decisions = self._decision_repo.list_for_session(session_id)
        escalations = self._escalation_repo.list_for_session(session_id)
        with session_scope(self._database_path) as conn:
            citation_rows = self._citation_repo.list_for_session(conn, session_id)
        citations = [self._citation_repo.to_citation_ref(row) for row in citation_rows]

        events = self._event_repo.list_for_session(session_id)
        usage = _sum_usage_from_events(events)
        case = await self._case_port.get_case(session["case_id"])

        ended_at = datetime.fromisoformat(session["closed_at"]) if session["closed_at"] else None

        summary = build_call_summary(
            session=session,
            observations=observations,
            decisions=decisions,
            citations=citations,
            escalations=escalations,
            patient_id=case.patient_id if case is not None else None,
            procedure=case.procedure if case is not None else None,
            surgery_date=case.surgery_date if case is not None else None,
            usage=usage,
            ended_at=ended_at,
        )
        if summary.followup_record is not None and summary.followup_record.patient_id:
            self._followup_repo.upsert(
                session_id=session_id,
                case_id=session["case_id"],
                record=summary.followup_record,
            )
        return summary

    def _log_event(
        self,
        *,
        session_id: str,
        correlation_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Telemetría no clínica: fail-open (architecture.md §13.1) — nunca
        se deja que un fallo de escritura de evento tumbe el ciclo de la
        llamada, pero tampoco se oculta: siempre queda en el log."""
        try:
            self._event_repo.add_event(
                session_id=session_id,
                correlation_id=correlation_id,
                component="orchestrator",
                event_type=event_type,
                payload=payload,
            )
        except Exception:  # noqa: BLE001 - fail-open intencional, ver docstring
            logger.exception(
                "orchestrator_event_persist_failed session_id=%s event_type=%s",
                session_id,
                event_type,
            )


__all__ = [
    "CallCycleOrchestrator",
    "SessionNotAcceptingTurnsError",
    "SessionNotFoundError",
    "TurnCycleResult",
]
