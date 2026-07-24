import type { MetricValue } from "@/lib/api";

type MetricProps = {
  label: string;
  metric: MetricValue;
};

const STATUS_LABEL: Record<MetricValue["status"], string> = {
  objetivo: "Objetivo",
  medido: "Medido",
  pendiente: "Pendiente",
};

export function Metric({ label, metric }: MetricProps) {
  return (
    <article className="metric-card">
      <p className="metric-card__label">{label}</p>
      <strong className="metric-card__value">{metric.value}</strong>
      <small className="metric-card__detail">
        {STATUS_LABEL[metric.status]} · {metric.detail}
      </small>
    </article>
  );
}

/**
 * Reuses the exact placeholder copy from
 * docs/care-companion-family-first-handoff.md §6 — these labels are the
 * spec's own intentional "objetivo/pendiente" markers, not fabricated
 * numbers, until docs/architecture.md §12 GET /api/metrics is wired.
 */
const DEFAULT_METRICS: { label: string; metric: MetricValue }[] = [
  {
    label: "Latencia P50",
    metric: { status: "objetivo", value: "< 1.2 s", detail: "Medir desde el 7 de agosto" },
  },
  {
    label: "Latencia P95",
    metric: { status: "objetivo", value: "< 2.5 s", detail: "Extremo a extremo" },
  },
  {
    label: "Tokens",
    metric: { status: "pendiente", value: "Por turno", detail: "Trazados, pendientes de medición" },
  },
  {
    label: "Costo",
    metric: { status: "pendiente", value: "Por llamada", detail: "Estimado, pendiente del LLM obligatorio" },
  },
];

export function MetricsBand() {
  return (
    <section className="metrics-band" aria-label="Métricas del concurso">
      {DEFAULT_METRICS.map((item) => (
        <Metric key={item.label} label={item.label} metric={item.metric} />
      ))}
    </section>
  );
}
