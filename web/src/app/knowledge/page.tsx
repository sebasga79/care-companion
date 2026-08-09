"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
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

function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-CO", { day: "2-digit", month: "2-digit", year: "numeric" });
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

/* Íconos de línea, inline (sin librería ni emoji — mismo criterio que el
   resto de la app: símbolos monocromos, no ilustraciones a color). */

function CloudUploadIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M7 18a4.5 4.5 0 0 1-.5-8.97A5.5 5.5 0 0 1 17.5 9.5 4 4 0 0 1 17 18H7Z" />
      <path d="M12 12.5v6M9.3 15l2.7-2.5 2.7 2.5" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1.5 12S5 5 12 5s10.5 7 10.5 7-3.5 7-10.5 7S1.5 12 1.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-8 0 1 12a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-12" />
    </svg>
  );
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

  // Dropzone: arrastrar y soltar, además del selector clásico. El input
  // real queda oculto (`sr-only`) pero sigue siendo el mismo <input
  // type="file" name="file"> que `handleUpload` ya leía — al soltar un
  // archivo se le asigna vía `DataTransfer`, así que el resto del flujo
  // de carga (validación, submit) no cambia una línea.
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);

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

  // Cada paso del recorrido (1/2/3) lleva aquí en vez de ser puramente
  // descriptivo. Bug real reportado en vivo: `block: "center"` centraba
  // la SECCIÓN completa (la tabla de 108 documentos), así que "Olvidar"
  // aterrizaba en cualquier fila del medio — no en el documento de
  // prueba, que es lo único que importa borrar. Dos correcciones: la
  // tabla se filtra a "de prueba" (mismo control que ya existía arriba
  // de la tabla, sólo se activa por código) antes de saltar, y el scroll
  // va al INICIO de la sección (`block: "start"`), no al centro.
  const jumpToStep = useCallback((headingId: string) => {
    if (headingId === "documents-heading") setInventoryScope("test");
    // El cambio de filtro reordena el DOM; se espera al siguiente frame
    // para que `scrollIntoView` mida posiciones ya actualizadas.
    requestAnimationFrame(() => {
      const heading = document.getElementById(headingId);
      const target = heading?.closest("section") ?? heading;
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      target.classList.add("step-target-highlight");
      window.setTimeout(() => target.classList.remove("step-target-highlight"), 2000);
    });
  }, []);

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

  function pickFile(file: File | null) {
    setSelectedFile(file);
  }

  function handleDropzoneClick() {
    fileInputRef.current?.click();
  }

  function handleDropzoneDragOver(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleDropzoneDragLeave(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
  }

  function handleDropzoneDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files?.[0];
    const input = fileInputRef.current;
    if (!file || !input) return;
    // Un <input type="file"> no acepta asignar `.files` directo con un
    // array — hay que construir un `DataTransfer` real. Así el resto del
    // flujo (`handleUpload` lee `form.elements.namedItem("file")`) sigue
    // funcionando exactamente igual, sin importar si el archivo llegó
    // por clic o por arrastre.
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    pickFile(file);
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
      pickFile(null);
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

      {/* Rediseño según sketch aportado por el usuario: una sola tarjeta
          con tres columnas (intro / dropzone / prueba en llamada) en vez
          de dos tarjetas separadas. El dropzone es funcional de verdad
          (arrastrar y soltar), no sólo decorativo. */}
      <section className="card card-pad knowledge-upload-card" aria-labelledby="upload-heading">
        <form onSubmit={handleUpload}>
          <div className="knowledge-upload-grid">
            <div className="knowledge-upload-intro">
              <h2 id="upload-heading">Cargar guía clínica</h2>
              <p>
                Sube aquí un documento clínico que el agente <strong>no conozca</strong>. Al
                cargarlo queda disponible de inmediato para las llamadas; al eliminarlo, el
                agente deja de usarlo. Es la prueba de conocimiento vivo.
              </p>
            </div>

            <div
              className="knowledge-dropzone"
              data-dragging={isDragging}
              onDragOver={handleDropzoneDragOver}
              onDragEnter={handleDropzoneDragOver}
              onDragLeave={handleDropzoneDragLeave}
              onDrop={handleDropzoneDrop}
            >
              <CloudUploadIcon />
              <p className="knowledge-dropzone-title">Arrastra y suelta archivos aquí</p>
              <button type="button" className="knowledge-dropzone-btn" onClick={handleDropzoneClick}>
                Seleccionar archivo
              </button>
              <label htmlFor="knowledge-file" className="sr-only">
                Documento (.txt, .md o .pdf)
              </label>
              <input
                ref={fileInputRef}
                id="knowledge-file"
                name="file"
                type="file"
                accept=".txt,.md,.pdf"
                required
                className="sr-only"
                onChange={(event) => pickFile(event.target.files?.[0] ?? null)}
              />
              <p className="knowledge-dropzone-filename">
                {selectedFile ? selectedFile.name : "Sin archivo seleccionado — .txt, .md o .pdf"}
              </p>
            </div>

            {demoCases.length > 0 ? (
              <div className="knowledge-call-test">
                <span className="knowledge-call-test-icon" aria-hidden="true">
                  <span className="mic-symbol" />
                </span>
                <h3>Probar en una llamada</h3>
                <p>Verifica lo que acabas de subir, sin historial previo.</p>
                <button type="button" className="knowledge-call-test-btn" onClick={startTestCall}>
                  Iniciar prueba
                </button>
              </div>
            ) : null}
          </div>

          <details className="advanced-fields knowledge-upload-advanced">
            <summary>Aplicabilidad clínica (opcional)</summary>
            <p className="advanced-fields-help">
              Acota a qué llamadas aplica. Si lo dejas sin especificar, el documento sirve
              para cualquier procedimiento.
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

          <span className="field-help knowledge-upload-help">
            Se valida extensión, tamaño, contenido real y duplicados antes de indexar. Un
            rechazo no deja el documento a medias.
          </span>

          <button type="submit" className="btn btn-primary knowledge-upload-submit" disabled={uploading}>
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
      </div>

      {/* Cada paso lleva a donde de verdad se hace esa acción — antes era
          puramente decorativo: decía "Olvidar" pero no había forma de
          saber dónde ocurría eso sin explicarlo aparte (hallazgo real del
          usuario: "ahí dice olvidar, pero dónde?"). */}
      <ol className="knowledge-steps" aria-label="Recorrido de evaluación de la base clínica">
        <li data-done={Boolean(uploadNote)}>
          <button type="button" onClick={() => jumpToStep("upload-heading")}>
            <span>1</span>
            <div><strong>Cargar</strong><small>Agrega una guía de prueba</small></div>
          </button>
        </li>
        <li data-done={Boolean(searchResult?.results.length)}>
          <button type="button" onClick={() => jumpToStep("verify-heading")}>
            <span>2</span>
            <div><strong>Recuperar</strong><small>Confirma que el agente la encuentra</small></div>
          </button>
        </li>
        <li data-done={Boolean(canaryNote?.includes("negativa ejecutada"))}>
          <button type="button" onClick={() => jumpToStep("documents-heading")}>
            <span>3</span>
            <div><strong>Olvidar</strong><small>Elimina la prueba y verifica el índice</small></div>
          </button>
        </li>
      </ol>

      {listError ? <StatusBanner message={listError} onRetry={reloadInventory} /> : null}

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
            detail="Los documentos cargados aparecerán aquí con su versión, estado y acciones de inspección/eliminación. Tamaño, aplicabilidad y checksum viven en “Ver detalle”."
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
                  <th scope="col">Nombre de la guía</th>
                  <th scope="col">Versión</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Fecha de subida</th>
                  <th scope="col">Acciones</th>
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
                        <td>v{doc.knowledgeVersionAdded}</td>
                        <td>
                          <span className="document-status-badge" data-status={doc.status}>
                            <span aria-hidden="true">{meta.icon}</span> {meta.label}
                          </span>
                        </td>
                        <td>{formatShortDate(doc.createdAt)}</td>
                        <td>
                          <div className="document-actions">
                            <button
                              type="button"
                              className="icon-btn"
                              onClick={() => toggleDetailRow(doc)}
                              aria-expanded={Boolean(detailState)}
                              aria-label={
                                detailState ? `Ocultar detalle de ${doc.filename}` : `Ver detalle de ${doc.filename}`
                              }
                              title={detailState ? "Ocultar detalle" : "Ver detalle"}
                            >
                              <EyeIcon />
                            </button>
                            {doc.status !== "deleted" && !doc.protected ? (
                              <button
                                type="button"
                                className="icon-btn icon-btn-danger"
                                onClick={() => openDeleteDialog(doc)}
                                aria-label={`Eliminar ${doc.filename}`}
                                title="Eliminar"
                                disabled={isPendingThisDoc}
                              >
                                <TrashIcon />
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
                          <td colSpan={5}>
                            <div className="document-detail-row">
                              {detailState.loading ? (
                                <p style={{ margin: 0 }}>Consultando detalle en el servidor…</p>
                              ) : detailState.error ? (
                                <StatusBanner
                                  message={detailState.error}
                                  onRetry={() => toggleDetailRow(doc)}
                                />
                              ) : detailState.detail ? (
                                <dl style={{ margin: 0 }}>
                                  <dt>Tamaño</dt>
                                  <dd>{formatBytes(doc.sizeBytes)}</dd>
                                  <dt>Aplicabilidad</dt>
                                  <dd>
                                    {entries.length === 0 ? (
                                      "General — aplica a cualquier procedimiento"
                                    ) : (
                                      <div className="applicability-chips">
                                        {entries.map(([key, value]) => (
                                          <span key={key} className="chip chip-neutral">
                                            {key}: {value}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </dd>
                                  <dt>Checksum</dt>
                                  <dd>
                                    <code className="checksum-code" title={doc.checksum}>
                                      {truncateChecksum(doc.checksum)}
                                    </code>
                                  </dd>
                                  <dt>Versión eliminada</dt>
                                  <dd>{doc.knowledgeVersionDeleted !== null ? `v${doc.knowledgeVersionDeleted}` : "—"}</dd>
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
                la canaria detecta contenido residual, el servidor revierte el borrado completo
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

    {/* Barra inferior: resumen de versión, según el sketch — antes vivía
        junto al hero como par de chips; ahora queda fija abajo, siempre
        visible mientras se navega la página. */}
    <div className="knowledge-status-bar">
      <span className="chip chip-simulation">
        {officialCount} guías oficiales protegidas · {testCount} de prueba
      </span>
      <span className="chip chip-info">
        Versión de conocimiento: {knowledgeVersion !== null ? `v${knowledgeVersion}` : "…"}
      </span>
    </div>

    {activeCallCase ? (
      <CallModal patientCase={activeCallCase} onClose={() => setActiveCallCase(null)} />
    ) : null}
    </>
  );
}
