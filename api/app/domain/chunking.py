"""Extracción/fragmentación de documentos de texto plano/Markdown (RAG-003).

Estrategia de dos niveles, determinista (misma entrada -> misma salida de
principio a fin, requisito para el test de snapshot y para que
`chunk_id` sea estable):

1. **Secciones** — el documento se separa por encabezados Markdown
   (`# ...` a `###### ...`); si no hay encabezados, todo el documento es
   una sola sección sin título (`section=None`). Esto es "fragmentar por
   estructura semántica, no por tamaño ciego" (architecture.md §9.2) en su
   forma más simple soportada por el alcance actual (txt/md).
2. **Ventana deslizante por caracteres dentro de cada sección** — con
   tamaño y solape configurables (`chunk_size_chars`/`overlap_chars`),
   ajustando el corte al siguiente espacio en blanco para no partir
   palabras a la mitad.

Para PDF (RAG-002 ampliado, `app/services/pdf_extraction.py`), el caller
invoca esta misma función una vez por página ya extraída, pasando `page` y
un `chunk_index_start` acumulado — el número de página real queda estampado
en cada `ChunkRecord` y el índice de chunk sigue siendo global y estable
para todo el documento.

`chunk_id` es `sha256(document_id|chunk_index|text)` (RAG-003: "chunk ids
estables y deterministas") — no un UUID aleatorio, para que dos corridas
del pipeline sobre el mismo documento produzcan los mismos ids."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    chunk_index: int
    section: str | None
    page: int | None
    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class _Section:
    title: str | None
    text: str
    offset: int  # posición absoluta de `text[0]` en el documento original


def chunk_document(
    document_id: str,
    text: str,
    *,
    chunk_size_chars: int = 800,
    overlap_chars: int = 150,
    page: int | None = None,
    chunk_index_start: int = 0,
) -> list[ChunkRecord]:
    if chunk_size_chars <= 0:
        raise ValueError("chunk_size_chars debe ser positivo")
    if overlap_chars < 0 or overlap_chars >= chunk_size_chars:
        raise ValueError("overlap_chars debe ser >= 0 y menor que chunk_size_chars")

    sections = _split_sections(text)
    records: list[ChunkRecord] = []
    chunk_index = chunk_index_start
    for section in sections:
        for window_text, start, end in _sliding_windows(
            section.text, chunk_size_chars, overlap_chars
        ):
            stripped = window_text.strip()
            if not stripped:
                continue
            chunk_id = _chunk_id(document_id, chunk_index, stripped)
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    chunk_index=chunk_index,
                    section=section.title,
                    page=page,
                    text=stripped,
                    char_start=section.offset + start,
                    char_end=section.offset + end,
                )
            )
            chunk_index += 1
    return records


def _chunk_id(document_id: str, chunk_index: int, text: str) -> str:
    payload = f"{document_id}|{chunk_index}|{text}".encode()
    return hashlib.sha256(payload).hexdigest()


def _split_sections(text: str) -> list[_Section]:
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return [_Section(title=None, text=text, offset=0)] if text else []

    sections: list[_Section] = []
    # Contenido antes del primer encabezado (si lo hay) es su propia
    # sección sin título.
    if headings[0].start() > 0:
        preamble = text[: headings[0].start()]
        if preamble.strip():
            sections.append(_Section(title=None, text=preamble, offset=0))

    for i, match in enumerate(headings):
        title = match.group(2).strip()
        body_start = match.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end]
        sections.append(_Section(title=title, text=body, offset=body_start))
    return sections


def _sliding_windows(text: str, chunk_size: int, overlap: int) -> list[tuple[str, int, int]]:
    if not text:
        return []
    windows: list[tuple[str, int, int]] = []
    length = len(text)
    start = 0
    while start < length:
        raw_end = min(start + chunk_size, length)
        end = raw_end
        # No cortar una palabra a la mitad: si no llegamos al final del
        # texto, retroceder hasta el último espacio en blanco anterior.
        if end < length:
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        windows.append((text[start:end], start, end))
        if end >= length:
            break
        next_start = end - overlap
        # Garantiza avance estricto (evita bucle infinito si el solape
        # coincide con el tamaño de la ventana producida).
        start = next_start if next_start > start else end
    return windows
