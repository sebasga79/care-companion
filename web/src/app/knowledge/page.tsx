"use client";

import { Fragment, useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBanner } from "@/components/StatusBanner";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  knowledgeApi,
  ApiError,
  type KnowledgeDocument,
  type KnowledgeDocumentDetail,
  type KnowledgeSearchResponse,
} from "@/lib/knowledge";

const STATUS_META: Record<string, { icon: string; label: string }> = {
  processing: { icon: "⋯", label: "Procesando" },
  ready: { icon: "✓", label: "Listo" },
  deleted: { icon: "⊘", label: "Eliminado" },
  failed: { icon: "!", label: "Falló" },
};

const SEARCH_TOP_K = 8;
const CANARY_WORD_COUNT = 8;

function statusMeta(status: string) {
  return STATUS_META[status] ?? { icon: "?", label: status };
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function truncateChecksum(checksum: string): string {
  if (checksum.length <= 18) return checksum;
  return `${checksum.slice(0, 10)}…${checksum.slice(-6)}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es");
}

function applicabilityEntries(applicability: Record<string, unknown>): [string, string][] {
  return Object.entries(applicability)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "")
    .map(([key, value]) => [key, String(value)]);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Error desconocido.";
}

type DetailRowState = {
  loading: boolean;
  detail: KnowledgeDocumentDetail | null;
  error: string | null;
};

type PendingDelete = {
  doc: KnowledgeDocument;
  verifyQuery: string | null;
  loadingVerify: boolean;
};

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeVersion, setKnowledgeVersion] = useState<number | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [procedure, setProcedure] = useState("");
  const [phase, setPhase] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNote, setUploadNote] = useState<string | null>(null);

  const [openDetails, setOpenDetails] = useState<Record<string, DetailRowState>>({});
  const [knownQueries, setKnownQueries] = useState<Record<string, string>>({});

  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResult, setSearchResult] = useState<KnowledgeSearchResponse | null>(null);
  const [canaryNote, setCanaryNote] = useState<string | null>(null);

  const [liveMessage, setLiveMessage] = useState("");

  async function fetchInventory() {
    try {
      const result = await knowledgeApi.listDocuments();
      setDocuments(result.documents);
      setKnowledgeVersion(result.knowledgeVersion);
      setListError(null);
    } catch (error) {
      setListError(errorMessage(error));
    } finally {
      setListLoading(false);
    }
  }

  function reloadInventory() {
    setListLoading(true);
    setListError(null);
    fetchInventory();
  }

  useEffect(() => {
    // Standard mount-time fetch, mirroring /audit and /call.
    fetchInventory();
  }, []);

  async function runSearch(query: string) {
    const trimmed = query.trim();
    if (!trimmed) return;
    setSearching(true);
    setSearchError(null);
    try {
      const result = await knowledgeApi.search(trimmed, { topK: SEARCH_TOP_K });
      setSearchResult(result);
      setLiveMessage(
        result.results.length === 0
          ? `Verificación: 0 resultados para "${trimmed}".`
          : `Verificación: ${result.results.length} resultado(s) para "${trimmed}".`,
      );
    } catch (error) {
      setSearchError(errorMessage(error));
      setSearchResult(null);
    } finally {
      setSearching(false);
    }
  }

  function handleSearchSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    runSearch(searchQuery);
  }

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setUploadNote(null);
    try {
      const result = await knowledgeApi.uploadDocument(file, { procedure, phase });
      form.reset();
      setProcedure("");
      setPhase("");
      setUploadNote(
        `"${result.document.filename}" quedó ${statusMeta(result.document.status).label.toLowerCase()} ` +
          `con ${result.chunkCount} fragmento(s). Versión de conocimiento ahora v${result.knowledgeVersion}.`,
      );
      setLiveMessage(`Documento cargado: ${result.document.filename}, versión v${result.knowledgeVersion}.`);
      reloadInventory();

      // Positive canary, live: derive a real verification query from the
      // file's own opening words (same idea as the backend's own canary —
      // app/services/ingestion.py `_pick_canary_query`) and actually query
      // /knowledge/search with it, so the newly learned content is shown
      // appearing in retrieval, not just asserted.
      const text = await file.text().catch(() => "");
      const words = text.split(/\s+/).filter(Boolean).slice(0, CANARY_WORD_COUNT).join(" ");
      if (words) {
        setKnownQueries((prev) => ({ ...prev, [result.document.id]: words }));
        setSearchQuery(words);
        setCanaryNote(`Canaria positiva: verificando "${words}" contra el índice…`);
        await runSearch(words);
        setCanaryNote(`Canaria positiva ejecutada para "${words}" tras la carga.`);
      }
    } catch (error) {
      setUploadError(errorMessage(error));
    } finally {
      setUploading(false);
    }
  }

  async function toggleDetailRow(doc: KnowledgeDocument) {
    const wasOpen = Boolean(openDetails[doc.id]);
    setOpenDetails((prev) => {
      if (wasOpen) {
        const next = { ...prev };
        delete next[doc.id];
        return next;
      }
      return { ...prev, [doc.id]: { loading: true, detail: null, error: null } };
    });
    if (wasOpen) return;

    try {
      const detail = await knowledgeApi.getDocument(doc.id);
      setOpenDetails((prev) =>
        doc.id in prev ? { ...prev, [doc.id]: { loading: false, detail, error: null } } : prev,
      );
      if (detail.canary) {
        setKnownQueries((prev) => ({ ...prev, [doc.id]: detail.canary!.query }));
      }
    } catch (error) {
      setOpenDetails((prev) =>
        doc.id in prev
          ? { ...prev, [doc.id]: { loading: false, detail: null, error: errorMessage(error) } }
          : prev,
      );
    }
  }

  function openDeleteDialog(doc: KnowledgeDocument) {
    setDeleteError(null);
    setPendingDelete({ doc, verifyQuery: knownQueries[doc.id] ?? null, loadingVerify: true });
    knowledgeApi
      .getDocument(doc.id)
      .then((detail) => {
        setPendingDelete((prev) =>
          prev && prev.doc.id === doc.id
            ? { ...prev, verifyQuery: detail.canary?.query ?? prev.verifyQuery, loadingVerify: false }
            : prev,
        );
      })
      .catch(() => {
        setPendingDelete((prev) => (prev && prev.doc.id === doc.id ? { ...prev, loadingVerify: false } : prev));
      });
  }

  function closeDeleteDialog() {
    if (deleting) return;
    setPendingDelete(null);
    setDeleteError(null);
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      const result = await knowledgeApi.deleteDocument(pendingDelete.doc.id);
      const verifyQuery = pendingDelete.verifyQuery;
      setPendingDelete(null);
      reloadInventory();
      setOpenDetails((prev) => {
        const next = { ...prev };
        delete next[result.document.id];
        return next;
      });
      setLiveMessage(
        `"${result.document.filename}" eliminado. Versión de conocimiento ahora v${result.knowledgeVersion}. ` +
          `Fragmentos purgados: ${result.purgedChunkCount}.`,
      );
      if (verifyQuery) {
        setSearchQuery(verifyQuery);
        setCanaryNote(`Canaria negativa: verificando "${verifyQuery}" tras el borrado…`);
        await runSearch(verifyQuery);
        setCanaryNote(`Canaria negativa ejecutada para "${verifyQuery}" tras eliminar.`);
      } else {
        setCanaryNote(
          "El documento se eliminó. No había una consulta de verificación precomputada — " +
            "escribe una frase del documento eliminado en el panel de abajo para confirmar 0 resultados.",
        );
      }
    } catch (error) {
      setDeleteError(errorMessage(error));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section aria-labelledby="knowledge-heading">
      <p role="status" aria-live="polite" className="sr-only">
        {liveMessage}
      </p>

      <div className="view-hero card">
        <div>
          <p className="eyebrow">Conocimiento gobernado</p>
          <h1 id="knowledge-heading">Aprende una guía nueva y demuestra que puede olvidarla</h1>
          <p>
            Esta vista opera contra el backend real: cargar un documento (learn), verlo
            participar en una consulta de recuperación (retrieve), y confirmar que al
            eliminarlo una consulta canaria negativa devuelve 0 resultados (forget).
          </p>
        </div>
        <div className="hero-actions">
          <span className="chip chip-simulation">Datos reales del backend · sin datos precargados</span>
          <span className="chip chip-info">
            Versión de conocimiento: {knowledgeVersion !== null ? `v${knowledgeVersion}` : "…"}
          </span>
        </div>
      </div>

      {listError ? <StatusBanner message={listError} onRetry={reloadInventory} /> : null}

      <div className="two-col">
        <section className="card card-pad" aria-labelledby="version-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Versión activa</p>
              <h2 id="version-heading">
                {listLoading
                  ? "Consultando el backend…"
                  : knowledgeVersion !== null
                    ? `Versión de conocimiento v${knowledgeVersion}`
                    : "Sin conexión al backend"}
              </h2>
            </div>
            {knowledgeVersion !== null ? <span className="status-orbit">v{knowledgeVersion}</span> : null}
          </div>
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>
            {knowledgeVersion !== null
              ? `${documents.length} documento(s) en el inventario (incluye tombstones de eliminados).`
              : "El inventario de conocimiento (documentos, versión y prueba canaria) aparecerá aquí cuando el backend esté disponible."}
          </p>
        </section>

        <section className="card card-pad" aria-labelledby="upload-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Ingesta</p>
              <h2 id="upload-heading">Cargar guía clínica</h2>
            </div>
          </div>

          <form className="upload-zone" onSubmit={handleUpload}>
            <label htmlFor="knowledge-file">Documento (.txt o .md)</label>
            <input id="knowledge-file" name="file" type="file" accept=".txt,.md" required />

            <label htmlFor="applicability-procedure">Procedimiento (opcional)</label>
            <input
              id="applicability-procedure"
              type="text"
              placeholder="p. ej. apendicectomía"
              value={procedure}
              onChange={(event) => setProcedure(event.target.value)}
            />

            <label htmlFor="applicability-phase">Fase (opcional)</label>
            <input
              id="applicability-phase"
              type="text"
              placeholder="p. ej. posoperatorio"
              value={phase}
              onChange={(event) => setPhase(event.target.value)}
            />

            <span className="field-help">
              El backend valida extensión, tamaño, firma real de bytes y checksum duplicado
              antes de indexar — un rechazo no persiste ningún cambio.
            </span>

            <button type="submit" className="btn btn-primary" disabled={uploading}>
              {uploading ? "Cargando…" : "Cargar documento"}
            </button>

            {uploadError ? <StatusBanner message={uploadError} /> : null}
            {uploadNote ? (
              <p role="status" style={{ fontSize: 12, color: "var(--lime-deep)", fontWeight: 700 }}>
                {uploadNote}
              </p>
            ) : null}
          </form>
        </section>
      </div>

      <section className="card card-pad" aria-labelledby="documents-heading" style={{ marginBottom: 24 }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Inventario real</p>
            <h2 id="documents-heading">Documentos versionados</h2>
          </div>
          <span className="chip chip-neutral">{documents.length} documento(s)</span>
        </div>

        {listLoading ? (
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>Consultando el backend…</p>
        ) : documents.length === 0 ? (
          <EmptyState
            icon="≡"
            title="Sin documentos aún"
            detail="Los documentos cargados aparecerán aquí con su versión, aplicabilidad, estado, checksum y acciones de inspección/eliminación."
          />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="document-table">
              <thead>
                <tr>
                  <th scope="col">Archivo</th>
                  <th scope="col">Tamaño</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Aplicabilidad</th>
                  <th scope="col">v. agregada</th>
                  <th scope="col">v. eliminada</th>
                  <th scope="col">Checksum</th>
                  <th scope="col">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => {
                  const meta = statusMeta(doc.status);
                  const entries = applicabilityEntries(doc.applicability);
                  const detailState = openDetails[doc.id];
                  const isPendingThisDoc = pendingDelete?.doc.id === doc.id;
                  return (
                    <Fragment key={doc.id}>
                      <tr>
                        <td>{doc.filename}</td>
                        <td>{formatBytes(doc.sizeBytes)}</td>
                        <td>
                          <span className="document-status-badge" data-status={doc.status}>
                            <span aria-hidden="true">{meta.icon}</span> {meta.label}
                          </span>
                        </td>
                        <td>
                          {entries.length === 0 ? (
                            "—"
                          ) : (
                            <div className="applicability-chips">
                              {entries.map(([key, value]) => (
                                <span key={key} className="chip chip-neutral">
                                  {key}: {value}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td>v{doc.knowledgeVersionAdded}</td>
                        <td>{doc.knowledgeVersionDeleted !== null ? `v${doc.knowledgeVersionDeleted}` : "—"}</td>
                        <td>
                          <code className="checksum-code" title={doc.checksum}>
                            {truncateChecksum(doc.checksum)}
                          </code>
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ minHeight: 36, padding: "0 10px" }}
                              onClick={() => toggleDetailRow(doc)}
                              aria-expanded={Boolean(detailState)}
                            >
                              {detailState ? "Ocultar detalle" : "Ver detalle"}
                            </button>
                            {doc.status !== "deleted" ? (
                              <button
                                type="button"
                                className="btn btn-danger"
                                style={{ minHeight: 36, padding: "0 10px" }}
                                onClick={() => openDeleteDialog(doc)}
                                aria-label={`Eliminar ${doc.filename}`}
                                disabled={isPendingThisDoc}
                              >
                                Eliminar
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                      {detailState ? (
                        <tr>
                          <td colSpan={8}>
                            <div className="document-detail-row">
                              {detailState.loading ? (
                                <p style={{ margin: 0 }}>Consultando detalle en el backend…</p>
                              ) : detailState.error ? (
                                <StatusBanner
                                  message={detailState.error}
                                  onRetry={() => toggleDetailRow(doc)}
                                />
                              ) : detailState.detail ? (
                                <dl style={{ margin: 0 }}>
                                  <dt>MIME</dt>
                                  <dd>{detailState.detail.document.mime}</dd>
                                  <dt>Creado</dt>
                                  <dd>{formatDate(detailState.detail.document.createdAt)}</dd>
                                  <dt>Actualizado</dt>
                                  <dd>{formatDate(detailState.detail.document.updatedAt)}</dd>
                                  {detailState.detail.document.status === "deleted" ? (
                                    <>
                                      <dt>Eliminado</dt>
                                      <dd>
                                        {formatDate(detailState.detail.document.deletedAt)}
                                        {detailState.detail.document.deletedBy
                                          ? ` · por ${detailState.detail.document.deletedBy}`
                                          : ""}
                                      </dd>
                                    </>
                                  ) : null}
                                  {detailState.detail.document.errorReason ? (
                                    <>
                                      <dt>Motivo del error</dt>
                                      <dd>{detailState.detail.document.errorReason}</dd>
                                    </>
                                  ) : null}
                                  <dt>Consulta canaria</dt>
                                  <dd>
                                    {detailState.detail.canary ? (
                                      <>
                                        “{detailState.detail.canary.query}” →{" "}
                                        <strong style={{ color: detailState.detail.canary.found ? "var(--lime-deep)" : "var(--coral-deep)" }}>
                                          {detailState.detail.canary.found ? "encontrado" : "no encontrado"}
                                        </strong>{" "}
                                        (verificado {formatDate(detailState.detail.canary.checkedAt)})
                                      </>
                                    ) : (
                                      "No aplica — solo se calcula para documentos en estado listo."
                                    )}
                                  </dd>
                                </dl>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card card-pad" aria-labelledby="verify-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Prueba de learn / retrieve / forget</p>
            <h2 id="verify-heading">Consulta de verificación</h2>
          </div>
          <span className="chip chip-neutral">
            {knowledgeVersion !== null ? `Consultando v${knowledgeVersion}` : "Sin versión activa"}
          </span>
        </div>
        <p style={{ color: "var(--ink-muted)", fontSize: 13, marginTop: 0 }}>
          Ejecuta cualquier frase contra <code>GET /knowledge/search</code>. Después de cargar
          un documento, esta consulta se precompleta y se ejecuta automáticamente con las
          primeras palabras del archivo (canaria positiva). Después de eliminar un documento,
          se vuelve a ejecutar la misma consulta para confirmar 0 resultados (canaria negativa).
        </p>

        <form className="search-form" onSubmit={handleSearchSubmit}>
          <div className="filter-field" style={{ minWidth: 260 }}>
            <label htmlFor="verify-query">Consulta</label>
            <input
              id="verify-query"
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="p. ej. las primeras palabras de un documento cargado"
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={searching || !searchQuery.trim()}>
            {searching ? "Buscando…" : "Buscar"}
          </button>
        </form>

        {canaryNote ? (
          <p role="status" style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 700 }}>
            {canaryNote}
          </p>
        ) : null}

        {searchError ? <StatusBanner message={searchError} onRetry={() => runSearch(searchQuery)} /> : null}

        {searching ? (
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>Consultando el backend…</p>
        ) : searchResult === null ? (
          <EmptyState
            icon="⌕"
            title="Sin consulta ejecutada todavía"
            detail="Escribe una frase y presiona Buscar, o carga/elimina un documento para ver la canaria correspondiente en vivo."
          />
        ) : searchResult.results.length === 0 ? (
          <EmptyState
            icon="⊘"
            title={`0 resultados para "${searchResult.query}"`}
            detail={`Consultado contra la versión de conocimiento v${searchResult.knowledgeVersion}. Este es exactamente el resultado esperado tras una eliminación (canaria negativa).`}
          />
        ) : (
          <div className="search-result-list">
            <p style={{ margin: "0 0 8px", fontSize: 12, color: "var(--ink-muted)" }}>
              {searchResult.results.length} resultado(s) para “{searchResult.query}” — versión de
              conocimiento v{searchResult.knowledgeVersion}.
            </p>
            {searchResult.results.map((result) => (
              <article key={result.chunkId} className="search-result-item">
                <header>
                  <strong>{result.documentTitle}</strong>
                  <span className="search-result-meta">
                    v{result.documentVersion}
                    {result.section ? ` · ${result.section}` : ""}
                    {result.page ? ` · pág. ${result.page}` : ""}
                  </span>
                </header>
                <p>{result.text}</p>
                <div className="score-row">
                  <span className="score-chip">RRF {result.rrfScore.toFixed(3)}</span>
                  {result.lexicalScore !== null ? (
                    <span className="score-chip">Léxico {result.lexicalScore.toFixed(3)}</span>
                  ) : null}
                  {result.semanticScore !== null ? (
                    <span className="score-chip">Semántico {result.semanticScore.toFixed(3)}</span>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {pendingDelete ? (
        <ConfirmDialog
          titleId="delete-document-title"
          title={`Eliminar "${pendingDelete.doc.filename}"`}
          confirmLabel="Eliminar y verificar"
          danger
          confirming={deleting}
          error={deleteError}
          onCancel={closeDeleteDialog}
          onConfirm={confirmDelete}
          description={
            <>
              <p>
                Esta acción es transaccional: se purgan sus fragmentos e índices dentro de la
                misma transacción, la versión de conocimiento avanza, y una consulta canaria
                negativa confirma que el contenido ya no aparece en resultados de búsqueda. Si
                la canaria detecta contenido residual, el backend revierte el borrado completo
                — nunca queda un borrado a medias.
              </p>
              {pendingDelete.loadingVerify ? (
                <p className="dialog-verify-query">Cargando una consulta de verificación real desde el backend…</p>
              ) : pendingDelete.verifyQuery ? (
                <p className="dialog-verify-query">
                  Tras confirmar, se ejecutará automáticamente esta consulta de verificación: “
                  {pendingDelete.verifyQuery}”. Debe devolver 0 resultados de este documento.
                </p>
              ) : (
                <p className="dialog-verify-query">
                  No se pudo precomputar una consulta de verificación para este documento.
                  Puedes verificar manualmente en el panel de abajo tras eliminar.
                </p>
              )}
              <p>El tombstone que queda conserva únicamente id, checksum y fecha de borrado.</p>
            </>
          }
        />
      ) : null}
    </section>
  );
}
