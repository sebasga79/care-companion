"""Validación de carga de documentos (RAG-002).

Todas las reglas son deterministas y se evalúan **antes** de escribir
nada en disco/BD (BR-016: "subir bytes no significa aprendido" — aquí
además ni siquiera llegan a considerarse "subidos" si son inválidos).

No se agrega ninguna dependencia nueva para esto (docs/policies/
dependencies.md): el saneo de nombre de archivo y el sniff de MIME son
unas pocas líneas de stdlib, no ameritan `python-magic` ni similares."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Firma de bytes iniciales -> familia real de archivo, para detectar un MIME
# "falso" (extensión .txt/.md sobre contenido que en realidad es otra cosa).
# Deliberadamente pequeño: solo lo necesario para los formatos most-likely
# a aparecer disfrazados en un intento de bypass (PDF, ZIP/Office, ELF/PE).
_MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "pdf"),
    (b"PK\x03\x04", "zip/office"),
    (b"\x7fELF", "elf-binary"),
    (b"MZ", "pe-binary"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
)


class UploadRejected(Exception):
    """Rechazo de carga con motivo explícito (nunca un fallo silencioso)."""

    def __init__(self, reason: str, *, code: str) -> None:
        self.reason = reason
        self.code = code
        super().__init__(reason)


@dataclass(frozen=True)
class ValidatedUpload:
    safe_filename: str
    extension: str
    checksum: str
    size_bytes: int


def sanitize_filename(raw_filename: str) -> str:
    """Quita cualquier componente de directorio (defensa contra path
    traversal: `../../etc/passwd`, `..\\..\\win.ini`, rutas absolutas) y
    exige una allowlist estricta de caracteres en lo que queda."""
    # basename manual: corta en el último separador de cualquiera de los
    # dos estilos de ruta, sin depender de `os.path` (cuyo comportamiento
    # de separador varía por plataforma — aquí queremos la misma regla
    # determinista sin importar el SO donde corra el proceso).
    candidate = raw_filename.replace("\\", "/").split("/")[-1].strip()
    if not candidate or candidate in {".", ".."}:
        raise UploadRejected(
            "Nombre de archivo vacío o inválido tras sanear la ruta", code="invalid_filename"
        )
    if not _SAFE_FILENAME_RE.match(candidate):
        raise UploadRejected(
            f"Nombre de archivo contiene caracteres no permitidos: {candidate!r}",
            code="invalid_filename",
        )
    return candidate


def extract_extension(safe_filename: str) -> str:
    if "." not in safe_filename:
        raise UploadRejected(
            f"El archivo no tiene extensión: {safe_filename!r}", code="missing_extension"
        )
    return safe_filename.rsplit(".", 1)[-1].lower()


def detect_declared_mime_mismatch(content: bytes, extension: str) -> str | None:
    """Compara los bytes iniciales contra `_MAGIC_SIGNATURES`. Devuelve una
    descripción del formato real detectado si contradice la extensión
    declarada (txt/md nunca deberían empezar con estas firmas), o `None`
    si no hay señal de falsificación."""
    if extension not in {"txt", "md"}:
        return None
    for signature, detected in _MAGIC_SIGNATURES:
        if content.startswith(signature):
            return detected
    return None


def validate_upload(
    *,
    raw_filename: str,
    content: bytes,
    allowed_extensions: frozenset[str],
    max_bytes: int,
    existing_active_checksums: frozenset[str],
) -> ValidatedUpload:
    """Corre todas las reglas de RAG-002 en orden y lanza `UploadRejected`
    en el primer incumplimiento, con `code` estable para que la capa API
    lo mapee a un status HTTP y el cliente pueda distinguir el motivo."""
    safe_filename = sanitize_filename(raw_filename)
    extension = extract_extension(safe_filename)

    if extension == "pdf":
        raise UploadRejected(
            "PDF no soportado aún: no hay librería de extracción aprobada "
            "(docs/policies/dependencies.md — sin dependencias nuevas sin necesidad "
            "demostrada); cargue .txt o .md mientras tanto.",
            code="pdf_not_supported",
        )
    if extension not in allowed_extensions:
        raise UploadRejected(
            f"Tipo de archivo no permitido: .{extension} "
            f"(permitidos: {', '.join(sorted(allowed_extensions))})",
            code="extension_not_allowed",
        )

    if len(content) == 0:
        raise UploadRejected("El archivo está vacío", code="empty_file")
    if len(content) > max_bytes:
        raise UploadRejected(
            f"El archivo excede el tamaño máximo permitido ({max_bytes} bytes)",
            code="file_too_large",
        )

    mismatch = detect_declared_mime_mismatch(content, extension)
    if mismatch is not None:
        raise UploadRejected(
            f"El contenido no coincide con la extensión .{extension} "
            f"(firma de bytes detectada: {mismatch})",
            code="mime_mismatch",
        )

    checksum = hashlib.sha256(content).hexdigest()
    if checksum in existing_active_checksums:
        raise UploadRejected(
            "Ya existe un documento activo con el mismo contenido (checksum duplicado)",
            code="duplicate_checksum",
        )

    return ValidatedUpload(
        safe_filename=safe_filename,
        extension=extension,
        checksum=checksum,
        size_bytes=len(content),
    )
