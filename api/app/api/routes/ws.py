"""`WS /ws/sessions/{session_id}` — turno conversacional en tiempo real
(API-002, architecture.md §5.1/§12.2).

Envelope versionado, adaptado de architecture.md §12.2 a los tipos
concretos que produce `CallCycleOrchestrator` (ORC-002):

    {"v": 1, "type": str, "seq": int, "payload": dict, "correlation_id": str}

`seq` es monotónico creciente PARA LOS MENSAJES QUE EL SERVIDOR envía en
esta conexión (arranca en 1, un contador por conexión — nunca se reordena
ni se reutiliza, incluso si el cliente manda varios `client.turn_text`
seguidos sin esperar respuesta).

Tipos:

- `client.turn_text` (entrante): `{"text": str}` — un turno de texto del
  cuidador/paciente. El pipeline de voz real (STT/TTS) es una decisión
  diferida al 7 de agosto (architecture.md §10.2); este ticket opera sobre
  texto para no acoplar el ciclo del orquestador a un adapter de voz que
  todavía no existe.
- `server.state` (saliente): estado FSM tras procesar el turno.
- `server.agent_response` (saliente): mensaje de `ResponseAgent` + intent +
  citas.
- `server.decision` (saliente): resultado de `reduce_decision` +
  escalamiento.
- `server.error` (saliente): error recuperable (sesión no encontrada,
  estado que no acepta turnos, mensaje malformado) — la conexión NO se
  cierra por esto, el cliente puede reintentar.
- `server.summary` (saliente): `CallSummary` (SUM-002) cuando el turno deja
  la sesión en `SUMMARIZING`/`FAIL_SAFE`.

Cada turno completo (recepción de `client.turn_text` -> envío de
`server.agent_response`) se instrumenta como evento `turn.response_sent`
con `latency_ms` real (`_log_turn_latency`) — es la única fuente que
`AuditRepository.latency_percentiles()` agrega para el P50/P95 exigido en
el README (rúbrica §5). Antes de esto, `/metrics` promediaba latencia de
CUALQUIER request HTTP (incluidos uploads de conocimiento, polling de
`/audit`), no la del turno conversacional — corregido tras la auditoría del
7 de agosto (`docs/auditoria-kit-oficial-2026-08-07.md` §9).

Consistencia ante desconexión: cada escritura de dominio (turno,
observación, decisión, escalamiento) ya vive en su propia transacción
corta dentro de `CallCycleOrchestrator.handle_turn` (DB-002) — si el socket
se cae a mitad de un ciclo, lo único que se pierde es el envelope de salida
que no llegó a enviarse; la sesión queda en el último estado
efectivamente persistido, nunca a medio escribir. `_send` nunca deja
escapar una excepción del transporte hacia el ciclo del orquestador: si el
socket ya está cerrado, deja de enviar y el loop termina en el próximo
`receive_json`."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocketState

from app.core.correlation_id import new_correlation_id, set_correlation_id
from app.domain.session_fsm import SessionState
from app.orchestrator.call_cycle import (
    CallCycleOrchestrator,
    SessionNotAcceptingTurnsError,
    SessionNotFoundError,
)
from app.repositories.events import EventRepository

logger = logging.getLogger("care_companion.ws")

router = APIRouter(tags=["sessions"])

ENVELOPE_VERSION = 1

_SUMMARY_STATES = frozenset({SessionState.SUMMARIZING, SessionState.CLOSED, SessionState.FAIL_SAFE})


class ClientTurnText(BaseModel):
    text: str


class _SeqCounter:
    def __init__(self) -> None:
        self._value = 0

    def next(self) -> int:
        self._value += 1
        return self._value


async def _send(
    websocket: WebSocket, *, type_: str, seq: int, payload: dict[str, Any], correlation_id: str
) -> bool:
    """Devuelve `False` si el socket ya no acepta escrituras (desconexión) —
    el llamador debe terminar el loop en ese caso, no seguir intentando."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return False
    envelope = {
        "v": ENVELOPE_VERSION,
        "type": type_,
        "seq": seq,
        "payload": payload,
        "correlation_id": correlation_id,
    }
    try:
        await websocket.send_json(envelope)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


def _log_turn_latency(
    websocket: WebSocket,
    *,
    session_id: str,
    correlation_id: str,
    state: str,
    intent: str,
    latency_ms: float,
) -> None:
    """Telemetría no clínica: fail-open (architecture.md §13.1), igual que
    `CallCycleOrchestrator._log_event` — un fallo de escritura nunca tumba
    el turno de voz, pero tampoco se oculta, siempre queda en el log.
    `event_type="turn.response_sent"` es el único que
    `AuditRepository.latency_percentiles()` agrega para P50/P95 (RAG-002/
    PERF-001) — así el HTTP administrativo (uploads, polling de /audit) no
    contamina la métrica de latencia conversacional."""
    try:
        event_repo: EventRepository = websocket.app.state.event_repo
        event_repo.add_event(
            session_id=session_id,
            correlation_id=correlation_id,
            component="ws",
            event_type="turn.response_sent",
            payload={"state": state, "intent": intent},
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception(
            "turn_latency_persist_failed session_id=%s correlation_id=%s",
            session_id,
            correlation_id,
        )


@router.websocket("/ws/sessions/{session_id}")
async def session_turn_websocket(websocket: WebSocket, session_id: str) -> None:
    orchestrator: CallCycleOrchestrator = websocket.app.state.call_cycle_orchestrator
    await websocket.accept()
    seq = _SeqCounter()

    while True:
        try:
            raw = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except ValueError:
            correlation_id = new_correlation_id()
            if not await _send(
                websocket,
                type_="server.error",
                seq=seq.next(),
                payload={"reason": "mensaje no es JSON válido"},
                correlation_id=correlation_id,
            ):
                return
            continue

        correlation_id = str(raw.get("correlation_id") or new_correlation_id())
        set_correlation_id(correlation_id)
        msg_type = raw.get("type")

        if msg_type != "client.turn_text":
            if not await _send(
                websocket,
                type_="server.error",
                seq=seq.next(),
                payload={"reason": f"tipo de mensaje no soportado: {msg_type!r}"},
                correlation_id=correlation_id,
            ):
                return
            continue

        try:
            turn_payload = ClientTurnText.model_validate(raw.get("payload") or {})
        except ValidationError as exc:
            if not await _send(
                websocket,
                type_="server.error",
                seq=seq.next(),
                payload={"reason": f"payload inválido: {exc.errors()}"},
                correlation_id=correlation_id,
            ):
                return
            continue

        turn_started_at = time.perf_counter()
        try:
            result = await orchestrator.handle_turn(session_id, turn_payload.text)
        except SessionNotFoundError:
            if not await _send(
                websocket,
                type_="server.error",
                seq=seq.next(),
                payload={"reason": "sesión no encontrada"},
                correlation_id=correlation_id,
            ):
                return
            continue
        except SessionNotAcceptingTurnsError as exc:
            if not await _send(
                websocket,
                type_="server.error",
                seq=seq.next(),
                payload={"reason": str(exc), "state": exc.state.value},
                correlation_id=correlation_id,
            ):
                return
            continue

        if not await _send(
            websocket,
            type_="server.state",
            seq=seq.next(),
            payload={"state": result.state.value},
            correlation_id=correlation_id,
        ):
            return

        if not await _send(
            websocket,
            type_="server.agent_response",
            seq=seq.next(),
            payload={
                "message": result.agent_message,
                "intent": result.intent,
                "needs_clarification": result.needs_clarification,
                "citations": [c.model_dump(mode="json") for c in result.citations],
            },
            correlation_id=correlation_id,
        ):
            return
        # Rúbrica §5: "latencia P50/P95 medida desde que el paciente termina
        # de hablar hasta que empieza a sonar el audio del agente". Este es
        # el mejor proxy medible en el backend: desde que se recibió
        # `client.turn_text` (fin del turno de STT, ya ocurrido en el
        # navegador) hasta que el envelope con el texto de respuesta salió
        # por el socket — el cliente inicia TTS inmediatamente al recibirlo.
        # No incluye el tiempo de red del envelope ni el arranque real del
        # motor de TTS en el navegador (Web Speech API es sincrónico y
        # rápido, pero no es 0ms) — límite conocido, documentado en vez de
        # fingir precisión que el backend no puede medir por sí solo.
        _log_turn_latency(
            websocket,
            session_id=session_id,
            correlation_id=correlation_id,
            state=result.state.value,
            intent=result.intent,
            latency_ms=(time.perf_counter() - turn_started_at) * 1000,
        )

        if not await _send(
            websocket,
            type_="server.decision",
            seq=seq.next(),
            payload={
                "level": result.decision_level.value,
                "should_escalate": result.should_escalate,
                "escalated": result.escalated,
            },
            correlation_id=correlation_id,
        ):
            return

        if result.state in _SUMMARY_STATES:
            summary = await orchestrator.build_summary(session_id)
            if not await _send(
                websocket,
                type_="server.summary",
                seq=seq.next(),
                payload=summary.model_dump(mode="json"),
                correlation_id=correlation_id,
            ):
                return
