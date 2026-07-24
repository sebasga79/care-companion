"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBanner } from "@/components/StatusBanner";
import { MetricsBand } from "@/components/MetricsBand";
import {
  api,
  ApiError,
  type AuditFilters,
  type AuditSessionRow,
  type RiskLevel,
} from "@/lib/api";

const RISK_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: "routine", label: "Rutinario" },
  { value: "needs_clarification", label: "Falta confirmar" },
  { value: "human_review", label: "Revisión humana" },
  { value: "urgent_human_review", label: "Atención prioritaria" },
  { value: "failed_safe", label: "Seguridad" },
];

export default function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const [rows, setRows] = useState<AuditSessionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchSessions(nextFilters: AuditFilters) {
    try {
      const result = await api.listAuditSessions(nextFilters);
      setRows(result);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Error desconocido.");
    } finally {
      setLoading(false);
    }
  }

  // Filter submissions and retries go through `runSearch`, which resets the
  // loading/error flags first, from an event handler rather than an effect.
  function runSearch(nextFilters: AuditFilters) {
    setLoading(true);
    setError(null);
    fetchSessions(nextFilters);
  }

  useEffect(() => {
    // Standard mount-time fetch of the unfiltered session list.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSessions({});
  }, []);

  return (
    <section aria-labelledby="audit-heading">
      <div className="view-hero card">
        <div>
          <p className="eyebrow">Auditoría del caso</p>
          <h1 id="audit-heading">Cada decisión importante conserva señal, fuente y responsable</h1>
          <p>
            Esta vista muestra evidencia verificable y resultados estructurados de
            agentes. No expone razonamiento interno ni reemplaza la revisión
            clínica.
          </p>
        </div>
        <div className="hero-actions">
          <span className="chip chip-simulation">Sesiones reales del backend · sin datos precargados</span>
        </div>
      </div>

      <MetricsBand />

      <section className="card card-pad" aria-labelledby="filters-heading" style={{ marginBottom: 24 }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Filtros</p>
            <h2 id="filters-heading">Sesiones auditadas</h2>
          </div>
        </div>

        <form
          className="filters-bar"
          onSubmit={(event) => {
            event.preventDefault();
            runSearch(filters);
          }}
        >
          <div className="filter-field">
            <label htmlFor="filter-date-from">Desde</label>
            <input
              id="filter-date-from"
              type="date"
              value={filters.dateFrom ?? ""}
              onChange={(event) => setFilters((f) => ({ ...f, dateFrom: event.target.value || undefined }))}
            />
          </div>
          <div className="filter-field">
            <label htmlFor="filter-date-to">Hasta</label>
            <input
              id="filter-date-to"
              type="date"
              value={filters.dateTo ?? ""}
              onChange={(event) => setFilters((f) => ({ ...f, dateTo: event.target.value || undefined }))}
            />
          </div>
          <div className="filter-field">
            <label htmlFor="filter-result">Resultado</label>
            <select
              id="filter-result"
              value={filters.result ?? ""}
              onChange={(event) =>
                setFilters((f) => ({ ...f, result: (event.target.value || undefined) as RiskLevel | undefined }))
              }
            >
              <option value="">Todos</option>
              {RISK_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-field">
            <label htmlFor="filter-escalated">Escalamiento</label>
            <select
              id="filter-escalated"
              value={filters.escalated === undefined ? "" : String(filters.escalated)}
              onChange={(event) =>
                setFilters((f) => ({
                  ...f,
                  escalated: event.target.value === "" ? undefined : event.target.value === "true",
                }))
              }
            >
              <option value="">Todos</option>
              <option value="true">Con escalamiento</option>
              <option value="false">Sin escalamiento</option>
            </select>
          </div>
          <div className="filter-field">
            <label htmlFor="filter-procedure">Procedimiento</label>
            <input
              id="filter-procedure"
              type="text"
              value={filters.procedure ?? ""}
              onChange={(event) => setFilters((f) => ({ ...f, procedure: event.target.value || undefined }))}
            />
          </div>
          <div className="filter-field" style={{ justifyContent: "flex-end" }}>
            <label className="sr-only" htmlFor="apply-filters">
              Aplicar filtros
            </label>
            <button id="apply-filters" type="submit" className="btn btn-primary" style={{ minHeight: 44 }}>
              Aplicar filtros
            </button>
          </div>
        </form>

        {error ? <StatusBanner message={error} onRetry={() => runSearch(filters)} /> : null}

        {loading ? (
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>Consultando el backend…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            icon="◷"
            title="Sin sesiones auditadas aún"
            detail="Cuando exista al menos una llamada completada, cada fila mostrará duración, nivel de riesgo, fuentes, latencia P95, tokens y costo."
          />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="document-table">
              <thead>
                <tr>
                  <th scope="col">Inicio</th>
                  <th scope="col">Duración</th>
                  <th scope="col">Nivel</th>
                  <th scope="col">Fuentes</th>
                  <th scope="col">Latencia P95</th>
                  <th scope="col">Tokens</th>
                  <th scope="col">Costo</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.sessionId}>
                    <td>{new Date(row.startedAt).toLocaleString("es")}</td>
                    <td>{Math.round(row.durationSeconds / 60)} min</td>
                    <td>{row.riskLevel}</td>
                    <td>{row.citationCount}</td>
                    <td>{row.latencyP95Ms ? `${row.latencyP95Ms} ms` : "—"}</td>
                    <td>{row.tokens ?? "—"}</td>
                    <td>{row.costUsd ? `$${row.costUsd.toFixed(3)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="two-col">
        <section className="card card-pad" aria-labelledby="timeline-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Secuencia verificable</p>
              <h2 id="timeline-heading">Línea de tiempo del handoff</h2>
            </div>
          </div>
          <EmptyState
            icon="→"
            title="Sin línea de tiempo todavía"
            detail="Selecciona una sesión auditada para ver la secuencia correlacionada: turno capturado → señal detectada → evidencia recuperada → decisión → handoff."
          />
        </section>

        <section className="card card-pad" aria-labelledby="agents-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Responsabilidad única</p>
              <h2 id="agents-heading">Resultados de agentes</h2>
            </div>
          </div>
          <EmptyState
            icon="⚙"
            title="Sin resultados de agentes todavía"
            detail="Orquestador, Safety Agent, Retrieval Agent y Conversation Agent mostrarán su salida estructurada aquí — nunca su razonamiento interno."
          />
          <div className="audit-note">
            <span aria-hidden="true">i</span>
            <p style={{ margin: 0 }}>
              Se guardan entradas, salidas estructuradas, decisiones y referencias.
              Nunca cadenas privadas de razonamiento.
            </p>
          </div>
        </section>
      </div>
    </section>
  );
}
