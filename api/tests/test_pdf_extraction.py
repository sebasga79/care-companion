"""RAG-002 ampliado — extracción de texto de PDF (`pdf_extraction.py`).

Los PDFs de prueba se generan en el propio test con `pypdf.PdfWriter`
(mismo paquete que ya es dependencia del proyecto) en vez de fixtures
binarias hardcodeadas: son deterministas, legibles en el diff y no
requieren commitear bytes opacos al repositorio."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.services.pdf_extraction import extract_pdf_pages
from app.services.upload_validation import UploadRejected


def _pdf_page_with_text(writer: PdfWriter, text: str) -> None:
    """Agrega una página con `text` renderizado vía un content stream
    mínimo. `pypdf` no ofrece una API de dibujo (no es un motor de
    render); se arma el operador `Tj` a mano, que es exactamente lo que
    produciría cualquier generador real de PDF con texto simple."""
    page = writer.add_blank_page(width=200, height=200)

    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)  # noqa: SLF001 — única forma pública indirecta

    resources = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    stream_obj = StreamObject()
    stream_obj.set_data(f"BT /F1 24 Tf 10 100 Td ({escaped}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream_obj)  # noqa: SLF001


def _build_pdf(*page_texts: str) -> bytes:
    writer = PdfWriter()
    for text in page_texts:
        _pdf_page_with_text(writer, text)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_pdf_pages_returns_text_per_page() -> None:
    content = _build_pdf("Primera pagina", "Segunda pagina")
    pages = extract_pdf_pages(content)
    assert len(pages) == 2
    assert "Primera pagina" in pages[0]
    assert "Segunda pagina" in pages[1]


def test_extract_pdf_pages_rejects_scanned_pdf_without_text_layer() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)  # sin content stream -> sin texto
    buf = io.BytesIO()
    writer.write(buf)

    with pytest.raises(UploadRejected) as exc_info:
        extract_pdf_pages(buf.getvalue())
    assert exc_info.value.code == "pdf_no_text_layer"


def test_extract_pdf_pages_rejects_corrupted_pdf() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        extract_pdf_pages(b"%PDF-1.4 esto no es un PDF valido de verdad, faltan los objetos")
    assert exc_info.value.code == "pdf_unreadable"


def test_extract_pdf_pages_rejects_encrypted_pdf() -> None:
    writer = PdfWriter()
    _pdf_page_with_text(writer, "contenido protegido")
    writer.encrypt(user_password="secret")
    buf = io.BytesIO()
    writer.write(buf)

    with pytest.raises(UploadRejected) as exc_info:
        extract_pdf_pages(buf.getvalue())
    assert exc_info.value.code == "pdf_encrypted"
