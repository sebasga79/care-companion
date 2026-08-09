import type { CitationRef } from "@/lib/api";
import { EmptyState } from "./EmptyState";

type EvidencePanelProps = {
  citations: CitationRef[];
};

/** Deliverable requires this panel to be explicitly "vacío-honesto". */
export function EvidencePanel({ citations }: EvidencePanelProps) {
  if (citations.length === 0) {
    return (
      <EmptyState
        icon="≡"
        title="Sin evidencia recuperada todavía"
        detail="Cuando se encuentren fuentes vigentes para esta conversación, cada cita mostrará documento, sección y versión."
      />
    );
  }

  return (
    <div className="evidence-list" aria-label="Evidencia activa">
      {citations.map((citation) => (
        <article key={citation.chunkId} className="evidence-item">
          <div>
            <strong>{citation.documentTitle}</strong>
            <small>
              v{citation.version}
              {citation.section ? ` · ${citation.section}` : ""}
              {citation.page ? ` · pág. ${citation.page}` : ""}
            </small>
          </div>
          <span className="chip chip-evidence">Verificada</span>
        </article>
      ))}
    </div>
  );
}
