# Care Companion — Apéndice de prompts y configuración (DOC-004)

> v1.2 · 7 de agosto de 2026 · Reproducible. **No** contiene chain-of-thought,
> secretos ni claves. Los prompts viven versionados en el código (`api/app/agents/`);
> este apéndice los referencia con hash para trazabilidad.

## 1. Modelo y proveedor

| Parámetro | Valor actual (pre-T0) | En T0 |
|---|---|---|
| `LLM_PROVIDER` | `fake` (determinista) | `groq` primario / `ollama` local |
| `LLM_MODEL` | `fake-model-v1` | Llama 3.1 70B / Phi-3.5 Mini |
| Adapter | `FakeLLM` | `OpenAICompatLLM` detrás del mismo `LLMPort` |

Allowlist de proveedores: **solo** `fake`, `groq` y `ollama` (validado en
`test_gates.py::test_gate_single_model_allowlist`). No hay adapters de otros
proveedores en el código.

## 2. Agentes — rol, presupuesto y prompt

Todos los agentes: reciben `AgentRequest`, devuelven `AgentResult` tipado, usan
**solo** el `LLMPort` inyectado, con **máximo 1 reintento** ante timeout/salida
inválida (2 intentos totales, `api/app/agents/support.py`), y ante segundo
fallo devuelven un resultado de fallo estructurado que el orquestador convierte
en `fail_safe`. **Ningún agente llama a otro** — solo el orquestador coordina.

### 2.1 InterviewAgent (`interview.py`)

- **Rol:** formular la siguiente pregunta del checklist o extraer observaciones
  estructuradas; nunca diagnostica ni decide riesgo.
- **Salvaguardas en el prompt (verbatim en código):** expresión coloquial
  ambigua → `needs_clarification=true` + pregunta abierta, conservando el texto
  original; contradicción intra-llamada → se señala citando lo previo;
  silencio/turno vacío → `not_assessed`, **nunca** `denied`.
- **Salida:** JSON estricto `{needs_clarification, clarification_question,
  next_objective_code, next_question, observations[]}`. Un saludo puro no crea
  observaciones; contexto de caso/seguimientos nunca se toma como síntoma actual.

### 2.2 TriageAgent (`triage.py`)

- **Rol:** evaluación de riesgo estructurada del modelo.
- **Salvaguarda dura:** su nivel **solo** puede ser `ROUTINE_FOLLOW_UP`,
  `MODEL_MODERATE_RISK` o `MODEL_HIGH_RISK`. No puede declarar una alerta dura —
  eso es exclusivo del motor de reglas determinista. Reforzado además por
  validación de tipo en `DecisionInputs.model_level`.
- **Salida:** JSON `{model_level, rationale, missing_information[],
  patient_message_intent}`.

### 2.3 ResponseAgent (`response.py`)

- **Rol:** respuesta hablable en español (2-4 frases). Nunca diagnostica,
  prescribe ni promete acciones reales. Responde saludos con naturalidad y evita
  muletillas repetidas antes de cada pregunta.
- **Groundedness:** solo puede afirmar contenido clínico que aparezca
  literalmente en los FRAGMENTOS DE EVIDENCIA aprobados por el evidence gate,
  pasados **como datos, no instrucciones** ("contenido no confiable"). Sin
  evidencia → aclara/abstiene/deriva.
- **Handoff de seguridad:** si la decisión implica escalamiento, no se llama al
  LLM. `safe-handoff-v1` construye un mensaje determinista; para
  `HARD_RED_FLAG` detiene el checklist, comunica valoración urgente, confirma el
  reporte al equipo de atención y abre la confirmación de dos teléfonos.

### 2.4 Hashes de reproducibilidad (SHA-256, 16 hex)

| Archivo | Hash |
|---|---|
| `api/app/agents/interview.py` | `f73e3b1fc2aafcae` |
| `api/app/agents/response.py` | `5e73be1fc147d7cc` |
| `api/app/agents/triage.py` | `615f7be7f80c9838` |

> Regenerar: `shasum -a 256 api/app/agents/{interview,response,triage}.py`.
> Cualquier cambio de prompt cambia el hash — es la versión del prompt.

## 3. Servicios deterministas (no-LLM)

- **RuleEngine** (`services/rule_engine.py`): red flags versionadas; dato
  ausente/ambiguo nunca produce "todo bien" → `missing_info`. Versión actual:
  `rules-v2`.
- **SafetySignalDetector** (`domain/safety_signals.py`):
  `safety-signal-detector-v1`, inspección del texto crudo con negación y
  precedencia sobre observaciones del LLM.
- **reduce_decision** (`domain/decision.py`): precedencia
  `HARD_RED_FLAG > DATA_INTEGRITY_FAILURE > EVIDENCE_INSUFFICIENT_WITH_RISK >
  MODEL_HIGH_RISK > MODEL_MODERATE_RISK > ROUTINE_FOLLOW_UP`. No degradable.

## 4. Configuración RAG (valores por defecto)

| Ajuste | Default | Nota |
|---|---|---|
| `RAG_ALLOWED_EXTENSIONS` | `txt,md,pdf` | PDF real soportado con `pypdf` |
| `RAG_MAX_UPLOAD_BYTES` | `15_000_000` | cubre el corpus oficial |
| `RAG_CHUNK_SIZE_CHARS` | `800` | con solape |
| `RAG_CHUNK_OVERLAP_CHARS` | `150` | |
| `RAG_EMBEDDING_DIMENSIONS` | `128` | FakeEmbeddings; el real llega en T0 |
| `RAG_RRF_K` | `60` | fusión Reciprocal Rank Fusion |
| `RAG_RETRIEVAL_TOP_K` | `5` | |
| `RAG_CANDIDATE_POOL_SIZE` | `200` | |
| `RAG_EVIDENCE_SCORE_THRESHOLD` | `0.2` | umbral del evidence gate |

## 5. Higiene

- Ningún secreto en prompts, config versionada ni logs. `.env.example` solo
  placeholders (`changeme`); credenciales reales fuera del repo
  (`docs/policies/secrets.md`).
- No se registra chain-of-thought ni audio bruto por defecto (spec §11.6).
- Los parámetros de temperatura/tokens del modelo obligatorio se fijan en T0
  con el proveedor real (AI-001) y se anexan aquí entonces.
