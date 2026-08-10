# Care Companion — Arquitectura implementada

> v2.0 · 9 de agosto de 2026. Este documento describe el sistema que existe
> en el repositorio y reemplaza la propuesta previa a la publicación del kit.

## 1. Objetivo y alcance

Care Companion es un agente de voz en español para seguimiento
postoperatorio. Inicia una llamada desde el navegador, recibe el contexto
longitudinal del paciente, entrevista de forma adaptativa, recupera evidencia
clínica vigente, clasifica riesgo y persiste un resumen auditable. Ante una
señal de alarma registra un handoff a revisión humana y cierra la llamada tras
confirmar dos teléfonos.

El sistema usa datos sintéticos del concurso. No implementa telefonía,
diagnóstico, prescripción, EHR ni comunicación hospitalaria real.

## 2. Drivers de arquitectura

1. Arranque limpio en menos de 15 minutos siguiendo el README.
2. LLM perteneciente a una familia permitida y verificable en configuración y
   trazas.
3. Voz en tiempo real desde navegador.
4. Learn/retrieve/forget desde la consola con versión y citas.
5. Asimetría clínica: un falso negativo es más grave que un falso positivo.
6. Métricas sostenibles por logs: voz P50/P95, tokens, invocaciones, RAG y
   costo por llamada.

No existe un umbral oficial de 2,5 s. Esa cifra fue una meta interna inicial;
la arquitectura instrumenta la latencia observada en lugar de ocultarla.

## 3. Vista de contenedores

| Contenedor | Tecnología | Responsabilidad |
|---|---|---|
| Web | Next.js, React, TypeScript | `/call`, `/knowledge`, `/audit`, STT/TTS y medición voz-a-voz |
| API | FastAPI, Python, Pydantic | REST, WebSocket, orquestación, agentes, seguridad, RAG y auditoría |
| Persistencia | SQLite WAL | Sesiones, turnos, evidencia, decisiones, métricas y resúmenes |
| LLM principal | Groq, `llama-3.3-70b-versatile` | Extracción, evaluación model-based y redacción grounded |
| LLM opcional | Ollama, `llama3.2:3b` | Resguardo local permitido si Groq falla |

Docker Compose publica la API en `49317` y la web en `49318`. El volumen
`care_companion_data` conserva dataset, corpus, índice y sesiones. El primer
arranque descarga 4 XLSX y 107 PDF, ejecuta OCR sobre el documento escaneado e
indexa el corpus antes de declarar la API lista.

## 4. Frontend

### 4.1 `/call`

- presenta 40 pacientes únicos como tarjetas buscables;
- muestra nombre, procedimiento y fecha de cirugía;
- al seleccionar uno muestra su evolución de días 1/3/7/14;
- al iniciar la llamada colapsa la selección y prioriza voz, conversación,
  evidencia y riesgo;
- el campo de texto aparece solo como fallback cuando SpeechRecognition no
  está disponible.

### 4.2 `/knowledge`

Es la consola de administración exigida por G5. Lista documentos, carga
`.txt`/`.md`/`.pdf`, muestra estado `ready`, permite borrar material agregado
por el usuario y verifica aprendizaje/olvido con consultas canarias. El corpus
oficial está identificado y protegido contra borrado accidental.

### 4.3 `/audit`

Selecciona la llamada terminada más reciente y muestra paciente,
procedimiento, duración, decisión, citas, handoff, contactos, seguimiento
estructurado y timeline de eventos. Las etiquetas técnicas de estado/riesgo se
traducen a lenguaje humano en presentación.

## 5. Datos longitudinales

El kit contiene 40 pacientes y 160 episodios: cuatro trayectorias por paciente
en los días 1, 3, 7 y 14. `DatasetCaseAdapter` une los tres XLSX de perfil y
trayectoria mediante `patient_id`, conserva los IDs originales de cada episodio
y expone una entidad `ChallengeCase` por paciente.

El agente recibe como contexto:

- identidad sintética y procedimiento;
- fecha de cirugía y datos clínicos relevantes;
- evolución histórica de dolor, temperatura, movilidad, herida, apetito y
  sueño;
- observaciones persistidas de llamadas anteriores del propio sistema.

La trayectoria de referencia usada para evaluar el dataset no se inyecta como
si fuera un síntoma actual. La llamada nueva produce un `followup_record` v1.2
con los mismos seis ejes, decisión, alerta y trazabilidad.

## 6. Orquestación

`CallCycleOrchestrator` coordina una FSM tipada:

```text
created → consent → interviewing → retrieving → deciding
        → responding → interviewing | summarizing → closed
                         ↘ escalated → summarizing → closed
                         ↘ fail_safe → summarizing | closed
```

Solo `CallOrchestrator.transition()` puede cambiar de estado. Los agentes no se
llaman entre sí y no controlan el flujo:

| Componente | Puede hacer | No puede hacer |
|---|---|---|
| `InterviewAgent` | extraer observaciones y proponer una pregunta | decidir riesgo o inventar datos actuales |
| `RetrievalAgent`/servicio | recuperar fragmentos activos y aplicables | responder al paciente |
| `TriageAgent` | proponer riesgo rutinario/moderado/alto del modelo | producir/rebajar una alerta determinista |
| `ResponseAgent` | redactar una respuesta breve sustentada | diagnosticar, prescribir o afirmar sin evidencia |
| `SummaryBuilder` | proyectar hechos persistidos a `CallSummary` | completar ausencias como negaciones |

Cada agente recibe un `AgentRequest`, devuelve `AgentResult`, tiene un deadline
y admite como máximo un reintento de salida inválida.

## 7. Flujo por turno

1. El navegador finaliza STT y envía `client.turn_text` por WebSocket.
2. Se persiste el turno original.
3. El detector determinista inspecciona el texto crudo con negación y contexto.
4. `InterviewAgent` extrae observaciones y decide si falta aclarar.
5. El RAG recupera evidencia por procedimiento y versión de conocimiento.
6. `RuleEngine` y `TriageAgent` producen entradas independientes de decisión.
7. `reduce_decision` aplica precedencia no degradable.
8. `ResponseAgent` responde si hay evidencia; el handoff crítico usa copy
   determinista y no llama al LLM.
9. La API envía estado, respuesta, decisión y, si termina, resumen.
10. El navegador inicia TTS y reporta la latencia voz-a-voz.

## 8. Seguridad clínica

Precedencia:

```text
HARD_RED_FLAG
> DATA_INTEGRITY_FAILURE
> EVIDENCE_INSUFFICIENT_WITH_RISK
> MODEL_HIGH_RISK
> MODEL_MODERATE_RISK
> ROUTINE_FOLLOW_UP
```

Las señales duras se detectan sobre texto crudo y observaciones normalizadas:
fiebre alta medida, dificultad respiratoria, pérdida de conciencia/confusión,
sangrado, dolor que empeora/no cede/insoportable, solicitud explícita de
urgencia y combinaciones clínicas versionadas. La negación se evalúa antes de
activar una señal.

Invariantes:

- el LLM nunca rebaja una señal determinista;
- “muy mal” inicia un microtriaje breve, no escala por sí solo;
- silencio, falta de dato y ambigüedad son `not_assessed`, no `denied`;
- ante fallo técnico con riesgo se abstiene/escala;
- el handoff es idempotente;
- el cierre crítico solicita teléfono principal y alternativo y finaliza en
  forma automática.

## 9. RAG y conocimiento vivo

Pipeline:

```text
archivo → validación → extracción/OCR → chunks → FTS5 + embeddings
       → consulta canaria positiva → status ready + knowledge_version
```

La recuperación combina BM25/FTS5 y coseno mediante Reciprocal Rank Fusion.
El arranque reproducible utiliza `LocalHashEmbeddings`, representación local de
n-gramas; `OpenAICompatEmbeddings` permite BGE-M3 por Ollama. El evidence gate
solo entrega fragmentos activos, vigentes y aplicables al procedimiento.

El borrado elimina chunks e invalida caché, incrementa `knowledge_version` y
solo confirma éxito tras una canaria negativa. Las sesiones fijan la versión
vigente al crearse, evitando mezclar conocimiento dentro de una llamada.

## 10. Voz

`useVoiceSession` usa Web Speech API:

- STT y TTS en el navegador;
- half-duplex y supresión por similitud para evitar eco del agente;
- barge-in: voz nueva cancela la locución;
- el micrófono se detiene en estados terminales, pero la última respuesta se
  reproduce antes de apagar el modo voz;
- `CallModal` mide fin de habla→inicio de audio y persiste la muestra.

La compatibilidad objetivo es Chrome/Edge. SpeechRecognition puede depender de
servicios del navegador; no se almacena audio bruto.

## 11. Persistencia y observabilidad

Tablas principales: `sessions`, `turns`, `observations`, `decisions`,
`escalations`, `followup_records`, `documents`, `document_chunks`, `citations`,
`events` y `knowledge_version`.

Cada evento incluye `correlation_id`, componente, tipo, payload, latencia y
fecha. `/metrics` separa:

- latencia de servidor (`turn.response_sent`);
- latencia voz-a-voz (`client.voice_latency_reported`);
- uso/costo de llamadas cerradas con `provider` y `model` reales.

Las sesiones abiertas, dobles de prueba y registros sin modelo verificable no
entran en denominadores por llamada. La telemetría secundaria es fail-open; las
decisiones, citas y escalamiento son persistencia clínica crítica.

## 12. API implementada

| Método | Ruta | Función |
|---|---|---|
| GET | `/health` | salud de API/DB |
| GET | `/api/v1/cases` | pacientes/casos disponibles |
| POST | `/api/v1/sessions` | crear llamada y mensaje de apertura |
| GET | `/api/v1/sessions/{id}` | estado de llamada |
| POST | `/api/v1/sessions/{id}/finish` | cierre explícito seguro |
| POST | `/api/v1/sessions/{id}/voice-latency` | persistir muestra voz-a-voz |
| WS | `/ws/sessions/{id}` | turnos y eventos conversacionales |
| GET/POST/DELETE | `/api/v1/documents...` | conocimiento vivo |
| GET | `/api/v1/search` | consulta RAG verificable |
| GET | `/api/v1/audit/sessions` | listado de auditoría |
| GET | `/api/v1/audit/sessions/{id}/trace` | traza completa |
| GET | `/api/v1/metrics` | métricas de rúbrica |

## 13. Reproducibilidad y seguridad operativa

`./levantar_app.sh` es idempotente: construye la primera vez, reutiliza
imágenes/volumen después y ofrece `--rebuild`, `--stop`, `--logs`, `--clean` y
`--local`. Si falta configuración, solicita una key Groq con entrada oculta y
crea `api/.env`; ningún secreto se versiona o llega al frontend.

El repositorio usa lockfiles, MIT para el código propio, NOTICE de terceros,
secret scanning, ruff, pytest, TypeScript, lint y build de Next.js.

## 14. Riesgos conocidos

| Riesgo | Mitigación actual |
|---|---|
| Cuota Groq | cero reintentos en llamada + resguardo Ollama opcional |
| Latencia voz elevada | medición real, respuestas breves y trabajo futuro fuera del camino crítico |
| Web Speech depende del navegador | Chrome/Edge declarados; fallback de texto |
| Corpus heterogéneo | validación, PDF protegido con contraseña vacía autorizada y OCR cacheado |
| Prototipo confundido con atención real | alcance explícito, datos sintéticos y handoff persistido sin integración externa |
