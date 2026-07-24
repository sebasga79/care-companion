"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { StatusBanner } from "@/components/StatusBanner";
import {
  api,
  ApiError,
  type CanaryResult,
  type KnowledgeInventory,
} from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  uploaded: "Cargado",
  processing: "Procesando",
  ready: "Listo",
  deleting: "Eliminando",
  deleted: "Eliminado",
};

export default function KnowledgePage() {
  const [inventory, setInventory] = useState<KnowledgeInventory | null>(null);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [loadingInventory, setLoadingInventory] = useState(true);

  const [applicableTo, setApplicableTo] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedTitle, setUploadedTitle] = useState<string | null>(null);

  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [lastCanary, setLastCanary] = useState<CanaryResult | null>(null);

  async function fetchInventory() {
    try {
      const result = await api.getKnowledgeInventory();
      setInventory(result);
      setInventoryError(null);
    } catch (error) {
      setInventoryError(error instanceof ApiError ? error.message : "Error desconocido.");
    } finally {
      setLoadingInventory(false);
    }
  }

  function reloadInventory() {
    setLoadingInventory(true);
    setInventoryError(null);
    fetchInventory();
  }

  useEffect(() => {
    // Standard mount-time fetch. `reloadInventory` resets the loading/error
    // flags for retries and post-mutation refreshes from event handlers.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchInventory();
  }, []);

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setUploadedTitle(null);
    try {
      const doc = await api.uploadKnowledgeDocument(file, applicableTo || undefined);
      setUploadedTitle(doc.title);
      form.reset();
      setApplicableTo("");
      reloadInventory();
    } catch (error) {
      setUploadError(error instanceof ApiError ? error.message : "Error desconocido.");
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirmDelete(documentId: string) {
    setDeleting(true);
    setDeleteError(null);
    try {
      const result = await api.deleteKnowledgeDocument(documentId);
      setLastCanary(result.canary);
      setPendingDeleteId(null);
      reloadInventory();
    } catch (error) {
      setDeleteError(error instanceof ApiError ? error.message : "Error desconocido.");
    } finally {
      setDeleting(false);
    }
  }

  const documents = inventory?.documents ?? [];

  return (
    <section aria-labelledby="knowledge-heading">
      <div className="view-hero card">
        <div>
          <p className="eyebrow">Conocimiento gobernado</p>
          <h1 id="knowledge-heading">Aprende una guía nueva y demuestra que puede olvidarla</h1>
          <p>
            Esta vista demuestra el ciclo learn → retrieve → forget: cargar un
            documento, verlo participar en la recuperación y confirmar que una
            eliminación deja 0 resultados en una consulta canaria.
          </p>
        </div>
        <div className="hero-actions">
          <span className="chip chip-simulation">Datos reales del backend · sin precarga ficticia</span>
        </div>
      </div>

      {inventoryError ? <StatusBanner message={inventoryError} onRetry={reloadInventory} /> : null}

      <div className="two-col">
        <section className="card card-pad" aria-labelledby="version-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Versión activa</p>
              <h2 id="version-heading">
                {loadingInventory
                  ? "Consultando el backend…"
                  : inventory
                    ? `Versión de conocimiento v${inventory.knowledgeVersion}`
                    : "Sin conexión al backend"}
              </h2>
            </div>
            {inventory ? <span className="status-orbit">v{inventory.knowledgeVersion}</span> : null}
          </div>
          <p style={{ color: "var(--ink-muted)", fontSize: 13 }}>
            {inventory
              ? `${documents.length} documento(s) activo(s)${
                  inventory.updatedAt
                    ? ` · última actualización ${new Date(inventory.updatedAt).toLocaleString("es")}`
                    : ""
                }.`
              : "El inventario de conocimiento (documentos, versión y prueba canaria) aparecerá aquí cuando el backend esté disponible."}
          </p>

          {lastCanary ? (
            <div className="canary-result">
              <span className="chip chip-evidence">{lastCanary.resultCount === 0 ? "✓" : "↻"}</span>
              <div>
                <strong>
                  Canario de olvido: {lastCanary.resultCount} resultado(s) para &ldquo;{lastCanary.query}&rdquo;
                </strong>
                <small>Ejecutado {new Date(lastCanary.executedAt).toLocaleTimeString("es")}</small>
              </div>
            </div>
          ) : null}
        </section>

        <section className="card card-pad" aria-labelledby="upload-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Ingesta</p>
              <h2 id="upload-heading">Simular carga de guía</h2>
            </div>
          </div>

          <form className="upload-zone" onSubmit={handleUpload}>
            <label htmlFor="knowledge-file">Documento (PDF o texto)</label>
            <input id="knowledge-file" name="file" type="file" accept=".pdf,.txt,.md" required />

            <label htmlFor="applicable-to">Aplicabilidad (opcional)</label>
            <input
              id="applicable-to"
              name="applicableTo"
              type="text"
              placeholder="p. ej. apendicectomía · posoperatorio"
              value={applicableTo}
              onChange={(event) => setApplicableTo(event.target.value)}
            />

            <span className="field-help">
              Valida tipo, tamaño y checksum antes de indexar. El estado pasa por
              uploaded → processing → ready.
            </span>

            <button type="submit" className="btn btn-primary" disabled={uploading}>
              {uploading ? "Cargando…" : "Cargar documento"}
            </button>

            {uploadError ? <StatusBanner message={uploadError} /> : null}
            {uploadedTitle ? (
              <p role="status" style={{ fontSize: 12, color: "var(--lime-deep)", fontWeight: 700 }}>
                &ldquo;{uploadedTitle}&rdquo; se envió para indexación.
              </p>
            ) : null}
          </form>
        </section>
      </div>

      <section className="card card-pad" aria-labelledby="documents-heading" style={{ marginBottom: 24 }}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Fuentes de este caso ficticio</p>
            <h2 id="documents-heading">Documentos clínicos versionados</h2>
          </div>
          <span className="chip chip-neutral">{documents.length} documento(s)</span>
        </div>

        {documents.length === 0 ? (
          <EmptyState
            icon="≡"
            title="Sin documentos aún"
            detail="Los documentos cargados aparecerán aquí con su versión, aplicabilidad, estado, número de fragmentos y última prueba canaria."
          />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="document-table">
              <thead>
                <tr>
                  <th scope="col">Título</th>
                  <th scope="col">Versión</th>
                  <th scope="col">Aplicabilidad</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Chunks</th>
                  <th scope="col">Última prueba canaria</th>
                  <th scope="col">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>{doc.title}</td>
                    <td>v{doc.version}</td>
                    <td>{doc.applicableTo ?? "—"}</td>
                    <td>
                      <span className="document-status-badge" data-status={doc.status}>
                        {STATUS_LABEL[doc.status] ?? doc.status}
                      </span>
                    </td>
                    <td>{doc.chunkCount}</td>
                    <td>{doc.lastCanaryAt ? new Date(doc.lastCanaryAt).toLocaleString("es") : "—"}</td>
                    <td>
                      {pendingDeleteId === doc.id ? (
                        <div style={{ display: "flex", gap: 6 }}>
                          <button
                            type="button"
                            className="btn btn-danger"
                            style={{ minHeight: 36, padding: "0 10px" }}
                            onClick={() => handleConfirmDelete(doc.id)}
                            disabled={deleting}
                          >
                            {deleting ? "Eliminando…" : "Confirmar"}
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ minHeight: 36, padding: "0 10px" }}
                            onClick={() => setPendingDeleteId(null)}
                          >
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ minHeight: 36, padding: "0 10px" }}
                          onClick={() => setPendingDeleteId(doc.id)}
                          aria-label={`Eliminar ${doc.title}`}
                        >
                          Eliminar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {deleteError ? <StatusBanner message={deleteError} /> : null}
      </section>

      <section className="card card-pad" aria-labelledby="activity-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Pipeline auditable</p>
            <h2 id="activity-heading">Actividad de ingestión</h2>
          </div>
        </div>
        <EmptyState
          icon="↻"
          title="Aún no hay actividad de ingestión"
          detail="Cada carga o eliminación mostrará su progreso real (uploaded → processing → ready, o deleting → deleted) en cuanto ocurra."
        />
      </section>
    </section>
  );
}
