#!/usr/bin/env python3
"""Descarga el dataset oficial del reto (`TechSphere2026/ParticipantArtifacts`)
a `DATASET_DIR` (default `./data/dataset`, gitignored — nunca se commitea).

No es Delta Share (la construcción anticipada lo asumió; el reto real
entrega 4 `.xlsx` + 107 PDFs dentro del propio repo de GitHub del kit — ver
docs/auditoria-kit-oficial-2026-08-07.md §4.2/§9.2). Este script es la
única forma prevista de poblar `DatasetCaseAdapter`
(`app/adapters/dataset_case_source.py`) y el corpus RAG real.

Uso:
    uv run python scripts/fetch_dataset.py                # todo (xlsx + 107 PDFs)
    uv run python scripts/fetch_dataset.py --no-textos     # solo los 4 xlsx (rápido)
    uv run python scripts/fetch_dataset.py --dest otra/ruta

Idempotente: si un archivo ya existe con el mismo tamaño reportado por
GitHub, no se vuelve a descargar (`--force` lo ignora). Usa la API pública
de contenidos de GitHub para listar (sin autenticar; 60 req/hora es de
sobra — son ~10 listados, no 107) y descarga cada blob desde su
`download_url` (CDN de `raw.githubusercontent.com`, no cuenta contra ese
límite)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

DEFAULT_REPO = "TechSphere2026/ParticipantArtifacts"
API_BASE = "https://api.github.com/repos"

DATASET_XLSX_FILES = (
    "dataset_final.xlsx",
    "trayectorias_postop_silver.xlsx",
    "perfiles_clinicos_pacientes_silver_contest.xlsx",
    "perfiles_pacientes_co.xlsx",
)

# Confirmado inspeccionando el repo oficial (docs/auditoria-kit-oficial-
# 2026-08-07.md §9.2): 5 carpetas, 107 PDFs en total, dos con espacio en
# el nombre.
TEXTOS_FOLDERS = (
    "Appendicitis",
    "breast_cancer",
    "cholecystitis",
    "colorectal cancer",
    "total joint replacement",
)


def _list_dir(client: httpx.Client, repo: str, path: str) -> list[dict]:
    response = client.get(f"{API_BASE}/{repo}/contents/{path}")
    response.raise_for_status()
    return response.json()


def _download_file(
    client: httpx.Client, *, download_url: str, dest: Path, expected_size: int, force: bool
) -> str:
    if not force and dest.is_file() and dest.stat().st_size == expected_size:
        return "skip (ya existe)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = client.get(download_url)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return f"ok ({len(response.content)} bytes)"


def fetch_xlsx(client: httpx.Client, *, repo: str, dest_dir: Path, force: bool) -> None:
    print("== .xlsx (dataset_final, trayectorias, perfiles) ==")
    items = {item["name"]: item for item in _list_dir(client, repo, "dataset")}
    for filename in DATASET_XLSX_FILES:
        item = items.get(filename)
        if item is None:
            print(f"  ! {filename}: no encontrado en el repo oficial (¿cambió el kit?)")
            continue
        status = _download_file(
            client,
            download_url=item["download_url"],
            dest=dest_dir / filename,
            expected_size=item["size"],
            force=force,
        )
        print(f"  {filename}: {status}")


def fetch_textos(client: httpx.Client, *, repo: str, dest_dir: Path, force: bool) -> None:
    print("== dataset/textos/ (corpus clínico PDF) ==")
    total = 0
    for folder in TEXTOS_FOLDERS:
        items = _list_dir(client, repo, f"dataset/textos/{folder}")
        pdf_items = [item for item in items if item["type"] == "file"]
        print(f"  {folder}/ ({len(pdf_items)} archivos)")
        for item in pdf_items:
            status = _download_file(
                client,
                download_url=item["download_url"],
                dest=dest_dir / "textos" / folder / item["name"],
                expected_size=item["size"],
                force=force,
            )
            total += 1
            print(f"    {item['name']}: {status}")
    print(f"  total: {total} PDFs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"default: {DEFAULT_REPO}")
    parser.add_argument("--dest", default="./data/dataset", help="default: ./data/dataset")
    parser.add_argument(
        "--no-textos", action="store_true", help="omite los 107 PDFs (solo los 4 xlsx)"
    )
    parser.add_argument(
        "--force", action="store_true", help="redescarga aunque el archivo ya exista"
    )
    args = parser.parse_args()

    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        try:
            fetch_xlsx(client, repo=args.repo, dest_dir=dest_dir, force=args.force)
            if not args.no_textos:
                fetch_textos(client, repo=args.repo, dest_dir=dest_dir, force=args.force)
        except httpx.HTTPStatusError as exc:
            print(f"ERROR: {exc.request.url} -> HTTP {exc.response.status_code}", file=sys.stderr)
            return 1

    print(f"\nListo — dataset en {dest_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
