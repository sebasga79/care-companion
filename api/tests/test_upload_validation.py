"""RAG-002 — validación de carga: tests negativos (malicioso, oversize,
duplicado, MIME falso) + camino feliz."""

from __future__ import annotations

import pytest

from app.services.upload_validation import UploadRejected, sanitize_filename, validate_upload

_ALLOWED = frozenset({"txt", "md"})


def test_valid_txt_upload_passes() -> None:
    result = validate_upload(
        raw_filename="guia.txt",
        content=b"contenido de prueba",
        allowed_extensions=_ALLOWED,
        max_bytes=1000,
        existing_active_checksums=frozenset(),
    )
    assert result.safe_filename == "guia.txt"
    assert result.extension == "txt"
    assert len(result.checksum) == 64  # sha256 hex


@pytest.mark.parametrize(
    "real_filename",
    [
        # Nombres reales del corpus oficial del reto (dataset/textos/) —
        # regresión directa: el allowlist ASCII original (`^[A-Za-z0-9]
        # [A-Za-z0-9._-]*$`) rechazaba estos, ~70% del corpus real, antes de
        # la corrección (docs/auditoria-kit-oficial-2026-08-07.md §9.2).
        "Adult appendicitis- Clinical practice guidelines from the French Society.txt",
        "PLAN DE CUIDADO EN CASA DE PACIENTE EN POSTOPERATORIO DE APENDICECTOMÍA.txt",
        "Epidemiología de la apendicitis aguda en Colombia.txt",
        "Acute Care Surgery Comprehensive Recovery Guide (Appendectomy).txt",
        "diagnóstico, tratamiento y seguimiento del paciente.txt",
        "Postoperative Infections After Appendectomy_ The Surgeon’s Checklist.txt",
        "Niveles de dolor, rigidez y funcionalidad (2023).txt",
        "Total Hip Arthroplasty in Patients with BMI ≥ 30 kg_m2.txt",
    ],
)
def test_sanitize_filename_accepts_real_academic_titles(real_filename: str) -> None:
    assert sanitize_filename(real_filename) == real_filename


@pytest.mark.parametrize(
    "raw_filename",
    [
        "../../etc/passwd.txt",
        "..\\..\\windows\\win.ini.txt",
        "/etc/passwd.txt",
        "a/b/../../c.txt",
    ],
)
def test_path_traversal_filenames_are_sanitized_or_rejected(raw_filename: str) -> None:
    # El basename resultante no debe contener separadores de ruta ni poder
    # escapar del directorio de destino, sin importar cuántos ".." tenga.
    safe = sanitize_filename(raw_filename)
    assert "/" not in safe
    assert "\\" not in safe
    assert ".." not in safe


def test_upload_rejects_malicious_filename_with_bad_characters() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="../../etc/passwd",  # sin extensión tras basename -> distinto motivo
            content=b"x",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code in {"invalid_filename", "missing_extension"}


def test_upload_rejects_filename_with_shell_metacharacters() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="evil;rm -rf ~.txt",
            content=b"x",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "invalid_filename"


def test_upload_rejects_oversize_file() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="grande.txt",
            content=b"x" * 2000,
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "file_too_large"


def test_upload_rejects_empty_file() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="vacio.txt",
            content=b"",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "empty_file"


def test_upload_rejects_duplicate_checksum() -> None:
    content = b"contenido identico"
    import hashlib

    checksum = hashlib.sha256(content).hexdigest()
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="dup.txt",
            content=content,
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset({checksum}),
        )
    assert exc_info.value.code == "duplicate_checksum"


def test_upload_rejects_disallowed_extension() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="script.exe",
            content=b"MZ" + b"\x00" * 20,
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "extension_not_allowed"


def test_upload_rejects_pdf_when_not_in_allowed_extensions() -> None:
    # `_ALLOWED` en este archivo es txt/md deliberadamente (no toda la
    # allowlist real) para seguir probando el rechazo por extensión no
    # permitida como caso independiente del soporte de PDF en sí.
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="informe.pdf",
            content=b"%PDF-1.4 contenido",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "extension_not_allowed"


def test_valid_pdf_upload_passes_validation() -> None:
    """La validación de bytes/tamaño/tipo pasa para un PDF real; la
    extracción de texto (RAG-002 ampliado) es responsabilidad de
    `app/services/pdf_extraction.py`, no de esta capa."""
    result = validate_upload(
        raw_filename="guia.pdf",
        content=b"%PDF-1.4\ncontenido binario simulado de un PDF real",
        allowed_extensions=frozenset({"txt", "md", "pdf"}),
        max_bytes=1000,
        existing_active_checksums=frozenset(),
    )
    assert result.extension == "pdf"


def test_upload_rejects_fake_pdf_disguised_as_pdf() -> None:
    """Extensión .pdf pero los bytes no empiezan con la firma real de PDF
    (`%PDF-`) — rechazo simétrico al caso txt/md con MIME falso."""
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="falso.pdf",
            content=b"esto no es un PDF de verdad",
            allowed_extensions=frozenset({"txt", "md", "pdf"}),
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "mime_mismatch"


def test_upload_rejects_fake_mime_pdf_disguised_as_txt() -> None:
    """Extensión .txt pero bytes iniciales son la firma real de un PDF —
    debe rechazarse por MIME falso, no aceptarse como texto plano."""
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="no_es_texto.txt",
            content=b"%PDF-1.7\n%\xe2\xe3\xcf\xd3 contenido binario simulado",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "mime_mismatch"


def test_upload_rejects_fake_mime_zip_disguised_as_md() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="oculto.md",
            content=b"PK\x03\x04" + b"\x00" * 30,
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "mime_mismatch"


def test_upload_rejects_empty_filename_after_sanitization() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="../",
            content=b"x",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "invalid_filename"


def test_upload_rejects_missing_extension() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        validate_upload(
            raw_filename="sin_extension",
            content=b"x",
            allowed_extensions=_ALLOWED,
            max_bytes=1000,
            existing_active_checksums=frozenset(),
        )
    assert exc_info.value.code == "missing_extension"


def test_sanitize_filename_rejects_excessively_long_name() -> None:
    with pytest.raises(UploadRejected) as exc_info:
        sanitize_filename("a" * 300 + ".txt")
    assert exc_info.value.code == "invalid_filename"
