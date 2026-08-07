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
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.interview import INTERVIEW_OBJECTIVES, InterviewAgent, InterviewTurnInput
from app.agents.response import ResponseAgent, ResponseTurnInput
from app.agents.triage import TriageAgent, TriageTurnInput
from app.core.correlation_id import get_correlation_id, new_correlation_id
from app.domain.decision import DecisionInputs, DecisionLevel, reduce_decision
from app.domain.evidence import EvidenceStatus, evaluate_evidence
from app.domain.models import AgentRequest, CitationRef, UsageMetrics
from app.domain.observation import Observation
from app.domain.session_fsm import CallOrchestrator, SessionState
from app.domain.summary import CallSummary, build_call_summary
from app.ports.challenge_case import ChallengeCasePort
from app.ports.embeddings import EmbeddingsPort
from app.ports.llm import LLMPort
from app.repositories.citations import CitationRepository
from app.repositories.db import get_connection, session_scope
from app.repositories.decisions import DecisionRepository
from app.repositories.escalations import EscalationRepository
from app.repositories.events import EventRepository
from app.repositories.observations import ObservationRepository
from app.repositories.sessions import SessionRepository
from app.repositories.turns import TurnRepository
from app.services.retrieval import hybrid_search
from app.services.rule_engine import RULESET_V1, evaluate_rules

logger = logging.getLogger("care_companion.orchestrator")

AGENT_DEADLINE_MS = 5000

# Códigos de observación que participan en al menos una regla determinista
# (SAFE-001). Se usan para distinguir "el motor de reglas casi disparó pero
# le faltó un dato" de "el motor de reglas nunca tuvo nada que evaluar" —
# ver `evidence_insufficient_with_risk` en `_run_cycle`. Derivado del
# ruleset real (no hardcodeado aparte) para que agregar una regla nueva
# actualice esta señal automáticamente.
_RULE_RELEVANT_CODES: frozenset[str] = frozenset(
    condition.observation_code for rule in RULESET_V1 for condition in rule.requires
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
        input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=latency_ms,
        provider=provider, model=model,
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
    ) -> None:
        self._database_path = database_path
        self._embeddings = embeddings
        self._case_port = case_port
        self._evidence_score_threshold = evidence_score_threshold
        self._candidate_pool_size = candidate_pool_size
        self._retrieval_top_k = retrieval_top_k

        self._interview_agent = InterviewAgent(llm)
        self._triage_agent = TriageAgent(llm)
        self._response_agent = ResponseAgent(llm)

        self._session_repo = SessionRepository(database_path)
        self._turn_repo = TurnRepository(database_path)
        self._observation_repo = ObservationRepository(database_path)
        self._decision_repo = DecisionRepository(database_path)
        self._escalation_repo = EscalationRepository(database_path)
        self._event_repo = EventRepository(database_path)
        self._citation_repo = CitationRepository()

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
                session_id, correlation_id,
            )
            result = self._fail_safe(
                session_id=session_id, fsm=fsm, correlation_id=correlation_id,
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
        existing_turns = self._turn_repo.list_for_session(session_id)
        next_sequence = len(existing_turns) + 1
        patient_turn = self._turn_repo.add(
            session_id=session_id, speaker="patient", text=patient_text, sequence=next_sequence
        )

        existing_observations = self._observation_repo.list_for_session(session_id)
        covered_codes = {o.code for o in existing_observations if o.certainty != "not_assessed"}
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
            ).model_dump(),
            deadline_ms=AGENT_DEADLINE_MS,
        )
        interview_result = await self._interview_agent.run(interview_request)
        self._log_event(
            session_id=session_id, correlation_id=correlation_id,
            event_type="agent.interview.completed", payload=interview_result.usage.model_dump(),
        )
        if interview_result.status == "error":
            return self._fail_safe(
                session_id=session_id, fsm=fsm, correlation_id=correlation_id,
                reason=f"InterviewAgent: {interview_result.output.get('reason')}",
            )

        needs_clarification = bool(interview_result.output.get("needs_clarification"))
        raw_observations = interview_result.output.get("observations", [])
        new_observations = [Observation.model_validate(item) for item in raw_observations]
        for observation in new_observations:
            self._observation_repo.add(session_id=session_id, observation=observation)

        if needs_clarification:
            clarification_text = (
                interview_result.output.get("clarification_question")
                or "¿Me puede contar un poco más para entender mejor lo que me describe?"
            )
            self._turn_repo.add(
                session_id=session_id, speaker="agent", text=clarification_text,
                sequence=next_sequence + 1,
            )
            self._log_event(
                session_id=session_id, correlation_id=correlation_id,
                event_type="interview.clarification_requested",
                payload={"question": clarification_text},
            )
            # Permanece en INTERVIEWING: la aclaración no consume
            # reglas/retrieval/decisión/respuesta todavía (AC-E2E-003).
            return TurnCycleResult(
                session_id=session_id, state=fsm.state, agent_message=clarification_text,
                intent="clarify", decision_level=DecisionLevel.ROUTINE_FOLLOW_UP,
                should_escalate=False, escalated=False, needs_clarification=True,
            )

        all_observations = existing_observations + new_observations
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
        case = await self._case_port.get_case(case_id)
        applicability_filter = (
            {"procedure": case.procedure_category}
            if case is not None and case.procedure_category
            else None
        )

        retrieval_query = interview_result.output.get("next_question") or patient_text
        conn = get_connection(self._database_path)
        try:
            retrieval_results = await hybrid_search(
                conn, retrieval_query, embeddings=self._embeddings,
                session_knowledge_version=knowledge_version,
                top_k=self._retrieval_top_k, candidate_pool_size=self._candidate_pool_size,
                applicability_filter=applicability_filter,
            )
        finally:
            conn.close()
        # Rúbrica §5 exige reportar "consultas al RAG por llamada" de forma
        # verificable en logs, no solo inferida de la estructura del código
        # (una consulta por turno hoy) — se instrumenta igual que el uso de
        # tokens de los agentes, vía el mismo `_log_event` fail-open.
        self._log_event(
            session_id=session_id, correlation_id=correlation_id,
            event_type="rag.retrieval.completed",
            payload={
                "top_k": self._retrieval_top_k,
                "result_count": len(retrieval_results),
                "knowledge_version": knowledge_version,
                "applicability_filter": applicability_filter,
            },
        )

        evidence_decision = evaluate_evidence(
            retrieval_results, score_threshold=self._evidence_score_threshold,
            knowledge_version=knowledge_version,
        )
        text_by_chunk = {r.chunk_id: r.text for r in retrieval_results}
        evidence_sufficient = evidence_decision.status == EvidenceStatus.SUFFICIENT

        # Heurística de diseño (no explícita en spec.md, documentada aquí
        # como el resto de decisiones de diseño del proyecto — ver
        # app.domain.decision._ESCALATING_LEVELS): EVIDENCE_INSUFFICIENT_
        # WITH_RISK solo aplica cuando (a) este turno reportó una señal
        # relevante para ALGUNA regla determinista (no basta con que
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
            o.code in _RULE_RELEVANT_CODES and o.certainty in ("confirmed", "uncertain")
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
                ).model_dump(),
                deadline_ms=AGENT_DEADLINE_MS,
            )
            triage_result = await self._triage_agent.run(triage_request)
            self._log_event(
                session_id=session_id, correlation_id=correlation_id,
                event_type="agent.triage.completed", payload=triage_result.usage.model_dump(),
            )
            if triage_result.status == "error":
                return self._fail_safe(
                    session_id=session_id, fsm=fsm, correlation_id=correlation_id,
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
                session_id=session_id, correlation_id=correlation_id,
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
                    # El agente debe CONDUCIR la entrevista, no solo
                    # reaccionar: la siguiente pregunta del checklist que
                    # decidió `InterviewAgent` llega hasta el paciente. Antes
                    # solo se usaba como consulta de retrieval y se
                    # descartaba, así que el agente nunca preguntaba nada.
                    next_question=interview_result.output.get("next_question"),
                ).model_dump(),
                deadline_ms=AGENT_DEADLINE_MS,
            )
        )
        self._log_event(
            session_id=session_id, correlation_id=correlation_id,
            event_type="agent.response.completed", payload=response_result.usage.model_dump(),
        )
        if response_result.status == "error":
            return self._fail_safe(
                session_id=session_id, fsm=fsm, correlation_id=correlation_id,
                reason=f"ResponseAgent: {response_result.output.get('reason')}",
            )

        agent_message = response_result.output["message"]
        intent = response_result.output["intent"]
        response_turn = self._turn_repo.add(
            session_id=session_id, speaker="agent", text=agent_message,
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
        # seguimiento"). El camino de escalamiento (ESCALATED) siempre va a
        # SUMMARIZING — no hay vuelta a interview tras escalar.
        if fsm.state is SessionState.ESCALATED:
            fsm.transition(SessionState.SUMMARIZING, event="handoff_registered")
        else:
            covered_after = {o.code for o in all_observations if o.certainty != "not_assessed"}
            objectives_pending = any(code not in covered_after for code, _ in INTERVIEW_OBJECTIVES)
            if objectives_pending:
                fsm.transition(SessionState.INTERVIEWING, event="needs_follow_up")
            else:
                fsm.transition(SessionState.SUMMARIZING, event="objectives_covered")

        return TurnCycleResult(
            session_id=session_id, state=fsm.state, agent_message=agent_message, intent=intent,
            decision_level=decision.level, should_escalate=decision.should_escalate,
            escalated=escalation_created, citations=list(response_result.evidence),
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
            session_id=session_id, correlation_id=correlation_id,
            event_type="orchestrator.fail_safe",
            payload={"reason": reason, "idempotency_key": escalation_record.idempotency_key},
        )

        safe_message = (
            "Tuvimos un inconveniente técnico procesando este turno. Por seguridad, "
            "voy a dejar este caso registrado para que lo revise una persona del equipo."
        )
        existing_turns = self._turn_repo.list_for_session(session_id)
        self._turn_repo.add(
            session_id=session_id, speaker="agent", text=safe_message,
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
            session_id=session_id, state=fsm.state, agent_message=safe_message, intent="handoff",
            decision_level=decision.level, should_escalate=True, escalated=True,
            warnings=[reason],
        )

    async def build_summary(self, session_id: str) -> CallSummary:
        """SUM-002: ensambla el `CallSummary` de una sesión a partir de lo
        ya persistido (observaciones, decisiones, citas, escalamientos,
        uso agregado desde los eventos `agent.*.completed`). No dispara
        ningún efecto secundario ni transición de la FSM — solo lectura."""
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

        ended_at = (
            datetime.fromisoformat(session["closed_at"]) if session["closed_at"] else None
        )

        return build_call_summary(
            session=session, observations=observations, decisions=decisions,
            citations=citations, escalations=escalations, usage=usage, ended_at=ended_at,
        )

    def _log_event(
        self, *, session_id: str, correlation_id: str, event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Telemetría no clínica: fail-open (architecture.md §13.1) — nunca
        se deja que un fallo de escritura de evento tumbe el ciclo de la
        llamada, pero tampoco se oculta: siempre queda en el log."""
        try:
            self._event_repo.add_event(
                session_id=session_id, correlation_id=correlation_id, component="orchestrator",
                event_type=event_type, payload=payload,
            )
        except Exception:  # noqa: BLE001 - fail-open intencional, ver docstring
            logger.exception(
                "orchestrator_event_persist_failed session_id=%s event_type=%s",
                session_id, event_type,
            )


__all__ = [
    "CallCycleOrchestrator",
    "SessionNotAcceptingTurnsError",
    "SessionNotFoundError",
    "TurnCycleResult",
]
