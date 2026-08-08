# Care Companion API — imagen de desarrollo/demo (REP-001).
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-spa \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.9.18

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
# Instala primero dependencias para conservar esta capa cuando solo cambia
# el código. El proyecto editable requiere README.md y el paquete `app`, que
# se incorporan en etapas separadas.
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

RUN mkdir -p /app/data
RUN chmod +x /app/scripts/docker_entrypoint.sh

ENV DATABASE_PATH=/app/data/care_companion.db \
    DATASET_DIR=/app/data/dataset \
    RAG_ALLOW_EMPTY_PDF_PASSWORD=true \
    BOOTSTRAP_OFFICIAL_DATASET=true \
    BOOTSTRAP_OFFICIAL_CORPUS=true \
    BOOTSTRAP_OFFICIAL_OCR=true \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
