import type { Turn } from "@/lib/api";
import { EmptyState } from "./EmptyState";

type TranscriptPanelProps = {
  turns: Turn[];
  patientAlias: string;
};

export function TranscriptPanel({ turns, patientAlias }: TranscriptPanelProps) {
  if (turns.length === 0) {
    return (
      <EmptyState
        icon="…"
        title="Aún no hay transcripción"
        detail="Los turnos de la conversación aparecerán aquí en cuanto la llamada esté conectada al servidor. Ningún dato de paciente se precarga."
      />
    );
  }

  return (
    <div className="transcript" aria-label="Transcripción en vivo">
      {turns.map((turn) => (
        <article
          key={turn.id}
          className={turn.speaker === "assistant" ? "message assistant-message" : "message patient-message"}
        >
          <span
            className={turn.speaker === "assistant" ? "speaker-icon assistant-icon" : "speaker-icon patient-icon"}
            aria-hidden="true"
          >
            {turn.speaker === "assistant" ? "CC" : patientAlias.charAt(0)}
          </span>
          <div>
            <p className="speaker-label">
              {turn.speaker === "assistant" ? "Asistente" : patientAlias} ·{" "}
              {new Date(turn.startedAt).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}
              {!turn.isFinal ? " · parcial" : ""}
            </p>
            <p>{turn.text}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
