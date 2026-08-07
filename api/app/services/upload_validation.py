"""Validación de carga de documentos (RAG-002).

Todas las reglas son deterministas y se evalúan **antes** de escribir
nada en disco/BD (BR-016: "subir bytes no significa aprendido" — aquí
además ni siquiera llegan a considerarse "subidos" si son inválidos).

No se agrega ninguna dependencia nueva para esto (docs/policies/
dependencies.md): el saneo de nombre de archivo y el sniff de MIME son
unas pocas líneas de stdlib, no ameritan `python-magic` ni similares."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# Deny-list, no allow-list (corregido tras probar contra el corpus real del
# reto, docs/auditoria-kit-oficial-2026-08-07.md §9.2): el allowlist ASCII
# original (`^[A-Za-z0-9][A-Za-z0-9._-]*$`) rechazaba ~70% de los 107 PDFs
# reales — títulos académicos reales llevan espacios, tildes, paréntesis,
# comas ("Adult appendicitis: Clinical practice guidelines...",
# "PLAN DE CUIDADO EN CASA..."). El filename nunca se usa para escribir un
# archivo real a disco ni se pasa a un shell (se guarda como texto en
# SQLite vía parámetro — `app/repositories/documents.py`); el riesgo real
# es más acotado que "cualquier carácter raro", así que se bloquean
# explícitamente los que sí importan: separadores de ruta (ya inalcanzables
# tras el basename de abajo, pero se listan por defensa en profundidad),
# caracteres de control/null, y los metacaracteres de shell clásicos —
# nunca vistos en los 107 nombres reales, así que no cuesta nada seguir
# bloqueándolos.
_DANGEROUS_CHARS = frozenset("/\\`$|<>;~") | {chr(i) for i in range(0x20)} | {chr(0x7F)}

# Puntuación vista en los 107 nombres de archivo reales del corpus oficial,
# más un margen razonable para lo que alguien suba manualmente desde la
# consola (comillas, corchetes, símbolos usuales en títulos). Los
# alfanuméricos Unicode (incluye tildes/ñ) se validan aparte con
# `str.isalnum()`, no están en este set.
_ALLOWED_EXTRA_PUNCTUATION = frozenset(" ._-(),+'’‘\"[]&%!?:‐‑≥≤")
_MAX_FILENAME_LENGTH = 255

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
    rechaza caracteres peligrosos en lo que queda — ver `_DANGEROUS_CHARS`/
    `_ALLOWED_EXTRA_PUNCTUATION` arriba para el porqué de un deny-list en
    vez de un allowlist ASCII."""
    # basename manual: corta en el último separador de cualquiera de los
    # dos estilos de ruta, sin depender de `os.path` (cuyo comportamiento
    # de separador varía por plataforma — aquí queremos la misma regla
    # determinista sin importar el SO donde corra el proceso).
    candidate = raw_filename.replace("\\", "/").split("/")[-1].strip()
    if not candidate or candidate in {".", ".."}:
        raise UploadRejected(
            "Nombre de archivo vacío o inválido tras sanear la ruta", code="invalid_filename"
        )
    if len(candidate) > _MAX_FILENAME_LENGTH:
        raise UploadRejected(
            f"Nombre de archivo demasiado largo ({len(candidate)} > {_MAX_FILENAME_LENGTH})",
            code="invalid_filename",
        )
    if any(char in _DANGEROUS_CHARS for char in candidate):
        raise UploadRejected(
            f"Nombre de archivo contiene caracteres no permitidos: {candidate!r}",
            code="invalid_filename",
        )
    if not all(char.isalnum() or char in _ALLOWED_EXTRA_PUNCTUATION for char in candidate):
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
    declarada, o `None` si no hay señal de falsificación.

    Dos direcciones de chequeo:
    - **txt/md**: nunca deberían empezar con ninguna firma binaria conocida
      (PDF/ZIP/ELF/PE/PNG/JPEG) — si empiezan, alguien renombró un binario.
    - **pdf**: al revés — SÍ debe empezar con la firma `%PDF-`; si no,
      alguien renombró otra cosa a `.pdf` (defensa simétrica a la anterior,
      spec.md §11 "no defaults inseguros")."""
    if extension == "pdf":
        return None if content.startswith(b"%PDF-") else "no-pdf-signature"
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
