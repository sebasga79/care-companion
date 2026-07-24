# Care Companion API — imagen de desarrollo/demo (REP-001).
FROM python:3.11-slim

RUN pip install --no-cache-dir uv==0.9.18

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

RUN mkdir -p /app/data

ENV DATABASE_PATH=/app/data/care_companion.db \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
