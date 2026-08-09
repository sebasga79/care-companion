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

**Modelo usado: `llama-3.3-70b-versatile` — Llama 3.3 70B servido por Groq.**
Configurado en [`api/app/core/config.py`](../api/app/core/config.py)
(`LLMProvider.GROQ`), verificable en `LLM_PROVIDER`/`LLM_MODEL` y en el
campo `provider`/`model` que cada llamada persiste en `events`.

**Por qué este y no otro.** Versión anterior de esta sección (hasta el 8 de
agosto) declaraba `llama-3.1-8b-instant`, razonando que había que preservar
el número de versión (`3.1`) de la referencia original de
[`docs/stack-tecnico.md`](https://github.com/TechSphere2026/ParticipantArtifacts/blob/main/docs/stack-tecnico.md)
(*"Llama 3.1 70B (vía Groq)"*, retirado del catálogo de Groq) y ceder en
tamaño antes que en versión. **Esa lectura era más estricta de lo que la
compuerta exige.** El texto completo de `stack-tecnico.md` §1 lo aclara
explícitamente:

> "La lista fija **familias**, no versiones puntuales, porque los
> proveedores retiran o reemplazan snapshots sin previo aviso […] Si un
> modelo sugerido ya no existe, usa el sucesor vigente **de la misma
> familia y proveedor**: la versión más reciente de Llama disponible en
> Groq […] Esto no cambia cómo se revisa la compuerta G3: lo que se evalúa
> es que el modelo pertenezca a una de las familias permitidas y esté
> vigente en su nivel gratuito o local, **no que coincida un identificador
> exacto de versión**."

`llama-3.3-70b-versatile` es exactamente eso: la versión de Llama vigente
en el nivel gratuito de Groq al momento de la entrega, misma familia y
proveedor que la referencia original. No hay conflicto con G3 en ningún
sentido — se corrige esta sección porque el argumento anterior ya no
describe el sistema real (el default de `api/.env`/`config.py` se cambió el
8 de agosto por capacidad: el nivel gratuito de `llama-3.1-8b-instant` da
**6.000 TPM**, el de `llama-3.3-70b-versatile` **12.000 TPM** — el doble de
margen para una conversación de varios turnos con tres agentes por turno),
no porque hubiera que resolver una ambigüedad de la compuerta.

**Alternativas evaluadas y descartadas.** Los modelos locales de la lista
(Llama 3.2 1B/3B y Phi-3.5 Mini vía Ollama) sí existen tal cual, sin
ambigüedad. Se midieron en la máquina de desarrollo: **~5,6 s por
invocación**, ~11 s por turno conversacional con tres agentes. Es inviable
para una conversación de voz, criterio que la rúbrica evalúa explícitamente
(15 pts). Llama 3.2 3B queda implementado y configurable como **resguardo**
(`LLM_FALLBACK_PROVIDER=ollama`, `LLM_FALLBACK_MODEL=llama3.2:3b`): si Groq
falla o no hay red durante la sesión de evaluación, la llamada continúa con
un modelo local de la lista en vez de caerse. Gemini 1.5 Flash se descartó
por requerir un segundo adapter con SDK propio sin ganancia sobre Groq.

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
turnos reales del dataset oficial contra Groq y compara contra
`label_ground_truth`. Tabla completa con costo por llamada en el
[README §Métricas](../README.md#métricas-rúbrica-5) (obligatoria por
rúbrica); metodología y ambas corridas en
[`docs/benchmarks/README.md`](benchmarks/README.md).

**Dos corridas con propósitos distintos, porque el modelo cambió a mitad de
sesión** (`llama-3.1-8b-instant` → `llama-3.3-70b-versatile`, más capacidad
por minuto — ver §2.1):

| | `capa1-groq.json` (8 ago) | `capa1-groq-70b.json` (9 ago) |
|---|---|---|
| Modelo | `llama-3.1-8b-instant` (histórico) | `llama-3.3-70b-versatile` (**desplegado hoy**) |
| Casos / turnos | 12 / 62 | 3 / 16 |
| Para qué sirve | Sensibilidad/especificidad — muestra grande | Latencia/tokens/costo del modelo real |
| Falsos negativos | 1 de 4 rojos (sensibilidad 75 %) | 0 de 1 rojo — muestra insuficiente para tasa |
| Falsos positivos | 0 de 6 verdes (especificidad 100 %) | 1 de 1 verde, ocurrido bajo agotamiento de cuota diaria (ver nota) — no se cuenta como hallazgo confirmado |
| Latencia p50 / p95 | 1.093 ms / 3.267 ms | 3.782 ms / 5.139 ms (14 turnos limpios) |
| Tokens por turno | 2.493 entrada · 290 salida | 3.590,7 entrada · 407,3 salida |
| Costo estimado por llamada | no calculado en esa corrida | **US$0,0114** |

La corrida del 9 de agosto es deliberadamente corta — no reemplaza la
sensibilidad/especificidad de la de 12 casos (para eso sigue siendo
autoridad), sólo refresca latencia/tokens/costo contra el modelo
efectivamente desplegado, porque reportar los números del modelo viejo
sería exactamente lo que la rúbrica penaliza ("reportar números que no se
sostienen es peor que no reportarlos"). Detalle completo, incluido el
hallazgo de que la cuota **diaria** (no sólo la de minuto) de Groq se agotó
a mitad de la corrida y forzó una caída al resguardo local en 2 de 16
turnos, en `docs/benchmarks/README.md`.

El costo por llamada de la tabla ya no es un cálculo manual de una corrida
puntual: `GET /api/v1/metrics` (y `/audit`) lo computa solo, en vivo, con
`LLM_COST_PER_MILLION_*` configurado al precio real de Groq —
`AuditRepository.usage_summary` desglosa tokens por proveedor
(`by_provider`) para no cobrar precio de Groq por tokens que en realidad
sirvió gratis el resguardo local, el mismo problema que contaminó la
corrida corta de arriba (auditoría §9.35).

El falso negativo de la corrida grande y su justificación están
documentados en `docs/benchmarks/README.md` — es un caso de minimización
verbal sostenida sin dato objetivo inequívoco, dejado como limitación
conocida en vez de un fix de riesgo a dos días del plazo. El benchmark
mismo encontró y corrigió un falso positivo real durante su desarrollo
(`PAIN_WORSENING` disparado por temor hipotético, no por síntoma
reportado) — ver commit `app/domain/safety_signals.py::_is_hypothetical_worry`.

**Verificable en los logs, no sólo aquí** (rúbrica §4/§5/§6 — la métrica
que no se sostiene contra logs es peor que no reportarla). Dos capas
reales, documentadas con el detalle exacto de qué contiene cada una en el
[README §Métricas](../README.md#cómo-verificar-estas-cifras-en-los-logs):
logs de proceso (`./levantar_app.sh --logs`, JSON estructurado con
`correlation_id`, confirma el proveedor real desde la línea de arranque) y
la traza estructurada (`/audit`, `GET /api/v1/metrics`) que trae el
desglose granular de tokens/proveedor/latencia por evento — con
`correlation_id` visible en la línea de tiempo de `/audit` para cruzar un
evento puntual contra el log de terminal y confirmar que es la misma
ejecución.

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
- **Modelo:** Groq (`llama-3.3-70b-versatile`) primario, Ollama local
  (`llama3.2:3b`) de resguardo si Groq falla o excede la cuota. Dataset
  oficial (160 casos, 4 xlsx) y corpus RAG oficial (107 PDFs, 9.296 chunks)
  integrados, con embeddings semánticos reales (BGE-M3 vía Ollama, 1024
  dim) — no `FakeEmbeddings`. `docker-compose.yml` carga la config real de
  `api/.env` vía `env_file` (antes corría con defaults `fake` sin avisar,
  ver `docs/auditoria-kit-oficial-2026-08-07.md` §9.19).
- **No es un producto clínico:** prototipo, sin EHR, sin diagnóstico ni
  prescripción, solo datos sintéticos.
- **Clean-install ≤15 min (NFR-004):** cronometrado dos veces, en dos
  configuraciones distintas — ambas cómodas dentro del límite:
  - **1 min 45 s** con el flujo real de un solo comando (`git clone` +
    `./levantar_app.sh`) y configuración por defecto (LLM y embeddings
    `fake`, cero pasos manuales) — clon público, máquina del usuario, no
    un ensayo interno. Sólo posible tras corregir dos bugs que antes lo
    impedían por completo en cualquier clon nuevo: `docker-compose.yml`
    exigía un `api/.env` que nunca existe en un clon fresco (Compose lo
    trata como error fatal, no como "sin variables extra"), y
    `web/public/` llevaba vacío desde el 23 de julio — git no rastrea
    directorios vacíos, así que la imagen `web` no podía construirse en
    ningún clon público. Ver §9.38 de la auditoría.
  - **9 min 50 s** con `docker compose down -v && up -d --build` y
    embeddings semánticos reales (BGE-M3 vía Ollama) configurados a mano
    — generar 9.296 vectores de embedding por inferencia real es más
    costoso que el hash determinista de `FakeEmbeddings`. Ver §9.19 de la
    auditoría.
  - Ninguna de las dos corridas mide una máquina con cero caché de capas
    Docker (imágenes base, dependencias) — esa parte depende de la
    velocidad de red del jurado y no se puede medir desde aquí; el margen
    hasta los 15 minutos es amplio incluso así.
- **Latencia voz-a-voz (spec.md §1.5), primeras muestras reales: P50
  6.154 ms / P95 6.507 ms (n=3, navegador real, 9 ago) — por encima del
  objetivo interno de ≤2,5s (NFR-002).** `CallModal.tsx` mide en el
  navegador, por llamada, desde que el paciente termina de hablar hasta
  que empieza a sonar el audio del agente — la definición exacta de la
  rúbrica §5 — y la reporta a `POST /api/v1/sessions/{id}/voice-latency`,
  persistida como evento auditable (`client.voice_latency_reported`).
  `GET /api/v1/metrics` y `/audit` la exponen sin depender de que alguien
  pase un número a mano. Con n=3 el número es preliminar, no una
  distribución estable, y queda declarado como tal — no se espera a tener
  más muestras para reportarlo, un real chico es mejor que "pendiente".
  El turno más lento de las 3 encadenó entrevista → RAG con embeddings
  reales → triage → respuesta (4 llamadas al modelo/embeddings en un
  único turno): el proxy de servidor de §4 (`turn.response_sent`, sin
  tránsito WS ni arranque real de TTS) subestima la experiencia real de
  punta a punta en ese escenario — diferencia honesta, no oculta. Detalle
  completo en el [README §Métricas](../README.md#métricas-rúbrica-5) y
  auditoría §9.20, §9.34, §9.35, §9.40.
- Filtros server-side de auditoría, reranker adicional y responsive móvil
  quedan como mejoras no bloqueantes.

## 7. Reproducibilidad

- Prompts y configuración: [`prompt-config-appendix.md`](prompt-config-appendix.md)
  (con hashes SHA-256 de los prompts).
- Dependencias y licencias: [`../NOTICE`](../NOTICE).
- Trazabilidad requisito→ticket→test→evidencia: [`traceability.md`](traceability.md).
- Plan y bitácora de ejecución: [`plan.md`](plan.md) y `../CLAUDE.md`.
