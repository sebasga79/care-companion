import type { RiskLevel } from "@/lib/api";

const RISK_LABELS: Record<RiskLevel, { icon: string; label: string }> = {
  routine: { icon: "✓", label: "Seguimiento rutinario" },
  needs_clarification: { icon: "?", label: "Falta confirmar" },
  human_review: { icon: "◐", label: "Revisión humana" },
  urgent_human_review: { icon: "!", label: "Atención prioritaria" },
  failed_safe: { icon: "⛨", label: "Revisión requerida por seguridad" },
};

type RiskPanelProps = {
  riskLevel: RiskLevel | null;
  alerted: boolean;
  onEscalate: () => void;
  onReset: () => void;
};

/**
 * Risk/supervision panel + the escalation CTA. The button is always
 * enabled (design.md §5.2 requires it be demonstrable end-to-end even
 * before real sessions exist), but the copy never claims a risk level
 * that hasn't actually been computed by a Triage Agent — when
 * `riskLevel` is null this renders an honest "sin evaluación" state
 * instead of a fabricated one.
 */
export function RiskPanel({ riskLevel, alerted, onEscalate, onReset }: RiskPanelProps) {
  return (
    <section className="card card-pad" aria-labelledby="risk-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Acompañamiento</p>
          <h2 id="risk-heading">Supervisión en tiempo real</h2>
        </div>
        <span className="chip chip-caution">Revisión disponible</span>
      </div>

      {riskLevel ? (
        <div className="risk-summary" data-level={riskLevel}>
          <span className="risk-summary-icon" aria-hidden="true">
            {RISK_LABELS[riskLevel].icon}
          </span>
          <div>
            <strong>{RISK_LABELS[riskLevel].label}</strong>
            <small>Evaluado por el Triage Agent con reglas deterministas + evidencia.</small>
          </div>
        </div>
      ) : (
        <div className="risk-summary">
          <span className="risk-summary-icon" aria-hidden="true">
            –
          </span>
          <div>
            <strong>Sin evaluación de riesgo todavía</strong>
            <small>Aparecerá cuando exista una llamada activa conectada al backend.</small>
          </div>
        </div>
      )}

      <div className="escalation-card" data-alerted={alerted}>
        <p style={{ margin: "0 0 6px", fontSize: 13, fontWeight: 800, color: alerted ? "var(--lime-deep)" : "var(--coral-deep)" }}>
          {alerted ? "Handoff simulado registrado" : "Revisión humana"}
        </p>
        <p>
          {alerted
            ? "El equipo recibiría este contexto en un despliegue real. Esta es una demostración auditable del flujo de escalamiento."
            : "Usa este control para simular el flujo de escalamiento a un miembro del equipo, incluso sin una llamada activa."}
        </p>

        <button type="button" className="btn btn-escalate" onClick={onEscalate} disabled={alerted}>
          <span aria-hidden="true">{alerted ? "✓" : "+"}</span>
          {alerted ? "Alerta registrada (simulada)" : "Simular alerta al equipo"}
        </button>

        <p className="escalation-note">
          {alerted
            ? "No se ejecutó ninguna acción hospitalaria real: ninguna llamada, mensaje ni escritura en un EHR."
            : "Al confirmar, no se ejecuta ninguna acción hospitalaria real."}
        </p>

        {alerted ? (
          <button
            type="button"
            className="btn btn-secondary"
            style={{ width: "100%", marginTop: 8, minHeight: 36 }}
            onClick={onReset}
          >
            Reiniciar vista previa
          </button>
        ) : null}
      </div>
    </section>
  );
}
