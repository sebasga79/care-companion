/**
 * Typed client for the Care Companion control API.
 *
 * Endpoints mirror docs/architecture.md §12 ("API propuesta"). The backend
 * (apps under api/) is being built in parallel by another executor and may
 * not be reachable yet — every call here fails loudly with a typed
 * `ApiError` instead of throwing a raw fetch/parse exception, so pages can
 * render honest "sin conexión" states instead of crashing or, worse,
 * silently falling back to fabricated data.
 *
 * No domain-specific SDK is used — plain `fetch` against
 * `NEXT_PUBLIC_API_URL`, consistent with ADR-001's "puertos/adaptadores
 * estrictos" rule (the frontend itself is the boundary here; it does not
 * import any provider SDK).
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number | null;
  readonly path: string;

  constructor(message: string, status: number | null, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

/**
 * Shared fetch wrapper — exported so other client modules (e.g.
 * `lib/knowledge.ts`) get the same honest-failure behavior instead of
 * duplicating fetch/error-parsing logic.
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      `No se pudo contactar ${API_BASE_URL}${path}. Verifica que el backend esté corriendo.`,
      null,
      path,
    );
  }

  if (!response.ok) {
    const raw = await response.text().catch(() => "");
    let message = raw || `El backend respondió ${response.status} en ${path}.`;
    // FastAPI error bodies are `{"detail": "..."}` or, for structured
    // rejections (e.g. upload validation), `{"detail": {"code", "message"}}`.
    // Unwrap either shape into one honest, human-readable message instead of
    // surfacing raw JSON text to the operator.
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as { detail?: unknown };
        if (typeof parsed.detail === "string") {
          message = parsed.detail;
        } else if (parsed.detail && typeof parsed.detail === "object") {
          const detail = parsed.detail as { code?: string; message?: string };
          message = detail.message ?? JSON.stringify(parsed.detail);
        }
      } catch {
        // Not JSON — keep the raw text as the message.
      }
    }
    throw new ApiError(message, response.status, path);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/* -------------------------------------------------------------------- */
/* Domain types — mirror docs/architecture.md §6.2, §8.2, §11.1, §12    */
/* -------------------------------------------------------------------- */

/** design.md §5.4 — "Color nunca será el único indicador" (icon+text pair each). */
export type RiskLevel =
  | "routine"
  | "needs_clarification"
  | "human_review"
  | "urgent_human_review"
  | "failed_safe";

/**
 * Backend decision precedence (api/app/domain/decision.py). This is the REAL
 * enum the WebSocket sends; the UI maps it to `RiskLevel` for display via
 * `decisionToRisk` below. Never invent a friendlier level than the backend
 * reported — a downgrade here would defeat the whole non-degradable-decision
 * guarantee.
 */
export type DecisionLevel =
  | "HARD_RED_FLAG"
  | "DATA_INTEGRITY_FAILURE"
  | "EVIDENCE_INSUFFICIENT_WITH_RISK"
  | "MODEL_HIGH_RISK"
  | "MODEL_MODERATE_RISK"
  | "ROUTINE_FOLLOW_UP";

/** UI mapping only — display, never a clinical re-classification. */
export function decisionToRisk(level: DecisionLevel): RiskLevel {
  switch (level) {
    case "HARD_RED_FLAG":
      return "urgent_human_review";
    case "DATA_INTEGRITY_FAILURE":
      return "failed_safe";
    case "EVIDENCE_INSUFFICIENT_WITH_RISK":
    case "MODEL_HIGH_RISK":
      return "human_review";
    case "MODEL_MODERATE_RISK":
      return "needs_clarification";
    case "ROUTINE_FOLLOW_UP":
      return "routine";
  }
}

/** architecture.md §7 / api/app/domain/session_fsm.py — real FSM state values. */
export type SessionStatus =
  | "created"
  | "consent"
  | "interviewing"
  | "retrieving"
  | "deciding"
  | "responding"
  | "summarizing"
  | "closed"
  | "fail_safe"
  | "escalated";

/** design.md §5.3 — voice states table. */
export type VoiceState =
  | "ready"
  | "listening"
  | "patient_speaking"
  | "thinking"
  | "assistant_speaking"
  | "interrupted"
  | "reconnecting"
  | "failed";

export interface CaseSummary {
  id: string;
  label: string;
  procedure: string;
  patientAlias: string;
  phase: string;
  daysSinceProcedure: number;
}

export interface ChallengeCase extends CaseSummary {
  openingPrompt: string;
}

export interface Session {
  id: string;
  caseId: string;
  status: SessionStatus;
  knowledgeVersion: number;
  startedAt: string;
  endedAt: string | null;
}

/* Raw backend shapes (snake_case) — mapped to the clean types above. */
interface RawCase {
  case_id: string;
  patient_display_name: string;
  procedure: string;
  phase: string;
  days_since_procedure: number;
}

interface RawSession {
  id: string;
  case_id: string;
  state: SessionStatus;
  knowledge_version: number;
  created_at: string;
  closed_at: string | null;
}

function mapCase(raw: RawCase): CaseSummary {
  return {
    id: raw.case_id,
    label: `${raw.patient_display_name} · ${raw.phase}`,
    procedure: raw.procedure,
    patientAlias: raw.patient_display_name,
    phase: raw.phase,
    daysSinceProcedure: raw.days_since_procedure,
  };
}

function mapSession(raw: RawSession): Session {
  return {
    id: raw.id,
    caseId: raw.case_id,
    status: raw.state,
    knowledgeVersion: raw.knowledge_version,
    startedAt: raw.created_at,
    endedAt: raw.closed_at,
  };
}

export interface Turn {
  id: string;
  sessionId: string;
  speaker: "patient" | "assistant";
  text: string;
  isFinal: boolean;
  startedAt: string;
}

export interface Observation {
  id: string;
  turnId: string;
  code: string;
  label: string;
  certainty: number | null;
}

export interface CitationRef {
  chunkId: string;
  documentId: string;
  documentTitle: string;
  version: string;
  section: string | null;
  page: number | null;
  snippet: string;
}

/** architecture.md §8.2 — exact triage output shape. */
export interface TriageDecision {
  level: RiskLevel;
  shouldEscalate: boolean;
  triggerCodes: string[];
  observationsUsed: string[];
  evidenceIds: string[];
  missingInformation: string[];
  rationaleForAudit: string;
  patientMessageIntent: string;
}

export interface Escalation {
  id: string;
  sessionId: string;
  status: "pending" | "created" | "acknowledged";
  createdAt: string;
  rationale: string;
  triggerCodes: string[];
}

export interface CallSummary {
  sessionId: string;
  knowledgeVersion: number;
  startedAt: string;
  endedAt: string | null;
  riskLevel: RiskLevel | null;
  escalation: Escalation | null;
  observations: Observation[];
  citations: CitationRef[];
}

// Note: the learn → retrieve → forget document lifecycle lives in
// `lib/knowledge.ts`, typed directly from the real, committed
// `/api/v1/knowledge/*` contract (api/app/api/schemas.py) rather than here.

export interface UsageMetrics {
  latencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  costUsd: number | null;
  provider: string | null;
}

/** architecture.md §6.1 — single-responsibility agents. */
export type AgentName =
  | "orchestrator"
  | "interview"
  | "retrieval"
  | "triage"
  | "response"
  | "summary"
  | "safety";

export interface AgentEvent {
  id: string;
  sessionId: string;
  agent: AgentName;
  status: "ok" | "abstain" | "error";
  outputSummary: string;
  evidenceIds: string[];
  usage: UsageMetrics | null;
  correlationId: string;
  startedAt: string;
  endedAt: string | null;
}

export interface TimelineEvent {
  id: string;
  time: string;
  title: string;
  detail: string;
  tone: "info" | "risk" | "evidence" | "resolution";
}

/** Never fabricate a number: every metric ships its own honesty status. */
export type MetricStatus = "objetivo" | "medido" | "pendiente";

export interface MetricValue {
  status: MetricStatus;
  value: string;
  detail: string;
}

export interface MetricsSnapshot {
  latencyP50: MetricValue;
  latencyP95: MetricValue;
  tokens: MetricValue;
  cost: MetricValue;
}

export interface TraceEvent {
  correlationId: string;
  component: string;
  eventType: string;
  latencyMs: number | null;
  createdAt: string;
}

export interface TraceDecision {
  level: DecisionLevel;
  shouldEscalate: boolean;
  triggerCodes: string;
  rationale: string;
  createdAt: string;
}

export interface TraceEscalation {
  decisionLevel: DecisionLevel;
  reasons: string;
  triggerCodes: string;
  createdAt: string;
}

export interface SessionTrace {
  sessionId: string;
  state: SessionStatus;
  knowledgeVersion: number;
  events: TraceEvent[];
  decisions: TraceDecision[];
  escalations: TraceEscalation[];
}

export interface AuditFilters {
  dateFrom?: string;
  dateTo?: string;
  result?: RiskLevel;
  escalated?: boolean;
  procedure?: string;
  knowledgeVersion?: number;
  sessionStatus?: SessionStatus;
}

export interface AuditSessionRow {
  sessionId: string;
  caseId: string;
  state: SessionStatus;
  startedAt: string;
  closedAt: string | null;
  durationSeconds: number | null;
  decisionLevel: DecisionLevel | null;
  riskLevel: RiskLevel | null;
  citationCount: number;
  escalated: boolean;
}

/* -------------------------------------------------------------------- */
/* WebSocket envelope contract — api/app/api/routes/ws.py                */
/* -------------------------------------------------------------------- */

export const ENVELOPE_VERSION = 1;

export interface ClientTurnText {
  v: 1;
  type: "client.turn_text";
  seq: number;
  payload: { text: string };
}

/** Citation as the WS serializes it (api/app/domain/models.py CitationRef). */
export interface WsCitation {
  citation_id: string;
  document_id: string;
  document_version: number;
  chunk_id: string;
  title: string;
  section: string | null;
  page: number | null;
  knowledge_version: number;
}

export type ServerEnvelope =
  | { v: 1; type: "server.state"; seq: number; payload: { state: SessionStatus }; correlation_id: string }
  | {
      v: 1;
      type: "server.agent_response";
      seq: number;
      payload: {
        message: string;
        intent: string | null;
        needs_clarification: boolean;
        citations: WsCitation[];
      };
      correlation_id: string;
    }
  | {
      v: 1;
      type: "server.decision";
      seq: number;
      payload: { level: DecisionLevel; should_escalate: boolean; escalated: boolean };
      correlation_id: string;
    }
  | { v: 1; type: "server.summary"; seq: number; payload: Record<string, unknown>; correlation_id: string }
  | { v: 1; type: "server.error"; seq: number; payload: { reason: string }; correlation_id: string };

/** Map a WS citation to the UI `CitationRef` shape used by EvidencePanel. */
export function mapWsCitation(c: WsCitation): CitationRef {
  return {
    chunkId: c.chunk_id,
    documentId: c.document_id,
    documentTitle: c.title,
    version: String(c.document_version),
    section: c.section,
    page: c.page,
    snippet: "",
  };
}

/** Build the ws:// URL for a session channel from the HTTP base. */
export function callSocketUrl(sessionId: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/ws/sessions/${sessionId}`;
}

/* -------------------------------------------------------------------- */
/* Endpoints — real backend (api/app/main.py registers under /api/v1)   */
/* -------------------------------------------------------------------- */

export const api = {
  health: () => request<{ status: string; version: string; db: string }>("/health"),

  listCases: async (): Promise<CaseSummary[]> => {
    const raw = await request<RawCase[]>("/api/v1/cases");
    return raw.map(mapCase);
  },

  createSession: async (caseId: string): Promise<Session> => {
    const raw = await request<RawSession>("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    });
    return mapSession(raw);
  },

  getSession: async (sessionId: string): Promise<Session> => {
    const raw = await request<RawSession>(`/api/v1/sessions/${sessionId}`);
    return mapSession(raw);
  },

  // Backend returns the SUM-002 CallSummary shape (snake_case); the /audit
  // page consumes it directly. Kept loosely typed until the audit read
  // endpoints (trace/metrics) exist server-side.
  finishSession: (sessionId: string) =>
    request<Record<string, unknown>>(`/api/v1/sessions/${sessionId}/finish`, {
      method: "POST",
    }),

  listAuditSessions: async (): Promise<AuditSessionRow[]> => {
    const body = await request<{ sessions: RawAuditRow[] }>("/api/v1/audit/sessions");
    return body.sessions.map(mapAuditRow);
  },

  getMetrics: async (): Promise<MetricsSnapshot> => {
    const raw = await request<{
      latency_p50: MetricValue;
      latency_p95: MetricValue;
      tokens: MetricValue;
      cost: MetricValue;
    }>("/api/v1/metrics");
    return {
      latencyP50: raw.latency_p50,
      latencyP95: raw.latency_p95,
      tokens: raw.tokens,
      cost: raw.cost,
    };
  },

  getTrace: async (sessionId: string): Promise<SessionTrace> => {
    const raw = await request<RawTrace>(`/api/v1/audit/sessions/${sessionId}/trace`);
    return {
      sessionId: raw.session_id,
      state: raw.state,
      knowledgeVersion: raw.knowledge_version,
      events: raw.events.map((e) => ({
        correlationId: e.correlation_id,
        component: e.component,
        eventType: e.event_type,
        latencyMs: e.latency_ms,
        createdAt: e.created_at,
      })),
      decisions: raw.decisions.map((d) => ({
        level: d.level,
        shouldEscalate: d.should_escalate === 1 || d.should_escalate === true,
        triggerCodes: d.trigger_codes,
        rationale: d.rationale,
        createdAt: d.created_at,
      })),
      escalations: raw.escalations.map((e) => ({
        decisionLevel: e.decision_level,
        reasons: e.reasons,
        triggerCodes: e.trigger_codes,
        createdAt: e.created_at,
      })),
    };
  },
};

interface RawTrace {
  session_id: string;
  state: SessionStatus;
  knowledge_version: number;
  events: {
    correlation_id: string;
    component: string;
    event_type: string;
    latency_ms: number | null;
    created_at: string;
  }[];
  decisions: {
    level: DecisionLevel;
    should_escalate: number | boolean;
    trigger_codes: string;
    rationale: string;
    created_at: string;
  }[];
  escalations: {
    decision_level: DecisionLevel;
    reasons: string;
    trigger_codes: string;
    created_at: string;
  }[];
}

interface RawAuditRow {
  session_id: string;
  case_id: string;
  state: SessionStatus;
  started_at: string;
  closed_at: string | null;
  duration_seconds: number | null;
  decision_level: DecisionLevel | null;
  citation_count: number;
  escalated: boolean;
}

function mapAuditRow(raw: RawAuditRow): AuditSessionRow {
  return {
    sessionId: raw.session_id,
    caseId: raw.case_id,
    state: raw.state,
    startedAt: raw.started_at,
    closedAt: raw.closed_at,
    durationSeconds: raw.duration_seconds,
    decisionLevel: raw.decision_level,
    riskLevel: raw.decision_level ? decisionToRisk(raw.decision_level) : null,
    citationCount: raw.citation_count,
    escalated: raw.escalated,
  };
}
