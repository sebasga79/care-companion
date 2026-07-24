"use client";

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

export default function CallPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [casesError, setCasesError] = useState<string | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");

  const [phase, setPhase] = useState<CallPhase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [fsmState, setFsmState] = useState<SessionStatus>("created");
  const [voiceState, setVoiceState] = useState<VoiceState>("ready");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [citations, setCitations] = useState<CitationRef[]>([]);
  const [riskLevel, setRiskLevel] = useState<RiskLevel | null>(null);
  const [decisionLevel, setDecisionLevel] = useState<DecisionLevel | null>(null);
  const [escalated, setEscalated] = useState(false);
  const [alerted, setAlerted] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const socketRef = useRef<WebSocket | null>(null);
  const clientSeqRef = useRef(0);
  // Refs so the WebSocket onmessage closure (captured once at connect time)
  // always reaches the latest voice behavior without being recreated.
  const voiceModeRef = useRef(false);
  const speakRef = useRef<(text: string) => void>(() => {});
  const sessionIdRef = useRef<string | null>(null);

  const fetchCases = useCallback(async () => {
    try {
      const result = await api.listCases();
      setCases(result);
      setCasesError(null);
    } catch (error) {
      setCasesError(error instanceof ApiError ? error.message : "Error desconocido.");
    } finally {
      setLoadingCases(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCases();
    return () => socketRef.current?.close();
  }, [fetchCases]);

  const selectedCase = cases.find((item) => item.id === selectedCaseId) ?? null;
  const patientAlias = selectedCase?.patientAlias ?? "Paciente";

  function handleServerEnvelope(env: ServerEnvelope, sid: string) {
    switch (env.type) {
      case "server.state":
        setFsmState(env.payload.state);
        setVoiceState(stateToVoice(env.payload.state));
        if (env.payload.state === "escalated") setEscalated(true);
        break;
      case "server.agent_response":
        if (env.payload.message) {
          setTurns((prev) => [...prev, makeTurn(sid, "assistant", env.payload.message)]);
          // Speak the reply only when the operator is running the call by voice.
          if (voiceModeRef.current) speakRef.current(env.payload.message);
        }
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
        break;
      case "server.error":
        setCallError(env.payload.reason);
        break;
    }
  }

  async function startCall() {
    if (!selectedCaseId) return;
    setPhase("connecting");
    setCallError(null);
    setTurns([]);
    setCitations([]);
    setRiskLevel(null);
    setDecisionLevel(null);
    setEscalated(false);
    setAlerted(false);
    clientSeqRef.current = 0;

    let session;
    try {
      session = await api.createSession(selectedCaseId);
    } catch (error) {
      setCallError(error instanceof ApiError ? error.message : "No se pudo crear la sesión.");
      setPhase("idle");
      return;
    }

    setSessionId(session.id);
    sessionIdRef.current = session.id;
    setFsmState(session.status);

    const ws = new WebSocket(callSocketUrl(session.id));
    socketRef.current = ws;

    ws.onopen = () => setPhase("active");
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

  // Voice status takes precedence over FSM-derived state for the orb display.
  const displayVoiceState: VoiceState = voice.speaking
    ? "assistant_speaking"
    : voice.partial
      ? "patient_speaking"
      : voice.listening
        ? "listening"
        : voiceState;

  return (
    <>
      <section className="context-strip card" aria-label="Contexto del caso">
        <div className="context-item">
          <span className="context-icon" aria-hidden="true">
            ✓
          </span>
          <span>
            <small>Tipo de llamada</small>
            <strong>Seguimiento posoperatorio</strong>
          </span>
        </div>
        <span className="context-divider" aria-hidden="true" />
        <div className="context-item">
          <label htmlFor="case-select" className="sr-only">
            Caso ficticio
          </label>
          <span className="context-icon" aria-hidden="true">
            C
          </span>
          <span>
            <small>Caso ficticio</small>
            {loadingCases ? (
              <strong>Cargando…</strong>
            ) : cases.length === 0 ? (
              <strong>Sin casos disponibles</strong>
            ) : (
              <select
                id="case-select"
                value={selectedCaseId}
                onChange={(event) => setSelectedCaseId(event.target.value)}
                disabled={isActive}
                style={{ border: 0, background: "transparent", fontWeight: 700, fontSize: 13 }}
              >
                <option value="">Selecciona un caso</option>
                {cases.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            )}
          </span>
        </div>
        <span className="context-divider" aria-hidden="true" />
        <div className="context-item">
          <span className="context-icon" aria-hidden="true">
            +
          </span>
          <span>
            <small>Procedimiento</small>
            <strong>{selectedCase?.procedure ?? "—"}</strong>
          </span>
        </div>

        <div className="call-status" aria-live="polite">
          <span className="dot" aria-hidden="true" />
          {phase === "idle" && "Sin llamada activa"}
          {phase === "connecting" && "Conectando…"}
          {phase === "active" && `En llamada · ${STATE_LABELS[fsmState]}`}
          {phase === "closed" && "Llamada finalizada"}
        </div>
      </section>

      {casesError ? <StatusBanner message={casesError} onRetry={fetchCases} /> : null}
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

          <VoiceOrb
            state={displayVoiceState}
            micEnabled={voice.listening}
            micDisabled={phase !== "active" || !voice.supported}
            onToggleMic={toggleMic}
          />

          {voice.partial ? (
            <p className="voice-partial" aria-live="polite" style={{ fontStyle: "italic", opacity: 0.8 }}>
              «{voice.partial}»
            </p>
          ) : null}

          <div className="call-controls" role="group" aria-label="Controles de llamada">
            {phase === "idle" || phase === "closed" ? (
              <button
                type="button"
                className="voice-preview-btn"
                onClick={startCall}
                disabled={!selectedCaseId}
              >
                Iniciar llamada
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="voice-preview-btn"
                  onClick={toggleMic}
                  disabled={phase !== "active" || !voice.supported}
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

          {phase === "active" ? (
            <form
              className="turn-composer"
              onSubmit={(e) => {
                e.preventDefault();
                sendTurn();
              }}
              style={{ display: "flex", gap: 8, marginTop: 16 }}
            >
              <label htmlFor="turn-input" className="sr-only">
                Turno del paciente (texto)
              </label>
              <input
                id="turn-input"
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Escribe lo que dice el paciente…"
                autoComplete="off"
                style={{ flex: 1, padding: "10px 12px", borderRadius: 10 }}
              />
              <button type="submit" className="voice-preview-btn" disabled={!draft.trim()}>
                Enviar turno
              </button>
            </form>
          ) : null}

          <h2 style={{ marginTop: 24, marginBottom: 12, fontSize: 15 }}>Transcripción</h2>
          <TranscriptPanel turns={turns} patientAlias={patientAlias} />
        </section>

        <aside className="clinical-rail" aria-label="Supervisión clínica">
          <section className="card card-pad" aria-labelledby="evidence-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Evidencia</p>
                <h2 id="evidence-heading">Fuentes citadas en esta llamada</h2>
              </div>
            </div>
            <EvidencePanel citations={citations} />
          </section>

          <RiskPanel
            riskLevel={riskLevel}
            alerted={alerted || escalated}
            onEscalate={() => setAlerted(true)}
            onReset={() => setAlerted(false)}
          />

          {decisionLevel ? (
            <p className="decision-code" translate="no" style={{ fontSize: 12, opacity: 0.75 }}>
              Nivel de decisión del motor: <strong>{decisionLevel}</strong>
              {escalated ? " · escalado" : ""}
            </p>
          ) : null}

          <div className="editorial-note">
            <strong>Referencia institucional</strong>
            Care Companion se inspira en el cuidado pediátrico familiar. No es un
            producto oficial de ningún hospital; no reproduce su logotipo ni
            fotografía institucional en este repositorio.
          </div>
        </aside>
      </div>
    </>
  );
}
