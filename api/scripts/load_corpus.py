#!/usr/bin/env python3
"""Carga el corpus clínico real del reto (`DATASET_DIR/textos/*/*.pdf`,
descargado por `fetch_dataset.py`) al RAG vía el mismo
`KnowledgeIngestionService` que usa la consola `/knowledge` — mismo
pipeline, mismas validaciones, misma transacción con canaria (RAG-002/
RAG-008), solo que en lote y sin pasar por HTTP.

Cada documento se etiqueta con `applicability={"procedure": <categoría>,
"source": "official_corpus"}`
según la carpeta de origen (mapeo confirmado inspeccionando
`perfiles_clinicos_pacientes_silver_contest.xlsx` — ver
docs/auditoria-kit-oficial-2026-08-07.md §9.2) para que
`CallCycleOrchestrator` pueda acotar el retrieval al procedimiento del
caso en curso, en vez de mezclar los 5 procedimientos del corpus.

Usa la MISMA `DATABASE_PATH`/`EMBEDDINGS_PROVIDER`/config que el backend
(vía `Settings`) — si tienes `EMBEDDINGS_PROVIDER=ollama` en tu `.env`,
este script también usa BGE-M3 real, no hace falta duplicar config.

Uso:
    uv run python scripts/load_corpus.py
    uv run python scripts/load_corpus.py --dataset-dir otra/ruta
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.adapters.local_hash_embeddings import LocalHashEmbeddings
from app.adapters.openai_compat_embeddings import OpenAICompatEmbeddings
from app.core.config import EmbeddingsProvider, Settings, get_settings
from app.repositories.db import apply_schema, get_connection
from app.repositories.documents import DocumentRepository
from app.services.embeddings_cache import EmbeddingsCache
from app.services.ingestion import (
    KnowledgeCanaryError,
    KnowledgeIngestionService,
    UploadRejected,
)

# Mapeo carpeta de `dataset/textos/` -> `procedure_category` (= modulo_synthea
# real del dataset, no el nombre de la carpeta — dos de las cinco carpetas
# tienen espacio en vez de guion bajo).
FOLDER_TO_PROCEDURE_CATEGORY = {
    "Appendicitis": "appendicitis",
    "breast_cancer": "breast_cancer",
    "cholecystitis": "cholecystitis",
    "colorectal cancer": "colorectal_cancer",
    "total joint replacement": "total_joint_replacement",
}

# Salida derivada y auditable del único PDF escaneado del kit. Se ingesta como
# texto, conservando el PDF original intacto en `textos/`.
OCR_TO_PROCEDURE_CATEGORY = {
    "appendicitis-literature-review-ocr.txt": "appendicitis",
}


def _build_embeddings_cache(settings: Settings) -> EmbeddingsCache:
    """Mismo criterio que `app/main.py::_build_embeddings_adapter` — se
    duplica aquí (no se importa `main.py`) para no arrastrar la app FastAPI
    completa a un script de batch."""
    if settings.embeddings_provider is EmbeddingsProvider.LOCAL_HASH:
        port = LocalHashEmbeddings(dimensions=settings.rag_embedding_dimensions)
    else:
        assert settings.embeddings_base_url is not None and settings.embeddings_model is not None
        port = OpenAICompatEmbeddings(
            base_url=settings.embeddings_base_url,
            api_key=settings.embeddings_api_key,
            model=settings.embeddings_model,
            provider_name=settings.embeddings_provider.value,
            timeout_seconds=settings.embeddings_request_timeout_seconds,
        )
    return EmbeddingsCache(port)


async def load_corpus(dataset_dir: Path, settings: Settings) -> None:
    conn = get_connection(settings.database_path)
    try:
        apply_schema(conn)
    finally:
        conn.close()

    embeddings_cache = _build_embeddings_cache(settings)
    document_repo = DocumentRepository(settings.database_path)
    ingestion = KnowledgeIngestionService(
        settings.database_path,
        embeddings_cache=embeddings_cache,
        settings=settings,
        document_repo=document_repo,
    )

    textos_dir = dataset_dir / "textos"
    if not textos_dir.is_dir():
        print(
            f"ERROR: no existe {textos_dir} — correr primero "
            "`uv run python scripts/fetch_dataset.py`.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ok = skipped = failed = 0
    for folder_name, category in FOLDER_TO_PROCEDURE_CATEGORY.items():
        folder = textos_dir / folder_name
        if not folder.is_dir():
            print(f"  ! carpeta no encontrada: {folder}")
            continue
        pdfs = sorted(folder.glob("*.pdf"))
        print(f"== {folder_name}/ ({category}) — {len(pdfs)} PDFs ==")
        for pdf_path in pdfs:
            try:
                result = await ingestion.learn(
                    raw_filename=pdf_path.name,
                    content=pdf_path.read_bytes(),
                    applicability={"procedure": category, "source": "official_corpus"},
                )
                ok += 1
                print(f"  ok: {pdf_path.name} ({result.chunk_count} chunks)")
            except UploadRejected as exc:
                # Esperado en 2 casos conocidos: duplicate_checksum (ya se
                # había cargado antes, correr el script de nuevo es
                # idempotente) y pdf_no_text_layer (el PDF escaneado de
                # Appendicitis/ sin capa de texto, documentado en el README
                # oficial del kit — no es un fallo del script).
                if exc.code == "duplicate_checksum":
                    skipped += 1
                    print(f"  skip (ya cargado): {pdf_path.name}")
                else:
                    failed += 1
                    print(f"  FALLÓ ({exc.code}): {pdf_path.name} — {exc.reason}")
            except KnowledgeCanaryError as exc:
                # Distinto de UploadRejected: la validación pasó pero la
                # consulta canaria no confirmó la carga dentro de la
                # transacción (RAG-008) — se revierte esa carga puntual
                # (rollback limpio, ver ingestion.py) y el lote sigue con
                # el resto en vez de abortar todo por un documento.
                failed += 1
                print(f"  FALLÓ (canary): {pdf_path.name} — {exc}")

    ocr_dir = dataset_dir / "ocr"
    for filename, category in OCR_TO_PROCEDURE_CATEGORY.items():
        txt_path = ocr_dir / filename
        if not txt_path.is_file():
            print(f"  ! OCR no encontrado: {txt_path}")
            continue
        try:
            result = await ingestion.learn(
                raw_filename=txt_path.name,
                content=txt_path.read_bytes(),
                applicability={"procedure": category, "source": "official_corpus"},
            )
            ok += 1
            print(f"  ok OCR: {txt_path.name} ({result.chunk_count} chunks)")
        except UploadRejected as exc:
            if exc.code == "duplicate_checksum":
                skipped += 1
                print(f"  skip OCR (ya cargado): {txt_path.name}")
            else:
                failed += 1
                print(f"  FALLÓ OCR ({exc.code}): {txt_path.name} — {exc.reason}")
        except KnowledgeCanaryError as exc:
            failed += 1
            print(f"  FALLÓ OCR (canary): {txt_path.name} — {exc}")

    print(f"\nListo — ok={ok} skip={skipped} fallidos={failed}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default=None, help="default: Settings.dataset_dir")
    args = parser.parse_args()

    settings = get_settings()
    dataset_dir = Path(args.dataset_dir) if args.dataset_dir else Path(settings.dataset_dir)
    asyncio.run(load_corpus(dataset_dir, settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
