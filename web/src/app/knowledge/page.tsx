"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBanner } from "@/components/StatusBanner";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { CallModal } from "@/components/CallModal";
import { api, type CaseSummary } from "@/lib/api";
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
const INVENTORY_PAGE_SIZE = 20;

const PROCEDURE_OPTIONS = [
  ["", "Todos los procedimientos"],
  ["appendicitis", "Apendicitis / apendicectomía"],
  ["breast_cancer", "Cáncer de mama"],
  ["cholecystitis", "Colecistitis / colecistectomía"],
  ["colorectal_cancer", "Cáncer colorrectal"],
  ["total_joint_replacement", "Reemplazo articular"],
] as const;

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
    .filter(([key]) => key !== "source")
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

  const [inventoryQuery, setInventoryQuery] = useState("");
  const [inventoryScope, setInventoryScope] = useState("all");
  const [inventoryPage, setInventoryPage] = useState(1);

  const [liveMessage, setLiveMessage] = useState("");

  // Llamada de prueba, sin salir de esta página (pedido explícito: probar
  // G5 — aprender/olvidar — requiere verificar en una llamada real que el
  // documento recién subido se usa, y el selector de 160 pacientes de
  // `/call` con su protocolo completo de historial sobra para esto). Los
  // "pacientes de prueba" (`isSyntheticDemo`) son los únicos candidatos.
  const [demoCases, setDemoCases] = useState<CaseSummary[]>([]);
  const [activeCallCase, setActiveCallCase] = useState<CaseSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listCases()
      .then((all) => {
        // El caso dedicado a esta prueba (skipInterviewChecklist) no
        // conduce el checklist clínico. Si por lo que sea no existiera,
        // se cae a cualquier caso sintético antes que no ofrecer nada —
        // sigue siendo mejor que forzar el protocolo completo de un
        // paciente real para una prueba ad-hoc.
        if (cancelled) return;
        const quickTest = all.find((item) => item.skipInterviewChecklist);
        const fallback = all.filter((item) => item.isSyntheticDemo);
        setDemoCases(quickTest ? [quickTest, ...fallback.filter((c) => c.id !== quickTest.id)] : fallback);
      })
      .catch(() => {
        // Silencioso a propósito: si esto falla, el botón de abajo
        // simplemente no aparece — no vale la pena un segundo StatusBanner
        // compitiendo con los errores del inventario de conocimiento, que
        // ya cubre "sin conexión al servidor".
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const startTestCall = useCallback(() => {
    if (demoCases.length > 0) setActiveCallCase(demoCases[0]);
  }, [demoCases]);

  const activeDocuments = documents.filter((doc) => doc.status !== "deleted");
  const officialCount = activeDocuments.filter((doc) => doc.protected).length;
  const testCount = activeDocuments.filter((doc) => !doc.protected).length;
  const filteredDocuments = useMemo(() => {
    const needle = inventoryQuery.trim().toLocaleLowerCase("es");
    return documents.filter((doc) => {
      const matchesScope =
        inventoryScope === "all" ||
        (inventoryScope === "official" && doc.protected && doc.status !== "deleted") ||
        (inventoryScope === "test" && !doc.protected && doc.status !== "deleted") ||
        (inventoryScope === "deleted" && doc.status === "deleted");
      if (!matchesScope) return false;
      if (!needle) return true;
      return `${doc.filename} ${JSON.stringify(doc.applicability)}`
        .toLocaleLowerCase("es")
        .includes(needle);
    });
  }, [documents, inventoryQuery, inventoryScope]);
  const inventoryPages = Math.max(1, Math.ceil(filteredDocuments.length / INVENTORY_PAGE_SIZE));
  const pagedDocuments = filteredDocuments.slice(
    (inventoryPage - 1) * INVENTORY_PAGE_SIZE,
    inventoryPage * INVENTORY_PAGE_SIZE,
  );

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

      // The backend extracts the canary from the indexed content, so this
      // works for text files and PDFs alike.
      const detail = await knowledgeApi.getDocument(result.document.id);
      const query = detail.canary?.query;
      if (query) {
        setKnownQueries((prev) => ({ ...prev, [result.document.id]: query }));
        setSearchQuery(query);
        setCanaryNote(`Canaria positiva: verificando "${query}" contra el índice…`);
        await runSearch(query);
        setCanaryNote(`Canaria positiva confirmada para "${query}" tras la carga.`);
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
    if (doc.protected) return;
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
    <>
    <section aria-labelledby="knowledge-heading">
      <p role="status" aria-live="polite" className="sr-only">
        {liveMessage}
      </p>

      <div className="view-hero card">
        <div>
          <p className="eyebrow">Base clínica versionada</p>
          <h1 id="knowledge-heading">Evidencia que el agente puede aprender y olvidar</h1>
          <p>
            Aquí se administra la evidencia que fundamenta las respuestas. El corpus oficial
            permanece protegido; los evaluadores pueden cargar una guía de prueba, recuperarla
            y eliminarla sin reiniciar el sistema.
          </p>
        </div>
        <div className="hero-actions">
          <span className="chip chip-simulation">
            {officialCount} guías oficiales protegidas · {testCount} de prueba
          </span>
          <span className="chip chip-info">
            Versión de conocimiento: {knowledgeVersion !== null ? `v${knowledgeVersion}` : "…"}
          </span>
        </div>
      </div>

      <ol className="knowledge-steps" aria-label="Recorrido de evaluación de la base clínica">
        <li data-done={Boolean(uploadNote)}>
          <span>1</span>
          <div><strong>Cargar</strong><small>Agrega una guía de prueba</small></div>
        </li>
        <li data-done={Boolean(searchResult?.results.length)}>
          <span>2</span>
          <div><strong>Recuperar</strong><small>Confirma que el agente la encuentra</small></div>
        </li>
        <li data-done={Boolean(canaryNote?.includes("negativa ejecutada"))}>
          <span>3</span>
          <div><strong>Olvidar</strong><small>Elimina la prueba y verifica el índice</small></div>
        </li>
      </ol>

      {/* "Recuperar" (paso 2) consulta el índice directo, no pasa por un
          agente conversando — es la prueba canaria del propio sistema.
          Esto es distinto y complementario: una llamada real, con el
          agente de voz completo, para confirmar que lo recién aprendido
          también se usa en la conversación — sin el selector de 160
          pacientes reales de `/call` ni su historial longitudinal. */}
      {demoCases.length > 0 ? (
        <div className="card card-pad" style={{ marginBottom: 20 }}>
          <p className="eyebrow">Verificación en vivo</p>
          <h2 style={{ marginTop: 4, marginBottom: 6, fontSize: 17 }}>
            Probar lo que acabas de subir en una llamada real
          </h2>
          <p style={{ color: "var(--ink-muted)", fontSize: 13, marginBottom: 12 }}>
            Abre una llamada con un paciente de prueba (sin historial previo) y pregunta algo
            que sólo el documento recién cargado respondería.
          </p>
          <button type="button" className="voice-preview-btn" onClick={startTestCall}>
            Probar en una llamada · {demoCases[0].patientAlias}
          </button>
        </div>
      ) : null}

      {listError ? <StatusBanner message={listError} onRetry={reloadInventory} /> : null}

      <div className="two-col knowledge-overview">
        <section className="card card-pad" aria-labelledby="version-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Versión activa</p>
              <h2 id="version-heading">
                {listLoading
                  ? "Consultando el servidor…"
                  : knowledgeVersion !== null
                    ? `Versión de conocimiento v${knowledgeVersion}`
                    : "Sin conexión al servidor"}
              </h2>
            </div>
            {knowledgeVersion !== null ? <span className="status-orbit">v{knowledgeVersion}</span> : null}
          </div>
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>
            {knowledgeVersion !== null
              ? `${activeDocuments.length} documentos activos: ${officialCount} oficiales protegidos y ${testCount} de prueba. Los borrados quedan como trazabilidad.`
              : "El inventario de conocimiento (documentos, versión y prueba canaria) aparecerá aquí cuando el servidor esté disponible."}
          </p>
        </section>

        <section className="card card-pad" aria-labelledby="upload-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Ingesta</p>
              <h2 id="upload-heading">Cargar guía clínica</h2>
            </div>
          </div>

          <p className="upload-purpose">
            Sube aquí un documento clínico que el agente <strong>no conozca</strong>. Al
            cargarlo queda disponible de inmediato para las llamadas; al eliminarlo, el
            agente deja de usarlo. Es la prueba de conocimiento vivo.
          </p>

          <form className="upload-zone" onSubmit={handleUpload}>
            {/* Cada campo va en su propio contenedor con la etiqueta encima
                del control. Antes los `label` y `select` eran hijos sueltos
                del grid, así que "Fase" terminaba flotando al lado del
                selector de "Procedimiento" y su propio selector caía en la
                línea siguiente, desalineado. */}
            <div className="upload-field">
              <label htmlFor="knowledge-file">Documento (.txt, .md o .pdf)</label>
              <input
                id="knowledge-file"
                name="file"
                type="file"
                accept=".txt,.md,.pdf"
                required
              />
            </div>

            <details className="advanced-fields">
              <summary>Aplicabilidad clínica (opcional)</summary>
              <p className="advanced-fields-help">
                Acota a qué llamadas aplica. Si lo dejas sin especificar, el documento
                sirve para cualquier procedimiento.
              </p>
              <div className="advanced-fields-grid">
                <div className="upload-field">
                  <label htmlFor="applicability-procedure">Procedimiento</label>
                  <select
                    id="applicability-procedure"
                    value={procedure}
                    onChange={(event) => setProcedure(event.target.value)}
                  >
                    {PROCEDURE_OPTIONS.map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>

                <div className="upload-field">
                  <label htmlFor="applicability-phase">Fase</label>
                  <select
                    id="applicability-phase"
                    value={phase}
                    onChange={(event) => setPhase(event.target.value)}
                  >
                    <option value="">Todas las fases</option>
                    <option value="postoperative">Posoperatorio</option>
                    <option value="discharge">Alta</option>
                    <option value="followup">Seguimiento</option>
                  </select>
                </div>
              </div>
            </details>

            <span className="field-help">
              Se valida extensión, tamaño, contenido real y duplicados antes de indexar.
              Un rechazo no deja el documento a medias.
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

        <div className="inventory-toolbar">
          <div className="filter-field">
            <label htmlFor="inventory-query">Buscar documento</label>
            <input
              id="inventory-query"
              value={inventoryQuery}
              onChange={(event) => {
                setInventoryQuery(event.target.value);
                setInventoryPage(1);
              }}
              placeholder="Nombre o procedimiento"
            />
          </div>
          <div className="filter-field">
            <label htmlFor="inventory-scope">Origen y estado</label>
            <select
              id="inventory-scope"
              value={inventoryScope}
              onChange={(event) => {
                setInventoryScope(event.target.value);
                setInventoryPage(1);
              }}
            >
              <option value="all">Todos</option>
              <option value="official">Corpus oficial protegido</option>
              <option value="test">Documentos de prueba</option>
              <option value="deleted">Eliminados</option>
            </select>
          </div>
          <span className="chip chip-neutral">{filteredDocuments.length} visibles</span>
        </div>

        {listLoading ? (
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>Consultando el servidor…</p>
        ) : documents.length === 0 ? (
          <EmptyState
            icon="≡"
            title="Sin documentos aún"
            detail="Los documentos cargados aparecerán aquí con su versión, aplicabilidad, estado, checksum y acciones de inspección/eliminación."
          />
        ) : filteredDocuments.length === 0 ? (
          <EmptyState
            icon="⌕"
            title="No hay coincidencias"
            detail="Cambia el texto de búsqueda o el filtro de origen y estado."
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
                {pagedDocuments.map((doc) => {
                  const meta = statusMeta(doc.status);
                  const entries = applicabilityEntries(doc.applicability);
                  const detailState = openDetails[doc.id];
                  const isPendingThisDoc = pendingDelete?.doc.id === doc.id;
                  return (
                    <Fragment key={doc.id}>
                      <tr>
                        <td>
                          <strong>{doc.filename}</strong>
                          <span className={`document-origin ${doc.protected ? "official" : "test"}`}>
                            {doc.protected ? "Oficial · protegido" : "Prueba del evaluador"}
                          </span>
                        </td>
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
                            {doc.status !== "deleted" && !doc.protected ? (
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
                            ) : doc.protected ? (
                              <span className="protected-label" title="El corpus oficial no se puede eliminar">
                                Protegido
                              </span>
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
            {inventoryPages > 1 ? (
              <nav className="inventory-pagination" aria-label="Páginas del inventario">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={inventoryPage === 1}
                  onClick={() => setInventoryPage((page) => Math.max(1, page - 1))}
                >
                  Anterior
                </button>
                <span>Página {inventoryPage} de {inventoryPages}</span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={inventoryPage === inventoryPages}
                  onClick={() => setInventoryPage((page) => Math.min(inventoryPages, page + 1))}
                >
                  Siguiente
                </button>
              </nav>
            ) : null}
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
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>Consultando el servidor…</p>
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
                <p className="dialog-verify-query">Cargando una consulta de verificación real desde el servidor…</p>
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

    {activeCallCase ? (
      <CallModal patientCase={activeCallCase} onClose={() => setActiveCallCase(null)} />
    ) : null}
    </>
  );
}
