"""RAG-006 — evidence gate: matriz de unit tests (architecture.md §9.4).

`evaluate_evidence` es pura: se construyen `RetrievalResult` a mano (sin
BD ni FTS) para probar cada rama de decisión de forma aislada."""

from __future__ import annotations

from app.domain.evidence import EvidenceStatus, evaluate_evidence
from app.services.retrieval import RetrievalResult

_THRESHOLD = 0.2
_KV = 7


def _result(
    *,
    chunk_id: str = "c1",
    document_id: str = "d1",
    semantic_score: float = 0.5,
    applicability: dict | None = None,
    title: str = "Doc",
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title=title,
        document_version=1,
        section="Sección",
        page=None,
        text="texto de ejemplo",
        lexical_rank=1,
        lexical_score=-1.0,
        semantic_rank=1,
        semantic_score=semantic_score,
        rrf_score=0.03,
        applicability=applicability or {},
        knowledge_version=_KV,
    )


def test_no_results_is_insufficient() -> None:
    decision = evaluate_evidence([], score_threshold=_THRESHOLD, knowledge_version=_KV)
    assert decision.status is EvidenceStatus.INSUFFICIENT
    assert decision.citations == []
    assert decision.reasons


def test_results_below_threshold_are_insufficient() -> None:
    results = [_result(semantic_score=0.05), _result(chunk_id="c2", semantic_score=0.1)]
    decision = evaluate_evidence(results, score_threshold=_THRESHOLD, knowledge_version=_KV)
    assert decision.status is EvidenceStatus.INSUFFICIENT


def test_results_above_threshold_are_sufficient_with_citations() -> None:
    results = [_result(semantic_score=0.6)]
    decision = evaluate_evidence(results, score_threshold=_THRESHOLD, knowledge_version=_KV)
    assert decision.status is EvidenceStatus.SUFFICIENT
    assert len(decision.citations) == 1
    citation = decision.citations[0]
    assert citation.document_id == "d1"
    assert citation.chunk_id == "c1"
    assert citation.knowledge_version == _KV


def test_wrong_applicability_is_insufficient() -> None:
    results = [_result(semantic_score=0.6, applicability={"procedure": "knee_surgery"})]
    decision = evaluate_evidence(
        results,
        score_threshold=_THRESHOLD,
        knowledge_version=_KV,
        required_applicability={"procedure": "appendectomy"},
    )
    assert decision.status is EvidenceStatus.INSUFFICIENT


def test_missing_applicability_metadata_is_insufficient_when_required() -> None:
    """BR: 'faltan metadatos obligatorios de procedencia' bloquea la
    afirmación aunque el score sea alto — a diferencia del filtro
    permisivo de `retrieval.py`, evidence gate exige procedencia explícita."""
    results = [_result(semantic_score=0.9, applicability={})]
    decision = evaluate_evidence(
        results,
        score_threshold=_THRESHOLD,
        knowledge_version=_KV,
        required_applicability={"procedure": "appendectomy"},
    )
    assert decision.status is EvidenceStatus.INSUFFICIENT


def test_explicit_general_applicability_passes_any_requirement() -> None:
    results = [_result(semantic_score=0.6, applicability={"general": True})]
    decision = evaluate_evidence(
        results,
        score_threshold=_THRESHOLD,
        knowledge_version=_KV,
        required_applicability={"procedure": "appendectomy"},
    )
    assert decision.status is EvidenceStatus.SUFFICIENT


def test_matching_applicability_is_sufficient() -> None:
    results = [_result(semantic_score=0.6, applicability={"procedure": "appendectomy"})]
    decision = evaluate_evidence(
        results,
        score_threshold=_THRESHOLD,
        knowledge_version=_KV,
        required_applicability={"procedure": "appendectomy"},
    )
    assert decision.status is EvidenceStatus.SUFFICIENT


def test_conflicting_sources_same_topic_different_stance() -> None:
    results = [
        _result(
            chunk_id="c1",
            document_id="d1",
            semantic_score=0.6,
            applicability={"topic": "wound_heat_normal_range", "stance": "expected"},
        ),
        _result(
            chunk_id="c2",
            document_id="d2",
            semantic_score=0.6,
            applicability={"topic": "wound_heat_normal_range", "stance": "warning"},
        ),
    ]
    decision = evaluate_evidence(results, score_threshold=_THRESHOLD, knowledge_version=_KV)
    assert decision.status is EvidenceStatus.CONFLICTING
    assert decision.citations == []


def test_same_stance_same_topic_is_not_a_conflict() -> None:
    results = [
        _result(
            chunk_id="c1",
            document_id="d1",
            semantic_score=0.6,
            applicability={"topic": "wound_heat_normal_range", "stance": "warning"},
        ),
        _result(
            chunk_id="c2",
            document_id="d2",
            semantic_score=0.55,
            applicability={"topic": "wound_heat_normal_range", "stance": "warning"},
        ),
    ]
    decision = evaluate_evidence(results, score_threshold=_THRESHOLD, knowledge_version=_KV)
    assert decision.status is EvidenceStatus.SUFFICIENT


def test_different_topics_do_not_conflict() -> None:
    results = [
        _result(
            chunk_id="c1",
            document_id="d1",
            semantic_score=0.6,
            applicability={"topic": "wound_heat", "stance": "warning"},
        ),
        _result(
            chunk_id="c2",
            document_id="d2",
            semantic_score=0.55,
            applicability={"topic": "fever_threshold", "stance": "expected"},
        ),
    ]
    decision = evaluate_evidence(results, score_threshold=_THRESHOLD, knowledge_version=_KV)
    assert decision.status is EvidenceStatus.SUFFICIENT


def test_citations_are_capped_at_max_citations() -> None:
    results = [_result(chunk_id=f"c{i}", document_id=f"d{i}", semantic_score=0.6) for i in range(5)]
    decision = evaluate_evidence(
        results, score_threshold=_THRESHOLD, knowledge_version=_KV, max_citations=2
    )
    assert decision.status is EvidenceStatus.SUFFICIENT
    assert len(decision.citations) == 2


def test_never_returns_sufficient_without_citations() -> None:
    """Invariante dura: si status es SUFFICIENT, siempre hay al menos una
    cita — nunca una 'luz verde' sin fuente que la respalde (BR-010)."""
    results = [_result(semantic_score=0.99)]
    decision = evaluate_evidence(results, score_threshold=_THRESHOLD, knowledge_version=_KV)
    if decision.status is EvidenceStatus.SUFFICIENT:
        assert len(decision.citations) > 0
