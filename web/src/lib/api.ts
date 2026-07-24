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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
    const detail = await response.text().catch(() => "");
    throw new ApiError(
      detail || `El backend respondió ${response.status} en ${path}.`,
      response.status,
      path,
    );
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

/** architecture.md §7 — state machine driving a call. */
export type SessionStatus =
  | "initializing"
  | "consent"
  | "interview"
  | "retrieve"
  | "assess"
  | "respond"
  | "escalate"
  | "summarize"
  | "closed";

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

/** architecture.md §9.3 — learn → retrieve → forget lifecycle. */
export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "ready"
  | "deleting"
  | "deleted";

export interface KnowledgeDocument {
  id: string;
  title: string;
  version: string;
  status: DocumentStatus;
  applicableTo: string | null;
  chunkCount: number;
  lastCanaryAt: string | null;
}

export interface KnowledgeInventory {
  knowledgeVersion: number;
  documents: KnowledgeDocument[];
  updatedAt: string | null;
}

export interface CanaryResult {
  query: string;
  resultCount: number;
  executedAt: string;
}

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

export interface SessionTrace {
  sessionId: string;
  timeline: TimelineEvent[];
  agentEvents: AgentEvent[];
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
  startedAt: string;
  durationSeconds: number;
  riskLevel: RiskLevel;
  citationCount: number;
  latencyP95Ms: number | null;
  tokens: number | null;
  costUsd: number | null;
  escalated: boolean;
}

/* -------------------------------------------------------------------- */
/* Endpoints — docs/architecture.md §12.1                               */
/* -------------------------------------------------------------------- */

export const api = {
  healthLive: () => request<{ status: string }>("/health/live"),
  healthReady: () => request<{ status: string }>("/health/ready"),

  listCases: () => request<CaseSummary[]>("/api/cases"),

  createSession: (caseId: string) =>
    request<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    }),

  finishSession: (sessionId: string) =>
    request<CallSummary>(`/api/sessions/${sessionId}/finish`, {
      method: "POST",
    }),

  getSession: (sessionId: string) => request<Session>(`/api/sessions/${sessionId}`),

  getSessionTrace: (sessionId: string) =>
    request<SessionTrace>(`/api/sessions/${sessionId}/trace`),

  listAuditSessions: (filters?: AuditFilters) => {
    const params = new URLSearchParams();
    if (filters) {
      for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined) params.set(key, String(value));
      }
    }
    const query = params.toString();
    return request<AuditSessionRow[]>(`/api/sessions${query ? `?${query}` : ""}`);
  },

  getKnowledgeInventory: () => request<KnowledgeInventory>("/api/knowledge"),

  uploadKnowledgeDocument: (file: File, applicableTo?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    if (applicableTo) formData.append("applicable_to", applicableTo);
    return request<KnowledgeDocument>("/api/knowledge/documents", {
      method: "POST",
      body: formData,
    });
  },

  deleteKnowledgeDocument: (documentId: string) =>
    request<{ knowledgeVersion: number; canary: CanaryResult }>(
      `/api/knowledge/documents/${documentId}`,
      { method: "DELETE" },
    ),

  searchKnowledge: (query: string) =>
    request<CitationRef[]>("/api/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  getMetrics: () => request<MetricsSnapshot>("/api/metrics"),
};
