/**
 * Typed client for the real, committed `/api/v1/knowledge/*` contract
 * (RAG-010, `api/app/api/routes/knowledge.py` + `api/app/api/schemas.py`).
 *
 * This module intentionally does not touch `lib/api.ts` beyond reusing its
 * `request()`/`ApiError` — the knowledge domain has its own wire shape
 * (snake_case JSON matching the FastAPI Pydantic models) that is mapped
 * explicitly to camelCase app types below, rather than assumed. Nothing
 * here is fabricated: every field mirrors a field the backend actually
 * returns.
 */

import { ApiError, request } from "./api";

export { ApiError };

/* -------------------------------------------------------------------- */
/* Wire types — mirror api/app/api/schemas.py exactly (snake_case)      */
/* -------------------------------------------------------------------- */

interface DocumentResponseWire {
  id: string;
  filename: string;
  checksum: string;
  status: string;
  mime: string;
  size_bytes: number;
  applicability: Record<string, unknown>;
  protected: boolean;
  knowledge_version_added: number;
  knowledge_version_deleted: number | null;
  error_reason: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  deleted_by: string | null;
}

interface DocumentListResponseWire {
  documents: DocumentResponseWire[];
  knowledge_version: number;
}

interface DocumentUploadResponseWire {
  document: DocumentResponseWire;
  knowledge_version: number;
  chunk_count: number;
}

interface DocumentDeleteResponseWire {
  document: DocumentResponseWire;
  knowledge_version: number;
  purged_chunk_count: number;
}

interface CanaryStatusWire {
  query: string;
  found: boolean;
  checked_at: string;
}

interface DocumentDetailResponseWire {
  document: DocumentResponseWire;
  canary: CanaryStatusWire | null;
}

interface SearchResultItemWire {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_version: number;
  section: string | null;
  page: number | null;
  text: string;
  lexical_rank: number | null;
  lexical_score: number | null;
  semantic_rank: number | null;
  semantic_score: number | null;
  rrf_score: number;
}

interface SearchResponseWire {
  query: string;
  knowledge_version: number;
  results: SearchResultItemWire[];
}

/* -------------------------------------------------------------------- */
/* App types — camelCase, used by the /knowledge page and components    */
/* -------------------------------------------------------------------- */

/**
 * `processing` is transient: `KnowledgeIngestionService.learn()` runs the
 * whole pipeline (validate → chunk → embed → index → canary) inside one
 * transaction, so a document is committed as `ready` (or not committed at
 * all, on rejection/canary failure) by the time the upload response comes
 * back. `failed` covers documents a future async path could mark rejected.
 */
export type KnowledgeDocumentStatus = "processing" | "ready" | "deleted" | "failed";

export interface KnowledgeDocument {
  id: string;
  filename: string;
  checksum: string;
  status: KnowledgeDocumentStatus;
  mime: string;
  sizeBytes: number;
  applicability: Record<string, unknown>;
  protected: boolean;
  knowledgeVersionAdded: number;
  knowledgeVersionDeleted: number | null;
  errorReason: string | null;
  createdAt: string;
  updatedAt: string;
  deletedAt: string | null;
  deletedBy: string | null;
}

export interface KnowledgeDocumentList {
  documents: KnowledgeDocument[];
  knowledgeVersion: number;
}

export interface KnowledgeDocumentUpload {
  document: KnowledgeDocument;
  knowledgeVersion: number;
  chunkCount: number;
}

export interface KnowledgeDocumentDelete {
  document: KnowledgeDocument;
  knowledgeVersion: number;
  purgedChunkCount: number;
}

export interface KnowledgeCanaryStatus {
  query: string;
  found: boolean;
  checkedAt: string;
}

export interface KnowledgeDocumentDetail {
  document: KnowledgeDocument;
  /** Only computed server-side when the document's status is `ready`. */
  canary: KnowledgeCanaryStatus | null;
}

export interface KnowledgeSearchResult {
  chunkId: string;
  documentId: string;
  documentTitle: string;
  documentVersion: number;
  section: string | null;
  page: number | null;
  text: string;
  lexicalRank: number | null;
  lexicalScore: number | null;
  semanticRank: number | null;
  semanticScore: number | null;
  rrfScore: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  knowledgeVersion: number;
  results: KnowledgeSearchResult[];
}

/* -------------------------------------------------------------------- */
/* Wire → app mapping                                                   */
/* -------------------------------------------------------------------- */

function toDocument(wire: DocumentResponseWire): KnowledgeDocument {
  return {
    id: wire.id,
    filename: wire.filename,
    checksum: wire.checksum,
    status: wire.status as KnowledgeDocumentStatus,
    mime: wire.mime,
    sizeBytes: wire.size_bytes,
    applicability: wire.applicability ?? {},
    protected: wire.protected,
    knowledgeVersionAdded: wire.knowledge_version_added,
    knowledgeVersionDeleted: wire.knowledge_version_deleted,
    errorReason: wire.error_reason,
    createdAt: wire.created_at,
    updatedAt: wire.updated_at,
    deletedAt: wire.deleted_at,
    deletedBy: wire.deleted_by,
  };
}

function toCanary(wire: CanaryStatusWire | null): KnowledgeCanaryStatus | null {
  if (!wire) return null;
  return { query: wire.query, found: wire.found, checkedAt: wire.checked_at };
}

function toSearchResult(wire: SearchResultItemWire): KnowledgeSearchResult {
  return {
    chunkId: wire.chunk_id,
    documentId: wire.document_id,
    documentTitle: wire.document_title,
    documentVersion: wire.document_version,
    section: wire.section,
    page: wire.page,
    text: wire.text,
    lexicalRank: wire.lexical_rank,
    lexicalScore: wire.lexical_score,
    semanticRank: wire.semantic_rank,
    semanticScore: wire.semantic_score,
    rrfScore: wire.rrf_score,
  };
}

/* -------------------------------------------------------------------- */
/* Endpoints — api/app/api/routes/knowledge.py, mounted under /api/v1   */
/* -------------------------------------------------------------------- */

export interface KnowledgeSearchOptions {
  topK?: number;
  procedure?: string;
  phase?: string;
}

export const knowledgeApi = {
  listDocuments: async (): Promise<KnowledgeDocumentList> => {
    const wire = await request<DocumentListResponseWire>("/api/v1/knowledge/documents");
    return {
      documents: wire.documents.map(toDocument),
      knowledgeVersion: wire.knowledge_version,
    };
  },

  uploadDocument: async (
    file: File,
    applicability?: Record<string, string>,
  ): Promise<KnowledgeDocumentUpload> => {
    const formData = new FormData();
    formData.append("file", file);
    const entries = applicability
      ? Object.entries(applicability).filter(([, value]) => value.trim().length > 0)
      : [];
    if (entries.length > 0) {
      formData.append("applicability", JSON.stringify(Object.fromEntries(entries)));
    }
    const wire = await request<DocumentUploadResponseWire>("/api/v1/knowledge/documents", {
      method: "POST",
      body: formData,
    });
    return {
      document: toDocument(wire.document),
      knowledgeVersion: wire.knowledge_version,
      chunkCount: wire.chunk_count,
    };
  },

  getDocument: async (documentId: string): Promise<KnowledgeDocumentDetail> => {
    const wire = await request<DocumentDetailResponseWire>(
      `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}`,
    );
    return { document: toDocument(wire.document), canary: toCanary(wire.canary) };
  },

  deleteDocument: async (documentId: string): Promise<KnowledgeDocumentDelete> => {
    const wire = await request<DocumentDeleteResponseWire>(
      `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}`,
      { method: "DELETE" },
    );
    return {
      document: toDocument(wire.document),
      knowledgeVersion: wire.knowledge_version,
      purgedChunkCount: wire.purged_chunk_count,
    };
  },

  search: async (query: string, options?: KnowledgeSearchOptions): Promise<KnowledgeSearchResponse> => {
    const params = new URLSearchParams({ q: query });
    if (options?.topK) params.set("top_k", String(options.topK));
    if (options?.procedure) params.set("procedure", options.procedure);
    if (options?.phase) params.set("phase", options.phase);
    const wire = await request<SearchResponseWire>(`/api/v1/knowledge/search?${params.toString()}`);
    return {
      query: wire.query,
      knowledgeVersion: wire.knowledge_version,
      results: wire.results.map(toSearchResult),
    };
  },
};
