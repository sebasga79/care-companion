# Plantilla — Architecture Decision Record (ADR)

> v0.1 · 23 de julio de 2026 · Ticket: PRE-014

Plantilla diseñada para completarse en menos de 10 minutos. Un ADR registra una decisión de arquitectura o de proceso relevante, no cada cambio pequeño. Se usa, por ejemplo, en CH-007 (pipeline de voz), RK-001 (delta ficha vs. SDD) o cualquier decisión que contradiga o reemplace una decisión anterior.

Copiar este archivo a `docs/adr/ADR-<NNN>-<slug>.md` (numeración secuencial, tres dígitos) al momento de tomar la decisión.

---

## ADR-XXX: <Título corto de la decisión>

- **Fecha:** AAAA-MM-DD
- **Estado:** propuesto | aceptado | reemplazado (por ADR-YYY)
- **Ticket relacionado:** <TICKET-ID>

### Contexto

<2 a 4 líneas: qué problema u obligación fuerza esta decisión, qué restricción de la ficha/spec/plan aplica. Sin relleno.>

### Opciones consideradas

| Opción | Pros | Contras |
|---|---|---|
| Opción A | | |
| Opción B | | |
| Opción C (si aplica) | | |

### Decisión

<Qué opción se eligió, en una o dos líneas. Debe ser accionable, no ambigua.>

### Consecuencias / riesgos

<Qué se gana, qué se sacrifica, qué riesgo queda abierto y quién lo monitorea (ver `plan.md` §13 registro de riesgos si aplica).>

### Fecha de revisión

<Cuándo se debe reconsiderar esta decisión — fecha fija o disparador ("si el volumen de datos supera X").>

---

## Ejemplo mínimo diligenciado (ficticio, no clínico)

## ADR-000: Formato de almacenamiento de logs de sesión local

- **Fecha:** 2026-07-23
- **Estado:** aceptado
- **Ticket relacionado:** PRE-014 (ejemplo ilustrativo, no ticket real de producto)

### Contexto

Durante los ensayos de PRE-020 necesitamos guardar logs de sesiones de prueba desechables en disco local sin depender de infraestructura externa, y sin acoplar el formato a un motor de base de datos específico todavía.

### Opciones consideradas

| Opción | Pros | Contras |
|---|---|---|
| JSON Lines (`.jsonl`) | Simple, streamable, legible línea por línea, fácil de grep | Sin schema fuerte por defecto |
| SQLite | Consultable con SQL, transaccional | Requiere migraciones para un log desechable de ensayo |
| CSV | Universal, abre en cualquier hoja de cálculo | Mal manejo de campos anidados/listas |

### Decisión

Usar JSON Lines (`.jsonl`) para logs de sesiones de ensayo desechables, con un objeto por línea y validación ligera vía Pydantic al leer.

### Consecuencias / riesgos

Ganamos velocidad de iteración y legibilidad en grep/diff. Sacrificamos consultas relacionales complejas — aceptable porque estos logs son desechables (Sprint P2) y no son la fuente de verdad del esquema operacional (eso lo define DB-001 en Sprint C1). Riesgo: si el volumen crece y se vuelve necesario consultar por rango o join, migrar a SQLite antes de C1.

### Fecha de revisión

Antes de iniciar Sprint C1 (T+2h), o antes si el volumen de logs de ensayo supera lo manejable con grep.
