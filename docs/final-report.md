# Care Companion — Informe final

> v1.0 · 24 de julio de 2026 · Source Meridian Tech Sphere Challenge 2026
> Estado: construcción anticipada pre-concurso (ADR-001).

## 1. Problema y valor

El seguimiento postoperatorio pediátrico depende de llamadas manuales que no
escalan. Care Companion es un **agente de voz en español** que conduce esa
llamada con un cuidador, apoyándose en **conocimiento clínico citable**, una
**decisión de riesgo que las reglas deterministas nunca dejan rebajar** por el
modelo, y **supervisión humana explícita**. La unidad de producto es una
*llamada clínica en curso* con cuatro capas observables: qué dice el paciente,
qué entiende el sistema, qué evidencia sustenta la respuesta y por qué
interviene —o no— una persona.

## 2. Arquitectura y decisiones

Monolito modular (FastAPI + SQLite WAL) + frontend Next.js. Detalle en
[`architecture.md`](architecture.md) y [`architecture-diagram.md`](architecture-diagram.md).

Decisiones principales y alternativas descartadas:

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| Monolito modular | Microservicios | Arranque ≤15 min, menos fallos operativos en 72 h |
| Orquestador FSM tipado | Superprompt único | Decisión auditable y no degradable |
| Agentes de responsabilidad única, sin comunicación entre sí | Malla de agentes | Contención de fallos, trazabilidad |
| Reglas deterministas + `reduce_decision` | Confiar el riesgo al LLM | Seguridad clínica no negociable |
| RAG SQLite (FTS5+coseno+RRF) | Vector store gestionado | Deletion demostrable, sin infraestructura |
| Puertos/adaptadores para todo proveedor | Acoplar el SDK del modelo | El modelo obligatorio de T0 es un cambio de adapter |
| Voz nativa del navegador (Web Speech) | Esperar al proveedor de T0 | Barge-in real ya demostrable, sin credenciales |

Decisión de proceso: **ADR-001** — construcción anticipada por decisión del
propietario, con puertos estrictos como mitigación de rework en T0.

## 3. Qué está implementado y verificado

| Área | Estado | Evidencia |
|---|---|---|
| RAG vivo (learn/forget transaccional, evidence gate, citas) | ✅ | E2E en vivo: canaria +/−; `test_ingestion`, `test_gates` |
| Decisión no degradable + escalamiento idempotente | ✅ | tests adversariales `test_decision_reducer`, `test_orchestrator` |
| Agentes + orquestador FSM | ✅ | `test_agents`, `test_orchestrator`, cobertura de estados |
| WebSocket con envelopes versionados + seq | ✅ | `test_ws`, `test_gates`; E2E contra uvicorn real |
| Voz realtime con barge-in (navegador) | ✅ (browser) | `useVoiceSession`; requiere validación humana con micrófono |
| Frontend 3 vistas, AA cumplido | ✅ | tsc/lint/build; contraste WCAG verificado (PRE-025) |
| `/audit` con traza real + métricas honestas | ✅ | `test_audit`; traza verificada en vivo |
| Repo/proceso (README, MIT, NOTICE, Docker, diagrama) | ✅ | este repositorio |

**Suite:** `make verify` = 240 tests (+ frontend `tsc`/`lint`/`build`).

## 4. Métricas

Latencia P50/P95 se calcula desde eventos instrumentados (`/api/v1/metrics`,
visible en `/audit`). Tokens y costo se reportan **honestamente como
`pendiente`** hasta conectar el modelo obligatorio en T0 (COST-001) — no se
inventan cifras. El benchmark oficial P50/P95 (PERF-002) se corre con el
formato que defina la ficha.

## 5. Seguridad clínica (garantías)

- Sin evidencia activa aplicable **no hay respuesta clínica** (evidence gate →
  abstención estructurada).
- Reglas de red flags **no degradables**: `reduce_decision` toma siempre la
  mayor severidad; el modelo no puede construir un nivel de alerta dura (tipo).
- Silencio/dato ambiguo **nunca** es negación (`not_assessed`).
- Fallo de modelo/RAG/persistencia con riesgo → `fail_safe`/escala.
- Documentos RAG tratados como **datos, no instrucciones**.

## 6. Límites y trabajo pendiente (honesto)

- **Voz:** funciona con Web Speech del navegador (Chrome; STT puede enrutar a
  Google). No validada aún con micrófono real en esta sesión. El STT/TTS o la
  voz realtime del modelo obligatorio se integran en T0 por el mismo puerto.
- **Modelo:** hoy corre `FakeLLM` determinista. El modelo obligatorio (AI-001)
  y el dataset Delta Share (DATA-001) se conectan en T0.
- **No es un producto clínico:** prototipo, sin EHR, sin diagnóstico ni
  prescripción, solo datos sintéticos.
- **Clean-install ≤15 min:** el stack Docker está listo; falta cronometrarlo
  una vez en hardware limpio (REL-001).
- Filtros server-side de auditoría, reranker adicional y responsive móvil
  quedan como mejoras no bloqueantes.

## 7. Reproducibilidad

- Prompts y configuración: [`prompt-config-appendix.md`](prompt-config-appendix.md)
  (con hashes SHA-256 de los prompts).
- Dependencias y licencias: [`../NOTICE`](../NOTICE).
- Trazabilidad requisito→ticket→test→evidencia: [`traceability.md`](traceability.md).
- Plan y bitácora de ejecución: [`plan.md`](plan.md) y `../CLAUDE.md`.
