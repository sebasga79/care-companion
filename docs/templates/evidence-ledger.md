# Plantilla — Evidence Ledger

> v0.1 · 23 de julio de 2026 · Ticket: PRE-015

Estructura para registrar la evidencia de cada ticket, en el formato exacto del schema definido en `docs/plan.md` §2.4. Cada ticket que llega a `Done` (o a un estado terminal como `Descoped`/`Superseded`) debe tener una entrada de ledger completa.

## 1. Schema (idéntico a `plan.md` §2.4)

Cada ticket conserva un bloque YAML con exactamente estos campos:

```yaml
ticket_id:
status:
started_at:
completed_at:
commit_sha:
requirements:
tests:
artifacts:
metrics_before:
metrics_after:
decisions:
risks:
review_notes:
```

Notas de uso por campo:

- `ticket_id`: el identificador exacto del ticket (ej. `RAG-006`).
- `status`: uno de los estados definidos en `plan.md` §2.1 (`Backlog`, `Ready`, `In progress`, `In review`, `Verified`, `Done`, `Blocked`, `Descoped`, `Superseded`).
- `started_at` / `completed_at`: timestamps ISO 8601.
- `commit_sha`: SHA(s) del/los commit(s) que implementan el ticket (ver CONTRIBUTING.md §4).
- `requirements`: lista de IDs de requisito/criterio de rúbrica que este ticket satisface (referenciar `docs/traceability.md`).
- `tests`: lista de tests/checks ejecutados y su resultado.
- `artifacts`: rutas a capturas, logs, videos, exports relacionados con este ticket.
- `metrics_before` / `metrics_after`: métricas relevantes antes/después del cambio, si aplica (ej. latencia, cobertura, tamaño de instalación).
- `decisions`: referencias a ADRs relacionados (ej. `ADR-007`).
- `risks`: riesgos abiertos o mitigados, referenciando `plan.md` §13 si aplica.
- `review_notes`: notas de la auto-revisión o de la verificación final.

## 2. Ejemplo de entrada completada (ficticio)

```yaml
ticket_id: PRE-014
status: Done
started_at: 2026-07-23T15:00:00-05:00
completed_at: 2026-07-23T15:20:00-05:00
commit_sha: 0000000000000000000000000000000000000a
requirements:
  - "Repo/proceso 15: ADR presente"
tests:
  - "revisión manual: plantilla completable en <10 min"
artifacts:
  - docs/evidence/PRE-014/adr-template-review-2026-07-23.md
metrics_before: null
metrics_after: null
decisions:
  - ADR-000 (ejemplo ilustrativo)
risks: []
review_notes: "Plantilla validada con un ADR ficticio de ejemplo; sin bloqueos."
```

## 3. Convención de carpetas

```
docs/evidence/<TICKET-ID>/
```

Una carpeta por ticket, en mayúsculas y con el ID exacto tal como aparece en `plan.md` (ej. `docs/evidence/RAG-006/`, `docs/evidence/PRE-011/`). Dentro de cada carpeta:

- capturas de pantalla,
- logs de ejecución (texto plano o `.jsonl`),
- métricas (`.json`/`.csv`/tabla en Markdown),
- el bloque YAML de la entrada del ledger para ese ticket, si se guarda por separado del archivo consolidado.

## 4. Nomenclatura de archivos

```
<tipo>-<descripcion-corta>-<AAAA-MM-DD>.<ext>
```

Ejemplos:

```
docs/evidence/PRE-011/clean-install-log-2026-07-25.md
docs/evidence/RAG-009/deletion-e2e-2026-08-14.jsonl
docs/evidence/SAFE-001/critical-branches-report-2026-08-13.md
docs/evidence/FIN-002/clean-room-final-2026-09-04.mp4
```

- `tipo`: sustantivo corto que identifica el artefacto (`clean-install-log`, `deletion-e2e`, `latency-trace`, `screenshot`).
- `descripcion-corta`: kebab-case, sin acentos.
- Fecha en formato `AAAA-MM-DD`, siempre la fecha de captura de la evidencia, no la fecha de commit.

## 5. Reglas

- Toda evidencia debe llevar fecha, ticket asociado (por ruta de carpeta) y `commit_sha` correspondiente (en el nombre del archivo, en el contenido, o en la entrada de ledger que la referencia).
- Ninguna evidencia contiene secretos, tokens, credenciales, ni datos reales/identificables de pacientes (PHI). Ver `docs/policies` y `spec.md` §11.2.
- Ninguna evidencia contiene chain-of-thought de un modelo (razonamiento interno crudo) — solo outputs, resúmenes estructurados, métricas y trazas de auditoría (`correlation_id`, `knowledge_version`, fuentes, usage), conforme a `spec.md` §11.2.
- Si una evidencia se genera y luego se descubre que contiene información prohibida, se elimina del working tree y del historial de Git (no basta con un commit que la borre) y se registra el incidente en `risks`/`review_notes`.
- La entrada de ledger de un ticket se completa al pasar a `Verified`/`Done`, no se retrasa para "después".
