# Care Companion — Matriz de trazabilidad

> SDD v0.1 · 23 de julio de 2026 · Propietario: SG
> Deriva de `spec.md` v0.1 (requisitos FR/BR/NFR, AC-E2E, OQ-001…OQ-010) y `plan.md` v0.1 (tickets §4–9, gates §10, rúbrica §11).
> Cobertura: 49 FR + 36 BR + 15 NFR = **100 requisitos**. Ningún requisito fue inventado; todos los IDs citan `spec.md`/`plan.md` literalmente.
> Los tickets de las fases C/R/F (post-T0) aún están en `Backlog`; su cita aquí es la asignación planeada, no evidencia ya producida. La ejecución real y el delta de requisitos ocurren a partir de T0 (7 de agosto), per `plan.md` §5 CH-008.

---

## 1. Matriz principal: requisito → ticket → test → evidencia → rúbrica/gate

Columnas: **Ticket(s)** = responsable(s) en `plan.md`; **Test** = verificación prevista; **Evidencia** = artefacto esperado; **Rúbrica/Gate** = criterio de 100 pts (`plan.md` §11) y/o compuerta eliminatoria (`plan.md` §10) a los que aporta — se sigue la asignación ticket→rúbrica que el propio `plan.md` §11 define; cuando un ticket no aparece en §10/§11, se marca como soporte transversal; **Estado** = `Pendiente-T0` + OQ si la verificación concreta depende de una decisión del 7 de agosto.

### 5.1 Inicio y sesión

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-001 | DATA-001 (dep. CH-005) | integration test con caso real | UI sin fixtures cuando el adapter está habilitado | Soporte transversal (no listado en §10/11); sustenta Video y demo 15 y RAG 20 vía datos reales | **Pendiente-T0** (OQ-003, OQ-004) |
| FR-002 | ORC-001, DB-001, API-001 | unit tests de state machine + test API | respuesta con `session_id`, estado, `knowledge_version` | Soporte transversal (no listado en §10/11); prerrequisito de todos los AC-E2E | — |
| FR-003 | ORC-001, API-001 (health) | unit test de compuerta de readiness | bloqueo de inicio demostrado si falta modelo/voz/DB/conocimiento | Decisión 20 (fail-safe, NFR-006) | — |
| FR-004 | ORC-001 (estado `consent` en la FSM) + CH-008 (resolver según ficha en T0) | test de transición `consent` en ORC-001; delta CH-008 documentado | checklist CH-008 con decisión FR-004 registrada | Conversación 15 | **Pendiente-T0** (la ficha define si se exige; se resuelve en CH-008) |
| FR-005 | DB-002 | concurrency smoke / test cruce de sesión | test negativo: ningún turno/observación cruza `session_id` | Soporte transversal; sustenta NFR-008 | — |

### 5.2 Voz

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-010 | FE-002, VOI-001 | browser evidence (permiso denegado → instrucción recuperable) | grabación/captura | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008 — pipeline vía CH-007) |
| FR-011 | API-002, VOI-010 | WebSocket test | trace de envelopes sin espera de archivo completo | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |
| FR-012 | VOI-012, FE-002 | test de reconciliación parcial/final | transcripciones finales persistidas con timestamp | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |
| FR-013 | VOI-013 | latency trace | audio inicia antes de generar todo (si el proveedor lo permite) | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |
| FR-014 | VOI-014 | E2E/video | evento `tts.cancel` registrado | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |
| FR-015 | VOI-015 | chaos test (reconnect/disconnect) | resume o cierre seguro documentado | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |
| FR-016 | VOI-013, VOI-014 | test de exclusión mutua TTS | solo una respuesta TTS activa por sesión | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |

### 5.3 Conversación

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-020 | CON-002 | scenario eval | siguiente pregunta depende de datos faltantes | Conversación 15 | — |
| FR-021 | CON-003 | ambiguous E2E (AC-E2E-003) | aclaración solicitada, sin diagnóstico atribuido | Conversación 15 | — |
| FR-022 | RES-001 | groundedness eval (turnos concisos) | transcripción sin JSON/citas leídas | Conversación 15 | — |
| FR-023 | CON-001 | validation tests (schema Observación) | `certainty` y `source_turn_id` presentes | Conversación 15 | — |
| FR-024 | CON-002/CON-003, RAG-006 | ambiguous/contradiction E2E | aclaración solicitada ante conflicto | Conversación 15 + RAG 20 | — |
| FR-025 | ORC-002, SUM-002 | state coverage test | toda transición terminal produce resumen | Conversación 15 | — |

### 5.4 Conocimiento y RAG

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-030 | RAG-002, RAG-001 | negative tests (tipo/tamaño) | estado `processing`→`ready` observado | RAG 20 · Gate: learn/forget | — |
| FR-031 | RAG-001 | migration + unit test | checksum/versión/vigencia persistidos | RAG 20 | — |
| FR-032 | RAG-008 | E2E positivo (AC-E2E-005) | consulta canaria recupera contenido nuevo | RAG 20 · Gate: learn/forget | — |
| FR-033 | RAG-009 | E2E deletion (AC-E2E-006) | chunks/índice/vectores/cachés removidos | RAG 20 · Gate: learn/forget | — |
| FR-034 | RAG-009, TST-003 | canary + E2E negativo | contenido eliminado no recuperable | RAG 20 · Gate: learn/forget | — |
| FR-035 | RAG-005 | retrieval eval (BM25+cosine+RRF) | resultados híbridos con filtros | RAG 20 | — |
| FR-036 | RAG-006 | unit matrix (fixtures ficticias PRE-017/018) | filtro por procedimiento/fase/audiencia/vigencia/versión | RAG 20 | **Pendiente-T0** (OQ-004 — mecanismo testable ya; corpus real pendiente) |
| FR-037 | RAG-007 | trace test | cita con `document_id`/versión/sección-página/`chunk_id` | RAG 20 | — |
| FR-038 | RAG-006 | unit matrix (AC-E2E-007) | abstención cuando ningún chunk supera el umbral | RAG 20 | — |
| FR-039 | RAG-006, SEC-003 | negative tests (upload/prompt injection) | instrucciones embebidas tratadas como contenido sin autoridad | RAG 20 + Decisión 20 (seguridad) | — |

### 5.5 Riesgo y escalamiento

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-040 | SAFE-001 | 100% critical branches | reglas versionadas corren antes de responder | Decisión 20 (AC-E2E-002) | — |
| FR-041 | SAFE-002 | schema/eval | salida de riesgo valida contra schema/enum | Decisión 20 | — |
| FR-042 | SAFE-003 | adversarial unit tests | modelo no puede rebajar una red flag | Decisión 20 | — |
| FR-043 | RES-001, UX-004 | accessibility/interaction test | explicación con señales, reglas, evidencia, datos faltantes | Decisión 20 | — |
| FR-044 | SAFE-004 | duplicate test | evento de alerta idempotente | Decisión 20 | — |
| FR-045 | RES-001 | groundedness eval | mensaje de handoff sin diagnóstico | Decisión 20 + Conversación 15 | — |
| FR-046 | SAFE-003, ORC-002 | fail-safe unit test | dato corrupto/incompleto con riesgo no continúa como rutina | Decisión 20, NFR-006 | — |
| FR-047 | SAFE-004 (alerta simulada, sin adapters de escritura en MVP — fuera de alcance §2.2) | revisión de alcance / code scan | ninguna alerta invoca sistemas hospitalarios reales | Decisión 20 | — |

### 5.6 Resumen y auditoría

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-050 | SUM-001, SUM-002 | validation test | resumen valida schema y versión | Conversación 15 | — |
| FR-051 | SUM-002 | golden snapshot | dato no preguntado no aparece como negativo | Conversación 15 | — |
| FR-052 | SUM-002, RAG-007, SAFE-004 | golden snapshot + trace test | ids de decisión/evidencia enlazan a eventos existentes | Conversación 15 (SUM-002) + Decisión 20 + RAG 20 | — |
| FR-053 | OBS-001, UX-005 | trace de una llamada | línea de tiempo turno→observación→recuperación→decisión→respuesta | Soporte transversal (OBS-001/UX-005 no listados en §11); sustenta Decisión 20 y RAG 20 | — |
| FR-054 | DOC-009 Export de evidencia de demo (C4 · Entregables) | validación del archivo exportado contra schema; scan de secretos sobre el export | archivo JSON/CSV exportado + resultado de validación | Repo/proceso 15 | — |
| FR-055 | DOC-004 | reproducible appendix | prompts/config por hash/versión, sin chain-of-thought | Repo/proceso 15 | — |
| FR-056 | PERF-001/002, COST-001 | reproducible report | P50/P95 globales + latencia/tokens/costo por sesión | Voz 15 (PERF-001/002) | **Pendiente-T0** (OQ-005) |

### 5.7 Reproducibilidad y entrega

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| FR-060 | REL-001, REP-003, DOC-001 | clean-room timer | log/video de instalación ≤15 min | Repo/proceso 15 · Gate: ≤15 min | **Pendiente-T0 parcial** (OQ-006 — mecanismo de credenciales) |
| FR-061 | CH-006, AI-001, SEC-006 | code/config/trace scan | solo el `model_id` obligatorio aparece en trazas | Gate: modelo único | **Pendiente-T0** (OQ-001) |
| FR-062 | DOC-007 | compliance check | LICENSE en raíz, nombre/año correctos | Repo/proceso 15 | **Pendiente-T0 parcial** (OQ-010 — alcance de licencias de terceros) |
| FR-063 | FIN-008 | gate manual | checklist de los 4 entregables completo | Gate: 4 entregables | — |
| FR-064 | DOC-002 | linked artifact | diagrama de arquitectura y decisión exportado | Gate: 4 entregables · Repo/proceso 15 | — |
| FR-065 | PERF-002, COST-001, DOC-001 | reproducible report | métricas reportadas en el formato exigido | Repo/proceso 15 + Voz 15 | **Pendiente-T0** (OQ-005) |

---

### 6.1 Sesión y contexto (BR)

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| BR-001 | DB-001, ORC-001 | schema + unit test | sesión ligada a un `case_id` y `knowledge_version` | RAG 20 (knowledge_version) + soporte transversal | — |
| BR-002 | DB-002 | test de aislamiento entre sesiones | sin mezcla de historial/fuentes/memoria | Soporte transversal; sustenta NFR-008 | — |
| BR-003 | ORC-001/002, DB-001 | unit test de inmutabilidad | corrección crea evento compensatorio, no reescribe | Decisión 20 (auditabilidad) | — |
| BR-004 | DATA-001, CH-005 | integration test con caso | solo campos mapeados y necesarios se procesan | Soporte transversal (privacidad/minimización) | **Pendiente-T0** (OQ-003) |
| BR-005 | SUM-002, CON-002 | golden snapshot | dato ausente no se convierte en negativo | Conversación 15 | — |
| BR-006 | CON-001 | validation test (Observation schema) | texto original + normalizado + certeza + procedencia | Conversación 15 | — |

### 6.2 Evidencia (BR)

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| BR-010 | RAG-006, RES-001 | unit matrix | toda afirmación clínica sustentada por fuente activa | RAG 20 | — |
| BR-011 | RAG-009 | E2E deletion | fuente eliminada no sustenta sesiones nuevas | RAG 20 · Gate: learn/forget | — |
| BR-012 | RAG-007 | trace test | cita señala documento, versión y ubicación | RAG 20 | — |
| BR-013 | RAG-005, RAG-006 | retrieval eval con fixtures ficticias | fuente de otro procedimiento/fase no aplica | RAG 20 | **Pendiente-T0 parcial** (OQ-004 — corpus real) |
| BR-014 | RAG-006, SAFE-003 | unit matrix (conflicto) | abstención o escalamiento ante contradicción sin precedencia | RAG 20 + Decisión 20 | — |
| BR-015 | RAG-006, SEC-003 | negative tests (prompt injection) | contenido recuperado no cambia prompt/reglas/permisos | RAG 20 + Decisión 20 | — |
| BR-016 | RAG-008 | E2E positivo | carga exitosa solo tras indexación + consulta canaria | RAG 20 · Gate: learn/forget | — |
| BR-017 | RAG-009 | E2E deletion | borrado exitoso solo tras purgar índices/cachés + canaria negativa | RAG 20 · Gate: learn/forget | — |

### 6.3 Decisión clínica (BR)

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| BR-020 | SAFE-001, SAFE-003 | 100% critical branches | reglas deterministas priman sobre el LLM | Decisión 20 | — |
| BR-021 | SAFE-003 | adversarial unit tests | severidad puede subir, nunca bajar una alerta dura | Decisión 20 | — |
| BR-022 | SAFE-002, RAG-006 | schema/eval | riesgo posible con evidencia insuficiente escala | Decisión 20 | — |
| BR-023 | SAFE-002/003 | adversarial unit tests | ninguna decisión depende solo de confidence numérico | Decisión 20 | — |
| BR-024 | SAFE-003, CON-002 | adversarial unit tests | "no escalar" exige ausencia de red flags + evidencia + datos mínimos | Decisión 20 | — |
| BR-025 | SAFE-004 | duplicate test | alerta idempotente por `session_id+trigger_set+decision_version` | Decisión 20 | — |
| BR-026 | RES-001, UX-004 | groundedness eval | agente explica observación y motivo sin diagnosticar | Decisión 20 + Conversación 15 | — |
| BR-027 | ORC-002, SAFE-003 | fail-safe unit test | fallo crítico con riesgo → abstención/escalamiento | Decisión 20, NFR-006 | — |

### 6.4 Conversación (BR)

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| BR-030 | RES-001, CON-002 | groundedness/naturalness checklist | español natural sin jerga innecesaria | Conversación 15 | — |
| BR-031 | CON-002 | scenario eval | cada pregunta pide una unidad principal de información | Conversación 15 | — |
| BR-032 | RES-001, EVA-003 | rubric eval | sin confirmación de diagnóstico/prescripción/tratamiento | Conversación 15 + Decisión 20 | — |
| BR-033 | CON-001/002, EVA-003 | rubric eval | sin datos demográficos/síntomas/medicación inventados | Conversación 15 | — |
| BR-034 | VOI-014 | E2E/video (AC-E2E-004) | interrupción cancela locución antes de otra | Voz 15 · Gate: voz realtime | **Pendiente-T0** (OQ-001, OQ-008) |
| BR-035 | CON-003, SAFE-002 | ambiguous E2E | aclaración cuando una expresión cambia el nivel de riesgo | Conversación 15 + Decisión 20 | — |
| BR-036 | RES-001, SUM-002, ORC-002 | state coverage test | cierre explica siguiente paso y revisión humana | Decisión 20 + Conversación 15 | — |

### 6.5 Datos, privacidad e IP (BR)

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| BR-040 | PRE-017/018, CH-003, SEC-002 | signed checklist | solo datos sintéticos/anonimizados/autorizados | Repo/proceso 15 (transversal, release blocker) | **Pendiente-T0** (OQ-003, OQ-010) |
| BR-041 | PRE-012, SEC-001 | secret scan (zero findings) | ningún secreto expuesto ni versionado | Repo/proceso 15 (transversal, release blocker) | — |
| BR-042 | SEC-002 | signed checklist | logs/capturas sin audio/PII salvo autorización | Repo/proceso 15 (transversal) | — |
| BR-043 | PRE-004, SEC-005 | asset review (every asset authorized) | sin info confidencial de Akron Children's/`caregaps-agent` | Repo/proceso 15 (transversal) | — |
| BR-044 | UX-009, SEC-005 | license record | logo/fotos/trade dress solo con permiso comprobable | Repo/proceso 15 + Video y demo 15 (activos) | — |
| BR-045 | DOC-007 | compliance check | MIT aplica solo al código propio | Repo/proceso 15 | **Pendiente-T0 parcial** (OQ-010) |
| BR-046 | PRE-004, SEC-004/005 | report/NOTICE | todo artefacto presumido público y reutilizable antes de incluir | Repo/proceso 15 (transversal) | **Pendiente-T0 parcial** (OQ-010) |

---

### 7. Requisitos no funcionales (NFR)

| ID | Ticket(s) | Test | Evidencia | Rúbrica/Gate | Estado |
|---|---|---|---|---|---|
| NFR-001 | PERF-002 | reproducible report | P50/P95 en formato oficial | Voz 15 | **Pendiente-T0** (OQ-005) |
| NFR-002 | PERF-001, VOI-013 | latency trace | fin de voz→audio ≤2.5s P95 (objetivo interno) | Voz 15 · Gate: voz realtime | **Pendiente-T0 parcial** (OQ-001, OQ-008 — objetivo interno usable ya; umbral oficial pendiente) |
| NFR-003 | PERF-001, VOI-014 | latency trace | barge-in cancela TTS ≤250ms P95 (objetivo interno) | Voz 15 · Gate: voz realtime | **Pendiente-T0 parcial** (OQ-001, OQ-008) |
| NFR-004 | REL-001 | clean-room timer | instalación/arranque limpio ≤15 min | Repo/proceso 15 · Gate: ≤15 min | **Pendiente-T0 parcial** (OQ-006) |
| NFR-005 | OBS-001 | chaos test (telemetría caída) | llamada continúa pese a fallo de telemetría secundaria | Soporte transversal (no listado en §11); DoD/reliability | — |
| NFR-006 | ORC-002, SAFE-003 | fail-safe unit test | fallo de decisión/citación/persistencia → estado seguro | Decisión 20 (ORC-002) | — |
| NFR-007 | SEC-001 | secret scan (zero findings) | cero secretos en Git/logs/capturas/imagen Docker | Repo/proceso 15 (transversal, release blocker) | — |
| NFR-008 | SEC-002, DB-002 | signed checklist + isolation test | minimización y separación de sesiones | Repo/proceso 15 (transversal); sustenta BR-002 | — |
| NFR-009 | UX-008, PRE-025 | automated + manual accessibility audit | WCAG 2.2 AA en contraste/teclado/foco/reduced motion | Ver **Huecos detectados** — UX-008 no listado en §11 | — |
| NFR-010 | DOC-001, FE-002 | browser test / prerequisites check | última versión estable Chrome/Edge soportada | Repo/proceso 15 (vía DOC-001) | — |
| NFR-011 | TST-001, SAFE-001 | coverage report | ≥80% reglas/contracts/RAG crítico; 100% ramas red flags | Repo/proceso 15 (TST-001) + Decisión 20 (SAFE-001) | — |
| NFR-012 | RAG-007, OBS-001 | trace test | 100% respuestas clínicas enlazadas a trace/citations | RAG 20 (RAG-007) | — |
| NFR-013 | AI-001, VOI-001/002, RAG-004 | contract test | LLM/STT/TTS/embeddings/storage detrás de adapters | Gate: modelo único (AI-001) + Voz 15 (VOI-001/002) | **Pendiente-T0 parcial** (OQ-001) |
| NFR-014 | TST-001/002/003, REP-003 | green run | typecheck/lint/unit/integration/E2E verdes | Repo/proceso 15 | — |
| NFR-015 | PRE-017, DOC-004 | reproducible appendix / rehearsal | casos demo reproducibles con seed/config versionados | Repo/proceso 15 + Video y demo 15 | — |

---

## 2. Cobertura de las 5 compuertas eliminatorias

Base: `plan.md` §10, expandida con los requisitos de `spec.md` que sustentan cada gate.

| Gate | Tickets owner (plan.md §10) | Test | Evidencia | Requisitos que la sustentan |
|---|---|---|---|---|
| **4 entregables** | DOC-002/003/006, FIN-008 | checklist release | URLs/hashes | FR-063, FR-064; apoyado por FR-055 (DOC-004 no está en la lista de §10 pero alimenta DOC-003), BR-045/046 |
| **≤15 min** | REP-003, REL-001, FIN-002 | clean-room timer | log/video | FR-060, NFR-004 · **Pendiente-T0 parcial** (OQ-006) |
| **modelo único** | CH-006, AI-001, SEC-006 | code/config/trace scan | model id | FR-061, NFR-013 · **Pendiente-T0** (OQ-001) |
| **voz realtime** | API-002, VOI-001/002/010–015 | E2E voice | video + P50/P95 | FR-010–016, NFR-002, NFR-003, BR-034 · **Pendiente-T0** (OQ-001, OQ-008) |
| **learn/forget** | RAG-008/009/011 | positive+deletion E2E | canaries + trace | FR-030–034, BR-011, BR-016, BR-017 |

**Ningún gate queda sin owner ni sin evidencia prevista.** Dos de los cinco (modelo único, voz realtime) tienen su test concreto condicionado a decisiones del 7 de agosto — el owner y el tipo de evidencia ya están definidos en `plan.md`, solo falta la instancia concreta (qué modelo, qué proveedor de voz).

---

## 3. Cobertura de los 6 criterios de rúbrica (100 pts)

Base: `plan.md` §11, expandida con los requisitos de `spec.md` que cubre cada criterio.

| Criterio | Puntos | Tickets principales (plan.md §11) | Requisitos que lo cubren |
|---|---:|---|---|
| RAG, precisión clínica y conocimiento vivo | 20 | RAG-001–011, EVA-001, UX-003/006 | FR-030–039, BR-010–017, NFR-012 (parcial) |
| Decisión y escalamiento | 20 | SAFE-001–004, ORC-002, EVA-002, UX-004 | FR-040–047, BR-020–027, NFR-006, NFR-011 (parcial) |
| Problema y conversación | 15 | CON-001–003, RES-001, SUM-002, EVA-003 | FR-020–025, FR-050–053 (parcial), BR-005, BR-006, BR-030–033, BR-035, BR-036 |
| Voz | 15 | VOI-001/002/010–017, PERF-001/002, UX-002 | FR-010–016, NFR-001, NFR-002, NFR-003, BR-034 · **Pendiente-T0** (OQ-001, OQ-008 para la implementación; OQ-005 para el formato de métricas) |
| Video y demo | 15 | PRE-021/024, DOC-005/006, FIN-004–006 | NFR-015; indirectamente todos los AC-E2E-00x (guion de demo los recorre) |
| Repositorio y proceso | 15 | REP-001–003, DOC-001/004/007, TST-001–003, FIN-001–003 | FR-055, FR-060–065, NFR-004, NFR-007, NFR-009 (parcial — ver huecos), NFR-010, NFR-011, NFR-014, NFR-015, BR-040–046 |

**Ningún criterio de rúbrica queda sin owner ni sin evidencia prevista.** El criterio "Voz" es el más expuesto a decisiones del 7 de agosto porque su implementación concreta depende de OQ-001/OQ-008, y su reporte de métricas depende de OQ-005.

---

## 4. Huecos y dependencias T0 (Pendiente-T0)

Requisitos cuya verificación concreta depende de una decisión abierta de `spec.md` §13 (7 de agosto). Total: **24 requisitos** (de 100).

| OQ | Pregunta (spec.md §13) | Requisitos Pendiente-T0 |
|---|---|---|
| OQ-001 | ¿Cuál es el modelo único y qué modalidades soporta? | FR-010–016, FR-061, NFR-002, NFR-003 (parcial), NFR-013 (parcial), BR-034 |
| OQ-003 | ¿Cuál es el schema, volumen y licencia del dataset? | FR-001, BR-004, BR-040 |
| OQ-004 | ¿Qué procedimientos/documentos cubre el corpus? | FR-001, FR-036, BR-013 (parcial) |
| OQ-005 | ¿Qué formato exacto de P50/P95, tokens y costo se exige? | FR-056, FR-065, NFR-001 |
| OQ-006 | ¿Qué significa exactamente "credenciales incluidas" en repo público? | FR-060 (parcial), NFR-004 (parcial) |
| OQ-008 | ¿Se permite STT/TTS externo o debe usarse un proveedor específico? | FR-010–016, NFR-002 (parcial), NFR-003 (parcial), BR-034 |
| OQ-010 | ¿Qué licencia aplica a dataset, documentos y starter? | FR-062 (parcial), BR-040, BR-045 (parcial), BR-046 (parcial) |

**No se adivinó ninguna decisión.** Donde `spec.md` §7 aclara que existe un "objetivo interno" que ya es utilizable antes del 7 de agosto (NFR-002, NFR-003), se marcó como *parcial*: el objetivo y su test unitario son implementables ya; solo el umbral/formato oficial y el proveedor concreto quedan pendientes.

**OQ-002, OQ-007 y OQ-009 no se atan a ningún requisito FR/BR/NFR específico** de `spec.md` (afectan la precisión de la suite de aceptación en general, el cronograma de cierre, y el disclosure de proceso en el informe, respectivamente) — no es un hueco de la matriz, es que esas preguntas operan a nivel de proceso/plan, no de requisito individual. Se deja constancia explícita para que no se lean como huecos.

---

## 5. Huecos detectados

Verificación explícita realizada: se recorrieron los 49 FR, 36 BR y 15 NFR de `spec.md` uno por uno contra los tickets de `plan.md` §4–9 y contra las matrices §10/§11. Resultado:

1. **FR-004** (consentimiento en el flujo de demo) — **RESUELTO 23 jul:** la resolución quedó asignada a CH-008 (delta de requisitos en T0), cuyas tareas en `plan.md` ahora incluyen "resolver FR-004 (consentimiento) según exigencia de la ficha" con aceptación "FR-004 con ticket o descope registrado". La cobertura técnica base sigue en ORC-001 (estado `consent` de la FSM).

2. **FR-054** (exportar evidencia de demo en JSON/CSV) — **RESUELTO 23 jul:** se creó el ticket **DOC-009 Export de evidencia de demo** (P1, 30m) en la tabla de Entregables de C4 en `plan.md`, con aceptación "archivo exportado validado contra schema" y prohibición de secretos/datos no autorizados.

3. **UX-001, UX-005, UX-007, UX-008, UX-009** sustentan requisitos reales (layout de llamada, línea de tiempo de auditoría FR-053, estados vacíos/error, accesibilidad NFR-009, imágenes autorizadas BR-044) pero **no aparecen en la matriz de rúbrica `plan.md` §11**, que solo cita UX-002/003/004/006 entre los tickets UX. No es necesariamente un error — puede ser intencional si esos tickets se consideran infraestructura de calidad transversal — pero el punto exacto de los 100 al que aportan no está explícito hoy. Están cubiertos por el Exit gate de C3 ("flujo crítico accesible por teclado") como bloqueante de fase, no como puntos de rúbrica. **Recomendación:** decidir explícitamente si se añaden a §11 o si se documenta que son bloqueantes de gate y no de puntuación.

4. **NFR-005, NFR-007, NFR-008** (disponibilidad de telemetría, cero secretos, minimización/privacidad) no están listados en ningún ticket de la matriz de rúbrica `plan.md` §11 ni de gates §10. Se tratan correctamente como bloqueantes de la lista "Antes de enviar" (`plan.md` §16: "0 secrets/PHI/IP blockers") en vez de como puntos de rúbrica — esto es consistente con que la seguridad/privacidad es un requisito de *pase/no pase*, no un criterio puntuado. Se deja constancia para que no se interprete como omisión.

5. No se detectaron requisitos de `spec.md` sin ningún ticket ni mención en `plan.md`, salvo los dos casos (1) y (2) anteriores.

6. No se detectó ningún gate o criterio de rúbrica sin owner o sin evidencia esperada — la cobertura de las secciones 2 y 3 de este documento es completa frente a `plan.md` §10/§11.

**Conclusión (actualizada 23 jul):** los 100 requisitos tienen ticket(s) responsable(s) identificado(s) — mapeados o marcados `Pendiente-T0` con su OQ. Los dos huecos originales (FR-004, FR-054) fueron resueltos el mismo día: FR-004 → CH-008 (decisión en T0), FR-054 → DOC-009 (nuevo ticket C4). Quedan como observaciones no bloqueantes los puntos (3) y (4).
