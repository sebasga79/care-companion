"""RAG-003 — extract/chunk: fragmentación por estructura + solape,
ids deterministas. Test de snapshot sobre un fixture fijo."""

from __future__ import annotations

from app.domain.chunking import chunk_document

_FIXTURE_DOCUMENT = """# Guia de alta postoperatoria

Instrucciones generales de cuidado para los primeros dias tras la cirugia.

## Signos de alarma

Si siente calor en la herida o fiebre mayor a 38 grados, contacte al \
equipo medico de inmediato. Esta es una senal de alarma importante que \
requiere atencion sin demora.

## Cuidado de la herida

Mantenga la herida limpia y seca. Cambie el vendaje segun las \
indicaciones del equipo medico y evite mojar el area directamente.
"""


def test_chunking_snapshot_is_deterministic_and_stable() -> None:
    chunks_a = chunk_document(
        "doc-fixture-1", _FIXTURE_DOCUMENT, chunk_size_chars=120, overlap_chars=30
    )
    chunks_b = chunk_document(
        "doc-fixture-1", _FIXTURE_DOCUMENT, chunk_size_chars=120, overlap_chars=30
    )

    assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]
    assert [c.text for c in chunks_a] == [c.text for c in chunks_b]

    # snapshot explícito: si esto cambia, es una decisión consciente de
    # fragmentación, no una regresión silenciosa.
    assert len(chunks_a) == 5
    assert [c.section for c in chunks_a] == [
        "Guia de alta postoperatoria",
        "Signos de alarma",
        "Signos de alarma",
        "Cuidado de la herida",
        "Cuidado de la herida",
    ]
    assert chunks_a[1].text.startswith("Si siente calor en la herida")
    assert "fiebre" in chunks_a[1].text


def test_chunk_ids_change_when_document_id_changes() -> None:
    chunks_doc1 = chunk_document("doc-1", _FIXTURE_DOCUMENT, chunk_size_chars=120, overlap_chars=30)
    chunks_doc2 = chunk_document("doc-2", _FIXTURE_DOCUMENT, chunk_size_chars=120, overlap_chars=30)
    assert [c.chunk_id for c in chunks_doc1] != [c.chunk_id for c in chunks_doc2]


def test_chunk_ids_are_stable_hash_of_doc_index_and_text() -> None:
    import hashlib

    chunks = chunk_document("doc-1", _FIXTURE_DOCUMENT, chunk_size_chars=120, overlap_chars=30)
    for chunk in chunks:
        expected = hashlib.sha256(
            f"doc-1|{chunk.chunk_index}|{chunk.text}".encode()
        ).hexdigest()
        assert chunk.chunk_id == expected


def test_overlap_produces_shared_text_between_consecutive_windows() -> None:
    long_section = "palabra " * 200  # una sola "sección" sin encabezados
    chunks = chunk_document("doc-overlap", long_section, chunk_size_chars=100, overlap_chars=20)
    assert len(chunks) > 1
    # el final del primer chunk y el inicio del segundo deben compartir texto
    tail = chunks[0].text[-15:]
    assert tail.strip() in chunks[1].text


def test_no_headings_produces_single_untitled_section() -> None:
    plain_text = "Este es un documento sin encabezados markdown, solo texto plano corrido."
    chunks = chunk_document("doc-plain", plain_text, chunk_size_chars=500, overlap_chars=50)
    assert len(chunks) == 1
    assert chunks[0].section is None


def test_empty_document_produces_no_chunks() -> None:
    assert chunk_document("doc-empty", "", chunk_size_chars=100, overlap_chars=10) == []
    assert chunk_document("doc-empty", "   \n\n  ", chunk_size_chars=100, overlap_chars=10) == []


def test_chunk_metadata_has_correct_char_offsets() -> None:
    chunks = chunk_document("doc-1", _FIXTURE_DOCUMENT, chunk_size_chars=120, overlap_chars=30)
    for chunk in chunks:
        recovered = _FIXTURE_DOCUMENT[chunk.char_start : chunk.char_end]
        assert chunk.text == recovered.strip()
