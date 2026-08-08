#!/usr/bin/env python3
"""Genera texto OCR para un PDF escaneado del kit oficial.

Usa Poppler para rasterizar páginas y Tesseract para reconocerlas. El archivo
de salida es texto plano, no reemplaza ni modifica el PDF original. Es
idempotente: si el destino ya tiene contenido, no vuelve a procesarlo.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def _ocr_language(tesseract: str, requested: str | None) -> str:
    if requested:
        return requested
    result = subprocess.run(  # noqa: S603 - fixed executable and argument list
        [tesseract, "--list-langs"], capture_output=True, text=True, check=True
    )
    languages = set(result.stdout.splitlines())
    if "spa" in languages and "eng" in languages:
        return "spa+eng"
    if "spa" in languages:
        return "spa"
    if "eng" in languages:
        print("WARN: idioma spa no instalado; OCR continuará con eng", file=sys.stderr)
        return "eng"
    raise RuntimeError("Tesseract no tiene instalado spa ni eng")


def ocr_pdf(input_pdf: Path, output_txt: Path, *, language: str | None = None) -> int:
    if not input_pdf.is_file():
        raise FileNotFoundError(input_pdf)
    if output_txt.is_file() and output_txt.stat().st_size > 0:
        print(f"OCR skip (ya existe): {output_txt}")
        return 0

    tesseract = "tesseract"
    pdftoppm = "pdftoppm"
    selected_language = _ocr_language(tesseract, language)
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="care-companion-ocr-") as temp_dir:
        prefix = Path(temp_dir) / "page"
        subprocess.run(  # noqa: S603 - fixed executable and argument list
            [pdftoppm, "-r", "220", "-png", str(input_pdf), str(prefix)],
            check=True,
            capture_output=True,
            text=True,
        )
        pages = sorted(Path(temp_dir).glob("page-*.png"))
        if not pages:
            raise RuntimeError(f"Poppler no produjo páginas para {input_pdf}")

        text_pages: list[str] = []
        for page in pages:
            result = subprocess.run(  # noqa: S603 - fixed executable and argument list
                [tesseract, str(page), "stdout", "-l", selected_language, "--psm", "3"],
                check=True,
                capture_output=True,
                text=True,
            )
            text_pages.append(result.stdout.strip())

    text = "\n\n".join(page for page in text_pages if page).strip()
    if not text:
        raise RuntimeError(f"OCR no produjo texto para {input_pdf}")
    output_txt.write_text(text + "\n", encoding="utf-8")
    print(f"OCR ok: {input_pdf.name} -> {output_txt} ({len(text)} caracteres)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--language", default=None, help="por ejemplo: spa+eng")
    args = parser.parse_args()
    try:
        return ocr_pdf(args.input, args.output, language=args.language)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR OCR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
