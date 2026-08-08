#!/bin/sh
# Primer arranque Docker: descarga el kit oficial al volumen persistente e
# indexa el corpus clínico antes de exponer la API. Los reinicios posteriores
# reutilizan archivos, base y marcador; no vuelven a descargar ni a indexar.

set -eu

DATASET_DIR="${DATASET_DIR:-/app/data/dataset}"
DATABASE_PATH="${DATABASE_PATH:-/app/data/care_companion.db}"
DATA_DIR="$(dirname "$DATABASE_PATH")"
CORPUS_MARKER="$DATA_DIR/.official_corpus_v2.loaded"
EXPECTED_PDF_COUNT=107
SCANNED_PDF="$DATASET_DIR/textos/Appendicitis/REVISIÓN DE LA LITERATURA SOBRE LAAPENDICITIS AGUDA PEDIATRICA NO ESPECIFICADA EN EL PERI000 2000-2021.pdf"
OCR_TEXT="$DATASET_DIR/ocr/appendicitis-literature-review-ocr.txt"

is_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

dataset_is_complete() {
  for filename in \
    dataset_final.xlsx \
    trayectorias_postop_silver.xlsx \
    perfiles_clinicos_pacientes_silver_contest.xlsx \
    perfiles_pacientes_co.xlsx
  do
    [ -s "$DATASET_DIR/$filename" ] || return 1
  done

  pdf_count="$(find "$DATASET_DIR/textos" -type f -name '*.pdf' 2>/dev/null | wc -l | tr -d ' ')"
  [ "$pdf_count" -ge "$EXPECTED_PDF_COUNT" ]
}

mkdir -p "$DATASET_DIR" "$DATA_DIR"

if is_enabled "${BOOTSTRAP_OFFICIAL_DATASET:-true}"; then
  if dataset_is_complete; then
    echo "[bootstrap] Dataset oficial completo; se reutiliza el volumen Docker."
  else
    echo "[bootstrap] Primera ejecución: descargando 4 XLSX y 107 PDF del kit oficial..."
    uv run --no-sync python scripts/fetch_dataset.py --dest "$DATASET_DIR"

    if ! dataset_is_complete; then
      echo "[bootstrap] ERROR: la descarga terminó, pero el dataset oficial está incompleto." >&2
      exit 1
    fi
    echo "[bootstrap] Dataset oficial descargado y validado."
  fi
else
  echo "[bootstrap] Descarga automática desactivada (BOOTSTRAP_OFFICIAL_DATASET=false)."
fi

if is_enabled "${BOOTSTRAP_OFFICIAL_CORPUS:-true}"; then
  if [ -f "$CORPUS_MARKER" ] && [ -f "$DATABASE_PATH" ]; then
    echo "[bootstrap] Corpus oficial ya indexado; se reutiliza la base persistente."
  else
    if ! dataset_is_complete; then
      echo "[bootstrap] ERROR: no se puede indexar el corpus sin el kit oficial completo." >&2
      exit 1
    fi
    if is_enabled "${BOOTSTRAP_OFFICIAL_OCR:-true}"; then
      echo "[bootstrap] Ejecutando OCR del PDF escaneado del kit..."
      uv run --no-sync python scripts/ocr_scanned_pdf.py \
        --input "$SCANNED_PDF" \
        --output "$OCR_TEXT"
    else
      echo "[bootstrap] OCR automático desactivado (BOOTSTRAP_OFFICIAL_OCR=false)."
    fi
    echo "[bootstrap] Indexando el corpus clínico oficial por primera vez..."
    uv run --no-sync python scripts/load_corpus.py --dataset-dir "$DATASET_DIR"
    printf '%s\n' "loaded_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$CORPUS_MARKER"
    echo "[bootstrap] Corpus oficial indexado; los próximos arranques lo reutilizarán."
  fi
else
  echo "[bootstrap] Indexación automática desactivada (BOOTSTRAP_OFFICIAL_CORPUS=false)."
fi

if dataset_is_complete && [ -f "$DATABASE_PATH" ]; then
  uv run --no-sync python scripts/mark_official_corpus.py --dataset-dir "$DATASET_DIR"
fi

exec "$@"
