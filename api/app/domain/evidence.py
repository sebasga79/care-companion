"""Evidence gate (RAG-006, architecture.md §9.4).

Función pura y determinista — sin llamadas a LLM, sin I/O propio (recibe
`RetrievalResult` ya calculados por `app/services/retrieval.py`). Decide si
hay evidencia activa suficiente para que `ResponseAgent` (aún no
implementado, llega en C2 con los agentes) pueda emitir una afirmación
clínica. Las cinco condiciones de bloqueo de architecture.md §9.4 se
mapean así:

| condición de architecture.md §9.4         | dónde se aplica aquí                          |
|--------------------------------------------|------------------------------------------------|
| sin fragmentos sobre el umbral             | `score_threshold`                               |
| fragmentos de una versión eliminada        | ya excluidos en retrieval (status='ready')      |
| fuente no aplicable a procedimiento/fase   | `required_applicability`                        |
| conflicto no resuelto entre documentos     | `_detect_conflict` (heurística MVP, ver abajo)  |
| faltan metadatos obligatorios              | `required_applicability` (ausencia = no aplica) |

Si no hay evidencia suficiente, el resultado es `insufficient` o
`conflicting` — nunca `sufficient` con una fuente forzada. La capa que
consuma esto (agente/orquestador, fuera de este ticket) debe tratar
cualquier status distinto de `sufficient` como abstención/aclaración/
escalamiento, nunca como luz verde para responder desde conocimiento
general del modelo (spec.md FR-038, BR-010)."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from app.domain.models import CitationRef
from app.services.retrieval import RetrievalResult


class EvidenceStatus(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


class EvidenceDecision(BaseModel):
    status: EvidenceStatus
    citations: list[CitationRef] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    knowledge_version: int


def evaluate_evidence(
    results: list[RetrievalResult],
    *,
    score_threshold: float,
    knowledge_version: int,
    required_applicability: dict[str, str] | None = None,
    max_citations: int = 3,
) -> EvidenceDecision:
    if not results:
        return EvidenceDecision(
            status=EvidenceStatus.INSUFFICIENT,
            reasons=["no se recuperó ningún fragmento"],
            knowledge_version=knowledge_version,
        )

    qualifying = [r for r in results if (r.semantic_score or 0.0) >= score_threshold]
    if not qualifying:
        return EvidenceDecision(
            status=EvidenceStatus.INSUFFICIENT,
            reasons=[f"ningún fragmento supera el umbral de score ({score_threshold})"],
            knowledge_version=knowledge_version,
        )

    if required_applicability:
        applicable = [
            r for r in qualifying if _is_applicable(r.applicability, required_applicability)
        ]
        if not applicable:
            return EvidenceDecision(
                status=EvidenceStatus.INSUFFICIENT,
                reasons=[
                    "ningún fragmento es aplicable al procedimiento/fase requerido "
                    "o le faltan metadatos obligatorios de procedencia"
                ],
                knowledge_version=knowledge_version,
            )
        qualifying = applicable

    conflict_reason = _detect_conflict(qualifying)
    if conflict_reason is not None:
        return EvidenceDecision(
            status=EvidenceStatus.CONFLICTING,
            reasons=[conflict_reason],
            knowledge_version=knowledge_version,
        )

    citations = [_to_citation(result, knowledge_version) for result in qualifying[:max_citations]]
    return EvidenceDecision(
        status=EvidenceStatus.SUFFICIENT,
        citations=citations,
        knowledge_version=knowledge_version,
    )


def _is_applicable(doc_applicability: dict, required: dict[str, str]) -> bool:
    """Más estricto que el filtro de `retrieval.py` (que es permisivo para
    no vaciar el top-k durante el ranking): aquí la ausencia de la clave
    requerida NO cuenta como "aplica a todos" salvo que el documento lo
    declare explícitamente con `applicability.general = true` — evidence
    gate es la última línea de defensa antes de una afirmación clínica
    (BR-013), así que exige procedencia explícita."""
    if doc_applicability.get("general") is True:
        return True
    for key, value in required.items():
        if doc_applicability.get(key) != value:
            return False
    return True


def _detect_conflict(results: list[RetrievalResult]) -> str | None:
    """Heurística MVP (no NLU): dos fuentes activas se consideran en
    conflicto solo si comparten `applicability.topic` y declaran un
    `applicability.stance` distinto (p. ej. topic="wound_heat_normal_range",
    stance="expected" vs stance="warning"). Detección semántica real de
    contradicción sin metadata explícita requeriría un LLM-judge —
    deliberadamente fuera de alcance aquí (no se agrega un LLM extra sin
    necesidad demostrada, docs/policies/dependencies.md; y esta capa debe
    seguir siendo determinista, no un agente)."""
    stance_by_topic: dict[str, set[str]] = {}
    for result in results:
        topic = result.applicability.get("topic")
        stance = result.applicability.get("stance")
        if topic is None or stance is None:
            continue
        stance_by_topic.setdefault(topic, set()).add(stance)
    for topic, stances in stance_by_topic.items():
        if len(stances) > 1:
            return f"fuentes activas en conflicto sobre '{topic}': posiciones {sorted(stances)}"
    return None


def _to_citation(result: RetrievalResult, knowledge_version: int) -> CitationRef:
    return CitationRef(
        citation_id=str(uuid.uuid4()),
        document_id=result.document_id,
        document_version=result.document_version,
        chunk_id=result.chunk_id,
        title=result.document_title,
        section=result.section,
        page=result.page,
        knowledge_version=knowledge_version,
    )
