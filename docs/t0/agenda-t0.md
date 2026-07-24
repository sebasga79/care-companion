# Agenda T0 — Primeros 120–160 minutos del concurso

> v0.1 · 23 de julio de 2026 · Ticket: PRE-031

## 0. Cómo usar esta agenda

Esta agenda mapea el Sprint **C0 — Intake & Constraint Freeze** (`plan.md` §5, tickets CH-001…CH-010) a bloques de tiempo consecutivos desde `T0` (inicio oficial del concurso, hora/zona pendiente de la ficha técnica — no se adivina, ver `plan.md` línea 99). No se ejecuta ni se decide nada aquí: es la plantilla que se llena en vivo el 7 de agosto.

**Nota de discrepancia (no resuelta a propósito):** la etiqueta del sprint en `plan.md` §3 dice `C0 Intake | T0–T+2h`, pero la suma de los timeboxes exactos de CH-001…CH-010 (columna "Timebox" de `plan.md` §5) da **160 minutos (2h 40m)**, no 120. Esta agenda usa los timeboxes exactos del plan, tal como pide el ticket, y dedica esta nota a exponer la diferencia en vez de ajustarla en silencio. La decisión de cómo cerrar esa brecha (comprimir tareas, paralelizar donde sea seguro, o aceptar que C0 dure ~2h40m) se toma en T0 con información real de la ficha, no antes.

## 1. Checklist previo a T0 (antes de que arranque el cronómetro)

A ejecutar en las horas/minutos inmediatamente anteriores a T0, con el reto ya accesible:

- [ ] **Correo:** confirmar que la bandeja de entrada (y spam) del correo de registro está monitoreada activamente; tener el correo de recepción de la ficha abierto y visible.
- [ ] **Descarga:** verificar ancho de banda y espacio en disco suficientes para starter + dataset; tener carpeta de destino ya creada y vacía (`material-original/` o equivalente, fuera del árbol que se publica).
- [ ] **Checksums:** tener listo el mecanismo para calcular SHA-256 de cada archivo recibido (starter, ficha, dataset si aplica) antes de abrirlo o modificarlo, para poder demostrar procedencia (insumo directo de CH-001).
- [ ] Estación de trabajo, Git/GitHub, navegador, micrófono y cámara ya verificados (PRE-010, ejecutado en Sprint P1 — esto solo se re-confirma, no se repite completo).
- [ ] Gestor de secretos y `.env.example` template listos (PRE-012).
- [ ] Plantilla de evidencia por ticket (`plan.md` §2.4) abierta y lista para llenarse en tiempo real.
- [ ] Cronómetro/registro de tiempo iniciado en `T0` exacto según la ficha (no antes).

## 2. Regla de agotamiento de timebox

Aplica a **cada** ticket CH-001…CH-010, tomada directamente de `plan.md` §2.5:

> "Si un spike no concluye en su timebox, se adopta la opción más simple que cumpla."

Operacionalmente: al llegar al minuto límite de un ticket sin cerrar su criterio de aceptación, se detiene el trabajo en ese ticket, se registra el estado real (parcial/bloqueado) en la evidencia del ticket, se adopta la opción más simple disponible que satisfaga el criterio mínimo, y se avanza al siguiente ticket. No se extiende un timebox a costa de los siguientes — el orden de los tickets y el exit gate C0 tienen prioridad sobre la perfección de un ticket individual.

## 3. Agenda minuto a minuto (T0 → T+160m)

| Bloque | Ticket | Timebox | Ventana (offset desde T0) | Tarea (resumen de `plan.md`) | Aceptación / evidencia |
|---|---|---:|---|---|---|
| 1 | CH-001 Preservar material original | 10m | T+0 → T+10 | Guardar starter/ficha/checksums/links; registrar recepción | Fuente original identificable |
| 2 | CH-002 Leer ficha completa | 25m | T+10 → T+35 | Modelo, gates, métricas, deadline, stack permitido, disclosure IA | Checklist sin campos vacíos |
| 3 | CH-003 Revisar licencias/uso de datos | 15m | T+35 → T+50 | Starter, dataset, documentos, credenciales y salida pública | Decisión de qué puede versionarse |
| 4 | CH-004 Inspeccionar repo base | 15m | T+50 → T+65 | Estructura, scripts, tests, Docker, constraints | Inventory y gaps |
| 5 | CH-005 Perfilar Delta Share | 20m | T+65 → T+85 | Schema, volumen, tipos, nulls, ejemplos autorizados | `data-contract.md`/schema snapshot |
| 6 | CH-006 Validar modelo obligatorio | 15m | T+85 → T+100 | Endpoint, SDK, output estructurado, streaming, límites, costo | Smoke trace con model id |
| 7 | CH-007 Elegir pipeline de voz | 25m | T+100 → T+125 | Spike mínimo de opciones; medir primer audio y barge-in posible (usar `docs/t0/voice-decision-scorecard.md`) | ADR-007 |
| 8 | CH-008 Delta de requisitos | 15m | T+125 → T+140 | Actualizar spec/architecture/plan; crear tickets nuevos; resolver FR-004 (consentimiento) | v1.0 sin supuestos críticos; FR-004 con ticket o descope registrado |
| 9 | CH-009 Congelar alcance P0/P1/P2 | 10m | T+140 → T+150 | MoSCoW, cutline y exclusiones | Backlog ordenado |
| 10 | CH-010 Baseline repo | 10m | T+150 → T+160 | Licencia/branch/initial checks según reglas | Commit inicial trazable |

**Nota sobre CH-007:** `architecture.md` §10.2 describe un "spike de 90 minutos" para decidir voz, pero el timebox oficial de CH-007 en `plan.md` es de 25 minutos. Esta agenda respeta el timebox oficial (25m) como límite duro del bloque 7; el spike de la matriz de voz (`voice-decision-scorecard.md`) está diseñado para poder ejecutarse dentro de esos 25 minutos si es necesario, aunque su diseño teórico tolera hasta 90 minutos si el timebox se extiende por decisión explícita en T0. Esta tensión no se resuelve aquí — se resuelve en vivo con la regla de la sección 2.

## 4. Cierre del bloque: Exit gate C0

Al llegar a T+160m (o al agotar el bloque 10, lo que ocurra primero según la regla de la sección 2), se verifica el exit gate C0 completo antes de pasar a Sprint C1 (`plan.md` §5):

- [ ] deadline y zona confirmados;
- [ ] un solo modelo configurado;
- [ ] dataset/credenciales/licencias comprendidos;
- [ ] voz y arquitectura decididas;
- [ ] ninguna compuerta sin ticket P0.

Si algún ítem del exit gate no se cumple, no se avanza a C1: se registra como blocker P0 y se resuelve antes de iniciar el vertical slice, según la disciplina de `plan.md` §2.5 (WIP máximo, un ticket crítico a la vez).
