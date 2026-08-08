#!/usr/bin/env python3
"""Marca como protegido el corpus oficial ya indexado en una base persistente.

El bootstrap anterior no guardaba el origen en ``applicability``. Este paso de
migración compara checksums contra los archivos oficiales del volumen y añade
``source=official_corpus`` sin reindexar ni cambiar la versión de conocimiento.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.core.config import get_settings
from app.repositories.db import session_scope


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mark_official_corpus(dataset_dir: Path, database_path: str) -> int:
    files = sorted((dataset_dir / "textos").glob("**/*.pdf"))
    files.extend(sorted((dataset_dir / "ocr").glob("*.txt")))
    checksums = {_checksum(path) for path in files if path.is_file()}
    updated = 0

    with session_scope(database_path) as conn:
        for row in conn.execute(
            "SELECT id, checksum, applicability FROM documents WHERE status != 'deleted'"
        ).fetchall():
            if row["checksum"] not in checksums:
                continue
            try:
                applicability = json.loads(row["applicability"] or "{}")
            except json.JSONDecodeError:
                applicability = {}
            if applicability.get("source") == "official_corpus":
                continue
            applicability["source"] = "official_corpus"
            conn.execute(
                "UPDATE documents SET applicability = ? WHERE id = ?",
                (json.dumps(applicability), row["id"]),
            )
            updated += 1

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default=None)
    args = parser.parse_args()
    settings = get_settings()
    dataset_dir = Path(args.dataset_dir or settings.dataset_dir)
    updated = mark_official_corpus(dataset_dir, settings.database_path)
    print(f"[bootstrap] Corpus oficial protegido: {updated} documento(s) actualizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
