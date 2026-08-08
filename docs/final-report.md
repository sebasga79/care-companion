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

## 2.1 Modelo de lenguaje declarado (compuerta G3)

**Modelo usado: `llama-3.1-8b-instant` — Llama 3.1 servido por Groq.**
Configurado en [`api/app/core/config.py`](../api/app/core/config.py)
(`LLMProvider.GROQ`), verificable en `LLM_PROVIDER`/`LLM_MODEL` y en el
campo `provider`/`model` que cada llamada persiste en `events`.

**Por qué este y no otro.** La lista cerrada de
[`docs/stack-tecnico.md`](https://github.com/TechSphere2026/ParticipantArtifacts/blob/main/docs/stack-tecnico.md)
nombra *"Llama 3.1 70B (vía Groq)"*. Al conectarlo encontramos que **Groq
retiró ese modelo de su catálogo**: hoy ofrece `llama-3.1-8b-instant`
(Llama 3.1, 8B) y `llama-3.3-70b-versatile` (70B, pero versión 3.3).
Ninguno reproduce exactamente el nombre de la lista, así que había que
elegir de qué lado desviarse:

| Candidato | Familia | Versión | Tamaño | Desviación respecto a la lista |
|---|---|---|---|---|
| `llama-3.1-8b-instant` | Llama | **3.1** ✅ | 8B ✗ | Sólo el tamaño |
| `llama-3.3-70b-versatile` | Llama | 3.3 ✗ | **70B** ✅ | Versión mayor distinta |

Elegimos conservar **familia y versión** (`3.1`) y ceder en el tamaño:
cambiar de versión mayor se aleja más de lo que la lista autoriza, y G3
**descalifica** —no penaliza— usar un modelo fuera de ella. La causa del
desvío es del proveedor, no una preferencia nuestra: el modelo exacto ya no
se puede invocar.

**Alternativas evaluadas y descartadas.** Los otros dos modelos de la lista
son locales (Llama 3.2 1B/3B y Phi-3.5 Mini vía Ollama) y sí existen tal
cual, sin ambigüedad. Se midieron en la máquina de desarrollo:
**~5,6 s por invocación**, ~11 s por turno conversacional con tres agentes.
Es inviable para una conversación de voz, criterio que la rúbrica evalúa
explícitamente (15 pts). Quedan implementados y configurables como
**resguardo** (`LLM_FALLBACK_PROVIDER=ollama`): si Groq falla o no hay red
durante la sesión de evaluación, la llamada continúa con un modelo local de
la lista en vez de caerse. Gemini 1.5 Flash se descartó por requerir un
segundo adapter con SDK propio sin ganancia sobre Groq.

**Embeddings (no restringidos por G3):** BGE-M3 local vía Ollama, el modelo
que el propio kit sugiere para español. No dependen de red externa.

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
visible en `/audit`), y también desde el arnés automatizado
([`api/scripts/benchmark.py`](../api/scripts/benchmark.py)), que reproduce
turnos reales del dataset oficial contra Groq (`llama-3.1-8b-instant`) y
compara contra `label_ground_truth`. Metodología completa en
[`docs/benchmarks/README.md`](benchmarks/README.md).

**Corrida `capa1-groq.json` (12 casos, 62 turnos, 2026-08-08):**

| Métrica | Valor |
|---|---|
| Falsos negativos | 1 de 4 rojos (sensibilidad 75 %) |
| Falsos positivos | 0 de 6 verdes (especificidad 100 %) |
| Latencia p50 / p95 | 1.093 ms / 3.267 ms (≈1,1 s / ≈3,3 s) |
| Tokens por turno | 2.493 entrada · 290 salida |
| Invocaciones LLM / consultas RAG por turno | 1,58 · 1,5 |

El falso negativo restante y su justificación están documentados en
`docs/benchmarks/README.md` — es un caso de minimización verbal sostenida
sin dato objetivo inequívoco, dejado como limitación conocida en vez de un
fix de riesgo a dos días del plazo. El benchmark mismo encontró y corrigió
un falso positivo real durante su desarrollo (`PAIN_WORSENING` disparado
por temor hipotético, no por síntoma reportado) — ver commit
`app/domain/safety_signals.py::_is_hypothetical_worry`.

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
  Google), validada con micrófono real, con half-duplex para evitar que el
  TTS del agente se autoescuche.
- **Modelo:** Groq (`llama-3.1-8b-instant`) primario, Ollama local
  (`llama3.2:3b`) de resguardo si Groq falla o excede la cuota. Dataset
  oficial (160 casos, 4 xlsx) y corpus RAG oficial (107 PDFs, 9.296 chunks)
  integrados, con embeddings semánticos reales (BGE-M3 vía Ollama, 1024
  dim) — no `FakeEmbeddings`. `docker-compose.yml` carga la config real de
  `api/.env` vía `env_file` (antes corría con defaults `fake` sin avisar,
  ver `docs/auditoria-kit-oficial-2026-08-07.md` §9.19).
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
