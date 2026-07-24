# Care Companion API

Backend del agente de voz postoperatorio Care Companion. Monolito modular
FastAPI + SQLite (WAL), sin ORM. Ver `../docs/architecture.md` y
`../docs/plan.md` (Sprint C1) para el diseño y el alcance de esta fase.

## Desarrollo local

```bash
cd api
uv sync --all-groups
cp .env.example .env   # editar si se necesita un valor distinto al default
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

O desde la raíz del repo: `make install && make dev`.

## Tests y lint

```bash
uv run pytest
uv run ruff check .
```

O desde la raíz: `make test`, `make lint`, `make verify` (lint + test).

## Estructura

```
app/
  core/          settings, logging, correlation_id, middleware
  domain/        modelos Pydantic, FSM del orquestador, reductor de decisión
  ports/         interfaces (LLM, STT, TTS, embeddings, casos del reto)
  adapters/      implementaciones (fakes deterministas + fixtures)
  repositories/  acceso a SQLite (WAL, transacciones cortas)
  api/           routers REST
  db/schema.sql  schema idempotente aplicado al arranque
```
