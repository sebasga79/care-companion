# Care Companion — Matriz de trazabilidad de entrega

> v2.0 · 9 de agosto de 2026. Fuente normativa: README, rúbrica y stack
> técnico de `TechSphere2026/ParticipantArtifacts`. Sustituye la matriz
> pre-kit que mantenía preguntas `Pendiente-T0`.

## 1. Compuertas eliminatorias

| Gate | Estado | Implementación | Prueba/evidencia | Pendiente humano |
|---|---|---|---|---|
| G1 · 4 entregables | Cumple | repositorio público, diagrama Markdown/Mermaid, informe y video en dos partes | `README.md`, `docs/architecture-diagram.md`, `docs/final-report.md`, [demo](https://youtu.be/wKgmlhy0Txo), [respuestas](https://youtu.be/cez5dnn9KEA) | ninguno |
| G2 · ≤15 min | Cumple observado | Docker Compose, volumen persistente y launcher idempotente | clon limpio: 1 min 45 s; `test_gates.py`, validación Compose/health | conservar key Groq válida para la revisión |
| G3 · modelo permitido | Cumple | Meta Llama 3.3 70B vía Groq; resguardo Llama 3.2 3B vía Ollama | allowlist runtime `groq\|ollama`; provider/model en `events`; `test_config.py`, `test_llm_adapters.py`, `test_gates.py` | verificar cuota antes de grabar/entregar |
| G4 · voz realtime | Cumple observado | Web Speech STT/TTS, WebSocket, barge-in, cierre hablado | ensayo manual con audio + 4 muestras voz-a-voz; `test_ws.py`, build frontend; [demo funcional](https://youtu.be/wKgmlhy0Txo) | repetir el intercambio en evaluación si el jurado lo solicita |
| G5 · learn/forget | Cumple | consola `/knowledge`, versión, canarias y borrado transaccional | `test_ingestion.py`, `test_knowledge_api.py`, `test_gates.py` | mostrar carga/uso/borrado en video |

## 2. Criterios de la rúbrica

| Criterio | Código principal | Evidencia observable | Riesgo residual |
|---|---|---|---|
| RAG, precisión clínica y conocimiento vivo · 20 | `services/ingestion.py`, `services/retrieval.py`, repositorios de documentos/chunks/citas | corpus oficial 107 docs, filtro por procedimiento, evidence gate, citas, learn/forget | probar con documento sorpresa del jurado |
| Decisión y escalamiento · 20 | `domain/safety_signals.py`, `services/rule_engine.py`, `domain/decision.py`, `orchestrator/call_cycle.py` | red flags no degradables, microtriaje, handoff, teléfonos, resumen | el handoff es un registro del sistema, no una integración hospitalaria |
| Problema y conversación · 15 | `agents/interview.py`, `agents/response.py`, contexto longitudinal | apertura contextual, preguntas adaptativas, no repetición, cierre automático | cuota/latencia puede afectar naturalidad |
| Calidad de voz · 15 | `web/src/lib/useVoiceSession.ts`, `web/src/components/CallModal.tsx`, WebSocket | voz real, interrupción, supresión de eco y P50/P95 persistidos | Web Speech depende de Chrome/servicios del navegador |
| Video y demo · 15 | `docs/video/`, app integrada | [demo funcional](https://youtu.be/wKgmlhy0Txo) + [argumentación y dos preguntas](https://youtu.be/cez5dnn9KEA) | ninguno documental |
| Repositorio/proceso · 15 | launcher, Compose, lockfiles, tests, ADRs, auditoría | un comando, métricas, trazas, historial y docs sincronizados | ejecutar última verificación y secret scan antes de push |

## 3. Requisito funcional → implementación → prueba

### 3.1 Datos y sesión

| Requisito observable | Implementación | Pruebas |
|---|---|---|
| Usar dataset oficial | `DatasetCaseAdapter`, bootstrap Docker | `test_dataset_case_source.py`, validación Compose/health |
| Mostrar 40 pacientes únicos | agrupación por `patient_id`, tarjetas `/call` | tests del adapter; build frontend |
| Conservar 160 episodios 1/3/7/14 | `HistoricalFollowup`, IDs de episodio | `test_dataset_case_source.py` |
| Pasar evolución completa al agente | `_case_context`, contexto previo por paciente | `test_orchestrator.py`, `test_agents.py` |
| Registrar nueva llamada en el patrón clínico | `followup_records`, `CallSummary` v1.2 | `test_summary_builder.py`, `test_orchestrator.py` |

### 3.2 Conversación y voz

| Requisito observable | Implementación | Pruebas/evidencia |
|---|---|---|
| Abrir con propósito/procedimiento | creación de sesión + opening message | `test_api.py`, `test_orchestrator.py` |
| Adaptarse a respuestas ambiguas | `InterviewAgent`, microtriaje determinista | `test_agents.py`, `test_gates.py` |
| Evitar preguntas repetidas | observaciones por objetivo y elipsis contextual | regresiones dolor/herida en `test_gates.py` |
| Hablar y escuchar | Web Speech + `client.turn_text` | ensayo manual; `test_ws.py` |
| Interrumpir TTS | barge-in/supresión de eco | lógica frontend + ensayo manual |
| Finalizar automáticamente | FSM + cierre rutinario/crítico | `test_orchestrator.py`, `test_ws.py` |

### 3.3 RAG vivo

| Requisito observable | Implementación | Pruebas |
|---|---|---|
| Subir documento | validación, extracción, chunks e índice | `test_ingestion.py`, `test_knowledge_api.py` |
| Mostrar procesado/disponible | status `ready` después de canaria | `test_ingestion.py` |
| Usar documento nuevo | retrieval por versión y procedimiento | `test_retrieval.py`, gate learn |
| Eliminar/olvidar | tombstone, purga, caché y canaria negativa | `test_ingestion.py`, gate forget |
| Citar fuente real | `CitationRef` con documento, versión, chunk, sección/página | `test_retrieval.py`, `test_summary_builder.py` |
| Abstenerse sin evidencia | evidence gate | `test_agents.py`, `test_orchestrator.py` |
| Resistir prompt injection en documento | contenido rotulado como no confiable | `test_agents.py`, tests de seguridad RAG |

### 3.4 Decisión y handoff

| Requisito observable | Implementación | Pruebas |
|---|---|---|
| Clasificar verde/ambiguo/urgente | reglas + triage estructurado | `test_rule_engine.py`, `test_decision_reducer.py` |
| Indagar antes de escalar ambigüedad | microtriaje de “muy mal” y dolor incompleto | `test_gates.py`, `test_orchestrator.py` |
| No perder una red flag | detector sobre texto crudo + precedencia | tests adversariales 40 °C, ambulancia, sangrado, desmayo |
| Registrar alerta persistente | `escalations`, decisión y triggers | `test_repositories.py`, `test_orchestrator.py` |
| Informar siguiente paso | `safe-handoff-v1` | `test_gates.py`, transcripción de demo |
| Confirmar dos teléfonos | observaciones `CONTACT_PRIMARY/EMERGENCY` | `test_orchestrator.py`, vista `/audit` |

### 3.5 Auditoría y métricas

| Requisito observable | Implementación | Pruebas/evidencia |
|---|---|---|
| Resumen con paciente/procedimiento/síntomas/decisión/citas | `SummaryBuilder`, `followup_records` | `test_summary_builder.py` |
| Traza por respuesta | `events`, `correlation_id`, citas y decisiones | `test_audit.py`, `/audit` |
| P50/P95 voz-a-voz | evento del navegador + percentiles | n=4 manual; `test_audit.py` |
| Tokens/invocaciones/RAG por llamada | eventos de agentes y retrieval | `test_audit.py` |
| Costo consistente | bucket por proveedor y llamadas cerradas | regresión de mezcla Groq/Ollama en `test_audit.py` |
| Excluir pruebas/incompletas | filtro estado cerrado + provider/model real | `test_usage_excludes_open_and_non_real_sessions` |

## 4. Invariantes de seguridad

| Invariante | Control | Evidencia |
|---|---|---|
| LLM no rebaja red flag | enum limitado + `reduce_decision` | `test_decision_reducer.py`, gate adversarial |
| Ausente ≠ negado | certainty + summary projection | `test_summary_builder.py` |
| Sin evidencia no se afirma | evidence gate | tests agentes/RAG |
| Fallo con riesgo va a estado seguro | `fail_safe` en FSM/orquestador | `test_orchestrator.py` |
| Solo datos sintéticos | kit oficial + fixtures rotulados | README, dataset adapter |
| Cero secreto en Git | `.gitignore`, launcher y política | gitleaks/scan antes de entrega |
| Sin audio/CoT persistido | solo texto final/eventos estructurados | revisión de schema/código |

## 5. Estado de cierre

Completados G1–G5 y los flujos de los seis criterios. El diagrama Mermaid
constituye el entregable 02; la documentación oficial no exige exportarlo a
otro formato. El video está publicado en dos partes: [demo
funcional](https://youtu.be/wKgmlhy0Txo) y [argumentación con las dos preguntas](https://youtu.be/cez5dnn9KEA).
Verificación del 9 de agosto:
`make verify` (415 passed/3 skipped), build frontend, Compose, health y consulta
de métricas en verde. Gitleaks verificó los 79 commits y el diff de entrega sin
hallazgos; `api/.env` está ignorado y no forma parte del repositorio.
