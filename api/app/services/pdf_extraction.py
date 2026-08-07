"""Extracción de texto de PDF (RAG-002 ampliado — el corpus real del reto,
`dataset/textos/`, son 107 PDFs; hasta el 7 de agosto de 2026 no había
necesidad demostrada de esta dependencia, ver
`docs/auditoria-kit-oficial-2026-08-07.md`).

Usa `pypdf` (BSD-3-Clause, mantenimiento activo — cumple
`docs/policies/dependencies.md` §1/§2) únicamente para extraer texto plano
por página. El contenido extraído se trata igual que cualquier otro texto
del pipeline de ingesta: nunca se interpreta como instrucción (spec.md §11,
BR-015), solo se fragmenta, se embebe y se indexa.

PDFs escaneados sin capa de texto (caso conocido en el corpus oficial:
`Appendicitis/` tiene un PDF así) no producen texto extraíble — se
detectan explícitamente y se rechazan con un motivo claro en vez de
indexar páginas vacías en silencio."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.upload_validation import UploadRejected


def extract_pdf_pages(content: bytes) -> list[str]:
    """Devuelve el texto de cada página, en orden (índice de lista = página
    - 1). Lanza `UploadRejected` si el PDF está corrupto, cifrado, o si
    ninguna página tiene texto extraíble."""
    try:
        reader = PdfReader(BytesIO(content))
    except (PdfReadError, ValueError) as exc:
        raise UploadRejected(
            f"No se pudo leer el PDF (archivo corrupto o formato no soportado): {exc}",
            code="pdf_unreadable",
        ) from exc

    if reader.is_encrypted:
        raise UploadRejected(
            "El PDF está protegido con contraseña; no se puede extraer texto",
            code="pdf_encrypted",
        )

    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pypdf puede lanzar varios tipos ante un PDF malformado
            raise UploadRejected(
                f"No se pudo extraer texto de una página del PDF: {exc}",
                code="pdf_unreadable",
            ) from exc
        pages.append(text.strip())

    if not any(pages):
        raise UploadRejected(
            "El PDF no tiene texto extraíble (probablemente escaneado sin capa de "
            "texto/OCR); cargue una versión con texto o un .txt/.md equivalente.",
            code="pdf_no_text_layer",
        )
    return pages


__all__ = ["extract_pdf_pages"]
