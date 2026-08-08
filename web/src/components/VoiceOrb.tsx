"use client";

import type { CSSProperties } from "react";
import type { VoiceState } from "@/lib/api";

const WAVEFORM_HEIGHTS = [
  10, 18, 28, 44, 62, 34, 20, 50, 70, 40, 24, 16, 36, 58, 76, 46, 24, 34, 66,
  52, 28, 18, 40, 62, 78, 54, 30, 20,
];

const STATE_CONTENT: Record<
  VoiceState,
  { icon: string; label: string; copy: string }
> = {
  ready: {
    icon: "○",
    label: "Listo para iniciar",
    copy: "Selecciona un paciente para comenzar la llamada de seguimiento.",
  },
  listening: {
    icon: "●",
    label: "Escuchando",
    copy: "Puedes interrumpir al asistente en cualquier momento.",
  },
  patient_speaking: {
    icon: "●",
    label: "El paciente está hablando",
    copy: "Transcribiendo en tiempo real.",
  },
  thinking: {
    icon: "···",
    label: "Revisando lo que nos contaste",
    copy: "Verificando evidencia clínica antes de responder.",
  },
  assistant_speaking: {
    icon: "▶",
    label: "Care Companion está respondiendo",
    copy: "La respuesta se apoya en evidencia citada.",
  },
  interrupted: {
    icon: "‖",
    label: "Te escucho",
    copy: "Se canceló la respuesta anterior para atenderte primero.",
  },
  reconnecting: {
    icon: "↻",
    label: "Reconectando el audio…",
    copy: "La conversación sigue disponible por texto mientras tanto.",
  },
  failed: {
    icon: "!",
    label: "No pudimos recuperar el audio",
    copy: "Puedes continuar la conversación por texto.",
  },
};

export const VOICE_STATES: VoiceState[] = [
  "ready",
  "listening",
  "patient_speaking",
  "thinking",
  "assistant_speaking",
  "interrupted",
  "reconnecting",
  "failed",
];

type VoiceOrbProps = {
  state: VoiceState;
  micEnabled: boolean;
  onToggleMic?: () => void;
  micDisabled?: boolean;
};

/**
 * Static (not wired to real audio yet) presentation of every voice state
 * from design.md §5.3. Icon + text + color together carry each state, so
 * the UI never depends on color alone (design.md §12).
 */
export function VoiceOrb({ state, micEnabled, onToggleMic, micDisabled = false }: VoiceOrbProps) {
  const content = STATE_CONTENT[state];

  return (
    <div className="voice-stage" data-state={state} aria-live="polite">
      <div className="waveform" aria-hidden="true">
        {WAVEFORM_HEIGHTS.map((height, index) => (
          <span
            key={index}
            style={
              {
                "--bar-height": `${height}px`,
                "--bar-delay": `${index * -36}ms`,
              } as CSSProperties
            }
          />
        ))}
      </div>

      <button
        type="button"
        className="mic-button"
        aria-pressed={micEnabled}
        aria-label={micEnabled ? "Pausar escucha del micrófono" : "Reanudar escucha del micrófono"}
        onClick={onToggleMic}
        disabled={micDisabled}
      >
        <span className="mic-symbol" aria-hidden="true" />
      </button>

      <strong className="voice-status-text">
        <span aria-hidden="true">{content.icon} </span>
        {content.label}
      </strong>
      <p className="voice-status-copy">{content.copy}</p>
    </div>
  );
}
