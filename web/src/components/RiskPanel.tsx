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
  handoffCreated: boolean;
};

/**
 * Panel de supervisión de solo lectura. El backend crea el handoff al
 * decidir riesgo; esta vista refleja ese resultado y nunca ofrece una
 * simulación manual que pueda divergir del registro auditable.
 */
export function RiskPanel({ riskLevel, handoffCreated }: RiskPanelProps) {
  return (
    <section className="card card-pad" aria-labelledby="risk-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Acompañamiento</p>
          <h2 id="risk-heading">Supervisión en tiempo real</h2>
        </div>
        <span className="chip chip-caution">Monitoreo automático</span>
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

      <div className="escalation-card" data-alerted={handoffCreated}>
        <p style={{ margin: "0 0 6px", fontSize: 13, fontWeight: 800, color: handoffCreated ? "var(--lime-deep)" : "var(--coral-deep)" }}>
          {handoffCreated ? "Handoff automático registrado" : "Handoff automático activo"}
        </p>
        <p>
          {handoffCreated
            ? "El reporte fue enviado al equipo de atención prioritaria. La confirmación de contacto continúa dentro de la llamada."
            : "No requiere acción manual: si se detecta un riesgo, el sistema detiene el cuestionario y crea el registro de revisión humana."}
        </p>
        <p className="escalation-note">
          El handoff conserva los hallazgos, la decisión y los teléfonos confirmados durante la conversación.
        </p>
      </div>
    </section>
  );
}
