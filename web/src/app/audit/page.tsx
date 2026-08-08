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
  type SessionTrace,
} from "@/lib/api";

const RISK_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: "routine", label: "Rutinario" },
  { value: "needs_clarification", label: "Falta confirmar" },
  { value: "human_review", label: "Revisión humana" },
  { value: "urgent_human_review", label: "Atención prioritaria" },
  { value: "failed_safe", label: "Seguridad" },
];

const DECISION_LABEL: Record<string, string> = {
  HARD_RED_FLAG: "Atención prioritaria",
  DATA_INTEGRITY_FAILURE: "Revisión por seguridad",
  EVIDENCE_INSUFFICIENT_WITH_RISK: "Riesgo por confirmar",
  MODEL_HIGH_RISK: "Riesgo alto",
  MODEL_MODERATE_RISK: "Riesgo moderado",
  ROUTINE_FOLLOW_UP: "Seguimiento rutinario",
};

const SESSION_LABEL: Record<string, string> = {
  created: "Creada",
  interviewing: "En llamada",
  closed: "Finalizada",
  escalated: "Escalada",
  fail_safe: "Detenida por seguridad",
};

const EVENT_LABEL: Record<string, string> = {
  "session.agent_opened": "Llamada iniciada por el agente",
  "turn.received": "Turno recibido",
  "agent.interview.completed": "Información clínica interpretada",
  "rag.retrieval.completed": "Evidencia clínica recuperada",
  "agent.triage.completed": "Riesgo evaluado",
  "agent.response.completed": "Respuesta preparada",
  "turn.response_sent": "Respuesta enviada",
  "handoff.created": "Reporte enviado a revisión humana",
  "escalation.created": "Alerta humana registrada",
  "handoff.contact_completed": "Teléfonos de contacto confirmados",
  "safety.signals_detected": "Señales de seguridad verificadas",
};

function displayClinicalValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Sin dato confirmado";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  return String(value).replaceAll("_", " ");
}

export default function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({});
  const [rows, setRows] = useState<AuditSessionRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [trace, setTrace] = useState<SessionTrace | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);

  async function selectSession(sessionId: string) {
    setSelectedId(sessionId);
    setTrace(null);
    setTraceError(null);
    try {
      setTrace(await api.getTrace(sessionId));
    } catch (err) {
      setTraceError(err instanceof ApiError ? err.message : "No se pudo cargar la traza.");
    }
  }

  async function fetchSessions(nextFilters: AuditFilters) {
    try {
      // The backend returns all sessions; filtering is applied client-side
      // here (server-side filter params are a later ticket). This keeps the
      // filter UI honest instead of silently ignoring it.
      const result = await api.listAuditSessions();
      const filtered = result.filter((row) => {
        if (nextFilters.result && row.riskLevel !== nextFilters.result) return false;
        if (nextFilters.escalated !== undefined && row.escalated !== nextFilters.escalated)
          return false;
        if (nextFilters.dateFrom && row.startedAt < nextFilters.dateFrom) return false;
        if (nextFilters.dateTo && row.startedAt > `${nextFilters.dateTo}T23:59:59`) return false;
        if (
          nextFilters.procedure &&
          !row.procedure?.toLocaleLowerCase("es").includes(nextFilters.procedure.toLocaleLowerCase("es"))
        )
          return false;
        return true;
      });
      setRows(filtered);
      setError(null);
      const preferred =
        filtered.find((row) => row.sessionId === selectedId) ??
        filtered.find((row) => row.state === "closed" || row.state === "escalated") ??
        filtered[0];
      if (preferred && preferred.sessionId !== selectedId) {
        await selectSession(preferred.sessionId);
      } else if (!preferred) {
        setSelectedId(null);
        setTrace(null);
      }
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

  // The fetch function intentionally owns the initial selection as well as
  // the list request; it is stable for this mount-only initialization.
  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    // Standard mount-time fetch of the unfiltered session list.
    fetchSessions({});
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

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
          <span className="chip chip-simulation">{rows.length} sesiones visibles · datos del backend</span>
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
                  <th scope="col">Paciente</th>
                  <th scope="col">Procedimiento</th>
                  <th scope="col">Inicio</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Resultado</th>
                  <th scope="col">Fuentes</th>
                  <th scope="col">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.sessionId}
                    onClick={() => selectSession(row.sessionId)}
                    aria-selected={selectedId === row.sessionId}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        selectSession(row.sessionId);
                      }
                    }}
                    style={{
                      cursor: "pointer",
                      background:
                        selectedId === row.sessionId
                          ? "color-mix(in srgb, var(--aqua-deep) 10%, transparent)"
                          : undefined,
                    }}
                  >
                    <td><strong>{row.patientDisplayName ?? "Paciente no identificado"}</strong></td>
                    <td>
                      {row.procedure ?? "—"}
                      {row.surgeryDate ? <small className="audit-cell-detail">Cirugía: {new Date(`${row.surgeryDate}T00:00:00`).toLocaleDateString("es")}</small> : null}
                    </td>
                    <td>{new Date(row.startedAt).toLocaleString("es")}</td>
                    <td>{SESSION_LABEL[row.state] ?? row.state}</td>
                    <td>
                      {row.decisionLevel ? DECISION_LABEL[row.decisionLevel] : "Sin decisión"}
                      {row.escalated ? <small className="audit-cell-detail risk">Reporte humano enviado</small> : null}
                    </td>
                    <td>{row.citationCount}</td>
                    {/* Botón explícito (hallazgo H-08 del video): la fila
                        completa sigue siendo clickeable, pero que lo sea no
                        era evidente para nadie que viera la tabla por
                        primera vez. */}
                    <td>
                      <button
                        type="button"
                        className="audit-detail-btn"
                        aria-current={selectedId === row.sessionId ? "true" : undefined}
                        onClick={(event) => {
                          event.stopPropagation();
                          selectSession(row.sessionId);
                        }}
                      >
                        {selectedId === row.sessionId ? "Viendo" : "Ver detalle"}
                      </button>
                    </td>
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
          {traceError ? <StatusBanner message={traceError} onRetry={() => selectSession(selectedId!)} /> : null}
          {!selectedId ? (
            <EmptyState
              icon="→"
              title="Sin línea de tiempo todavía"
              detail="Selecciona una sesión de la tabla para ver la secuencia correlacionada: eventos instrumentados, decisiones y handoff."
            />
          ) : !trace ? (
            <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>Cargando traza…</p>
          ) : trace.events.length === 0 ? (
            <EmptyState
              icon="→"
              title="Sesión sin eventos instrumentados"
              detail="Esta sesión no registró eventos con latencia todavía (p. ej. se creó pero no procesó turnos)."
            />
          ) : (
            <ol className="trace-timeline" style={{ margin: 0, paddingLeft: 18 }}>
              {trace.events.map((event, index) => (
                <li key={`${event.correlationId}-${index}`} style={{ marginBottom: 10 }}>
                  <strong>{EVENT_LABEL[event.eventType] ?? event.eventType}</strong>
                  <span style={{ opacity: 0.7 }}> · {event.component}</span>
                  {event.latencyMs != null ? (
                    <span style={{ opacity: 0.7 }}> · {event.latencyMs.toFixed(0)} ms</span>
                  ) : null}
                  <br />
                  <small style={{ opacity: 0.7 }}>
                    {new Date(event.createdAt).toLocaleTimeString("es")}
                  </small>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="card card-pad" aria-labelledby="agents-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Decisión y escalamiento</p>
              <h2 id="agents-heading">Resultados estructurados</h2>
            </div>
          </div>
          {!selectedId || !trace ? (
            <EmptyState
              icon="⚙"
              title="Sin decisiones cargadas"
              detail="Selecciona una sesión para ver su nivel de decisión, motivo y escalamientos — nunca su razonamiento interno."
            />
          ) : trace.decisions.length === 0 && trace.escalations.length === 0 ? (
            <EmptyState
              icon="⚙"
              title="Sesión sin decisiones registradas"
              detail="Aún no se produjo una decisión clínica en esta sesión."
            />
          ) : (
            <div>
              {trace.followupRecord ? (
                <div className="followup-audit-card">
                  <div className="followup-audit-heading">
                    <strong>Seguimiento clínico consolidado</strong>
                    <span className={`chip ${trace.followupRecord.medicalTeamAlert ? "chip-simulation" : "chip-neutral"}`}>
                      {trace.followupRecord.medicalTeamAlert ? "Alerta enviada" : "Sin alerta"}
                    </span>
                  </div>
                  <dl className="followup-audit-grid">
                    {[
                      ["Dolor", trace.followupRecord.painNrs, "/10"],
                      ["Temperatura", trace.followupRecord.temperatureC, " °C"],
                      ["Movilidad", trace.followupRecord.mobility, ""],
                      ["Herida", trace.followupRecord.wound, ""],
                      ["Alimentación", trace.followupRecord.appetite, ""],
                      ["Sueño", trace.followupRecord.sleep, ""],
                    ].map(([label, field, suffix]) => {
                      const clinicalField = field as typeof trace.followupRecord.painNrs;
                      return (
                        <div key={label as string}>
                          <dt>{label as string}</dt>
                          <dd>
                            {clinicalField
                              ? `${displayClinicalValue(clinicalField.value)}${suffix as string}`
                              : "No evaluado"}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                </div>
              ) : null}
              {trace.decisions.map((decision, index) => (
                <div key={index} className="trace-decision" style={{ marginBottom: 12 }}>
                  <strong>{DECISION_LABEL[decision.level] ?? decision.level}</strong>
                  {decision.shouldEscalate ? (
                    <span className="chip chip-simulation" style={{ marginLeft: 8 }}>
                      escala
                    </span>
                  ) : null}
                  <p style={{ margin: "4px 0 0", fontSize: 13, opacity: 0.85 }}>
                    {decision.rationale}
                  </p>
                </div>
              ))}
              {trace.escalations.length > 0 ? (
                <>
                  <p style={{ fontSize: 13 }}>
                    <strong>{trace.escalations.length}</strong> escalamiento(s) registrado(s).
                  </p>
                  {trace.contacts.length > 0 ? (
                    <div className="trace-decision" style={{ marginTop: 12 }}>
                      <strong>Datos para contacto inmediato</strong>
                      {trace.contacts.map((contact) => (
                        <p key={contact.code} style={{ margin: "6px 0 0", fontSize: 13 }}>
                          {contact.label}: <strong>{contact.value}</strong>
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p style={{ fontSize: 13 }}>Esperando confirmación de teléfonos.</p>
                  )}
                </>
              ) : null}
            </div>
          )}
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
