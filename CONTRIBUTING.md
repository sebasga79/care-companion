# CONTRIBUTING

> v0.1 · 23 de julio de 2026 · Ticket: PRE-013

Convenciones de Git para este repositorio. Ejecución individual (un solo desarrollador humano) asistida por herramientas de IA (Codex/Claude) bajo las reglas de `docs/spec.md` §11. El objetivo es que cada cambio sea rastreable a un ticket, un requisito y una evidencia — sin proceso de PR/revisión de equipo, pero con la misma disciplina.

## 1. Ramas

Formato:

```
tipo/TICKET-ID-descripcion-corta
```

- `tipo`: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `spike` (spikes desechables, ver §2.5 de `plan.md`).
- `TICKET-ID`: el identificador exacto del ticket en `plan.md` (ej. `RAG-005`, `PRE-013`, `SAFE-002`).
- `descripcion-corta`: kebab-case, en español o inglés técnico, sin acentos.

Ejemplos:

```
feat/RAG-005-retrieval-hibrido
fix/SAFE-003-reducer-no-degradable
docs/PRE-014-adr-template
spike/CH-007-voz-pipeline
```

Rama base: `main`. No se crean ramas de larga vida fuera de `main` y la rama de trabajo activa, salvo `POST-002` (branch post-submit, ver `plan.md` fase R).

## 2. Commits

### 2.1 Formato

```
TICKET-ID: descripción imperativa y concisa

Qué cambia: <una o dos líneas describiendo el cambio concreto>
Por qué: <una o dos líneas describiendo el motivo/requisito que lo origina>
```

- El asunto (primera línea) usa modo imperativo ("agrega", "corrige", "documenta"), no pasado ni gerundio.
- El asunto no excede ~72 caracteres.
- El cuerpo siempre distingue **qué** cambia de **por qué** cambia; no basta con repetir el asunto.
- Si el commit resulta de una decisión registrada en un ADR, referenciar el ADR en el cuerpo.

Ejemplo:

```
RAG-006: agrega umbral de abstención al evidence gate

Qué cambia: TriageAgent ahora abstiene la respuesta clínica cuando la
similitud máxima de recuperación cae bajo el umbral configurado.
Por qué: SAFE-001 exige que ninguna respuesta clínica se emita sin
evidencia aplicable (spec.md §11.2, "no responder sin evidencia activa").
```

### 2.2 Un ticket por commit

- Cada commit corresponde a exactamente un `TICKET-ID`. Si un cambio abarca trabajo de dos tickets, se separa en dos commits (o se decide cuál ticket es el dueño real del cambio y se ajusta el alcance).
- No se mezclan cambios de documentación de un ticket con implementación de otro en el mismo commit.
- Commits pequeños, por comportamiento verificable (regla de `plan.md` §2.5) — no un commit gigante al cerrar el ticket.

### 2.3 Checklist de self-review antes de comitear

Antes de ejecutar `git commit`, verificar:

- [ ] Los checks relevantes del ticket pasan (lint, type-check, tests, build según aplique).
- [ ] No hay secretos, tokens, claves ni credenciales en el diff (`git diff --staged`).
- [ ] No hay datos reales/identificables de pacientes ni material de terceros no autorizado.
- [ ] El diff toca solo archivos dentro del alcance del ticket — nada fuera de alcance quedó incluido por accidente.
- [ ] La documentación relevante (README, ADR, `spec.md`/`plan.md`/`architecture.md`, evidence ledger) está actualizada si el cambio la afecta.
- [ ] El mensaje de commit sigue el formato de §2.1 y referencia el `TICKET-ID` correcto.

### 2.4 Disclosure de asistencia de IA

Si un commit fue generado o asistido sustancialmente por un asistente de IA (Codex/Claude), se agrega una línea de coautoría al final del mensaje:

```
Co-Authored-By: <nombre del asistente> <noreply@anthropic.com>
```

Esto es obligatorio para mantener trazabilidad de qué cambios tuvieron asistencia de IA, requerido por la ficha del reto (disclosure de IA) y por `spec.md` §11.

## 3. Push y operaciones remotas

- No se hace `push --force` ni `push --force-with-lease` sin decisión humana explícita registrada (no basta con que el asistente de IA lo proponga).
- No se reescribe historial ya publicado (`rebase` sobre commits en el remoto, `commit --amend` sobre commits ya pusheados) sin decisión humana explícita.
- El asistente de IA no ejecuta `push` de forma autónoma salvo instrucción directa y explícita para esa operación puntual.
- Cualquier operación destructiva (`reset --hard`, `clean -f`, eliminar una rama) requiere confirmación humana previa, incluso en ramas de trabajo propias.

## 4. Relación con el ledger de evidencia

Todo commit relevante para un ticket en `Done` debe quedar referenciado (por `commit_sha`) en su entrada del evidence ledger (`docs/templates/evidence-ledger.md`, ver PRE-015). Un ticket no se marca `Done` sin un commit trazable, según la Definition of Done de `plan.md` §2.3.
