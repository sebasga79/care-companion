"use client";

import { useEffect, useState } from "react";
import { api, type MetricValue } from "@/lib/api";

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
  // El detalle trae las cifras que la rúbrica §5 exige reportar (tokens de
  // entrada/salida, invocaciones al modelo por turno, consultas RAG por
  // llamada) — no se pueden omitir. Lo que sí se corrige (hallazgo H-07 del
  // video) es la presentación: en vez de una sola cadena densa separada por
  // "·", que parecía salida de depuración, cada cifra va en su propia línea
  // con el estado como etiqueta y no como prefijo del texto.
  const detailParts = metric.detail
    .split("·")
    .map((part) => part.trim())
    .filter(Boolean);

  return (
    <article className="metric-card">
      <p className="metric-card__label">
        {label}
        <span className={`metric-card__status metric-card__status--${metric.status}`}>
          {STATUS_LABEL[metric.status]}
        </span>
      </p>
      <strong className="metric-card__value">{metric.value}</strong>
      <ul className="metric-card__detail-list">
        {detailParts.map((part) => (
          <li key={part}>{part}</li>
        ))}
      </ul>
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
    label: "Latencia voz-a-voz",
    metric: {
      status: "objetivo",
      value: "< 2.5 s",
      detail: "Fin de habla del paciente → inicio de audio del agente",
    },
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
  // Live metrics from GET /api/v1/metrics; falls back to the spec's honest
  // "objetivo/pendiente" placeholders if the backend is unreachable (never
  // fabricated numbers).
  const [metrics, setMetrics] = useState(DEFAULT_METRICS);

  useEffect(() => {
    let cancelled = false;
    api
      .getMetrics()
      .then((snapshot) => {
        if (cancelled) return;
        setMetrics([
          { label: "Latencia P50", metric: snapshot.latencyP50 },
          { label: "Latencia P95", metric: snapshot.latencyP95 },
          { label: "Latencia voz-a-voz", metric: snapshot.latencyVoice },
          { label: "Tokens", metric: snapshot.tokens },
          { label: "Costo", metric: snapshot.cost },
        ]);
      })
      .catch(() => {
        // Keep honest placeholders on failure.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="metrics-band" aria-label="Métricas del concurso">
      {metrics.map((item) => (
        <Metric key={item.label} label={item.label} metric={item.metric} />
      ))}
    </section>
  );
}
