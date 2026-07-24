# ADR-001 — Construcción anticipada de la solución antes de T0

> v1.0 · 23 de julio de 2026 · Estado: **aceptado** · Decisor: SG (propietario)

## Contexto

El plan original (PRE-037) establecía stop-work de código de solución hasta T0 (7 de agosto) para preservar equidad de arranque. El propietario decidió el 23 de julio iniciar la construcción real de Care Companion de inmediato, priorizando velocidad y ensayo sobre la interpretación estricta del stop-work. La ficha técnica (modelo obligatorio, dataset Delta Share, starter, métricas) sigue sin publicarse.

## Opciones consideradas

1. **Solo docs hasta T0** — máxima equidad; cero ensayo de construcción. Descartada por el propietario.
2. **Ensayo desechable (PRE-020)** — slice toy en carpeta separada. Descartada por el propietario.
3. **Construir la solución ya** — riesgo de rework en T0; ventaja de llegar con base construida y ensayada. **Elegida.**

## Decisión

Se construye la solución real desde el 23 de julio, con estas reglas de mitigación obligatorias:

- **Puertos/adaptadores estrictos** para LLM, STT, TTS, embeddings y fuente de casos (`ChallengeCasePort`). Ninguna lógica de dominio importa SDKs de proveedor directamente.
- El adapter LLM activo antes de T0 es **provisional y configurable** (se reemplaza por el modelo obligatorio en CH-006/AI-001 sin tocar dominio).
- La fuente de casos usa **fixtures sintéticos propios** (docs/fixtures/) hasta que exista el Delta Share real (DATA-001).
- Si el starter oficial impone estructura, **su estructura prevalece** y este código se adapta o descarta por módulos (regla ya presente en CLAUDE.md).
- Las reglas de seguridad clínica de spec.md §11 aplican desde la primera línea de código.

## Consecuencias y riesgos

- RK-001 (ficha contradice SDD) sube de probabilidad: se acepta; respuesta sigue siendo ADR delta + replan en T0.
- PRE-037 y `docs/t0/stop-work-note.md` quedan **Superseded** por esta decisión.
- El cumplimiento de las reglas del concurso sobre trabajo previo es responsabilidad del propietario; el equipo técnico deja constancia de la decisión aquí.

## Revisión

En T0 (7 de agosto): confrontar cada adapter con la ficha real y registrar el delta en CH-008.
