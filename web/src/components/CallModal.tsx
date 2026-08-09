"use client";

/**
 * `CallModal` — la experiencia completa de una llamada de voz, como
 * ventana modal reutilizable.
 *
 * Extraído de `/call/page.tsx` (9 ago) para que `/knowledge` también
 * pueda abrir una llamada real sin duplicar toda la lógica de WebSocket,
 * voz y estado de turno — pedido explícito: la prueba de G5 (aprender/
 * olvidar) necesita verificar en una llamada real que el documento recién
 * subido se usa, sin forzar el selector de pacientes de `/call` ni su
 * protocolo completo de historial longitudinal.
 *
 * Quien renderiza este componente es responsable de decidir QUÉ caso
 * recibe la llamada (`patientCase`) y qué pasa al cerrarla (`onClose`) —
 * el modal en sí no sabe si vino de un selector de 160 pacientes reales o
 * de un botón "Probar en una llamada" con un caso sintético.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { VoiceOrb } from "@/components/VoiceOrb";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { RiskPanel } from "@/components/RiskPanel";
import { StatusBanner } from "@/components/StatusBanner";
import { useVoiceSession } from "@/lib/useVoiceSession";
import {
  api,
  ApiError,
  callSocketUrl,
  decisionToRisk,
  mapWsCitation,
  type CaseSummary,
  type CitationRef,
  type DecisionLevel,
  type RiskLevel,
  type ServerEnvelope,
  type SessionStatus,
  type Turn,
  type VoiceState,
} from "@/lib/api";

/** FSM state → voice-orb state (display only). */
function stateToVoice(state: SessionStatus): VoiceState {
  switch (state) {
    case "retrieving":
    case "deciding":
      return "thinking";
    case "responding":
      return "assistant_speaking";
    case "fail_safe":
      return "failed";
    case "interviewing":
    case "consent":
    case "escalated":
      return "listening";
    default:
      return "ready";
  }
}

const STATE_LABELS: Record<SessionStatus, string> = {
  created: "Sesión creada",
  consent: "Consentimiento",
  interviewing: "Entrevistando",
  retrieving: "Buscando evidencia",
  deciding: "Evaluando riesgo",
  responding: "Respondiendo",
  summarizing: "Resumiendo",
  closed: "Llamada cerrada",
  fail_safe: "Modo seguro",
  escalated: "Escalado a persona",
};

type CallPhase = "idle" | "connecting" | "active" | "closed";

/**
 * Estados en los que el backend YA NO acepta turnos nuevos — complemento
 * exacto de `_ACCEPTS_TURN` (app/orchestrator/call_cycle.py). Si el
 * frontend sigue enviando turnos en estos estados, el backend responde
 * `server.error` en cada uno.
 */
const TERMINAL_STATES = new Set<SessionStatus>([
  "summarizing",
  "closed",
  "fail_safe",
]);

let turnCounter = 0;
function makeTurn(sessionId: string, speaker: Turn["speaker"], text: string): Turn {
  turnCounter += 1;
  return {
    id: `${sessionId}-${turnCounter}`,
    sessionId,
    speaker,
    text,
    isFinal: true,
    startedAt: new Date().toISOString(),
  };
}

function formatSurgeryDate(value: string | null): string {
  if (!value) return "Fecha no disponible";
  return new Date(`${value}T00:00:00`).toLocaleDateString("es-CO", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatClinicalValue(value: string): string {
  return value.replaceAll("_", " ");
}

export interface CallModalProps {
  patientCase: CaseSummary;
  onClose: () => void;
}

export function CallModal({ patientCase, onClose }: CallModalProps) {
  const patientAlias = patientCase.patientAlias;

  const [phase, setPhase] = useState<CallPhase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fsmState, setFsmState] = useState<SessionStatus>("created");
  const [voiceState, setVoiceState] = useState<VoiceState>("ready");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [citations, setCitations] = useState<CitationRef[]>([]);
  const [riskLevel, setRiskLevel] = useState<RiskLevel | null>(null);
  const [decisionLevel, setDecisionLevel] = useState<DecisionLevel | null>(null);
  const [escalated, setEscalated] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const socketRef = useRef<WebSocket | null>(null);
  const clientSeqRef = useRef(0);
  // Refs so the WebSocket onmessage closure (captured once at connect time)
  // always reaches the latest voice behavior without being recreated.
  const voiceModeRef = useRef(false);
  const speakRef = useRef<(text: string) => void>(() => {});
  const sessionIdRef = useRef<string | null>(null);
  const stopListeningRef = useRef<() => void>(() => {});
  const startListeningRef = useRef<() => void>(() => {});
  // El último estado FSM conocido, leído desde closures del socket/voz sin
  // recrearlas (el estado de React no está disponible dentro de ellas).
  const fsmStateRef = useRef<SessionStatus>("created");

  useEffect(() => {
    return () => socketRef.current?.close();
  }, []);

  function handleServerEnvelope(env: ServerEnvelope, sid: string) {
    switch (env.type) {
      case "server.state":
        setFsmState(env.payload.state);
        fsmStateRef.current = env.payload.state;
        setVoiceState(stateToVoice(env.payload.state));
        if (env.payload.state === "escalated") setEscalated(true);
        // Una vez que el backend deja la sesión en un estado que ya no
        // acepta turnos hay que apagar SOLO el micrófono. No usar
        // `voice.stop()` aquí: el contrato WS envía `server.state` ANTES de
        // `server.agent_response`, y `stop()` también cancela TTS y apaga el
        // modo voz. Ese orden hizo que el handoff crítico apareciera escrito
        // pero nunca se pronunciara. `stopListening()` preserva la salida de
        // voz final sin permitir nuevos turnos ni reabrir el micrófono.
        if (TERMINAL_STATES.has(env.payload.state)) {
          stopListeningRef.current();
        }
        break;
      case "server.agent_response":
        if (env.payload.message) {
          setTurns((prev) => [...prev, makeTurn(sid, "assistant", env.payload.message)]);
          // Pronuncia la respuesta cuando la llamada está usando salida de voz.
          // En un estado terminal esta es la última locución: se encola
          // primero y luego se desactiva el modo para mensajes posteriores.
          if (voiceModeRef.current) speakRef.current(env.payload.message);
        }
        if (TERMINAL_STATES.has(fsmStateRef.current)) voiceModeRef.current = false;
        if (env.payload.citations.length > 0) {
          setCitations(env.payload.citations.map(mapWsCitation));
        }
        break;
      case "server.decision":
        setDecisionLevel(env.payload.level);
        setRiskLevel(decisionToRisk(env.payload.level));
        if (env.payload.escalated) setEscalated(true);
        break;
      case "server.summary":
        setVoiceState("ready");
        socketRef.current?.close();
        setPhase("closed");
        break;
      case "server.error":
        setCallError(env.payload.reason);
        break;
    }
  }

  async function startCall() {
    setPhase("connecting");
    setCallError(null);
    setTurns([]);
    setCitations([]);
    setRiskLevel(null);
    setDecisionLevel(null);
    setEscalated(false);
    clientSeqRef.current = 0;

    let session;
    try {
      session = await api.createSession(patientCase.id);
    } catch (error) {
      setCallError(error instanceof ApiError ? error.message : "No se pudo crear la sesión.");
      setPhase("idle");
      return;
    }

    setSessionId(session.id);
    sessionIdRef.current = session.id;
    setFsmState(session.status);
    fsmStateRef.current = session.status;

    const ws = new WebSocket(callSocketUrl(session.id));
    socketRef.current = ws;

    ws.onopen = () => {
      setPhase("active");
      if (session.openingMessage) {
        setTurns([makeTurn(session.id, "assistant", session.openingMessage)]);
        // Ambas funciones son no-op seguro si la capacidad no existe. No
        // se condiciona el TTS a que STT también esté disponible: incluso
        // con fallback textual, un navegador con síntesis debe pronunciar
        // la apertura y las respuestas.
        voiceModeRef.current = true;
        startListeningRef.current();
        speakRef.current(session.openingMessage);
      }
    };
    ws.onmessage = (event) => {
      try {
        const env = JSON.parse(event.data) as ServerEnvelope;
        handleServerEnvelope(env, session.id);
      } catch {
        setCallError("Mensaje del servidor ilegible.");
      }
    };
    ws.onerror = () => {
      setCallError("Error de conexión con el canal de la llamada.");
      setVoiceState("failed");
    };
    ws.onclose = () => {
      if (phase !== "closed") setPhase((p) => (p === "active" ? "active" : "idle"));
    };
  }

  const sendText = useCallback((rawText: string) => {
    const text = rawText.trim();
    const ws = socketRef.current;
    const sid = sessionIdRef.current;
    if (!text || !ws || ws.readyState !== WebSocket.OPEN || !sid) return;
    // Defensa en profundidad: aunque `stopListeningRef` ya apaga el
    // micrófono al llegar a un estado terminal, un turno en vuelo (o el
    // cuadro de texto) no debe provocar un `server.error` innecesario.
    if (TERMINAL_STATES.has(fsmStateRef.current)) return;
    clientSeqRef.current += 1;
    setTurns((prev) => [...prev, makeTurn(sid, "patient", text)]);
    setVoiceState("thinking");
    ws.send(
      JSON.stringify({
        v: 1,
        type: "client.turn_text",
        seq: clientSeqRef.current,
        payload: { text },
      }),
    );
  }, []);

  function sendTurn() {
    sendText(draft);
    setDraft("");
  }

  // Voice pipeline (VOI-*): browser-native STT/TTS with barge-in, behind a
  // provider-agnostic hook. A recognized patient utterance is sent as a WS
  // text turn — identical contract to typing.
  const voice = useVoiceSession({
    onFinalTurn: (text) => sendText(text),
    onBargeIn: () => setVoiceState("interrupted"),
    lang: "es-CO",
  });
  useEffect(() => {
    stopListeningRef.current = voice.stopListening;
  }, [voice.stopListening]);
  useEffect(() => {
    startListeningRef.current = voice.start;
  }, [voice.start]);
  useEffect(() => {
    speakRef.current = voice.speak;
  }, [voice.speak]);

  async function endCall() {
    voice.stop();
    voiceModeRef.current = false;
    const ws = socketRef.current;
    ws?.close();
    setPhase("closed");
    setVoiceState("ready");
    if (sessionId) {
      try {
        await api.finishSession(sessionId);
      } catch {
        // finish is best-effort here; the summary view lives in /audit.
      }
    }
  }

  // Cerrar el modal cuelga la llamada si estaba activa: salir dejando un
  // WebSocket vivo de fondo sería un estado invisible para el usuario.
  const modalRef = useRef<HTMLDivElement | null>(null);

  async function closeCallModal() {
    if (phase === "active" || phase === "connecting") {
      await endCall();
    }
    onClose();
  }

  // Escape cierra, y el scroll del fondo se bloquea mientras está abierto
  // (si no, la rueda del ratón mueve lo de atrás y el modal parece pegado
  // a una página que se desliza sola).
  useEffect(() => {
    modalRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") void closeCallModal();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleMic() {
    if (voice.listening) {
      voice.stop();
      voiceModeRef.current = false;
    } else {
      voiceModeRef.current = true;
      voice.start();
    }
  }

  const isActive = phase === "active" || phase === "connecting";
  const isTerminal = TERMINAL_STATES.has(fsmState);

  // Voice status takes precedence over FSM-derived state for the orb display.
  const displayVoiceState: VoiceState = voice.speaking
    ? "assistant_speaking"
    : voice.partial
      ? "patient_speaking"
      : voice.listening
        ? "listening"
        : voiceState;

  return (
    <div
      className="call-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        // Sólo cierra si el clic empezó en el backdrop, no si vino de
        // arrastrar una selección de texto desde dentro del panel.
        if (event.target === event.currentTarget) closeCallModal();
      }}
    >
      <div
        className="call-modal-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`Llamada de seguimiento con ${patientAlias}`}
        ref={modalRef}
      >
        <button
          type="button"
          className="call-modal-close"
          onClick={closeCallModal}
          aria-label="Cerrar la llamada"
        >
          ×
        </button>

        <section className="context-strip card" aria-label="Contexto del caso">
          <div className="context-item">
            <span className="context-icon" aria-hidden="true">
              P
            </span>
            <span>
              <small>Paciente</small>
              <strong>{patientCase.patientAlias}</strong>
            </span>
          </div>
          <span className="context-divider" aria-hidden="true" />
          <div className="context-item">
            <span className="context-icon" aria-hidden="true">
              +
            </span>
            <span>
              <small>Procedimiento</small>
              <strong>{patientCase.procedure}</strong>
            </span>
          </div>
          <span className="context-divider" aria-hidden="true" />
          <div className="context-item">
            <span className="context-icon" aria-hidden="true">
              ◷
            </span>
            <span>
              <small>Cirugía</small>
              <strong>{formatSurgeryDate(patientCase.surgeryDate)}</strong>
            </span>
          </div>

          {!isActive && phase !== "closed" ? (
            <button type="button" className="context-start-btn" onClick={startCall}>
              Iniciar llamada
            </button>
          ) : (
            <div className="call-status" aria-live="polite">
              <span className="dot" aria-hidden="true" />
              {phase === "connecting" && "Conectando…"}
              {phase === "active" && `En llamada · ${STATE_LABELS[fsmState]}`}
              {phase === "closed" && "Llamada finalizada"}
            </div>
          )}
        </section>

        {callError ? <StatusBanner message={callError} onRetry={() => setCallError(null)} /> : null}

        <div className="call-grid" style={{ marginTop: 20 }}>
          <section className="voice-card card card-pad" aria-labelledby="voice-heading">
            <div className="voice-card-head">
              <div>
                <p className="eyebrow">Conversación de seguimiento</p>
                <h1 id="voice-heading">Una llamada que escucha antes de orientar</h1>
              </div>
              <span className="live-pill">
                <span className="dot" aria-hidden="true" />
                {phase === "active" ? STATE_LABELS[fsmState] : "Sin conexión de audio"}
              </span>
            </div>

            <div className="voice-card-body">
              <div className="voice-transcript">
                <h2 className="voice-transcript-title">Transcripción</h2>
                <TranscriptPanel turns={turns} patientAlias={patientAlias} />
              </div>

              <div className="call-voice-panel">
                <VoiceOrb
                  state={displayVoiceState}
                  micEnabled={voice.listening}
                  micDisabled={phase !== "active" || !voice.supported || isTerminal}
                  onToggleMic={toggleMic}
                />

                {voice.partial ? (
                  <p
                    className="voice-partial"
                    aria-live="polite"
                    style={{ fontStyle: "italic", opacity: 0.8 }}
                  >
                    «{voice.partial}»
                  </p>
                ) : null}

                <div className="call-controls" role="group" aria-label="Controles de llamada">
                  {phase === "idle" || phase === "closed" ? (
                    <button type="button" className="voice-preview-btn" onClick={startCall}>
                      Iniciar llamada
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="voice-preview-btn"
                        onClick={toggleMic}
                        disabled={phase !== "active" || !voice.supported || isTerminal}
                        aria-pressed={voice.listening}
                      >
                        {voice.listening ? "Detener voz" : "Hablar por voz"}
                      </button>
                      <button type="button" className="voice-preview-btn" onClick={endCall}>
                        Finalizar llamada
                      </button>
                    </>
                  )}
                </div>

                {phase === "active" && !voice.supported ? (
                  <p className="voice-note" style={{ fontSize: 12, opacity: 0.75, marginTop: 8 }}>
                    Este navegador no soporta reconocimiento de voz; continúa por texto abajo.
                  </p>
                ) : null}

                {phase === "active" && !voice.supported ? (
                  <form
                    className="turn-composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      sendTurn();
                    }}
                    style={{ display: "flex", gap: 8, marginTop: 16 }}
                  >
                    <label htmlFor="turn-input" className="sr-only">
                      Respuesta del paciente (texto)
                    </label>
                    <input
                      id="turn-input"
                      type="text"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder="Escribe tu respuesta…"
                      autoComplete="off"
                      style={{ flex: 1, padding: "10px 12px", borderRadius: 10 }}
                    />
                    <button type="submit" className="voice-preview-btn" disabled={!draft.trim()}>
                      Enviar respuesta
                    </button>
                  </form>
                ) : null}
              </div>
            </div>
          </section>

          <aside className="clinical-rail" aria-label="Supervisión clínica">
            {/* La evolución vive en el rail, no encima de la conversación
                (hallazgo H-03): sigue visible para que el jurado compruebe la
                memoria longitudinal, pero ya no empuja la llamada fuera del
                viewport. Colapsable, cerrada durante la llamada activa.
                Los casos de prueba no tienen historial, así que esta
                sección simplemente no aparece — no hace falta una rama
                especial para "sin evolución". */}
            {patientCase.historicalFollowups.length > 0 ? (
              <details className="card card-pad history-details" open={!isActive}>
                <summary>
                  <span>
                    <small className="eyebrow">Evolución conocida</small>
                    <strong>Últimos {patientCase.historicalFollowups.length} seguimientos</strong>
                  </span>
                </summary>
                <p className="history-baseline">Línea base disponible para el agente</p>
                <div className="history-timeline">
                  {patientCase.historicalFollowups.map((followup) => (
                    <article className="history-node" key={followup.day}>
                      <span className="history-day">Día {followup.day}</span>
                      <strong>Dolor {followup.painNrs}/10</strong>
                      <span>{followup.temperatureC.toFixed(1)} °C</span>
                      <small>Herida: {formatClinicalValue(followup.wound)}</small>
                      <small>Apetito: {formatClinicalValue(followup.appetite)}</small>
                    </article>
                  ))}
                </div>
              </details>
            ) : null}

            <section className="card card-pad" aria-labelledby="evidence-heading">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Evidencia</p>
                  <h2 id="evidence-heading">Fuentes citadas en esta llamada</h2>
                </div>
              </div>
              <EvidencePanel citations={citations} />
            </section>

            <RiskPanel riskLevel={riskLevel} handoffCreated={escalated} />

            {decisionLevel ? (
              <p className="decision-code" translate="no" style={{ fontSize: 12, opacity: 0.75 }}>
                Nivel de decisión del motor: <strong>{decisionLevel}</strong>
                {escalated ? " · escalado" : ""}
              </p>
            ) : null}
          </aside>
        </div>
      </div>
    </div>
  );
}
