# Auditoría: kit oficial vs. estado del repositorio — 7 de agosto de 2026

> Disparada por la llegada del kit de construcción real (correo de Source Meridian, 7 ago
> 2026) contra `https://github.com/TechSphere2026/ParticipantArtifacts`. Este documento
> reemplaza las Decisiones pendientes del 7 de agosto anotadas en la raíz del `CLAUDE.md`
> del repo y en `docs/spec.md` §13 (OQ-001…OQ-010): esas preguntas ya tienen respuesta
> oficial, citada aquí con su fuente.
>
> Fuentes primarias descargadas y leídas completas: `README.md`,
> `docs/rubrica-evaluacion.md`, `docs/stack-tecnico.md` del repo oficial (commit `main` al
> 2026-08-07). El contenido de `dataset/` se auditó por metadata (README oficial + listado
> de árbol), no fila por fila — el volumen (4 `.xlsx` + 107 PDFs) no justificaba
> descargarlo completo para este documento.
>
> **Este documento es un punto-en-el-tiempo (snapshot del 7 de agosto, mañana).** Varios de
> los hallazgos marcados abajo como "falta"/"bloqueante" ya se implementaron esa misma
> tarde — el detalle de qué cambió y qué sigue abierto está en el **§9 Addendum**, al final.
> Las secciones 1–8 se dejan tal como se escribieron originalmente (valor de bitácora); no
> se editaron en retrospectiva para no perder el registro de qué se sabía y cuándo.

## 0. Resumen ejecutivo

La construcción anticipada (ADR-001) fue una apuesta correcta: hay un monolito FastAPI +
Next.js real, con máquina de estados tipada, agentes de responsabilidad única, motor de
decisión no degradable, RAG híbrido con learn/forget transaccional, WebSocket de sesión,
panel de auditoría y voz en tiempo real por navegador — 240+ tests verdes, arquitectura de
puertos/adaptadores lista para recibir el proveedor real. Eso sigue siendo cierto y sigue
siendo la base.

Pero el kit real trajo tres sorpresas que **invalidan supuestos concretos** sobre los que
se construyó, no solo detalles:

1. **No hay "el modelo obligatorio".** Hay una lista cerrada de 4 modelos a elegir —
   decisión resuelta en este documento (§3).
2. **El dataset no es un Delta Share externo.** Es un `dataset/` dentro del mismo
   repositorio del reto: 4 `.xlsx` con conversaciones reales, trayectorias clínicas,
   perfiles de paciente y demografía colombiana, más **107 PDFs** como corpus RAG. El
   `ChallengeCasePort` existente apunta a 3 casos ficticios inventados por el equipo, no al
   dataset real (§4.2).
3. **El corpus real es PDF y el sistema rechaza PDF explícitamente.**
   `upload_validation.py` lanza `pdf_not_supported` a propósito (era una decisión correcta
   *entonces*: no había necesidad demostrada). Hoy la necesidad está demostrada por 107
   archivos del propio kit — es el hallazgo más urgente de esta auditoría (§4.1).

A esto se suma que **el repositorio no tiene remoto de GitHub** (`git remote -v` vacío) y
el entregable 01 exige repo público — sin esto no hay entrega posible, independientemente
de cuánto funcione el resto.

Quedan **3 días** (7–10 de agosto) para: conectar un LLM real de la lista permitida,
levantar soporte de PDF, integrar el dataset real, publicar el repo, cronometrar el
arranque de 15 min con el flujo real, cablear tokens/costo en métricas, grabar el video y
cerrar el informe final con la declaración de modelo que exige G3.

## 1. Qué exige el kit oficial (fuente: repo `ParticipantArtifacts`)

### 1.1 El problema y qué construir

Agente de voz en español que hace la llamada de seguimiento postoperatorio: conversa con
un cuidador (no necesariamente el paciente), interpreta lenguaje ambiguo/regional
colombiano, responde con RAG sobre corpus clínico, decide si escalar a un humano y deja un
resumen estructurado. Dos superficies obligatorias, pueden vivir en una sola app:

| Superficie | Contrato funcional mínimo |
|---|---|
| Consola de administración | Subir documento · listar · eliminar · indicación "procesado y disponible" |
| Interfaz de llamada | Iniciar llamada de voz desde navegador · hablar (micrófono) · escuchar al agente |

Explícitamente fuera de alcance: telefonía real, integración hospitalaria real, auth
empresarial/roles, cobertura de todos los procedimientos médicos.

### 1.2 El dataset real (`dataset/` del repo oficial)

| Archivo | Contenido |
|---|---|
| `dataset_final.xlsx` | 3.991 filas × 13 columnas — **una fila es un turno, no una conversación**. 40 pacientes, 160 casos (paciente × día postop 1/3/7/14), dos capas (`capa1_limpia`/`capa2_ruidosa`), `label_ground_truth` (`verde`/`amarillo`/`rojo`) constante por `caso_id`. Clases desbalanceadas: 123 verde / 25 amarillo / 12 rojo. |
| `trayectorias_postop_silver.xlsx` | 160 filas — cuadro clínico real por caso (dolor, fiebre, movilidad, herida, apetito, sueño, arquetipo de recuperación). Es lo que el paciente vive y el agente **solo puede averiguar conversando**, no leer directo. |
| `perfiles_clinicos_pacientes_silver_contest.xlsx` | 40 filas — procedimiento, fecha de cirugía, edad, género, comorbilidades (lista JSON en celda de texto). |
| `perfiles_pacientes_co.xlsx` | 40 filas — demografía colombiana sintética (nombre, dirección, ciudad, departamento, documento, EPS); `adaptation_fields` (JSON en celda) lista qué se adaptó de una población base estadounidense. |
| `textos/` | **107 PDFs** en español/inglés, en 5 carpetas por escenario (dos con espacios en el nombre), con duplicados y **un PDF de `Appendicitis/` escaneado sin capa de texto** (necesita OCR o queda fuera). |

Join: `paciente_id` conecta los 4 archivos; `caso_id = "caso_" + trayectoria_id` conecta
conversaciones con trayectorias (no es un join directo por nombre). Todos los `.xlsx`
tienen una sola hoja llamada `result`. **"El material entregado no es todo el material de
evaluación"** — el jurado prueba con conocimiento clínico que el agente no habrá visto, lo
que valida (y exige) el flujo de learn/forget ya construido.

### 1.3 Las 5 compuertas eliminatorias (binarias — lo que no pasa, no se puntúa)

| # | Compuerta | Verificación |
|---|---|---|
| G1 | 4 entregables completos (repo, diagrama, informe, video) | antes de agendar evaluación |
| G2 | Levantable en ≤15 min siguiendo solo el README, credenciales incluidas | cronometrado en vivo; única corrección contemplada es credenciales rotas (24h, un reintento) |
| G3 | Modelo de la lista permitida, declarado y verificado contra dependencias/config/código | descalifica si se usa otro modelo |
| G4 | Voz en tiempo real funciona: saludo + pregunta trivial | "un chatbot de texto no compite" |
| G5 | Conocimiento vivo desde la consola: subir doc de prueba (no visto) → se usa; eliminar → se olvida | |

### 1.4 Los 6 criterios (100 pts)

| Pts | Criterio |
|---:|---|
| 20 | RAG, precisión clínica y conocimiento vivo |
| 20 | Lógica de decisión y escalamiento |
| 15 | Comprensión del problema y diseño de la conversación |
| 15 | Calidad de la conversación (voz) |
| 15 | Video de argumentación y demo (incluye 2 preguntas de cierre frente a cámara) |
| 15 | Repositorio, proceso y buenas prácticas |

Principio explícito: **asimetría clínica** — un falso negativo (no alertar cuando había
que hacerlo) pesa más que un falso positivo, y puede anular por sí solo el criterio de
decisión/escalamiento si es reincidente.

### 1.5 Métricas obligatorias en el README (no opcionales)

- Latencia **P50/P95**, medida desde que el paciente termina de hablar hasta que **empieza
  a sonar** el audio del agente (no hasta que el LLM responde — incluye TTS).
- Tokens de entrada/salida por turno y por llamada, invocaciones al modelo por turno,
  consultas al RAG por llamada.
- Costo estimado por llamada (si corre local, extrapolar a precios de producción con el
  cálculo explicado).

Contrastado contra logs reales de la sesión: "reportar números que no se sostienen es peor
que no reportarlos".

### 1.6 Modelos permitidos (`docs/stack-tecnico.md` §1 — lista cerrada, G3)

| Modelo | Dónde | Notas del kit |
|---|---|---|
| Gemini 1.5 Flash | Nube, free tier | 15 RPM gratis, ventana de 1M tokens |
| Llama 3.1 70B vía Groq | Nube, free tier | LPU, latencia ultra-baja; Groq también da Whisper Large V3 gratis |
| Llama 3.2 (1B/3B) | Local CPU | 1B ≈ 1.2 GB RAM |
| Phi-3.5 Mini (3.8B) | Local CPU | ≈ 2.8 GB RAM, fuerte en seguir instrucciones |

Resto del stack (orquestación, voz, RAG, embeddings) es libre — las sugerencias del kit
(ChromaDB, BGE-M3, Kokoro-82M, Piper, Ollama) son referencia, no obligación.

## 2. Qué ya existe en el repositorio (inventario verificado)

No es una lista de intenciones: es código que corre y tiene tests. Estado por área:

| Área | Evidencia en el repo | Estado real |
|---|---|---|
| Máquina de estados de llamada | [api/app/domain/session_fsm.py](../api/app/domain/session_fsm.py), [api/app/orchestrator/call_cycle.py](../api/app/orchestrator/call_cycle.py) | Implementado, testeado |
| Agentes de responsabilidad única | [api/app/agents/](../api/app/agents/) (`interview`, `triage`, `response`, `support`) | Implementado, sin comunicación agente↔agente |
| Decisión no degradable | [api/app/domain/decision.py](../api/app/domain/decision.py) | Implementado; precedencia `HARD_RED_FLAG > … > ROUTINE_FOLLOW_UP` testeada contra intento de rebaje por el modelo |
| RAG (FTS5 + coseno + RRF) | [api/app/services/retrieval.py](../api/app/services/retrieval.py), [api/app/services/ingestion.py](../api/app/services/ingestion.py) | Implementado, learn/forget transaccional con canarias verificado en vivo |
| Evidence gate | [api/app/domain/evidence.py](../api/app/domain/evidence.py) | Implementado |
| WebSocket de sesión | [api/app/api/routes/ws.py](../api/app/api/routes/ws.py) | Implementado, probado E2E |
| Auditoría / métricas | [api/app/repositories/audit.py](../api/app/repositories/audit.py), [api/app/api/routes/audit.py](../api/app/api/routes/audit.py) | P50/P95 con muestras reales; tokens/costo **hardcoded `pendiente`** (§4.6) |
| Consola de conocimiento | [web/src/app/knowledge/page.tsx](../web/src/app/knowledge/page.tsx) | Implementado (upload/list/delete/canaria en vivo) — cumple el contrato de G5 salvo por PDF (§4.1) |
| Interfaz de llamada | [web/src/app/call/page.tsx](../web/src/app/call/page.tsx), [web/src/lib/useVoiceSession.ts](../web/src/lib/useVoiceSession.ts) | Voz vía Web Speech API del navegador (STT+TTS+barge-in), no vía backend |
| Arranque de un comando | [levantar_app.sh](../levantar_app.sh), [docker-compose.yml](../docker-compose.yml) | Existe; **no cronometrado con datos/LLM reales todavía** |
| Puertos/adaptadores | [api/app/ports/](../api/app/ports/) (`llm`, `stt`, `tts`, `embeddings`, `challenge_case`) | Diseño correcto y ya validado por este mismo cambio de kit: conectar el proveedor real no debería tocar dominio |

Esta capa de puertos es la razón por la que la construcción anticipada sigue siendo un
activo neto pese a las sorpresas del kit: el *dominio* (FSM, decisión, evidence gate) no
cambia; lo que cambia son los adaptadores concretos y el `ChallengeCasePort`.

## 3. Decisión: modelo(s) de lenguaje (G3)

**Decisión tomada (7 ago 2026): Groq · Llama 3.1 70B como modelo primario, con Ollama
local (Phi-3.5 Mini o Llama 3.2 3B) como fallback si Groq no está disponible en el
momento de la evaluación.**

Justificación:

- **Mejor balance razonamiento/latencia de los 4 permitidos.** 70B parámetros para las
  20+20 pts de RAG/precisión clínica y lógica de decisión — donde un modelo de 1B–3.8B
  arriesga más el peor escenario de la rúbrica (falso negativo penaliza fuerte y puede
  anular el criterio). LPU de Groq da la latencia baja que exige el criterio de voz.
- **Encaja sin fricción en el patrón ya construido.** `Settings.llm_provider` ya tiene el
  valor `openai_compat` (base_url + api_key + model) en
  [api/app/core/config.py](../api/app/core/config.py); Groq expone
  `https://api.groq.com/openai/v1` compatible con ese mismo protocolo. **No hace falta un
  SDK nuevo**, solo un adapter HTTP (`httpx`, ya es dependencia) que implemente
  `LLMPort.generate` contra ese endpoint.
- **Groq también resuelve STT real gratis** (Whisper Large V3), lo que permite migrar la
  voz del navegador (Web Speech API, hoy dependiente de servicios de Google en Chrome, ver
  §4.5) a un STT propio detrás de `STTPort` si el tiempo alcanza — no es bloqueante para G4
  pero mejora el criterio de calidad de conversación y quita una dependencia opaca de
  terceros no declarada.
- **El fallback local cubre el riesgo real de la sesión en vivo**: si la red del jurado o
  la cuenta gratuita de Groq falla durante G2/G4, la demo entera se cae con un único
  proveedor de nube. Ollama expone el mismo protocolo `openai_compat` en
  `http://localhost:11434/v1`, así que el fallback es **configuración, no arquitectura
  nueva** — mismo adapter, otro `LLM_BASE_URL`.
- Se descartó Gemini 1.5 Flash como primario por friction/tiempo: no es compatible con el
  protocolo OpenAI de forma estable (requeriría un segundo adapter con SDK propio de
  Google) y su free tier de 15 RPM es más ajustado si cada turno dispara RAG + LLM + TTS
  frente al jurado. Queda como opción documentada, no implementada.

Lo que falta implementar concretamente (no hecho todavía, este documento es auditoría, no
el cambio de código):

1. `LLMProvider` en `config.py` hoy solo tiene `FAKE` y `OPENAI_COMPAT` genérico — separar
   o parametrizar para que `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` puedan apuntar a Groq o
   a Ollama sin ambigüedad, y decidir el mecanismo de fallback (¿reintento automático a
   Ollama si Groq responde error/timeout, o failover manual por env var?).
2. Adapter real en `api/app/adapters/` (p. ej. `openai_compat_llm.py`) que implemente
   `LLMPort.generate` sobre `httpx`, mapeando `usage.prompt_tokens`/`completion_tokens` de
   la respuesta a `LLMResult.input_tokens`/`output_tokens` — de eso depende directamente
   destrabar la métrica de tokens/costo de §4.6.
3. `_build_llm_adapter` en [api/app/main.py:128](../api/app/main.py#L128) hoy lanza
   `RuntimeError` explícito para cualquier proveedor que no sea `fake` — es el punto de
   enganche correcto, diseñado para esto.
4. Declarar la elección y su razón en el informe final (`docs/final-report.md`), tal como
   exige G3 explícitamente ("tu informe debe declarar cuál usaste y por qué").
5. `GROQ_API_KEY` es una credencial gratuita pero es una credencial: revisar
   `docs/policies/secrets.md` y el `.gitleaks.toml` ya existente para que no se filtre, y
   documentar en el README cómo el jurado la obtiene para el arranque de G2 (la rúbrica
   exige "credenciales incluidas" en el procedimiento de 15 minutos — vía `.env.example`
   con instrucciones, nunca la key real commiteada).

## 4. Hallazgos, de mayor a menor severidad

### 4.1 [Bloqueante] El corpus real es PDF; el sistema lo rechaza a propósito

`validate_upload` en
[api/app/services/upload_validation.py:106](../api/app/services/upload_validation.py#L106)
lanza `UploadRejected(code="pdf_not_supported")` para cualquier `.pdf`, con el comentario
"no hay librería de extracción aprobada". Era correcto bajo la política de dependencias
(`docs/policies/dependencies.md` §1: "necesidad demostrada") cuando no existía el reto real.
Hoy la necesidad la demuestran los 107 PDFs de `dataset/textos/`. Sin esto:

- G5 no se puede demostrar con el corpus real (aunque sí con un `.txt`/`.md` de prueba,
  que es lo que efectivamente verifica el jurado — leer bien la letra de G5: "un documento
  de prueba que no forma parte de ningún corpus entregado", así que G5 en sí *podría*
  pasar con un `.txt`; pero el criterio de 20 pts de RAG evalúa contra el corpus real, y
  ese es 100% PDF).
- El criterio de 20 pts "RAG, precisión clínica y conocimiento vivo" no se puede puntuar
  bien si el corpus nunca se cargó.

Acción: agregar extracción de texto de PDF (candidato: `pypdf`, licencia BSD, sin
dependencias nativas pesadas — compatible con `docs/policies/dependencies.md` §2.1) y
actualizar `rag_allowed_extensions` default. Aparte: uno de los PDFs de `Appendicitis/`
está escaneado sin capa de texto — decidir si se excluye, se documenta como límite conocido
del corpus, o se agrega OCR (probablemente fuera de alcance en 3 días; documentar la
decisión es suficiente).

### 4.2 [Bloqueante] El dataset real no está integrado; `ChallengeCasePort` apunta a casos inventados

`FixtureCaseAdapter` en
[api/app/adapters/fixture_cases.py](../api/app/adapters/fixture_cases.py) sirve 3 casos
ficticios ("Camila", "Julián", "Sofía") con un procedimiento genérico inventado. El
`ChallengeCase` (mismo archivo, líneas 26–34) tampoco tiene campos para lo que el dataset
real trae: trayectoria clínica (dolor/fiebre/movilidad/herida/apetito/sueño),
comorbilidades, EPS, capa de dificultad (`capa1_limpia`/`capa2_ruidosa`).

Esto importa más allá de "usar datos reales por prolijidad": el jurado prueba con
escenarios de decisión interpretados en vivo (§7 de la rúbrica) y con las clases
desbalanceadas reales (123 verde / 25 amarillo / 12 rojo) — el motor de decisión nunca se
ha ejercitado contra la distribución real ni contra `capa2_ruidosa` (respuestas evasivas,
info faltante, interrupciones de un familiar), que es exactamente el escenario de
"entradas adversas" que vale puntos en "Calidad de la conversación" y en "Comprensión del
problema".

Acción: nuevo adapter de `ChallengeCasePort` sobre los `.xlsx` (parseando con
`openpyxl`/`pandas` — evaluar cuál ya está disponible o cuál agregar bajo la política de
dependencias), respetando el join real
(`caso_id = "caso_" + trayectoria_id`, `paciente_id` como llave común, `comorbilidades` y
`adaptation_fields` como JSON embebido en celda). Ampliar `ChallengeCase` con los campos
clínicos reales que el `InterviewAgent`/`TriageAgent` necesitan para indagar en vez de leer
directo (la trayectoria es "lo que el paciente vive", no lo que se le entrega al agente).

### 4.3 [Bloqueante] El repositorio no está publicado en GitHub

`git remote -v` no devuelve nada; `gh repo view` confirma "no git remotes found". El
entregable 01 exige "repositorio público en GitHub" y G2 se verifica clonándolo. Sin esto
no hay entrega evaluable, sin importar el resto del estado. Acción: crear el repo remoto,
push, y confirmar visibilidad pública (no solo "no privado" — revisar org/settings).

### 4.4 [Alto] No hay ningún LLM real conectado

Solo existen `FakeLLM` y `ScriptedFakeLLM` en
[api/app/adapters/fake_llm.py](../api/app/adapters/fake_llm.py). `_build_llm_adapter` en
`main.py` falla rápido y a propósito para cualquier proveedor que no sea `fake` — buen
diseño defensivo, pero significa que **hoy G3 no se puede pasar** y ninguna de las
conversaciones/decisiones ha sido ejercitada contra un modelo real todavía (todo el
comportamiento observado hasta ahora es determinista/scripted). Ver plan de
implementación en §3.

### 4.5 [Medio] La voz depende de servicios del navegador, no de un adapter propio

`useVoiceSession.ts` usa `SpeechRecognition`/`SpeechSynthesis` nativos del navegador
(comentario propio en el archivo: "zero external provider"), lo cual en Chrome
efectivamente reenvía audio a servidores de Google para el reconocimiento — una dependencia
externa real, aunque no pase por el `STTPort`/`TTSPort` que sí existen en
[api/app/ports/stt.py](../api/app/ports/stt.py) y
[api/app/ports/tts.py](../api/app/ports/tts.py) y que hoy solo tienen adapters `fake`. No
es un incumplimiento de G3 (que solo restringe el LLM), pero sí dos riesgos:

- El jurado puede correr la sesión en un entorno sin Chrome/sin conectividad a los
  servicios de reconocimiento de Google, o con un navegador que no implemente
  `webkitSpeechRecognition` — G4 se juega en vivo.
- La latencia P50/P95 que exige la rúbrica es end-to-end (fin del habla → inicio del audio
  del agente); hoy esa medición mezclaría el tiempo del navegador con el del backend sin
  que el backend controle ni instrumente la parte de voz.

Acción sugerida (no bloqueante para G3, sí relevante para el criterio de voz y para tener
number honestos): evaluar mover STT a Groq Whisper (mismo proveedor que el LLM primario,
gratis, ya resuelto por la decisión de §3) detrás de `STTPort`, manteniendo Web Speech como
fallback de UI si el tiempo no alcanza.

### 4.6 [Medio] Tokens/costo por llamada están hardcodeados como "pendiente"

`GET /metrics` en
[api/app/api/routes/audit.py:60](../api/app/api/routes/audit.py#L60) devuelve
`{"status": "pendiente", ...}` fijo para tokens y costo — correcto mientras no había LLM
real (honestidad > números fabricados, coherente con la regla del kit de que "reportar
números que no se sostienen es peor que no reportarlos"), pero ahora es una dependencia
directa de §3: `LLMResult.input_tokens`/`output_tokens` ya existe en el contrato
([api/app/ports/llm.py](../api/app/ports/llm.py)), falta que el adapter real los llene con
el `usage` real de la respuesta de Groq/Ollama y que `audit.py` dejе de hardcodear
"pendiente" una vez haya muestras.

### 4.7 [Bajo] Inconsistencias menores de documentación

- `README.md` línea 127 dice "Licencia MIT (pendiente de archivo `LICENSE`...)" pero
  `LICENSE` ya existe en la raíz desde el commit `2e027aa` (DOC-007) — línea desactualizada.
- `docs/spec.md` §13 (OQ-001…OQ-010) sigue listando como abiertas preguntas que este
  documento ya responde con fuente oficial (modelo, dataset/schema, formato de métricas);
  vale la pena resolverlas explícitamente ahí o remitir a este documento, para que quien
  lea `spec.md` no reabra una pregunta ya cerrada.
- `docs/plan.md` (tickets DATA-001/AI-001) fue escrito anticipando un "Delta Share adapter"
  — el dataset real no es Delta Share, es `.xlsx` dentro del propio repo del reto. El
  ticket DATA-001 debería re-especificarse contra el formato real antes de ejecutarse.
- `CLAUDE.md` de este repo (raíz) tiene su "Registro de ejecución" cortado al 24 de julio y
  su sección "Decisiones pendientes del 7 de agosto" ahora resuelta por este documento —
  actualizar en el mismo cambio que se cierre esta auditoría, según la propia regla de
  mantenimiento de `CLAUDE.md` del monorepo hermano (`platform-core`) que aplica el mismo
  principio de higiene documental.

## 5. Compuertas eliminatorias — estado a 7 de agosto

| Compuerta | Estado | Qué falta |
|---|---|---|
| G1 Cuatro entregables | 🔴 Falta | Diagrama existe (`docs/architecture-diagram.md`), informe existe en borrador desactualizado, video no grabado, repo no publicado |
| G2 Arranque ≤15 min | 🟡 Parcial | Script y compose existen; no cronometrado con LLM real + dataset real + PDFs cargados (el costo de arranque cambia con dependencias nuevas de §4.1/§4.4) |
| G3 Modelo permitido | 🔴 Falta | Decisión tomada (§3), cero líneas de adapter real todavía |
| G4 Voz en tiempo real | 🟡 Parcial | Funciona en navegador con `fake` LLM; nunca probado con LLM real de punta a punta |
| G5 Conocimiento vivo | 🟢 Cumple con `.txt`/`.md` | El corpus real (PDF) no se puede probar hasta §4.1 |

## 6. Criterios de puntuación — lectura de riesgo

| Criterio | Riesgo si no se actúa |
|---|---|
| 20 · RAG y conocimiento vivo | Alto — corpus real nunca cargado (§4.1), citas nunca verificadas contra los 107 PDFs reales |
| 20 · Decisión y escalamiento | Alto — motor nunca ejercitado contra distribución real (123/25/12) ni `capa2_ruidosa` (§4.2); el kit pesa explícitamente el falso negativo |
| 15 · Comprensión y diseño de conversación | Medio — el diseño existe, pero las 4 trayectorias/día por paciente del dataset real no se han usado para afinar apertura/cierre/manejo de "se sale del guion" |
| 15 · Calidad de voz | Medio — depende de que G4 se pruebe con LLM real y de la dependencia de navegador (§4.5) |
| 15 · Video | Alto — no existe grabación; el guion (`docs/video/two-questions-script.md`) sigue con 11 marcas "PENDIENTE-T0" |
| 15 · Repositorio y proceso | Medio-alto — repo no público (§4.3) es automáticamente el peor caso posible de este criterio hasta que se resuelva |

## 7. Plan de acción sugerido (orden de dependencia, no de prioridad aislada)

1. **Publicar el repo en GitHub** (§4.3) — desbloquea todo lo demás, es gratis en tiempo.
2. **Adapter LLM real** (§3/§4.4): Groq primario vía `openai_compat`, con Ollama como
   fallback configurable. Sin esto no hay G3 ni datos reales de latencia/tokens.
3. **Soporte PDF en ingestión** (§4.1) + cargar el corpus real de `dataset/textos/` vía la
   consola de `/knowledge` — valida G5 y el criterio de RAG con datos reales, no ficticios.
4. **Adapter de `ChallengeCasePort` sobre el dataset real** (§4.2) — desbloquea probar
   decisión/escalamiento contra la distribución y el ruido reales.
5. **Cablear tokens/costo en `/metrics`** (§4.6) — depende de 2.
6. **Probar G4 de punta a punta con LLM real** y decidir si migrar STT a Groq Whisper
   (§4.5) o quedarse con Web Speech documentando el riesgo.
7. **Cronometrar G2 real** (arranque limpio, con `GROQ_API_KEY` de ejemplo, con el corpus
   cargado) y ajustar README si se pasa de 15 min.
8. **Informe final** (`docs/final-report.md`): declarar modelo + razón (exigido
   textualmente por G3), actualizar con lo realmente implementado (hoy fecha 24 jul,
   pre-kit).
9. **Diagrama**: confirmar que `docs/architecture-diagram.md` sigue correspondiendo al
   código real (el jurado toma elementos del diagrama al azar y los busca en el código).
10. **Video**: grabar demo + responder las 2 preguntas de cierre frente a cámara, usando
    `docs/video/two-questions-script.md` como base ya preparada.

## 8. Riesgos abiertos

- **Tiempo**: 3 días para 10 elementos de la lista de §7, varios con dependencias
  cruzadas (LLM real bloquea métricas y G4 real; dataset real bloquea probar decisión).
- **Cuenta Groq/Ollama en la sesión del jurado**: si la evaluación en vivo no tiene acceso
  a internet o a la cuenta gratuita de Groq (rate limit, caída del servicio), el fallback a
  Ollama local debe estar realmente probado, no solo configurado — un fallback nunca
  ejercitado es, en la práctica, no tener fallback.
- **Volumen del corpus real** (107 PDFs, algunos duplicados, uno sin capa de texto,
  carpetas con espacios en el nombre) contra `rag_max_upload_bytes`/tiempo de ingestión —
  puede exponer límites de rendimiento del pipeline actual que nunca se probaron a esta
  escala (el corpus de pruebas hasta ahora fue mucho más chico).
- **`docs/plan.md`/`docs/spec.md`** quedan con referencias a un "Delta Share" y a "el
  modelo obligatorio" (singular) que no corresponden a la realidad del kit; si no se
  actualizan, cualquier ejecutor (humano o agente) que los lea de nuevo puede re-derivar
  trabajo contra el supuesto viejo.

## 9. Addendum (7 ago, misma tarde) — qué se implementó tras esta auditoría

Ejecutado en la misma sesión, después de escribir §0–§8. `make verify` = 266 tests
(ruff limpio). Commits en `git log`; detalle también en el "Registro de ejecución" de
`CLAUDE.md`.

| # | Hallazgo original | Estado ahora |
|---|---|---|
| §4.3 | Repo no publicado (bloqueante) | **Resuelto.** `github.com/sebasga79/care-companion`, público. |
| §4.4 / §3 | Ningún LLM real conectado (alto) | **Resuelto.** `OpenAICompatLLM` ([api/app/adapters/openai_compat_llm.py](../api/app/adapters/openai_compat_llm.py)) + `FallbackLLM` ([api/app/adapters/fallback_llm.py](../api/app/adapters/fallback_llm.py)) tras `LLMPort`. `LLMProvider` allowlist pasó de `fake\|openai_compat` a `fake\|groq\|ollama` (`app/core/config.py`), con defaults de `base_url`/`model` por proveedor y validación de credenciales al arranque (Groq exige `LLM_API_KEY` real; Ollama no). `_build_llm_adapter` en `main.py` arma primario + resguardo opcional vía `LLM_FALLBACK_PROVIDER`. 14 tests con `httpx.MockTransport` (éxito, HTTP 4xx/5xx, red caída, forma inesperada, `response_schema`→`json_object`, fallback activándose/no activándose, ambos fallando). **No probado contra la API real de Groq/Ollama todavía** — el mock cubre el contrato HTTP, no la disponibilidad/latencia/calidad real del proveedor en vivo; sigue pendiente antes de la sesión de evaluación. |
| §4.1 | Corpus real es PDF, sistema lo rechaza (bloqueante) | **Resuelto.** `pypdf` (BSD, ver §3 de dependencies.md) agregado; `app/services/pdf_extraction.py` extrae texto por página y rechaza explícito PDF cifrado/corrupto/sin texto (`pdf_encrypted`/`pdf_unreadable`/`pdf_no_text_layer`). `chunk_document` ahora acepta `page`/`chunk_index_start`; cada chunk de PDF lleva el número de página real. `rag_allowed_extensions` default pasó a `txt,md,pdf`. `detect_declared_mime_mismatch` valida la firma `%PDF-` simétrico al chequeo existente de txt/md. 12 tests nuevos (extracción aislada + e2e vía `/api/v1/knowledge/documents`). **No probado contra los 107 PDFs reales del kit** — falta descargar `dataset/textos/` y cargarlo por la consola para validar a la escala/variedad real (nombres con espacios, duplicados, el PDF de `Appendicitis/` sin capa de texto). |
| §4.6 | Tokens/costo hardcodeados "pendiente" (medio) | **Resuelto en el lado de tokens; costo sigue condicionalmente pendiente.** `AuditRepository.usage_summary()` agrega tokens/invocaciones LLM/consultas RAG desde `events` reales (nuevo evento `rag.retrieval.completed` logueado una vez por turno en `call_cycle.py`). `/metrics` ya no fabrica nada: tokens se reportan "medido" en cuanto hay sesiones reales; costo queda "pendiente" hasta fijar `LLM_COST_PER_MILLION_INPUT_TOKENS`/`_OUTPUT_TOKENS` (deliberado — no se inventó un precio de Groq sin verificarlo contra su página de pricing vigente al momento de la entrega). |
| §4.2 | Dataset real no integrado, `ChallengeCasePort` con 3 casos inventados (bloqueante) | **Sigue abierto.** Es el ítem más grande que queda del plan de §7 (punto 4) — parsear los 4 `.xlsx`, resolver el join `caso_id = "caso_" + trayectoria_id`, y ampliar `ChallengeCase` con los campos clínicos reales. No se tocó en esta sesión. |
| §4.5 | Voz depende de Web Speech API del navegador (medio) | **Sigue abierto**, sin cambios. Groq Whisper como STT real queda disponible (mismo proveedor ya conectado) pero no se implementó. |
| §5/§6 gates y criterios | — | G3 pasa de 🔴 a 🟡: el adapter existe y tiene tests, pero **no se ha ejercitado ni una sola vez contra Groq/Ollama reales** ni contra el flujo de voz completo (G4) — de "declarado y verificado contra dependencias/config/código" solo falta la verificación en vivo. G1 sigue 🔴: repo ya público, pero informe (declarar el modelo, texto exigido por G3) y video siguen sin existir. |

**Lo que sigue siendo el plan, en orden** (§7 original, renumerado): (1) dataset real
(`ChallengeCasePort`, §4.2 — el más grande); (2) probar Groq/Ollama reales y el fallback en
condiciones reales, no solo mockeadas; (3) cargar el corpus real de 107 PDFs vía la
consola; (4) cronometrar G2 con todo lo anterior en su lugar; (5) probar G4 de punta a
punta con voz + LLM real; (6) informe final con la declaración de modelo que exige G3
textualmente; (7) diagrama actualizado; (8) video.

### 9.1 Segunda pasada (misma tarde) — foco explícito en "voz y respuestas"

El propietario pidió priorizar que el modelo de voz y las respuestas funcionen
correctamente antes de seguir con el dataset. Auditoría dirigida a esa ruta crítica
(`InterviewAgent`/`TriageAgent`/`ResponseAgent`, `agents/support.py`, `ws.py`,
`AuditRepository`) encontró y corrigió dos problemas reales, no cosméticos:

- **`/metrics` medía la latencia equivocada.** `BaseHTTPMiddleware` (de donde salía el
  único `latency_ms` persistido hasta ahora) no se ejecuta sobre conexiones WebSocket — así
  que P50/P95 promediaba latencia de tráfico HTTP administrativo (subir un documento,
  listar `/audit/sessions`) y **nunca** la del turno conversacional real. Corregido:
  `ws.py` instrumenta cada turno (`client.turn_text` → `server.agent_response` enviado)
  como evento `turn.response_sent`, y `AuditRepository.latency_percentiles()` ahora filtra
  estrictamente a ese `event_type`. Sin esta corrección, el número que iba a terminar en el
  README habría sido honesto en apariencia ("medido", con muestras) pero **factualmente
  otra cosa** frente a lo que pide la rúbrica — exactamente el tipo de discrepancia que la
  sesión de evaluación cruza contra los logs.
- **Interview/TriageAgent no pedían JSON mode al proveedor real y el parser no toleraba
  fences de markdown.** Con `FakeLLM`/`ScriptedFakeLLM` esto nunca se notó (siempre
  devuelven JSON limpio); un LLM real a veces envuelve la respuesta en ` ```json ... ``` `
  pese a que el prompt pida "solo JSON". Corregido: ambos agentes ahora pasan
  `response_schema={"type": "object"}` (activa `response_format=json_object` en
  `OpenAICompatLLM`) y `extract_json_payload` (`agents/support.py`) pela fences/prosa antes
  de `json.loads`. Sin esto, el riesgo concreto era que turnos perfectamente respondibles
  cayeran en `AgentInvocationError` → fail-safe/abstención por un problema de parsing, no de
  criterio clínico — indistinguible desde afuera de "el modelo no funciona".

`make verify` = 274 tests. **Sigue sin probarse contra la API real de Groq/Ollama** — las
dos correcciones de arriba se verificaron con `httpx.MockTransport`/`ScriptedFakeLLM`, no
con tráfico real; el propietario va a correr esa prueba con su propia API key.
