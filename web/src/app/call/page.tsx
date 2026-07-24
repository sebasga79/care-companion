"use client";

import { useEffect, useState } from "react";
import { VOICE_STATES, VoiceOrb } from "@/components/VoiceOrb";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { RiskPanel } from "@/components/RiskPanel";
import { StatusBanner } from "@/components/StatusBanner";
import { api, ApiError, type CaseSummary, type VoiceState } from "@/lib/api";

const VOICE_STATE_LABELS: Record<VoiceState, string> = {
  ready: "Listo",
  listening: "Escuchando",
  patient_speaking: "Paciente habla",
  thinking: "Pensando",
  assistant_speaking: "Asistente responde",
  interrupted: "Interrumpido",
  reconnecting: "Reconectando",
  failed: "Error de audio",
};

export default function CallPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [casesError, setCasesError] = useState<string | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");

  const [voiceState, setVoiceState] = useState<VoiceState>("ready");
  const [alerted, setAlerted] = useState(false);

  async function fetchCases() {
    try {
      const result = await api.listCases();
      setCases(result);
      setCasesError(null);
    } catch (error) {
      setCasesError(error instanceof ApiError ? error.message : "Error desconocido.");
    } finally {
      setLoadingCases(false);
    }
  }

  function retryCases() {
    setLoadingCases(true);
    setCasesError(null);
    fetchCases();
  }

  useEffect(() => {
    // Standard mount-time fetch (no live backend to subscribe to yet — this
    // loads the case list once). Initial `loading`/`error` state already
    // covers the pending/clean case; `retryCases` above resets them for
    // user-triggered retries from a click handler, not from an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCases();
  }, []);

  const selectedCase = cases.find((item) => item.id === selectedCaseId) ?? null;
  const patientAlias = selectedCase?.patientAlias ?? "Paciente";

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

        <div className="call-status">
          <span className="dot" aria-hidden="true" />
          Sin llamada activa · vista previa de interfaz
        </div>
      </section>

      {casesError ? <StatusBanner message={casesError} onRetry={retryCases} /> : null}

      <div className="call-grid" style={{ marginTop: 20 }}>
        <section className="voice-card card card-pad" aria-labelledby="voice-heading">
          <div className="voice-card-head">
            <div>
              <p className="eyebrow">Conversación de seguimiento</p>
              <h1 id="voice-heading">Una llamada que escucha antes de orientar</h1>
            </div>
            <span className="live-pill">
              <span className="dot" aria-hidden="true" />
              Vista previa · sin conexión de audio
            </span>
          </div>

          <VoiceOrb
            state={voiceState}
            micEnabled={voiceState === "listening"}
            onToggleMic={() => setVoiceState((current) => (current === "listening" ? "ready" : "listening"))}
          />

          <div className="voice-preview" role="group" aria-label="Vista previa de estados de voz">
            <span className="voice-preview-label">
              Vista previa de estados de voz (sin conexión — design.md §5.3)
            </span>
            {VOICE_STATES.map((state) => (
              <button
                key={state}
                type="button"
                className="voice-preview-btn"
                aria-pressed={voiceState === state}
                onClick={() => setVoiceState(state)}
              >
                {VOICE_STATE_LABELS[state]}
              </button>
            ))}
          </div>

          <h2 style={{ marginTop: 24, marginBottom: 12, fontSize: 15 }}>Transcripción</h2>
          <TranscriptPanel turns={[]} patientAlias={patientAlias} />
        </section>

        <aside className="clinical-rail" aria-label="Supervisión clínica">
          <section className="card card-pad" aria-labelledby="evidence-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Evidencia</p>
                <h2 id="evidence-heading">Fuentes citadas en esta llamada</h2>
              </div>
            </div>
            <EvidencePanel citations={[]} />
          </section>

          <RiskPanel
            riskLevel={null}
            alerted={alerted}
            onEscalate={() => setAlerted(true)}
            onReset={() => setAlerted(false)}
          />

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
