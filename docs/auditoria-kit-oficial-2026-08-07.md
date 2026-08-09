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
| §4.2 | Dataset real no integrado, `ChallengeCasePort` con 3 casos inventados (bloqueante) | **Resuelto (§9.3).** `DatasetCaseAdapter` parsea los 4 `.xlsx` reales, 160 casos verificados contra el dataset descargado de verdad. |
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

## 9.3 Tercera pasada (misma noche) — dataset real, RAG y hallazgos con datos reales

El propietario pidió releer con cuidado los requisitos de RAG del kit e implementar el
dataset real y la carga del corpus. Esta pasada descargó y probó contra los datos
**reales** del reto (no fixtures, no simulacros) — lo que expuso bugs que ningún test con
datos sintéticos pequeños había atrapado nunca.

**Esquema real confirmado con `openpyxl`** (no asumido — inspeccionado archivo por
archivo): `dataset_final.xlsx` (3.991 filas, columnas `dialogo_id/caso_id/paciente_id/
dia_postop/turno_idx/hablante/texto/label_ground_truth/estilo_paciente/.../capa`),
`trayectorias_postop_silver.xlsx` (160 filas, `dolor_nrs/fiebre_c/movilidad/herida/
apetito/sueno`), `perfiles_clinicos_pacientes_silver_contest.xlsx` (`modulo_synthea` mapea
1:1 a las 5 carpetas de `dataset/textos/`), `perfiles_pacientes_co.xlsx`. Confirmado: 160
casos, 123/25/12 verde/amarillo/rojo, 107 PDFs exactos en 5 carpetas (24+19+17+25+22) —
coincide con lo documentado en el README oficial.

**Decisión de embeddings** (pedida explícitamente antes de implementar): se consideró
Gemini embeddings y se descartó — no es open-weight (solo API cerrada de Google, aunque
tenga free tier) y hubiera sumado una segunda dependencia de nube en la sesión de
evaluación en vivo. Se eligió Ollama + BGE-M3 (el modelo que el propio kit sugiere),
reusando la infraestructura de Ollama ya decidida como resguardo del LLM.

### Qué se implementó

| Pieza | Archivo | Qué hace |
|---|---|---|
| Embeddings reales | [api/app/adapters/openai_compat_embeddings.py](../api/app/adapters/openai_compat_embeddings.py) | `EmbeddingsProvider` allowlist `fake\|ollama`, mismo patrón HTTP que el LLM. 10 tests con `httpx.MockTransport`. |
| Dataset real | [api/app/adapters/dataset_case_source.py](../api/app/adapters/dataset_case_source.py) | `DatasetCaseAdapter` parsea los 3 `.xlsx` de perfil/trayectoria (no `dataset_final.xlsx`, que es para un futuro arnés de evaluación), construye `caso_id = "caso_" + trayectoria_id`. `ChallengeCase` ampliado con edad/género/comorbilidades/ciudad/departamento/`ReferenceTrajectory` (cuadro clínico real — **nunca se pasa al prompt de `InterviewAgent`**, es contexto para quien actúa de paciente en la demo). `main.py` cae a `FixtureCaseAdapter` si el dataset no está descargado (nunca falla el arranque por esto). 13 tests con `.xlsx` construidos en el propio test + verificado contra los 160 casos reales. |
| Descarga del dataset | [api/scripts/fetch_dataset.py](../api/scripts/fetch_dataset.py) | Descarga los 4 `.xlsx` + 107 PDFs del repo oficial a `DATASET_DIR` (gitignored). Corrido de verdad: 127 MB, 107/107 archivos. |
| Carga del corpus al RAG | [api/scripts/load_corpus.py](../api/scripts/load_corpus.py) | Ingesta en lote vía el mismo `KnowledgeIngestionService` de la consola, etiquetando `applicability.procedure` por carpeta. |
| Retrieval acotado por procedimiento | [api/app/orchestrator/call_cycle.py](../api/app/orchestrator/call_cycle.py) | `CallCycleOrchestrator` ahora recibe `case_port` y pasa `applicability_filter={"procedure": ...}` a `hybrid_search` — **antes no pasaba ningún filtro**, así que con 5 procedimientos en la misma base, una sesión de apendicectomía podía recibir evidencia de un reemplazo de cadera. 1 test que ingesta 2 documentos con procedimientos distintos y confirma que solo el correcto aparece citado. |

### Bugs reales encontrados corriendo contra el corpus real (no hipotéticos)

Cada uno se descubrió porque el corpus real es grande y variado — ninguno era visible con
los fixtures pequeños de texto limpio que usan los tests hasta ahora. Los cuatro están
corregidos y cada uno tiene un test de regresión que falla sin el fix (verificado
revirtiendo el fix y confirmando que el test nuevo rompe):

1. **Citas nunca llegaban al resultado, aunque hubiera evidencia suficiente.**
   `evidence_fragments` se armaba como `{"title":..., "text":...}` — le faltan los campos
   que `CitationRef.model_validate()` exige (`citation_id`/`document_id`/`chunk_id`/etc.),
   así que `ResponseAgent` descartaba CADA fragmento en silencio (`except Exception:
   continue`) y `result.citations` quedaba vacío siempre, sin importar el intent. Directamente
   contradice el criterio de 20 pts "si cada respuesta clínica puede rastrearse hasta el
   documento que la sustenta" — nunca se podía. Corregido: se pasa `citation.model_dump()`
   completo más el campo extra `text`; Pydantic ignora el campo desconocido.
2. **El validador de nombre de archivo rechazaba ~70% de los PDFs reales.** El allowlist
   ASCII original (`^[A-Za-z0-9][A-Za-z0-9._-]*$`) no permitía espacios — y casi ningún
   título académico real carece de espacios. Tampoco tildes, paréntesis, comas. Corregido:
   deny-list (bloquea separadores de ruta, caracteres de control, metacaracteres de shell
   clásicos — ninguno aparece en los 107 nombres reales) en vez de allow-list ASCII.
3. **Límite de tamaño (2 MB) rechazaba PDFs académicos reales legítimos** de hasta 10 MB.
   Subido a 15 MB.
4. **La consulta canaria fallaba ~46% de las veces a partir de un corpus de tamaño
   moderado.** Toma las primeras 8 palabras del primer chunk como consulta de verificación
   — en un PDF real eso casi siempre es boilerplate de journal ("Contents lists available
   at ScienceDirect...", fechas de revisión) que decenas de documentos comparten. Con
   `top_k=5` (el de retrieval clínico normal), el chunk recién insertado quedaba fuera del
   top-5 aunque SÍ estuviera indexado — la carga se revertía por un falso negativo, no por
   un problema real. Corregido: la canaria usa `top_k=50`/`candidate_pool_size=500`,
   deliberadamente más generoso que el retrieval real (el propósito es "¿es localizable en
   absoluto?", no "¿rankea entre los mejores resultados?").

**Resultado verificado end-to-end** (no solo tests unitarios): `fetch_dataset.py` + `load_corpus.py`
corridos de verdad contra el repo oficial → **103 de 107 PDFs cargados** al RAG con
embeddings, chunking por página y `applicability` por procedimiento. Los 4 restantes son
rechazos legítimos ya conocidos por el propio kit: 3 PDFs protegidos con contraseña + el
PDF escaneado sin capa de texto de `Appendicitis/` que el README oficial ya advertía.
`DatasetCaseAdapter` sirve los 160 casos reales verificados contra el dataset descargado
(no simulado).

`make verify` = 310 tests, ruff limpio.

### Lo que sigue abierto

- **G3 sigue sin probarse contra Groq/Ollama reales** (heredado de §9.1/§9.2).
- **Voz sigue en Web Speech API del navegador** (§4.5, sin cambios).
- Cronometrar G2 con el dataset+corpus reales ya cargados (el arranque limpio nunca se
  midió con este volumen: 127 MB de descarga + ~9.000 chunks de embeddings).
- El informe final y el video (§4.7/plan original) no se tocaron.
- `docs/plan.md`/`docs/spec.md` siguen con referencias a "Delta Share" — actualizar antes
  de que alguien las relea sin este documento a mano.

## 9.4 Cuarta pasada — bugs encontrados probando `/call` con voz real en el navegador

Probando la llamada de voz de verdad (micrófono + parlantes de un portátil, no tests)
aparecieron tres fallos que ninguna prueba automatizada podía atrapar, porque los tres
sólo existen fuera del proceso: en el audio, en el navegador y en la base de datos real.

**1. Bucle de eco: la voz del propio agente entraba como turno del paciente.** En la
transcripción se veía literalmente al paciente "diciendo" la frase anterior del asistente.
El micrófono capta el TTS por los parlantes y `SpeechRecognition` lo transcribe como habla
del usuario; ese texto se enviaba por el WebSocket como `client.turn_text`. Peor: el
barge-in colgado de `onspeechstart` disparaba con la propia voz del agente, así que el
asistente se interrumpía solo en cada respuesta. La Web Speech API no da acceso al stream
de audio, así que no se puede activar cancelación de eco por hardware — se implementó
**supresión por contenido** ([web/src/lib/useVoiceSession.ts](../web/src/lib/useVoiceSession.ts)):
mientras el asistente habla (más una cola de 1,5 s, porque los `final` llegan tarde),
cualquier transcripción que solape ≥60 % de sus tokens con lo que se está diciendo se
descarta como eco. El barge-in real se conserva: habla que NO coincide con lo que decimos
sí interrumpe.

**2. La UI seguía escuchando después de que la llamada terminó.** Cuando el backend deja
la sesión en un estado que ya no acepta turnos (`summarizing`/`closed`/`escalated`/
`fail_safe` — complemento de `_ACCEPTS_TURN`), el micrófono seguía activo y cada frase
capturada producía un `server.error` en pantalla ("la sesión … no acepta turnos nuevos"),
que parecía un fallo del sistema cuando la llamada simplemente había terminado. Corregido
en [web/src/app/call/page.tsx](../web/src/app/call/page.tsx): al entrar en un estado
terminal se apaga la escucha, y `sendText` no envía en esos estados (defensa en
profundidad para turnos en vuelo).

**3. Falso positivo de escalamiento: saludar escalaba la llamada.** Dos turnos de saludo
("aló, buenas tardes" → "sí, con él habla") terminaban en `EVIDENCE_INSUFFICIENT_WITH_RISK`
y revisión humana. La cadena: `FakeLLM` marcaba el siguiente objetivo pendiente del
checklist como `uncertain` **sin mirar el contenido del turno**, y el segundo objetivo es
`FEVER` — un código que alimenta reglas clínicas deterministas. "Fiebre incierta" sin
evidencia dispara `evidence_insufficient_with_risk` → escalado. Corregido: el adapter
`fake` nunca declara `confirmed`/`uncertain` sobre códigos de regla clínica (`FEVER`,
`PAIN_WORSENING`, `WOUND_DISCHARGE`); usa `not_assessed`, que es la representación honesta
de "este adapter no evaluó esto" y por diseño no dispara reglas. La rúbrica evalúa
explícitamente el comportamiento "en situaciones donde escalar claramente NO es lo
correcto" — un saludo que alerta a una persona es justo el caso.

Además: el corpus se había cargado a una base temporal durante las pruebas, no a la que usa
la app (`api/data/care_companion.db`), así que `/call` corría con RAG vacío y toda respuesta
caía en abstención por falta de evidencia. Cargado a la base real: **102 documentos, 8.725
chunks**.

Los tres bugs tienen test de regresión, y el de escalamiento se verificó revirtiendo el fix
(el test falla con el mensaje exacto: "un saludo no debe escalar la llamada (turno 2)").
`make verify` = 311 tests; `pnpm build` + `pnpm lint` verdes.

## 9.5 Quinta pasada — el eco volvió, y el agente no conducía la entrevista

**El bucle de eco reapareció.** La supresión por contenido de §9.4 **no alcanzó**: los
fragmentos que el reconocedor entrega son cortos ("Gracias" = 7 caracteres, "por
contarme", "Gracias por") y caían bajo el umbral mínimo de longitud; bastaba que uno se
colara para realimentar el ciclo. La transcripción quedaba en un bucle infinito del
paciente "diciendo" trozos de la frase anterior del asistente.

Corregido cambiando de heurística a **half-duplex**: el reconocimiento se apaga
(`abort()`, que descarta lo capturado en vuelo) antes de emitir el primer sonido y se
reanuda cuando termina la locución. Elimina el bucle por construcción, no por umbral. Se
añadió un watchdog por si `onend` de `speechSynthesis` nunca dispara (bug conocido de
Chrome con textos largos) — sin él, el micrófono quedaría apagado y la llamada moriría en
silencio. La supresión por contenido se mantiene como segunda línea para la ventana de
reinicio, con umbral bajado a 3 caracteres.

**Costo aceptado y documentado:** se pierde el barge-in por voz mientras suena el audio.
Escuchar y hablar a la vez sin cancelación de eco por hardware no es posible, y la Web
Speech API no expone el stream. Un bucle infinito frente al jurado es catastrófico; perder
barge-in con parlantes abiertos es un demérito menor. Con audífonos el problema no
existiría, pero no se puede asumir el hardware del evaluador.

**El agente nunca preguntaba nada.** Hallazgo de producto, no de infraestructura: la
`next_question` que decide `InterviewAgent` se usaba **sólo como consulta de retrieval** y
se descartaba — nunca llegaba al `ResponseAgent` ni al paciente. El resultado era una
"llamada de seguimiento" que no recolectaba información: sólo reaccionaba, repitiendo la
misma frase. Afecta directamente dos criterios de la rúbrica: "cómo abre, conduce y cierra
el agente la conversación" (15 pts) y "si indaga antes de decidir" (20 pts).

Corregido: `ResponseTurnInput` lleva `next_question`, el prompt del sistema instruye
explícitamente a conducir la entrevista y cerrar con esa pregunta (excepto en `handoff`,
donde seguir el checklist sería incoherente), y el orquestador la pasa. `FakeLLM` ahora
rota por los objetivos pendientes del checklist según el número de turnos, en vez de
devolver una pregunta genérica fija.

Verificado end-to-end con una conversación de 5 turnos: el agente pregunta por objetivos
distintos en cada turno (ánimo → tolerancia a líquidos → fiebre), no escala, y no repite
la misma frase. `make verify` = 312 tests; `pnpm build` + `pnpm lint` verdes.

**Límite conocido del adapter `fake`:** no puede cerrar objetivos clínicos (nunca afirma
nada sobre fiebre/dolor/herida), así que con `LLM_PROVIDER=fake` la entrevista se queda
preguntando por el objetivo clínico pendiente y la llamada no termina sola — se cierra con
"Finalizar llamada". Es el comportamiento honesto para un adapter sin modelo; con Groq
real el checklist se cubre normalmente.

## 9.6 Sexta pasada — falso negativo crítico ante 40 °C, dolor y temor por la vida

Una prueba manual mostró el fallo clínico más grave encontrado hasta ahora. El paciente
reportó, en turnos sucesivos, dolor abdominal intenso y persistente, dolor al ingerir
alimentos o líquidos, necesidad percibida de hospitalización, 40 °C de fiebre y “me voy a
morir”. El agente repitió que todo estaba dentro de lo esperado y volvió a preguntar por
fiebre. No era solo una mala redacción: el motor determinista recibía únicamente las
`Observation` extraídas por el LLM. Con `LLM_PROVIDER=fake`, el adapter no interpreta
síntomas y entregaba `not_assessed`; por tanto las reglas nunca veían el texto literal.

La corrección añade defensa en profundidad sin convertir el fake en un pseudo-modelo:

1. `safety-signal-detector-v1` analiza siempre el texto crudo antes de aceptar una rama de
   aclaración del LLM. Reconoce temperatura numérica, dolor intenso/persistente,
   dificultad respiratoria, sangrado, cambios de herida, intolerancia oral y solicitudes
   explícitas de urgencia. Conserva texto y turno fuente, maneja negaciones y conectores,
   y una confirmación determinista no puede ser rebajada por el agente.
2. El ruleset sube a `rules-v2`. La temperatura numérica >38 °C produce `HIGH_FEVER` y
   `HARD_RED_FLAG`; una mención de “fiebre” sin valor permanece separada para evitar una
   ampliación clínica indiscriminada. El comparador estricto (`>`, no `>=`) se contrastó
   con el corpus oficial ya cargado: guías de apendicectomía, colecistectomía, cirugía
   intestinal y reemplazo articular usan “mayor/superior a 38 °C”. Dolor que empeora,
   dificultad respiratoria, sangrado y solicitud explícita de urgencia también tienen
   reglas auditables.
3. Los handoffs dejan de generarse con LLM: `safe-handoff-v1` produce un mensaje
   determinista según el nivel de decisión. Ante alerta dura detiene el cuestionario,
   explica las señales generales, pide valoración médica urgente y aclara que el
   prototipo no contacta por sí solo a un equipo real. El texto rutinario hardcodeado del
   `FakeLLM` ya no afirma normalidad; solo registra y continúa la pregunta.

La regresión WebSocket comienza con “buenas tardes” (no escala) y luego reproduce el
primer reporte de dolor de la conversación real. En ese mismo turno la sesión pasa a
`summarizing`, la decisión es `HARD_RED_FLAG`, se crea un único escalamiento y la respuesta
no contiene la frase de falsa tranquilidad. Pruebas unitarias adicionales cubren 40 °C,
36,5 °C, negación explícita, síntoma resuelto, conector adversativo, frases exactas de
dolor/hospitalización/temor por la vida y precedencia frente a una negación del LLM.

`make verify` desde la raíz: **330 tests recolectados, 327 passed, 3 skipped; ruff limpio**.

## 9.7 Séptima pasada — el handoff crítico se escribía, pero no se pronunciaba

Después de corregir el falso negativo de §9.6, la conversación manual ya produjo el
mensaje urgente correcto, pero únicamente en la transcripción: el TTS no pronunció la
última respuesta. La causa fue una carrera determinista entre el contrato WebSocket y el
ciclo de vida de voz del frontend, no un fallo del sintetizador.

Por cada turno, el backend envía los envelopes en este orden: `server.state`,
`server.agent_response`, `server.decision` y, si corresponde, `server.summary`. El handoff
deja la sesión en `summarizing`, por lo que `/call` recibía primero un estado terminal y
ejecutaba `voice.stop()`. Ese método combinaba tres responsabilidades: detener STT,
cancelar `speechSynthesis` y reanudar/desactivar el modo de voz. Cuando llegaba el envelope
de respuesta unos milisegundos después, React añadía el texto a la transcripción, pero
`voiceModeRef` ya era `false` y no llamaba a `speak()`.

Corregido en `useVoiceSession` separando `stopListening()` de `stop()`. Un estado terminal
ahora destruye únicamente el reconocimiento y evita nuevos turnos, pero conserva el modo
de salida el tiempo suficiente para encolar la respuesta final. Después de llamar a
`speak()` se desactiva el modo voz para cualquier mensaje posterior; `server.summary` no
cancela la locución. El control del micrófono también queda deshabilitado en estados
terminales. La protección half-duplex contra eco se conserva: no se vuelve a abrir STT al
terminar el TTS porque la referencia de reconocimiento ya fue eliminada.

Verificación ejecutada: `pnpm lint`, `pnpm exec tsc --noEmit`, `pnpm build` y `make verify`
(330 recolectados, 327 passed, 3 skipped) verdes. Queda como comprobación humana escuchar
el caso en Chrome con parlantes reales; Web Speech API no expone una señal automatizable
que pruebe que el sistema operativo emitió sonido.

## 9.8 Octava pasada — de formulario asistido a llamada agéntica

Una nueva prueba manual dejó cinco problemas de producto: el agente respondía “Gracias por
contarme” ante un saludo, nunca explicaba por qué llamaba, ignoraba procedimiento e historial,
repetía la misma muletilla/pregunta y la UI presentaba controles de operador (“Escribe lo que
dice el paciente” y “Simular alerta al equipo”). El motor sí persistía un escalamiento cuando
la decisión lo requería, pero la interfaz sugería incorrectamente que dependía de un clic.

### Decisión de alcance contrastada con el kit oficial

La [página oficial del reto](https://www.sourcemeridian.com/tech-sphere-challenge) describe
un agente que realiza la llamada, conversa, se adapta y decide cuándo generar una alerta. El
[README de ParticipantArtifacts](https://github.com/TechSphere2026/ParticipantArtifacts)
exige iniciar una llamada de voz desde el navegador, hablar por micrófono y escuchar al agente;
no exige telefonía real, EHR ni integración hospitalaria. La rúbrica evalúa apertura,
conducción, adaptación fuera de guion, registro/persistencia de la alerta y resumen final.
Conclusión: seleccionar un caso e iniciar la llamada es una concesión legítima del demo; enviar
cada turno o disparar manualmente la alerta no lo es.

“Alertar a un humano” se implementa hasta el límite autorizado y verificable del reto: el
backend crea automáticamente un `EscalationRecord` idempotente y persistente, detiene el
cuestionario, lo refleja en resumen/auditoría y comunica al paciente el siguiente paso. No se
finge haber llamado o enviado mensajes a un hospital: esa última milla necesita un canal real,
credenciales y autorización institucional que el reto no entrega ni requiere.

### Cambios implementados

1. **Apertura automática y contextual.** `POST /sessions` persiste el primer turno del agente,
   avanza la FSM a `interviewing` y devuelve `opening_message`. La apertura saluda, explica el
   propósito, nombra el procedimiento y el tiempo desde la cirugía y pregunta cómo se siente
   hoy. `/call` la muestra y la pronuncia por TTS al abrir el WebSocket; activa escucha sin un
   segundo clic.
2. **Memoria clínica acotada.** `ChallengeCase.patient_id` enlaza seguimientos del mismo
   paciente. Los agentes reciben hasta tres llamadas anteriores cerradas, derivadas solo de
   observaciones y decisiones persistidas. La trayectoria de referencia (`dolor_nrs`, fiebre,
   herida, etc.) sigue excluida por construcción: el kit la define como verdad oculta que el
   agente solo puede descubrir conversando.
3. **Interpretación antes de secuenciar.** El checklist ahora cubre las siete dimensiones del
   dataset (estado general, dolor, ingesta, fiebre, herida, movilidad y sueño). Un saludo puro
   no crea observaciones. Se extrae toda información explícita aunque llegue fuera del orden;
   después de fusionar extracción LLM + detector determinista, el orquestador valida que la
   próxima pregunta siga pendiente. La consulta RAG usa el texto actual del paciente, no la
   pregunta siguiente.
4. **Conversación menos mecánica.** ResponseAgent responde saludos como saludos y prohíbe la
   muletilla fija “Gracias por contarme”. El adapter `fake` reconoce formas sociales y señales
   comunes suficientes para que la demo local no avance por conteo de turnos ni invente que un
   objetivo quedó cubierto.
5. **Handoff automático visible.** Se eliminó “Simular alerta al equipo”. El panel muestra
   monitoreo automático y solo marca handoff cuando el envelope de decisión confirma el
   escalamiento persistido por backend. El compositor textual se oculta en navegadores con
   voz y queda exclusivamente como fallback técnico si SpeechRecognition no existe.
6. **Resumen completo.** `CallSummary.procedure`, que existía en el schema pero siempre quedaba
   `null`, ahora se llena desde el caso para cumplir el contenido mínimo de la rúbrica.

Pruebas añadidas/actualizadas: apertura y primer turno persistido, memoria de seguimiento
previo, exclusión de `reference_trajectory`, saludo natural sin muletilla, handoff automático
en el resumen, cobertura completa del checklist, semántica exacta de 38 °C y `patient_id` del
dataset. Verificación: **334 tests recolectados, 331 passed, 3 skipped**; ruff, ESLint,
TypeScript y build Next.js de producción verdes.

## 9.9 Novena pasada — caracterización del dolor, contacto y cierre automático

La prueba manual posterior a §9.8 mostró que la nueva red de seguridad era demasiado
agresiva para una frase aislada: “sigo muy inflamado y me duele mucho” se normalizaba como
`PAIN_WORSENING`, activaba `HARD_RED_FLAG` y detenía la entrevista sin preguntar dónde dolía,
qué intensidad tenía ni si estaba mejorando. Además, el handoff terminaba la sesión antes de
confirmar cómo localizar al paciente y el copy visible explicaba repetidamente que era un
prototipo, debilitando la demostración del producto.

### Separación entre dolor por caracterizar y dolor que empeora

`safety-signal-detector-v1` distingue ahora dos conceptos:

- `PAIN_SEVERE`: “me duele mucho”, dolor fuerte/intenso/persistente. No dispara por sí solo
  una alerta dura; prioriza tres objetivos conversacionales: ubicación exacta, intensidad de
  0 a 10 y evolución.
- `PAIN_WORSENING`: “cada vez peor”, “empeoró”, “no cede”, “insoportable”. Conserva la regla
  determinista no degradable `RF-002` y activa el handoff.

Si el paciente niega dolor, los tres detalles se consideran no aplicables y no se preguntan.
El adapter `fake` reconoce negaciones explícitas para no convertir “no tengo dolor/fiebre” en
una confirmación accidental.

### Handoff completo y fin autónomo de la llamada

Una decisión de escalamiento deja ahora la sesión en `escalated` como estado conversacional
acotado. El mensaje confirma que el reporte fue enviado al equipo de atención prioritaria y
pregunta el número principal. El siguiente turno solicita un número adicional de emergencia;
al confirmarlo:

1. ambos números quedan como observaciones `CONTACT_PRIMARY` y `CONTACT_EMERGENCY` con turno
   fuente y normalización determinista;
2. la traza de `/audit` los entrega y la UI los muestra junto al handoff;
3. el agente confirma que una persona contactará al paciente;
4. la FSM avanza `escalated → summarizing → closed`, persiste `closed_at`, pronuncia la
   despedida y el frontend cierra el WebSocket sin cancelar el último TTS.

Las llamadas rutinarias también terminan automáticamente cuando todos los objetivos quedan
cubiertos. Ya no dependen del botón “Finalizar llamada” para alcanzar `closed`.

### Decisión sobre la segunda página

La página no se elimina. La web oficial enumera como construcción obligatoria “una consola
para actualizar el conocimiento en caliente”, y la compuerta G5 elimina la entrega si subir y
eliminar conocimiento no funciona. Se renombró “Conocimiento” a **“Base clínica”**, se explicó
en la cabecera que demuestra learn/retrieve/forget sin reinicio y se habilitó `.pdf` en el
selector, coherente con el backend y el corpus oficial. “Auditoría” también se conserva porque
demuestra trazabilidad, decisiones, handoff y métricas exigidas.

La experiencia visible dejó de presentarse como “prototipo clínico”: encabezado, metadata,
footer, panel de handoff y respuesta hablada usan lenguaje de producto del caso simulado. La
documentación técnica mantiene las limitaciones reales y la naturaleza del concurso, donde sí
corresponde.

Regresión E2E completa: saludo → dolor fuerte (sin escalar) → ubicación → intensidad →
evolución peor → `HARD_RED_FLAG` → teléfono principal → teléfono alternativo → `closed` +
`server.summary`; además valida que ambos teléfonos aparecen en la traza humana. Verificación:
**336 tests recolectados, 333 passed, 3 skipped**; ruff, ESLint, TypeScript y build Next.js
verdes.

## 9.10 Décima pasada — bucle de herida y backend local desactualizado

Una nueva prueba hablada mostró esta secuencia incorrecta: “tengo dolor” avanzó al estado
general sin localizarlo y, más tarde, “está un poco roja e inflamada” provocó tres preguntas
idénticas sobre la herida. La inspección encontró dos causas distintas:

1. la API local había arrancado antes de la corrección de dolor y `levantar_app.sh` ejecutaba
   Uvicorn sin `--reload`; Next.js sí se actualizaba, de modo que la UI nueva podía conversar
   con lógica Python antigua;
2. el adapter determinista reconocía `WOUND_APPEARANCE` únicamente cuando la respuesta
   repetía “herida”, “secreción”, “olor”, etc. No comprendía la elipsis natural “está roja e
   inflamada” después de una pregunta cuyo sujeto ya era la herida.

El arranque local usa ahora `uvicorn --reload`. El adapter reconoce color, enrojecimiento e
inflamación como respuesta al aspecto de la herida y varía sus acuses según el contenido del
turno, sin anteponer siempre “Entiendo”. Además, el prompt de cada turno calcula objetivos cubiertos con la
misma función del orquestador: una negación de dolor no vuelve a introducir ubicación,
intensidad y evolución como pendientes fantasma.

Dos pruebas WebSocket reproducen las frases observadas. La primera exige que “un poco mejor,
pero tengo dolor” produzca “¿En qué parte exacta siente el dolor?” antes de estado general. La
segunda recorre dolor negado, estado general, ingesta, fiebre negada y herida roja/inflamada;
verifica que la siguiente pregunta sea movilidad y que la herida no se repita. Verificación:
**338 tests recolectados, 335 passed, 3 skipped**; ruff, ESLint, TypeScript, build Next.js y
validación sintáctica de `levantar_app.sh` verdes.

## 9.11 Undécima pasada — “muy mal”, microtriaje y decisión sobre Docker

La frase aislada “muy mal” disparaba `EMERGENCY_CONCERN`, por lo que el agente afirmaba haber
detectado una solicitud explícita de atención urgente y creaba el handoff sin saber qué le
ocurría al paciente. Esa normalización no era fiel al texto y fallaba precisamente el caso
ambiguo que la rúbrica exige indagar antes de decidir.

Se separó malestar inespecífico de una alarma concreta. “Muy mal”, “me siento terrible” y
formas equivalentes producen ahora una observación trazable de estado general y una única
intervención de microtriaje: pide el síntoma principal y pregunta por dificultad respiratoria,
desmayo/confusión, sangrado abundante, dolor insoportable, fiebre medida y vómito persistente.
No se ejecutan todavía retrieval, triage ni decisión. Si la respuesta contiene una señal
inequívoca, el detector sobre texto crudo la eleva inmediatamente a las reglas no degradables;
por ejemplo, “no puedo respirar” produce `HARD_RED_FLAG` y crea el reporte en ese turno.
Desmayo, pérdida de conciencia y confusión se incorporaron al detector y a `RF-008`; no se
pregunta por una señal que luego el motor sea incapaz de interpretar.

También se revisó G2. El requisito normativo es que la solución quede accesible en 15 minutos
siguiendo el README; el formulario oficial menciona explícitamente `docker-compose` entre las
formas aceptadas de declarar dependencias. Por decisión del propietario, Docker Compose se
mantiene como ruta recomendada para el jurado y `./levantar_app.sh` como alternativa local.
El compose ya no fuerza necesariamente el adapter de prueba: acepta
`LLM_PROVIDER=groq` y `LLM_API_KEY` desde el entorno, mientras mantiene `fake` únicamente
como smoke test sin secretos.

La primera ejecución real del build encontró dos defectos que una validación estática de
Compose no mostraba: Corepack descargaba pnpm 11 sin versión fijada y la política de scripts
ignorados fallaba; además, la imagen API ejecutaba `uv sync` antes de copiar el README exigido
por Hatchling. Se fijó `pnpm@10.28.0`, se separó la instalación de dependencias del proyecto
editable y se añadieron `.dockerignore` para ambos servicios. El contexto del frontend bajó
de aproximadamente 747 MB a 2,17 KB. Después, ambas imágenes construyeron, Compose levantó
API y web, `/health` quedó sano, `/call` respondió 200 y un turno WebSocket dentro del stack
devolvió el microtriaje esperado sin escalar “muy mal”.

Regresión viva y automatizada: “muy mal” permanece en `interviewing` y formula el microtriaje;
“no puedo respirar y siento que me voy a desmayar” produce `HARD_RED_FLAG` y handoff. Suite:
**343 tests recolectados, 340 passed, 3 skipped**; ruff, `git diff --check`, sintaxis del
script, build de imágenes y `docker compose up` verdes.

## 9.12 Duodécima pasada — launcher único e idempotente

La ruta Docker todavía obligaba al evaluador a recordar comandos de Compose y el script
`levantar_app.sh` servía únicamente para desarrollo local. Se unificó la entrada operativa:

```bash
./levantar_app.sh
```

El launcher inspecciona el estado antes de actuar. La primera ejecución construye imágenes y
crea servicios; con imágenes pero sin contenedores usa `up --no-build`; con contenedores
detenidos usa `compose start`; si `/health` y `/call` ya responden, no reinicia ni reinstala.
Después espera ambos endpoints, muestra las URLs y abre `/call`. Los procesos quedan en
segundo plano, como una aplicación instalada.

Se añadieron `--rebuild` para cambios de código/dependencias, `--stop`, `--logs`,
`--no-open`, `--clean` y `--local` para conservar el flujo de desarrollo con hot reload. La
prueba real ejecutó `--stop`, luego el comando normal (salida “sin reinstalar”), y una segunda
ejecución que detectó la instancia sana. API y web quedaron `Up` en 49317/49318 y los datos
persistentes no se eliminaron.

## 9.13 Decimotercera pasada — dataset y corpus reales dentro de Docker

Después de convertir Docker en la ruta predeterminada apareció una regresión de empaquetado:
el host conservaba `api/data/dataset` con el kit completo, pero `.dockerignore` excluía `data`
y Compose montaba un volumen nuevo sobre `/app/data`. El backend no encontraba los tres XLSX
requeridos por `DatasetCaseAdapter`, registraba el fallback y mostraba únicamente Camila,
Julián y Sofía. Una instalación del jurado habría reproducido exactamente ese estado, aunque
la máquina de desarrollo mostrara antes los 160 casos oficiales.

La solución no depende de una carpeta preexistente en el computador del autor. La imagen API
incluye ahora `fetch_dataset.py`, `load_corpus.py` y un entrypoint idempotente. Antes de iniciar
Uvicorn, el primer arranque:

1. descarga desde `TechSphere2026/ParticipantArtifacts` los 4 XLSX y los 107 PDF;
2. valida archivos no vacíos y el conteo completo del corpus;
3. ejecuta la misma ingestión usada por la consola de Base clínica contra la SQLite del
   volumen;
4. crea un marcador versionado únicamente después de terminar la indexación.

El volumen `care_companion_data` conserva dataset, documentos, chunks, sesiones y marcador.
Los reinicios siguientes verifican y reutilizan ese estado sin redescargar ni recalcular. Dos
variables explícitas permiten desactivar cada bootstrap para diagnóstico, pero sus defaults de
Compose son seguros para evaluación. Si la descarga queda incompleta, el contenedor falla con
un error visible en vez de levantar silenciosamente tres fixtures.

La preparación inicial puede incluir ~127 MB y miles de chunks, por lo que el launcher espera
hasta 15 minutos y emite progreso periódico; el tiempo se mantiene alineado con la compuerta G2.
También se corrigió un defecto independiente: `--rebuild` se ignoraba cuando los endpoints ya
estaban sanos debido al atajo inicial del launcher. Ese atajo ahora solo aplica si no se pidió
rebuild, reinstall ni limpieza.

El ensayo real reveló además que `DatasetCaseAdapter` cargaba 160 casos, pero
`CaseFilters.limit=20` ocultaba 140 porque la UI no implementa paginación. El valor
predeterminado subió a 200 y `/api/v1/cases` entrega ahora los 160. Uvicorn se ejecuta
directamente desde el entorno ya construido para que `uv run` no sincronice dependencias de
desarrollo al iniciar el contenedor.

Prueba completa sobre el volumen de Compose ya existente: descarga de 111 archivos (~128 MB),
ingestión `ok=103 / fallidos esperados=4`, 8.987 chunks persistidos, marcador presente y log
`case_port=DatasetCaseAdapter case_count=160`. Después de elevar el límite, el endpoint entrega
los 160 casos. El proceso completo desde recreate hasta health-check tardó ~166 segundos con
las capas base disponibles; aún falta medir un clon sin caché para cerrar formalmente G2.
Suite: **344 tests recolectados, 341 passed, 3 skipped**; ruff, sintaxis shell,
`docker compose config`, build de imágenes y health-check verdes.

## 9.14 Inspección de los cuatro PDF no indexados

La cifra de 103/107 no significa que el volumen esté incompleto. Se inspeccionaron los cuatro
rechazos sobre los archivos descargados del kit:

| Archivo | Resultado técnico | Observación |
|---|---|---|
| `breast_cancer/Herramientas-Tecnica-Cancer-cuello-uterino-2018.pdf` | cifrado AES, 14 páginas | `pdfinfo` marca `copy:no`, `print:no`; contraseña de usuario vacía permite abrirlo técnicamente. |
| `breast_cancer/cervical-es-patient.pdf` | cifrado RC4, 76 páginas | contraseña de usuario vacía permite abrirlo técnicamente; `copy:no`. |
| `breast_cancer/gom226c.pdf` | cifrado RC4, 10 páginas | contraseña de usuario vacía permite abrirlo técnicamente; `copy:yes`. |
| `Appendicitis/REVISIÓN DE LA LITERATURA SOBRE LAAPENDICITIS AGUDA PEDIATRICA NO ESPECIFICADA EN EL PERI000 2000-2021.pdf` | no cifrado, sin capa de texto útil | requiere OCR o una versión con texto; `pdftotext` solo produce una línea vacía. |

El repositorio oficial no atribuye una contraseña ni explica una decisión de cifrado específica.
Sí aclara que los PDF son obra de sus respectivos autores/editores y conservan sus propios
derechos, aunque se incluyan como referencia para el reto
([README oficial](https://github.com/TechSphere2026/ParticipantArtifacts)). La explicación más
prudente es que las protecciones vienen heredadas de las fuentes originales, no que Docker o
Care Companion las haya cifrado.

### Qué haría falta para descifrarlos

La vía correcta es obtener del titular una copia sin restricciones o la contraseña/licencia de
extracción. Con autorización explícita, se puede usar `qpdf --password='...' --decrypt` o
`pypdf` (para AES, además, instalar `cryptography`) y después cargar una copia derivada al RAG.
Los dos RC4 y el AES aceptaron la contraseña vacía durante la inspección, pero automatizar ese
desbloqueo para eliminar `copy:no` sería saltarse una restricción del editor; no se incorporó al
bootstrap ni se intentó fuerza bruta.

Por eso el comportamiento actual es intencional: se indexan 103 documentos legibles, se dejan
los tres cifrados y el escaneado registrados con una causa verificable, y el sistema sigue
funcionando con el corpus restante. Si el organizador confirma que el uso de esos cuatro PDF y
la eliminación de sus restricciones está autorizado, se puede añadir un paso de descifrado
controlado y auditable; no hace falta cambiar Docker para ello.

## 9.15 Revisión de requisitos de privacidad y HIPAA

Se volvió a revisar el README oficial, `docs/rubrica-evaluacion.md` y
`docs/stack-tecnico.md` del kit, buscando `HIPAA`, `HIPPA`, `PHI`, privacidad, datos personales,
cifrado y requisitos equivalentes. El resultado es:

- El kit declara que los datos del reto son sintéticos y que ningún paciente, nombre, documento,
  dirección o EPS corresponde a una persona real.
- La rúbrica exige una solución reproducible, voz, RAG, decisiones, escalamiento y conocimiento
  vivo; no exige HIPAA, una BAA, telefonía real, EHR, autenticación empresarial ni un entorno de
  producción hospitalario.
- El README oficial indica que los PDF conservan los derechos de sus autores y editores. Eso
  explica por qué no se debe asumir que el participante está autorizado a quitar restricciones
  de copia solo porque la contraseña de usuario esté vacía.

El repositorio propio aplica una capa de seguridad proporcional al concurso: BR-040 exige solo
datos sintéticos, anonimizados o autorizados; BR-042 excluye audio/PII de logs y capturas por
defecto; NFR-008 exige minimización y separación de sesiones; y el release gate bloquea secretos,
PHI o IP no autorizada. La implementación no se presenta como “HIPAA compliant”.

HIPAA sería una cuestión de una eventual operación real: según HHS, sus reglas aplican a entidades
cubiertas y business associates que manejan PHI identificable, normalmente con acuerdos y
salvaguardas específicos ([HHS: Covered Entities and Business Associates](https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html)). Si Care Companion
se conectara después a un hospital o recibiera pacientes reales, habría que hacer una revisión
legal y de seguridad, incluyendo BAA cuando corresponda, retención, control de acceso, cifrado,
auditoría, consentimiento y respuesta a incidentes. Ese trabajo está correctamente separado en
`PROD-011 Privacy/compliance`; no forma parte del concurso actual.

## 9.16 Extracción de los tres PDF protegidos y OCR del escaneo

Dado que no existe un canal operativo para obtener respuesta del organizador, se hizo una
verificación técnica local antes de cambiar el comportamiento: los tres PDF protegidos aceptan
contraseña de usuario vacía y producen texto; no se intentó fuerza bruta ni se suministra una
contraseña externa. La extracción quedó encapsulada en `extract_pdf_pages()` y requiere
`cryptography` para el PDF AES.

El cuarto archivo (`Appendicitis/REVISIÓN...2000-2021.pdf`) tiene una sola página escaneada.
Docker incorpora `poppler-utils`, `tesseract-ocr` y `tesseract-ocr-spa`; `scripts/ocr_scanned_pdf.py`
rasteriza a 220 DPI, reconoce `spa+eng` y escribe una salida `.txt` idempotente en el volumen.
`load_corpus.py` ingesta esa salida con la categoría `appendicitis`, manteniendo el PDF original
sin modificar.

El marcador de bootstrap pasó a `v2` para que una instalación existente reprocesara la ampliación
una sola vez. Ensayo real contra el volumen Docker: los tres PDF protegidos quedaron en estado
`ready`, el OCR generó 4.985 caracteres y 8 chunks, el corpus quedó en **107 documentos listos**
(`106 PDF + 1 texto OCR`) y **9.296 chunks**. El backend sigue levantando como
`DatasetCaseAdapter case_count=160`. En futuras cargas manuales de documentos, el rechazo de
PDF cifrados permanece como comportamiento conservador; la apertura con contraseña vacía se
aplica al batch oficial del kit.

## 9.17 Paciente como entidad longitudinal y nuevo seguimiento

La inspección directa de los XLSX confirmó 40 `paciente_id` únicos y 160 trayectorias: todos
los pacientes tienen exactamente los días 1, 3, 7 y 14, además de una fecha de cirugía en el
perfil clínico. La lista plana anterior era fiel al `case_id` técnico, pero repetía cuatro veces
cada nombre y hacía que el jurado tuviera que interpretar identificadores de fase.

`DatasetCaseAdapter` construye ahora 40 agregados de paciente. Cada uno conserva perfil,
procedimiento, fecha de cirugía y los cuatro hitos históricos con dolor NRS, temperatura,
movilidad, herida, apetito y sueño. Los 160 episodios originales continúan resolviendo por su
`case_id`, pero `/api/v1/cases` devuelve las 40 entidades que la interfaz representa como
tarjetas buscables. La llamada se presenta como un seguimiento nuevo posterior a la historia
disponible; la apertura no obliga al usuario a escoger ni pronuncia un día posoperatorio.

Los agentes reciben el perfil estable y los cuatro hitos dentro de `prior_followups`, además de
las llamadas nuevas previamente completadas para el mismo `patient_id`. El registro producido
por la nueva llamada conserva las observaciones fuente y añade una proyección `FollowupRecord`
con los nombres del dataset (`dolor_nrs`, `fiebre_c`, `movilidad`, `herida`, `apetito`, `sueno`),
nivel de decisión y `alerta_equipo_medico`. La proyección se materializa idempotentemente en
SQLite (`followup_records`); Redis no aporta valor para 40 entidades y añadiría otro servicio al
arranque cronometrado de Docker. Verificación: API real devuelve 40 pacientes con cuatro hitos
cada uno; Docker, build Next y `make verify` verdes (**348 recolectados, 345 passed, 3 skipped**).

## 9.18 Auditoría de conversación longitudinal, normalización y superficies del jurado

La prueba con Janeth mostró cuatro fallos conectados. “Más o menos” era atribuido a dolor sin
evidencia; ante “usted tiene todos mis registros” el agente ignoraba su propia línea base; un
dolor siete, fiebre de 38 °C e incisión roja/inflamada no se combinaban hasta que la persona
pidiera una ambulancia; y el registro final conservaba frases libres o datos de otra pregunta
en los campos del dataset.

Se añadieron guardas conversacionales deterministas. Una respuesta general vaga pregunta qué
no está bien antes de crear un síntoma. Una referencia a los registros reconoce el último hito,
contrasta dolor histórico y actual, y solicita solo inicio/evolución de hoy. Dolor expresado con
palabras se convierte a NRS 0–10, la fiebre numérica a grados Celsius y movilidad, herida,
apetito y sueño a categorías semiestructuradas. `CallSummary` pasa a v1.2; campos inciertos ya
no contaminan `followup_records`.

`rules-v2` incorpora dos combinaciones de deterioro posoperatorio: fiebre + dolor ≥7 + herida
inflamada, o fiebre + dolor ≥7 + intolerancia oral. Dolor alto aislado todavía se caracteriza;
“quiero que me hospitalicen” sí se reconoce como solicitud urgente, y “no puedo comer” queda
como intolerancia oral, nunca como vómito inventado. Para señales de amenaza inmediata, el
cierre hablado indica contactar servicios de emergencia sin esperar la devolución del equipo.

En `/call`, el selector se repliega durante la conversación y una línea longitudinal expone los
cuatro hitos que el agente conoce. `/knowledge` se rediseñó como consola administrativa guiada:
el corpus oficial se identifica por checksum/origen y está protegido en API y UI, mientras los
documentos cargados por el evaluador conservan el ciclo learn/retrieve/forget. El inventario
tiene búsqueda, filtros y paginación. `/audit` ya no obliga a interpretar UUID o enums: muestra
paciente, procedimiento, estado/resultados legibles, selecciona la sesión reciente y presenta
el `followup_record` consolidado.

Verificación: **361 tests recolectados, 358 passed, 3 skipped**; ruff, ESLint y build Next.js
verdes. La imagen Docker migra de forma idempotente bases persistentes anteriores para marcar
el corpus oficial sin reindexarlo ni alterar `knowledge_version`.

## 9.19 El contenedor Docker corría con FakeLLM; se activó RAG semántico real

Sospecha del usuario al probar en vivo: la conversación se sentía "demasiado rápida" para ser
un modelo real. La sospecha era correcta. `docker-compose.yml` nunca leía `api/.env` — sólo
cableaba `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL` a mano desde variables del *shell* del host,
con default `fake`/vacío si no se exportaban antes de `docker compose up`. El contenedor llevaba
15 horas corriendo con esos defaults, ajeno a cada edición de `api/.env` de toda la sesión
(modelo, API key, resguardo, rate limiting). Verificado con `docker exec ... env`:
`LLM_PROVIDER=fake`, `LLM_API_KEY=` vacío, pese a que `api/.env` en disco tenía la config real.

Dos fixes en `docker-compose.yml`:
1. `env_file: ./api/.env` — Compose carga toda la config automáticamente; variables nuevas ya
   no requieren tocar este archivo. `DATABASE_PATH`/`DATASET_DIR`/flags de bootstrap se dejan en
   `environment:` (que tiene prioridad) porque son rutas dentro del contenedor, no del host.
2. `LLM_FALLBACK_BASE_URL=http://host.docker.internal:11434/v1` + `extra_hosts:
   host.docker.internal:host-gateway` — el resguardo Ollama corre en el host (Ollama.app), no en
   un contenedor; `localhost:11434` desde adentro del contenedor es el contenedor mismo
   (connection refused, verificado). Sin esto el resguardo quedaba inalcanzable justo cuando más
   se necesita: un 429 de Groq.

Investigar esto reveló un segundo hallazgo, más profundo: `EMBEDDINGS_PROVIDER` nunca estuvo
seteado en `api/.env`, así que el RAG corría sobre `FakeEmbeddings` (n-gramas hasheados) desde
el principio de la sesión, pese a que la decisión documentada en §3/§9 era BGE-M3 vía Ollama.
El retrieval léxico (FTS5) funcionaba; la mitad semántica de la fusión RRF nunca se ejercitó
con vectores reales.

Se activó con tiempo de sobra antes del plazo. `ollama pull bge-m3` (1.2 GB). `api/.env`:
`EMBEDDINGS_PROVIDER=ollama`, `EMBEDDINGS_MODEL=bge-m3`, y
`EMBEDDINGS_REQUEST_TIMEOUT_SECONDS=300` — el documento más grande del corpus tiene **1.127
chunks** que van en una sola llamada batch (`embed_batch` es por documento, no por chunk); el
default de 30 s no alcanza. Cambiar de proveedor de embeddings invalida los vectores ya
indexados (dimensiones distintas), así que se hizo reingestión completa: `docker compose down
-v` (borra el volumen: dataset + base + índice) seguido de `docker compose up -d --build`, que
dispara el bootstrap desde cero.

Resultado, cronometrado (sirve como medición real de G2, arranque ≤15 min, pendiente desde
hacía días): contenedor creado a las 19:50:29 UTC, `care_companion_app_ready` a las 20:00:20
UTC — **9 min 50 s** con descarga del kit oficial (107 PDF + 4 xlsx), OCR del PDF escaneado, e
indexación completa con embeddings reales incluidos. 107/107 documentos, 9.296 chunks — mismos
números que con `FakeEmbeddings` (confirma que el chunking es determinista; sólo cambió el
vector). Un solo "fallido" en el log de carga es el comportamiento esperado: el PDF escaneado se
rechaza como PDF crudo (`pdf_no_text_layer`) y su versión OCR se indexa aparte — 107 documentos
`ready` en total. Embedding verificado en 1024 dimensiones (float32, 4096 bytes), coincide con
BGE-M3, no con la dimensión de `FakeEmbeddings`.

Prueba end-to-end real tras la reingesta: turno con "me sale un liquido amarillo de la herida y
tengo mal olor" devolvió `intent=grounded_answer` con 3 citas reales (documento, página,
`chunk_id`) de dos PDF distintos del corpus oncológico/colorrectal — RAG semántico real
funcionando de punta a punta, no un artefacto de prueba.

Verificación: 383 passed / 3 skipped, ruff verde. El contenedor se reinició solo una vez durante
la verificación (exit code 0, sin OOM — atribuible a Docker Desktop, no a la app); los datos
sobrevivieron porque viven en el volumen nombrado `care_companion_data`, no en la capa del
contenedor.

## 9.20 Cuota diaria de Groq (TPD) es ventana móvil, no reset a medianoche

Varias corridas del benchmark el mismo día agotaron el límite diario de Groq (`tokens per day
(TPD): Limit 500000`). Supuesto inicial equivocado: que resetea a medianoche UTC. Prueba
directa que lo refuta — una llamada mínima a las 00:03 UTC funcionó ("cuota restablecida"),
pero a las 00:07 UTC (4 minutos después) `Used 498653` volvió a rechazar la siguiente llamada
real. Es una **ventana móvil de 24 h**: el consumo de hace 24 h exactas es lo único que libera
cupo, no un reloj fijo. Consecuencia práctica: correr el benchmark de decisión completo varias
veces el mismo día no es viable — cada corrida completa (~12 casos × ~6 turnos × ~2.000 tokens)
consume una fracción significativa del cupo diario, y reintentarlo agota lo que queda sin
avisar con antelación (el único aviso es el propio 429).

Decisión: no perseguir más corridas completas de decisión el mismo día. `groq-latency.json`
(5 llamadas aisladas, medidas *antes* de que la cuota se acercara al límite) sigue siendo la
medición de latencia vigente. Pendiente real, sin resolver todavía: el número que exige el README
oficial no es latencia LLM-a-LLM sino **voz a voz** — desde que el paciente termina de hablar
hasta que **empieza a sonar** el audio del agente (fin de STT → inicio de TTS), spec.md §1.5.
Ni `groq-latency.json` ni `capa1-groq.json` miden eso: ambos miden texto de punta a punta,
sin STT ni TTS. Falta instrumentar esa métrica del lado del cliente (browser) durante una
llamada real.

## 9.21 Pregunta de aclaración repetida palabra por palabra — hallazgo en vivo del jurado

Transcripción real compartida por el usuario (paciente "Jean León Sepúlveda", colecistectomía):
el paciente contestó "que ya no tengo dolor, la herida está muchísimo mejor, ya está menos
inflamado y menos roja" — información real — y el agente volvió a preguntar **casi la misma
pregunta sobre "ánimo"** dos veces más, incluso después de que el paciente respondiera "ya le
dije".

Causa: `GENERAL_STATE` (ánimo) es un objetivo legítimo que el paciente nunca contestó
directamente (describió síntomas físicos, no estado de ánimo), así que `_covered_objective_codes`
nunca lo marcaba cubierto y `InterviewAgent` seguía proponiendo `clarification_question` sobre
lo mismo turno tras turno — sin que nada comparara la pregunta nueva contra la última realmente
formulada. Repetir la pregunta idéntica es peor que aceptar lo que hay: un paciente real no lo
tolera, y pesa directamente en el criterio "Comprensión y diseño de conversación" (15 pts).

Fix genérico (no específico a `GENERAL_STATE`, cubre cualquier objetivo donde esto pueda
repetirse): `_is_near_duplicate_question` compara por solapamiento de palabras (no exige texto
idéntico — el modelo reordena/parte la frase entre intentos, visto en la transcripción real) la
`clarification_question` propuesta contra el último turno del agente. Si hay solapamiento
≥70%, se descarta la repetición: `needs_clarification` se fuerza a `False`, se registra una
observación `uncertain` para el objetivo atascado (no se inventa un valor — spec.md §11.2) y
la entrevista avanza al siguiente objetivo pendiente. Evento nuevo
`interview.clarification_repetition_avoided` para auditoría.

Dos tests de regresión con el texto real de la transcripción: uno confirma que la segunda
aclaración casi idéntica se bloquea y la entrevista avanza; el contrapeso confirma que dos
aclaraciones **legítimamente distintas** seguidas (dolor, luego herida) se hacen las dos —
mismo patrón de verificación que los fixes de `safety_signals.py` de esta sesión.

388 passed / 3 skipped, ruff verde.

## 9.22 Llamada de prueba reutilizable, sin el protocolo de un paciente longitudinal

Pedido del usuario tras probar G5 en vivo: subir un documento de prueba en `/knowledge`
funciona, pero verificarlo en una llamada real obligaba a ir a `/call` y elegir uno de los
40 pacientes reales — activando todo su protocolo (saludo con evolución conocida, 4
seguimientos previos) sólo para una prueba de "¿el agente usa lo que acabo de subir?".

**Auditoría previa a implementar (instrucción explícita del usuario: auditar y validar
antes de tocar código):**

- **El reto no exige un paciente del dataset oficial para la prueba en vivo.** G4 (única
  compuerta sobre voz) dice literalmente "saludo + pregunta trivial" — genérico. La propia
  auditoría anota que "el jurado prueba con escenarios de decisión interpretados en vivo":
  el jurado improvisa el rol de paciente, no sigue un guion de historial precargado.
- **La pieza ya existía, apagada.** `app/adapters/fixture_cases.py` tiene 3 casos
  sintéticos (Camila/Julián/Sofía) sin historial, construidos en ADR-001 antes del dataset
  real. Sólo se usaban como resguardo de arranque si faltaban los archivos del dataset — con
  el dataset presente (como está hoy), quedaban completamente inalcanzables desde la API.

**Implementado (opción A del análisis, la de menor riesgo):**

- `CaseSummary`/`ChallengeCase` ganan `is_synthetic_demo: bool = False` — `True` sólo en
  los 3 casos de `FixtureCaseAdapter`.
- `CombinedCaseAdapter` nuevo (`app/adapters/combined_cases.py`): compone
  `DatasetCaseAdapter` (primario) + `FixtureCaseAdapter` (extra) sobre el mismo
  `ChallengeCasePort` — cero cambios en el dominio, mismo principio que el resto de la
  arquitectura de adapters. `_build_case_port` en `main.py` lo usa cuando el dataset carga
  bien; si falta el dataset, el comportamiento de resguardo no cambia (fixtures solos).
- `/call` filtra `isSyntheticDemo` de su selector — sigue mostrando exactamente los mismos
  pacientes reales que antes, sin sorpresas.
- `/knowledge` obtiene un botón "Probar en una llamada" que abre el primer caso sintético
  directamente, sin selector.
- Limpieza menor de paso: el nombre de procedimiento de los 3 casos era un slug interno
  (`cirugia_ambulatoria_general_x`) que hasta ahora nunca se mostraba al usuario final —
  con la nueva superficie sí se muestra, así que pasa a "Seguimiento general (paciente de
  prueba)". `procedure_category` (usado internamente para el filtro de aplicabilidad del
  RAG) no cambió.

**Refactor de UI, pedido explícito ("reciclar y reutilizar... ventana modal que surja al
frente igual que en la otra"):** toda la lógica de una llamada (WebSocket, voz, turnos,
estado) se extrajo de `/call/page.tsx` a `web/src/components/CallModal.tsx` — un componente
autocontenido que recibe `patientCase`/`onClose` y no sabe si vino de un selector de 160
pacientes o de un botón de prueba con un caso sintético. `/call` quedó reducido a la
lista + selección; `/knowledge` lo reutiliza sin duplicar una sola línea de la lógica de
llamada.

Verificado de punta a punta contra el stack Docker reconstruido: `POST /api/v1/sessions`
con `demo-case-001` abre con saludo limpio, sin mención de "evolución registrada" (no hay
`prior_followups`); un turno preguntando por el documento subido en la sesión anterior de
G5 lo recupera y cita correctamente (`prueba-g5-conocimiento-vivo.txt`), confirmando que el
camino de retrieval es idéntico al de un paciente real — sólo cambia qué caso abre la
llamada.

398 passed / 3 skipped (backend), tsc + eslint + build de Next limpios.

## 9.23 Dos bugs reales de la llamada de prueba, encontrados por el usuario en vivo

Transcripción real con `demo-case-001` (Camila) desde el nuevo botón "Probar en una
llamada": el agente sí respondió bien sobre el documento de prueba G5 (Programa Cicatriz
Segura, con cita), pero (1) siguió empujando el checklist clínico completo (dolor,
líquidos, movilidad) después de la respuesta ad-hoc, y (2) volvió a saludar dos veces a
mitad de la llamada ("¡Hola Camila!", "es un gusto hablar contigo de nuevo").

### Bug 1 — el checklist se activaba también en la llamada de prueba

`next_question` (lo que empuja al `ResponseAgent` a conducir el checklist) se calculaba
siempre, sin condición — correcto para los 40 pacientes reales, pero indeseado para una
prueba ad-hoc pensada sólo para verificar RAG/G5.

**Intento fallido, corregido antes de commitear:** atarlo a `is_synthetic_demo` rompió 5
tests de `test_gates.py`, que usan `demo-case-001` (Camila) como vehículo por defecto para
probar el checklist completo desde antes de que existiera el botón de `/knowledge`. Los
tres casos originales (Camila/Julián/Sofía) son "sintéticos" pero SÍ deben conducir el
checklist. `is_synthetic_demo` (identidad: "¿es uno de los pacientes de prueba?") y
"¿debe forzar el checklist?" son preguntas distintas — mezclarlas rompía un propósito para
arreglar otro.

**Fix real:** un cuarto caso dedicado, `demo-case-quicktest` ("Paciente de prueba"), con un
flag nuevo y separado, `skip_interview_checklist=True`. Camila/Julián/Sofía quedan
exactamente como estaban (`skip_interview_checklist=False` por default) — `test_gates.py`
no se tocó. `/knowledge` ahora busca específicamente ese caso (con fallback al primer
sintético si no aparece) en vez de tomar "el primero que sea sintético".

### Bug 2 — el agente volvía a saludar a mitad de la llamada

Causa raíz, confirmada leyendo `response.py`: `ResponseTurnInput` no tenía NINGÚN campo que
le dijera al modelo "esto ya es un turno intermedio" — ni número de turno, ni un flag de
"ya saludaste". Desde la perspectiva del LLM, cada turno podía parecer el primero. Con
Llama 3.3 70B (más conversacional que el 8B) eso se manifestó como re-saludos espontáneos
en formas que el regex de la sesión anterior (`_strip_redundant_greeting`) no cubría
("es un gusto hablar contigo de nuevo" no empieza con ninguna palabra de saludo conocida).

**Fix de raíz, no sólo el parche determinista:** `ResponseTurnInput.already_greeted: bool`,
nuevo. Contexto **efímero**, como pidió explícitamente el usuario ("no crear una base de
datos persistente... sería sobre ingeniería") — se deriva de `len(existing_turns) >= 1`
dentro de `handle_turn`, leyendo la tabla `turns` que YA existe y YA se consulta para el
historial de ese mismo turno (línea ~786 de `call_cycle.py`). No se agregó ninguna tabla ni
columna nueva. Cuando es `True`, `_build_user_prompt` antepone una instrucción explícita:
"ya saludaste, no vuelvas a saludar ni a presentarte".

**Bug adicional encontrado revisando el parche anterior:** `_strip_redundant_greeting`
tampoco atrapaba "¡Hola Camila!" — el signo de apertura "¡" va ANTES de la palabra de
saludo en español, y `^\s*(?:hola|...)` nunca consumía ese carácter (no es espacio en
blanco), así que el saludo redundante se colaba intacto pese al fix de la sesión anterior.
Corregido (`^[\s¡]*`), y se mantiene como respaldo determinista — el fix de raíz (el
prompt) es la defensa principal contra frases nuevas que un regex no puede anticipar.

Cinco tests nuevos: instrucción "no saludes" presente/ausente según `already_greeted`
(agentes.py); regex con "¡Hola" al inicio (orchestrator); checklist suprimido en
`demo-case-quicktest` vs. conducido normalmente en Camila, ambos verificando el prompt
real que llega al `ResponseAgent`, no sólo el mensaje final.

Verificado de punta a punta reproduciendo la transcripción real del usuario contra Docker
reconstruido: 3 turnos, sin re-saludo ni una vez, sin ninguna pregunta de dolor/líquidos/
movilidad — el agente se queda en el tema (Programa Cicatriz Segura) hasta que el usuario
cierra la llamada manualmente.

403 passed / 3 skipped (backend), tsc + eslint + build de Next limpios.

## 9.24 Jerarquía visual del CTA de "Probar en una llamada"

Pedido del usuario: el botón "Probar en una llamada" debía tener "todo el protagonismo del
mundo porque ejecuta una acción, lo demás es solo informativo" — pero usaba
`.voice-preview-btn`, el mismo botón gris de 11px que "Hablar por voz"/"Detener voz" (un
control secundario dentro de una llamada activa), metido en una tarjeta blanca idéntica a
las demás. Visualmente no se distinguía de la información de alrededor.

Rediseño (`.knowledge-cta` en globals.css): tarjeta con fondo sólido en gradiente de marca
(`--blue-deep` → `--aqua-deep`), texto blanco, botón invertido (fondo blanco, texto azul,
24px/16px vs. los 17px/11px anteriores) con sombra elevada. Se movió a ser el PRIMER
elemento de la página — antes del hero informativo — para que sea literalmente lo primero
que se ve, no una tarjeta más entre el resumen de versión y el formulario de carga.

tsc + eslint limpios, build de Next OK, verificado que la clase nueva llega al bundle CSS
servido por el contenedor reconstruido.

## 9.25 El agente devolvía la pregunta del paciente como si fuera propia

Hallazgo en vivo: ante "¿dónde puedo conseguir este parche?", el agente respondía "¿Cuál
es la fuente de donde se puede obtener este parche...?" — un eco, no una respuesta. Pasó
tres veces seguidas, incluso después de que el paciente lo corrigiera explícitamente
("eso es lo que le estoy preguntando a usted").

Causa raíz (dos mecanismos del prompt en tensión, ver `app/agents/response.py`):
`evidence_sufficient` se calcula a nivel de TEMA (¿se recuperó algo relevante?), no de
DATO PUNTUAL (¿la evidencia responde exactamente lo preguntado?) — el documento cubre el
protocolo del parche pero no dónde comprarlo, así que el sistema entra en modo
`grounded_answer` sin instrucción para el caso "tema cubierto, dato puntual ausente". Y el
system prompt ordenaba incondicionalmente "conduce la llamada... cierra con una pregunta"
— sin una pregunta real que ofrecer, el modelo resolvía la tensión fabricando una a partir
de la del paciente.

Fix de dos capas (sólo prompt, sin código de dominio — el problema es abierto, no
enumerable):
1. `_GROUNDED_INSTRUCTIONS` gana una sección explícita para evidencia parcial: afirmar lo
   soportado, admitir el vacío puntual con claridad, redirigir a farmacia/equipo médico —
   sin tratarlo como abstención total.
2. `_BASE_SYSTEM_PROMPT` deja de exigir cerrar con pregunta sin excepción, y prohíbe
   explícitamente devolver la pregunta del paciente reformulada, con el ejemplo exacto del
   bug real como caso ilustrativo.

Verificación honesta, con un tropiezo real en el camino: la primera prueba en vivo (misma
transcripción, 3 turnos) dio un mensaje corrupto ("autoadheóso", "aplicaÁrse") que parecía
peor que el bug original. Investigado antes de reportar nada: los eventos mostraban
`provider: ollama, model: llama3.2:3b` en LOS TRES turnos — Groq daba 429 en cada llamada
de esa sesión (confirmado en logs del contenedor), así que la prueba completa corrió sobre
el resguardo local, no sobre el modelo que se acababa de cambiar. La corrupción es
calidad del modelo de 3B, no una regresión del fix.

Hallazgo aparte, real e importante: **el 70B tiene una cuota diaria (TPD) mucho menor que
el 8B** — 100.000 tokens/día contra 500.000 — y las pruebas de la sesión ya la habían
consumido casi entera (99.274/100.000) en el momento del intento. Con ~1.500-2.000 tokens
por turno × 3 agentes, 100k TPD alcanza para apenas 15-20 turnos de prueba al día. Esto no
estaba considerado cuando se decidió el cambio a 70B (auditoría, sección anterior) — sólo
se verificó el límite por minuto (12.000 TPM, mejor que el 8B), no el diario (peor).

Verificación real, aislando sólo lo que cambió: en vez de una conversación completa (9
llamadas LLM: interview+triage+response × 3 turnos, todas compitiendo por la misma cuota
ya agotada), se invocó `ResponseAgent.run()` directo contra Groq real con el escenario
exacto (evidencia sobre el parche, pregunta "dónde lo consigo") — 1 sola llamada. Esperó
~1 min a que la ventana de cuota liberara margen (mensaje 429 con "Please try again in
51.84s", confirmando de nuevo el comportamiento de ventana móvil de sesiones anteriores).
Resultado, confirmado `provider=groq model=llama-3.3-70b-versatile`:

> "...no tengo información específica sobre dónde comprarlo. Te sugiero consultar con tu
> farmacia o tu equipo médico... ¿Has hablado con tu equipo médico sobre este tema?"

Sin eco. Afirma lo soportado, admite el vacío puntual, redirige. Cierra con una pregunta
pese a `next_question=None` — no cumple la instrucción 2 al pie de la letra, pero esa
pregunta de cierre es genuinamente nueva (no repite la del paciente), así que no es el
patrón que se estaba corrigiendo; se documenta como imperfección conocida, no como falla.

Cuatro tests nuevos en `test_agents.py`, incluido el contrapeso obligatorio (con
`next_question` real presente, el mecanismo de conducir la entrevista sigue intacto).
407 passed / 3 skipped, ruff verde.

## 9.26 El recorrido de pasos de /knowledge era decorativo, no navegable

Hallazgo del usuario: el tracker "1 Cargar → 2 Recuperar → 3 Olvidar" dice qué hacer pero
no dónde — "ahí dice olvidar, pero dónde?". Para un jurado siguiendo el recorrido sin guía,
eso es fricción real: tendría que buscar por su cuenta la tabla de documentos y encontrar
el botón de eliminar.

Cada `<li>` del tracker pasa a ser un botón (`jumpToStep`) que hace scroll suave hasta la
sección real donde ocurre esa acción (`upload-heading` / `verify-heading` /
`documents-heading`, los tres `id` ya existentes de las secciones correspondientes) y la
resalta 2 s con un aro de color (`prefers-reduced-motion` cae a un outline fijo sin
animación). Cero endpoints nuevos — sólo navegación dentro de la página que ya tenía todo
lo necesario.

tsc + eslint limpios, build de Next OK, verificado que el CSS nuevo llega al bundle
servido por el contenedor reconstruido.

Bug real encontrado probando el fix anterior: `scrollIntoView({block: "center"})` centraba
la SECCIÓN completa — que contiene la tabla de 108 documentos — así que "Olvidar" aterrizaba
en cualquier fila del medio (vista real: una tanda de PDFs oficiales de reemplazo articular,
nada que ver con el documento de prueba). Dos correcciones: `jumpToStep` ahora fija
`inventoryScope="test"` (el mismo filtro que ya existía sobre la tabla, "Origen y estado")
antes de saltar al paso 3, así que la tabla queda reducida a los documentos de prueba —
normalmente uno solo; y el scroll pasa a `block: "start"`, al inicio de la sección, no al
centro. El cambio de filtro se espera un frame (`requestAnimationFrame`) antes de medir la
posición de scroll, para no calcularla contra el DOM todavía sin filtrar.

## 9.27 "Olvidar" fallaba con 500 en el documento que de verdad se había usado

Hallazgo en vivo, el más grave de esta ronda porque bloquea G5 (compuerta eliminatoria)
exactamente en el recorrido que el reto pide hacer: cargar un documento, usarlo en una
llamada real, eliminarlo. El primer intento de eliminar `prueba-g5-conocimiento-vivo.txt`
—el mismo documento usado en decenas de llamadas de prueba de toda la sesión— devolvía 500.

Traceback real:
```
sqlite3.IntegrityError: FOREIGN KEY constraint failed
  at document_chunks.py:81, DELETE FROM document_chunks WHERE document_id = ?
```

Causa: `citations.chunk_id REFERENCES document_chunks(id)` sin `ON DELETE CASCADE` — a
propósito, según el propio docstring de `CitationRepository`: "una cita ya registrada es
un hecho histórico de auditoría, no debe desaparecer si el documento se borra después".
Pero `delete_for_document` sí hacía `DELETE FROM document_chunks` sin condición, así que en
cuanto un chunk tenía una cita real apuntándolo, SQLite (con `foreign_keys=ON`) rechazaba
el borrado — el código y el comentario decían una cosa, el `DELETE` hacía otra.

**Hallazgo aparte, sobre por qué esto no se atrapó antes**: ya existía un test
(`test_citations.py::test_citation_persists_even_after_source_document_is_deleted`) con el
nombre exacto de esta garantía — pero simulaba el borrado con `UPDATE documents SET
status='deleted'` directo, sin pasar nunca por `DELETE FROM document_chunks`. Validaba el
docstring, no el código que lo rompía. El test nuevo (`test_ingestion.py`) llama a
`svc.forget()` de verdad.

Fix, sin tocar el esquema (SQLite no permite relajar un FK existente sin reconstruir la
tabla completa — riesgo innecesario a un día del plazo): los chunks CITADOS se dejan como
**tombstone** en `delete_for_document` — `text`/`embedding` vaciados (el contenido real se
purga, cumpliendo RAG-009) pero la fila sobrevive para que la cita siga resolviendo. Los
chunks sin ninguna cita — el caso común — se siguen borrando por completo, sin cambio de
comportamiento. `_find_remaining_chunk_rows` (el chequeo de canaria que confirma un borrado
completo) se actualizó en paralelo: un chunk cuenta como "aún presente" por `text != ''`,
no por la mera existencia de la fila — y sigue exigiendo ausencia total en FTS.

Dos tests nuevos en `test_ingestion.py`: el caso real (chunk citado, `svc.forget()` no
debe lanzar, la cita sobrevive, el chunk deja de ser buscable) y el contrapeso obligatorio
(documento nunca citado, sigue siendo un borrado completo byte a byte, sin tombstones de
sobra). 409 passed / 3 skipped, ruff verde.

Verificado contra el caso real que falló en pantalla, no sólo con tests: `DELETE
/api/v1/knowledge/documents/7b1c767b-...` (el documento exacto de la captura) devuelve 200
tras el fix. Las 21 citas acumuladas de toda la sesión sobre ese documento siguen intactas;
ambos chunks quedaron con `text=''`, `embedding=NULL`.

## 9.28 Restos de inglés que sobrevivieron a la limpieza anterior (§9.24)

El barrido de §9.24 (grep sobre `Retrieval|Handoff|Backend`) no encontró estos tres porque
el patrón exacto no calzaba: `RiskPanel.tsx` tenía "Evaluado por el **Triage Agent**..." y
"El **handoff** conserva los hallazgos..." (minúscula, distinto del "Handoff" que sí se
había cambiado antes en el mismo archivo); `knowledge/page.tsx` tenía "Consultando detalle
en el **backend**…" en el diálogo de detalle de documento, un `<p>` que el grep anterior no
cubrió. Los tres eran texto visible en pantalla, no identificadores internos.

Corregidos: "Triage Agent" → "reglas clínicas deterministas y evidencia citada" (se quita
la referencia al nombre interno del agente, no sólo se traduce); "el handoff conserva" →
"la derivación conserva"; "backend" → "servidor". Barrido final con un patrón más amplio
(`backend|Backend|handoff|Handoff|Agent\b`) sobre todo `src/app` y `src/components`: sin
más coincidencias.

tsc + eslint limpios, build de Next OK, verificado en el contenedor reconstruido.

## 9.29 Rediseño de la fila superior de /knowledge: texto invisible + jerarquía pedida

Causa del texto blanco ilegible reportado en vivo, confirmada leyendo el CSS servido: el
`.topbar` de navegación es `position: sticky; top: 0; backdrop-filter: blur(18px)` (efecto
vidrio esmerilado, ya existía antes de esta sesión). La tarjeta `.knowledge-cta` del diseño
anterior (§9.24) quedaba como el primer elemento de la página, pegada al borde superior, y
el desenfoque del header caía directamente sobre su texto.

En vez de solo corregir el solape, se rediseñó por completo según lo pedido:
- La sección "Cargar guía clínica" pasa a ser el PRIMER elemento de la página, con más
  jerarquía visual que las tarjetas informativas (borde de color de marca + sombra propia,
  no `.card` genérica) — antes vivía a mitad de página, en un `two-col` junto a "Versión
  activa".
- El botón de llamada de prueba es ahora independiente: su propia tarjeta
  (`.knowledge-call-fab-card`), hermana de la de carga dentro de `.knowledge-top-row`, no
  anidada dentro de ella.
- El botón es redondo y reutiliza el ícono exacto de `VoiceOrb` (`.mic-button`/
  `.mic-symbol`, mismas medidas y colores) en vez de un ícono nuevo — es el mismo símbolo
  de "llamada" en toda la app.
- "Versión activa" queda sola donde antes compartía el `two-col` con "Cargar" — ya no
  fuerza dos columnas con un solo elemento.

tsc + eslint limpios, build de Next OK, verificado que las clases nuevas llegan al bundle
CSS servido por el contenedor reconstruido. 409 passed / 3 skipped (sin cambios de
backend).

## 9.30 Las dos tarjetas quedaron pegadas: `--space-5` no existía

Feedback en vivo tras §9.29: la tarjeta de carga y el botón de llamada quedaron
completamente pegados, sin separación, y la de carga ganó un borde/sombra de color que el
usuario no pidió ("la idea era dejar la caja de carga igual a como estaba antes... y el
micrófono al lado, pero separados").

Causa del pegado, no estética sino un bug real: `.knowledge-top-row { gap: var(--space-5); }`
— **`--space-5` nunca se definió** en la escala de espaciado (`:root` sólo tenía
`--space-1/2/3/4/6/8`). Sin fallback, `var()` con una variable inexistente se resuelve a su
valor inicial — para `gap`, eso es `normal`/0 — así que el `gap` no aplicaba nada pese a
estar escrito. Grep confirmó que no era sólo mío: `--space-5` se usaba en **7 reglas del
archivo**, varias de antes de esta sesión, todas potencialmente con el mismo problema
silencioso.

Fix de raíz, no un parche local: se agregó `--space-5: 20px` al `:root` (seguía la
progresión 4/8/12/16/_20_/24/32 ya establecida), corrigiendo las 7 reglas de una vez en vez
de poner un valor hardcodeado sólo en las dos que se acababan de escribir.

Además, revertido lo que el usuario no pidió: `.knowledge-upload-card` perdió el borde de
2px en `--aqua-deep` y la sombra propia que le había agregado en §9.29 — vuelve a ser una
`.card` genérica, mismo tamaño/forma que antes, tal como se pidió ("mismo tamaño,
dimensiones, formas"). La jerarquía sigue viniendo del ORDEN (va primera en la página), no
de un estilo distinto. También se cambió `align-items: stretch` (default de flex, estiraba
la tarjeta de llamada a la altura completa de la de carga) a `flex-start`, para que cada
tarjeta tenga su alto natural.

tsc + eslint limpios, build de Next OK, `--space-5:20px` verificado en el bundle CSS
servido. 409 passed / 3 skipped (sin cambios de backend).

## 9.31 La caja de carga seguía demasiado grande — le faltaba el límite de ancho

Feedback en vivo tras §9.30: el borde/sombra ya se había quitado, pero la caja seguía
ocupando casi todo el ancho de la fila — el usuario pidió "dejarlo donde está [primera en
la página], pero más pequeño [el tamaño que tenía antes]".

Causa: `flex: 1 1 auto` (agregado en §9.29) estira el elemento para llenar TODO el espacio
disponible de la fila flex. Antes del rediseño, la tarjeta vivía en un `.two-col`
(`grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr)`) junto a "Versión activa" —
ocupaba ~45% del ancho del contenedor, no el 100%.

Fix: `flex: 0 1 680px` — no crece más allá de 680px (aproxima el ancho que tenía en el
`0.9fr` del grid anterior), sí se encoge en pantallas angostas. Mantiene la posición (primer
elemento de la página, fuera del grid de dos columnas) sin heredar el tamaño de "ocupar
todo lo que sobre".

Build OK, `flex:0 680px` verificado en el bundle CSS servido (normalizado por el
minificador, equivalente a `flex: 0 1 680px`). 409 passed / 3 skipped (sin cambios de
backend).

## 9.32 Rediseño de /knowledge según sketch del usuario: dropzone real, tabla simplificada, barra inferior

El usuario aportó un sketch/mockup detallado y pidió rediseñar la página según ese dibujo.
Cambio más grande de la sesión sobre esta página, en una sola tarjeta unificada de tres
columnas donde antes había dos tarjetas separadas (§9.29):

- **Columna 1** — texto introductorio ("Cargar guía clínica" + descripción), sin cambios de
  contenido.
- **Columna 2** — zona de arrastrar-y-soltar **funcional**, no decorativa: `onDragOver` /
  `onDragLeave` / `onDrop` sobre un `<div>`, que al soltar un archivo lo asigna al
  `<input type="file">` real (ahora oculto, `sr-only`) construyendo un `DataTransfer` —
  `input.files = transfer.files` — porque un `<input type="file">` no acepta un array de
  archivos por asignación directa. El botón "Seleccionar archivo" sigue abriendo el selector
  nativo (`fileInputRef.current.click()`). `handleUpload` no cambió una línea: sigue leyendo
  `form.elements.namedItem("file")`, así que la validación/subida es exactamente la misma
  sin importar si el archivo llegó por clic o por arrastre.
- **Columna 3** — "Probar en una llamada" con su propio botón de texto ("Iniciar prueba")
  en vez de que el ícono redondo fuera el control (como en §9.29) — coincide con lo dibujado
  en el sketch.
- Los campos de aplicabilidad (procedimiento/fase) pasan a vivir en un `<details>` de ancho
  completo debajo de las tres columnas, no dentro de ninguna de ellas — el sketch no los
  dibuja explícitamente, así que se conservó la funcionalidad sin inventar una ubicación que
  no estaba especificada.
- El hero pierde los dos chips que llevaba al lado ("N guías oficiales" / "Versión de
  conocimiento") — se consolidan en una **barra inferior nueva** (`.knowledge-status-bar`)
  al final del contenido, sin `position: fixed` (la página ya tiene modal de llamada +
  diálogo de confirmación, cada uno con su propio `z-index`; una barra fija sumaba solapes
  posibles sin necesidad real, dado que es información de apoyo, no una acción).
- La tabla de documentos se simplifica a las columnas del sketch (Nombre de la guía /
  Versión / Estado / Fecha de subida / Acciones) con **botones de solo ícono** (ojo/basura,
  SVG en línea, sin librería) en vez de botones de texto. Nada de información se pierde:
  Tamaño, Aplicabilidad, Checksum y Versión eliminada se mueven a la fila de detalle
  expandible que ya existía (`toggleDetailRow`), sólo se sacan de la vista por defecto.
- `createdAt` ya vivía en `KnowledgeDocument` a nivel de lista (confirmado antes de tocar
  nada) — la columna "Fecha de subida" no necesitó ningún cambio de API ni de tipos.

Dos decisiones de alcance, explícitas y no preguntadas antes de implementar (siguiendo el
mismo criterio usado con el 4º caso de prueba en §9.22 — decidir y explicar, no bloquear en
una pregunta cuando el criterio es claro):
- **Se conserva** el recorrido de pasos 1/2/3 (`.knowledge-steps`, §9.26) aunque no aparece
  en el sketch — es una funcionalidad ya pedida explícitamente antes, y nada en el pedido de
  esta vez decía quitarla; se interpreta el sketch como gobernando la tarjeta superior y la
  tabla, no la página completa.
- **Se elimina** la tarjeta separada "Versión activa": su información quedó duplicada por la
  nueva barra inferior, y el sketch no la dibuja. "Consulta de verificación" (búsqueda G3)
  se conserva sin cambios — es evidencia funcional de learn/retrieve, no meramente
  informativa.

Verificación: tsc + eslint limpios, `next build` OK. Contenedor `web` reconstruido; el HTML
servido por curl sólo muestra las partes estáticas (React aún no hidrató), así que la
verificación real fue contra el **bundle JS y CSS servidos**: las clases y textos nuevos
(`knowledge-dropzone*`, `knowledge-call-test*`, `knowledge-status-bar`, `icon-btn*`,
"Arrastra y suelta archivos aquí", "Iniciar prueba", "Nombre de la guía", "Fecha de
subida") aparecen; las clases muertas del diseño anterior (`knowledge-top-row`,
`knowledge-call-fab*`, `upload-zone`) no aparecen en ningún bundle. CSS servido con llaves
balanceadas (417/417). Se confirmó además contra la API real y viva: `GET /api/v1/cases`
devuelve el caso `skip_interview_checklist=true` que alimenta la columna 3, y
`GET /api/v1/knowledge/documents` devuelve 108 documentos (107 oficiales protegidos + el
resto de prueba) todos con `created_at`, exactamente lo que la tabla y la barra inferior
esperan una vez hidratada la página en un navegador real. 409 passed / 3 skipped (sin
cambios de backend).

## 9.33 El ícono de micrófono chocaba con el encabezado en la columna "Probar en una llamada"

Feedback en vivo tras §9.32, con screenshot: el ícono de micrófono quedaba pegado al texto
"Probar en una llamada", encimado, y la columna se veía "mal distribuida" en conjunto.

Causa, la misma familia de bug que `--space-5` (§9.30) — la caja CSS no coincide con lo que
se ve: `.mic-symbol` declara una caja de `28px` de alto, pero su glifo se dibuja con
`::before`/`::after` posicionados en **absoluto** (la base y el pie del micrófono), que se
salen de esa caja y llegan a `~44px` reales. En `.mic-button` (76px, el ícono siempre solo,
sin hermanos debajo dentro del mismo contenedor) el desborde nunca se notaba porque no había
nada con qué chocar. Aquí, como hijo directo de un `flex-direction: column` con
`gap: 2px` y un `<h3>` justo debajo, el pie del glifo quedaba montado sobre el texto.

Fix: envolver el glifo en `.knowledge-call-test-icon` (52×52px, `display:grid;
place-items:center`), mismo patrón ya usado en `.context-icon` / `.speaker-icon` /
`.risk-summary-icon` — el espaciado con el encabezado pasa a calcularse sobre la caja real
de la insignia, no sobre la engañosa de 28px del glifo. De paso, `gap` de la columna sube de
`2px` a `8px` para un ritmo vertical parejo con la columna del dropzone.

Verificación: tsc + eslint limpios, build OK, contenedor reconstruido. Confirmado en el CSS
servido que `.knowledge-call-test-icon{place-items:center;width:52px;height:52px;
display:grid}` está presente y que la regla vieja `.knowledge-call-test .mic-symbol{...}`
ya no existe; confirmado en el bundle JS que la clase nueva se emite desde el componente.

## 9.34 Latencia voz-a-voz, corrección de G3, disco lleno y cuota diaria de Groq — cuatro hallazgos de una sola tarea

Pedido: "obtener los datos de latencia y lo otro que piden en los requisitos del concurso.
No vamos a correr tests largos, solo lo que pidan en el concurso." Cuatro hallazgos reales,
en el orden en que aparecieron.

**1. `docs/final-report.md` §2.1 pedía una compuerta más estricta de la que existe.**
Antes de tocar código, se releyó la rúbrica y `stack-tecnico.md` del kit oficial
palabra por palabra (`raw.githubusercontent.com`, no la página de marketing —
el primer fetch a `sourcemeridian.com/tech-sphere-challenge` dio un resumen genérico y
sin cifras, y llevó a un segundo fetch más específico). El texto verbatim de
`stack-tecnico.md` §1:

> "La lista fija **familias**, no versiones puntuales [...] Si un modelo sugerido ya no
> existe, usa el sucesor vigente de la misma familia y proveedor [...] Esto no cambia cómo
> se revisa la compuerta G3: lo que se evalúa es que el modelo pertenezca a una de las
> familias permitidas [...] no que coincida un identificador exacto de versión."

La sección anterior (hasta el 8 de agosto) declaraba `llama-3.1-8b-instant` razonando que
había que preservar el número de versión (`3.1`) de la lista original y ceder en tamaño.
Esa lectura era más estricta de lo que la compuerta exige — no había ambigüedad de G3 que
resolver, sólo un cambio de capacidad (12.000 TPM del 70B vs 6.000 del 8B, ver §9.20/9.21)
que la documentación nunca reflejó. Reescrito con la cita verbatim de por qué, en vez de
sólo cambiar el nombre del modelo. Se corrigieron además tres menciones obsoletas en el
README raíz (`"Llama 3.1 70B"` en el resumen de arquitectura — un tercer nombre distinto,
nunca actualizado desde antes de la primera corrección de modelo — y `"Phi-3.5 Mini"` como
resguardo, cuando el resguardo real siempre fue `Ollama/llama3.2:3b`).

**2. Disco lleno a mitad de sesión — bloqueo real de entorno, no de código.** Con la sesión
en curso, Bash empezó a fallar con `ENOSPC` en cualquier comando, incluido uno sin salida
(`true`); `Edit` confirmó que no era una partición aislada del harness, sino el disco real
del proyecto (`.tmp` de escritura atómica falló dentro de `web/src/app/`). Verificado que no
hubo corrupción (los archivos afectados quedaron exactamente como antes de cada intento
fallido — la escritura atómica falla antes de tocar el archivo real). El usuario liberó
espacio de Docker manualmente.

**3. Docker no volvía a responder tras liberar espacio.** `docker info`/`docker version`
colgaban indefinidamente pese a que los procesos de Docker Desktop, `com.docker.backend` y
`com.docker.virtualization` (la VM) seguían vivos — el daemon estaba en un estado atascado,
no caído. `osascript -e 'quit app "Docker"'` no cerró todo en 30s; escaló a `pkill`, pero un
proceso `com.docker.backend` (PID viejo, de antes del intento de reinicio) sobrevivió al
`pkill` y bloqueó que el relanzamiento (`open -a Docker`) levantara una instancia nueva y
limpia — el VM console log no mostraba actividad nueva pese al relanzamiento. Matar ese PID
específico y relanzar sí funcionó: daemon respondiendo en ~15s. El volumen persistente
(`source-meridian-agent_care_companion_data`) sobrevivió intacto — no hizo falta
re-ingestar el corpus ni el dataset.

**4. La cuota *diaria* de Groq (TPD), no sólo la de minuto (TPM), se agota con uso real
acumulado.** Con Docker recuperado, se corrió una medición corta (3 casos del dataset, no
los 12 completos — "no vamos a correr tests largos") contra `llama-3.3-70b-versatile`, el
modelo realmente desplegado (la corrida `capa1-groq.json` del 8 de agosto medía
`llama-3.1-8b-instant`, ya no el default). A mitad del turno 5 del tercer caso, Groq empezó
a responder 429 con `tokens per day (TPD): Limit 100000, Used 99659` — cuota consumida por
el desarrollo/pruebas acumuladas del día, no por esta corrida sola. El adapter
(`FallbackLLM`) cayó al resguardo local como debía, sin romper la conversación, pero eso
contaminó 2 de 16 turnos con tiempo de reintento + modelo local en vez de Groq real.
Verificado por proveedor consultando la tabla `events` directamente (payload de cada
`agent.*.completed` trae `provider`): 32 de 36 invocaciones fueron `groq`, 3 `ollama` — las
3 últimas de la sesión `verde`, ninguna antes. Se reportan ambos números (limpio de 14
turnos: P50 3.782 ms / P95 5.139 ms; crudo de 16: P50 4.044,6 ms / P95 13.984,6 ms) en vez
de promediarlos — mismo criterio que el outlier de 24,5s de la corrida anterior. El único
falso positivo de esta corrida ocurrió exactamente en el turno servido por el resguardo, así
que no se cuenta como hallazgo de precisión del modelo primario. Tokens/costo de la tabla
principal usan sólo los 32 llamados a Groq, para no atribuirle a Groq consumo que sirvió
gratis el modelo local. Documentado como riesgo operativo para la sesión del jurado: si
evalúan el mismo día que hubo desarrollo activo, pueden toparse con el mismo 429→resguardo.

**Además, instrumentación nueva** (no un hallazgo, una pieza que faltaba): `CallModal.tsx`
mide en el navegador, por llamada, latencia voz-a-voz real — desde que termina de hablar el
paciente (`sendText`, mismo punto para turno de voz o fallback de texto) hasta que empieza a
sonar el audio del agente (transición `false→true` de `voice.speaking`, que ocurre en
`utter.onstart`) — la definición exacta de la rúbrica §5. Se muestra en vivo junto al
micrófono (P50/P95 acumulados de la llamada en curso) y se loguea a consola. No hay forma de
generar una muestra real sin una llamada real con micrófono (STT/TTS son ambos del
navegador) — instrumentado y verificado en el bundle servido, pendiente de una llamada real
para tener muestras.

Verificación: tsc + eslint limpios, `next build` OK, instrumentación confirmada en el bundle
JS/CSS servido (clase `.voice-latency-readout` presente con las reglas correctas). Backend:
ruff + pytest limpios (409 passed / 3 skipped) antes de la corrida del benchmark — sin
cambios de código de backend en esta tarea, sólo documentación y el script de medición ya
existente. `docs/final-report.md` §2.1, §4 y §6 y `README.md` actualizados con cifras y
modelo reales; `docs/benchmarks/README.md` con el detalle completo de la corrida nueva.

## 9.35 Latencia voz-a-voz persistida como evento auditable, no sólo en memoria del navegador

Pregunta del usuario tras §9.34: si hace una llamada, ¿queda "registrada"? Respuesta honesta
en su momento: no — la instrumentación vivía en un `ref`/`state` de React dentro de
`CallModal.tsx`, visible sólo mientras el modal estuviera abierto, sin tocar el backend. El
usuario pidió explícitamente la opción robusta: "necesitamos este porque el jurado me
imagino que debe corroborar por sus propios medios" — coherente con la rúbrica §5
("se contrasta con lo que ocurre en la sesión... con tus logs").

**Backend, reutilizando infraestructura ya existente en vez de inventar una nueva:**
- `POST /api/v1/sessions/{id}/voice-latency` (`VoiceLatencyRequest{latency_ms: float, gt=0}`,
  204 sin cuerpo) — valida que la sesión exista (404 si no) y persiste vía
  `EventRepository.add_event(event_type="client.voice_latency_reported", latency_ms=...)`,
  el mismo repositorio que ya usa `session.finished` y todo el resto de la traza.
- `AuditRepository.voice_latency_percentiles()` — misma fórmula de percentil que
  `latency_percentiles()` (extraída a un helper compartido, `_percentile_stats`, para no
  duplicarla), filtrando `client.voice_latency_reported` en vez de `turn.response_sent`.
  Devuelve `sample_size=0`/`None` sin muestras — nunca inventa un número.
- `GET /api/v1/metrics` gana el campo `latency_voice`, separado de `latency_p50`/`latency_p95`
  a propósito: son dos definiciones distintas (proxy de servidor vs. medición real de
  navegador), mezclarlas habría sido engañoso.

**Bug real encontrado de paso, no buscado:** al leer `usage_summary()` para decidir dónde
enganchar esto, `_cost_metric` sumaba TODOS los tokens de `agent.*.completed` sin mirar el
proveedor real de cada llamada. Con el hallazgo de §9.34 (cuota diaria de Groq agotada a
mitad de una corrida, `FallbackLLM` degradando algunas llamadas a Ollama gratis) esto ya no
era hipotético: cualquier sesión con al menos una llamada degradada infla el costo reportado
cobrando precio de Groq por tokens que sirvió gratis el modelo local — exactamente el tipo de
número que "no se sostiene" que la rúbrica penaliza explícitamente. `usage_summary()` ahora
desglosa tokens por proveedor (`by_provider`, leído del `payload.provider` que cada
`agent.*.completed` ya traía) y `_cost_metric` sólo cobra los del proveedor primario
configurado (`settings.llm_provider`), reportando aparte cuántos tokens de resguardo quedaron
excluidos. Verificado en producción, no sólo en test: `GET /api/v1/metrics` contra los datos
reales acumulados de toda la sesión de desarrollo mostró `"33496 tokens de resguardo
excluidos, sin costo real"` — la mezcla no era un caso de laboratorio, ya estaba pasando.

**Config:** se activó el precio real de Groq (`LLM_COST_PER_MILLION_INPUT_TOKENS=0.59`,
`OUTPUT_TOKENS=0.79`, verificado en §9.34) tanto en `api/.env` como en `.env.example` — antes
estaba comentado con valores ilustrativos `0.00`, así que `/metrics` reportaba costo
"pendiente" incluso con tokens medidos. Con esto, costo por llamada se calcula solo, en vivo,
sin depender de que alguien lo compute a mano.

**Frontend:** `CallModal.tsx` llama `api.reportVoiceLatency(sessionId, latencyMs)` justo
después de calcular cada muestra (mismo punto que ya alimentaba el readout en pantalla y la
consola) — *fire-and-forget*, con `.catch()` que descarta el error en silencio: es telemetría
secundaria, un fallo de red aquí nunca debe interrumpir la llamada en curso, mismo criterio
que `EventRepository` ya documentaba para sus propios llamadores. `MetricsBand.tsx` (la banda
de métricas de `/audit`) gana una quinta tarjeta, "Latencia voz-a-voz", junto a P50/P95/
Tokens/Costo — con lo que la grilla fija de 4 columnas dejaba una tarjeta sola en una segunda
fila; cambiada a `repeat(auto-fit, minmax(200px, 1fr))` para que se acomode sola sin importar
el conteo.

**Tests nuevos (5), todos verificando comportamiento real, no sólo forma:**
- `test_report_voice_latency_persists_event_and_returns_204` — round-trip completo: POST →
  204 → aparece en `/api/v1/metrics` Y en la traza de la sesión.
- `test_report_voice_latency_missing_session_returns_404` /
  `..._rejects_non_positive_value` (422).
- `test_metrics_voice_latency_percentiles_with_multiple_samples` — 5 muestras con P50≠P95
  para probar la fórmula, no un caso trivial de una sola muestra.
- `test_cost_only_counts_primary_provider_tokens_not_fallback` — la regresión del bug de
  arriba: dos eventos en la misma sesión, uno `provider=groq` y otro `provider=ollama`, y se
  verifica que sólo el primero entra al costo. Requirió construir un `TestClient(create_app())`
  local dentro del test (en vez del fixture `client` compartido) porque `Settings` se lee al
  crear la app — un `monkeypatch.setenv` dentro del cuerpo del test llega tarde si la app ya
  se construyó en un fixture.

Verificación: tsc + eslint + build limpios. Backend: ruff limpio, 414 passed / 3 skipped
(409 anteriores + 5 nuevos). Contenedores reconstruidos (api y web); verificado en vivo contra
el sistema real corriendo, no sólo contra tests: sesión real creada, `POST .../voice-latency`
→ 204, `GET /api/v1/metrics` devolviendo `latency_voice` medido y `cost` medido con el
desglose de resguardo excluido sobre datos reales acumulados. Confirmado en el bundle JS
servido que `reportVoiceLatency` y la tarjeta "Latencia voz-a-voz" se emiten desde el
componente.

## 9.36 Auditoría de `docs/`: 11 archivos muertos borrados, diagrama reconstruido con el sistema real

Pedido: "hay demasiada documentación regada y no está consolidada... vamos a revisar qué se
puede depurar... dar un reporte conciso y detallado de los hallazgos antes de tomar la
decisión." Se auditaron los 33 archivos de `docs/` más `CLAUDE.md`, `CONTRIBUTING.md`,
`NOTICE` y los README de `api/`/`web/` — no por nombre, sino por fecha del último commit,
quién los referencia **desde código real** (no solo desde otros docs) y lectura directa del
contenido. El reporte completo con las cuatro categorías (eliminar / fusionar / mantener-
corrigiendo / mantener tal cual) se entregó al usuario antes de tocar nada; esta entrada
documenta solo lo que se decidió ejecutar.

**Patrón que confirmó la sospecha del usuario:** 19 de 33 archivos no se tocan desde el
23-24 de julio (fase previa al kit oficial, "T0") — nunca se volvieron a editar pese a que
el sistema cambió por completo desde entonces.

**Borrados (11 archivos, decisión del usuario — "Eliminarlos ya"):** confirmado que ninguno
tiene referencia ni desde código (`api/`, `web/src`) ni desde los documentos que sí se
conservan (`README.md`, `final-report.md`, `plan.md`, `CLAUDE.md`, `architecture.md`,
`spec.md`, `traceability.md` — verificado con grep explícito antes de borrar, cero
coincidencias). Eran plantillas con scores vacíos para decisiones ya tomadas
(`rag-decision-scorecard.md`, `voice-decision-scorecard.md`: literalmente dicen "nadie debe
completar los scores antes del 7 de agosto" para un RAG y una voz que ya estaban
implementados desde el 23-24 de julio), una nota que se autodeclara superseded
(`stop-work-note.md`), plantillas de proceso nunca llenadas (`adr-template.md`,
`clean-install-log.md`, `evidence-ledger.md`), y artefactos de logística personal sin
relación con el producto (`health-shift-plan.md`, `pre-010-workstation.md`,
`agenda-t0.md`, `organizer-questions-draft.md`). Además, `web/README.md`: era el boilerplate
sin editar de `create-next-app` ("This is a Next.js project bootstrapped with...") — cero
contenido del proyecto real. Se reemplazó por uno real (estructura de `src/`, comandos de
desarrollo con los puertos reales, mención a `CallModal` compartido).

**Diagrama reconstruido, no retocado (`docs/architecture-diagram.md`, entregable #2):** la
v1.0 (24 de julio) mostraba `LLMPort → FakeLLM`, `EmbeddingsPort → Fake` y
`ChallengeCasePort → Fixture (Delta Share en T0)` — ninguno de los tres existe hoy (nunca
hubo Delta Share; Groq real + Ollama de resguardo; embeddings reales BGE-M3). Dado que el
criterio de 15pts "Comprensión del problema y diseño de la conversación" dice explícitamente
que el jurado toma piezas del diagrama al azar y las busca en el código, un diagrama
desalineado es peor que no tenerlo. v2.0 corrige los tres adapters, agrega el
`SafetySignalDetector` (ausente del original pese a ser parte real del flujo de decisión) y
la ruta de auditoría/métricas completa (`AuditRepository`, el evento
`client.voice_latency_reported` de §9.35) — inexistente en v1.0 porque `/audit` con métricas
reales no existía todavía el 24 de julio.

**Verificación del Mermaid sin poder renderizar en este entorno:** `mermaid-cli` vía `npx`
no encontró Chrome pese a instalar `chrome-headless-shell` y luego la versión exacta que
pedía (148.0.7778.97) — desajuste de rutas entre el caché de `npx` y el de `puppeteer
browsers install`, no resuelto por no ser bloqueante. En su lugar se validó con la librería
`mermaid` real en Node vía `jsdom` (sin necesidad de un navegador completo,
`mermaid.parse()` sobre cada bloque extraído): **ambos diagramas parsean sin error**
(`diagramType: 'flowchart-v2'`). Verificación estructural adicional: 4 `subgraph` / 4 `end`
balanceados; el único texto nuevo con `{}` literales (un parámetro de ruta en una etiqueta
de arista) se simplificó para no depender de que las llaves escapen igual dentro de
`-->|"..."|` que dentro de `[""]` (el otro uso de `{id}` que sí se conservó es idéntico al
de la v1.0 ya renderizada como DOC-002).

**Pendiente, explícitamente diferido por decisión del usuario:** las bitácoras solapadas
(`plan.md`, `CLAUDE.md`, `auditoria-kit-oficial-2026-08-07.md` cuentan la misma historia
tres veces) y los documentos citados desde código con datos falsos (`prompt-config-
appendix.md` con hashes de `interview.py`/`response.py` desactualizados —ambos se
reescribieron esta sesión—, `CLAUDE.md` con "Llama 3.1 70B" en su línea 117,
`traceability.md` con 34 de ~150 filas todavía marcadas `Pendiente-T0`) — el usuario pidió
priorizar el diagrama primero; estos quedan para una siguiente pasada.

Verificación: sin cambios en `api/app`, `api/tests` ni `web/src` (solo `docs/` y
`web/README.md`) — no aplica rebuild de Docker ni reejecutar la suite completa; se confirmó
con `git status` que el cambio queda acotado a documentación.

## 9.37 README: el comando de arranque pasa a ser lo primero, con URL real y sin `fake` como default

Pedido explícito: la URL real del repo en vez de `<repo-url>`, el comando de un solo paso
primero en el documento ("es lo más importante... súper sencillo de ejecutar"), la key de
Groq justo después, y quitar el adapter `fake` como camino recomendado ("eso complica las
cosas") — todo lo demás pasa a ser lectura adicional para cuando el jurado tenga tiempo.

**URL real:** `https://github.com/sebasga79/care-companion.git` (confirmada con
`git remote -v`, no de memoria).

**Orden nuevo:** "Qué hace" (contexto de 10 segundos) → **"Arranque en un solo comando"**
(movido de la línea 142 a la línea 25, justo después del contexto) → "Arquitectura" →
separador → todo lo demás bajo "información adicional para cuando el jurado tenga tiempo".

**Por qué la key de Groq queda "después" del comando pero técnicamente hay que configurarla
antes de correrlo la primera vez** — tensión real entre lo pedido literalmente y la
corrección funcional, resuelta así: `api/.env` nunca puede traer una key real de fábrica (es
un secreto, no se commitea), así que no existe versión del "un solo comando" que hable con
Groq sin que alguien pegue su propia key en algún momento. La resolución: el comando aparece
primero y grande (satisface "aparece de primero, es lo más importante"), inmediatamente
debajo — no en una sección aparte más abajo — están los 2 pasos para la key, enmarcados como
"antes de correrlo por primera vez". Se agregó además la instrucción de `--rebuild` para
quien corra el comando antes de configurar la key: `docker compose up -d` sin `--build`
no relee `api/.env` si los contenedores ya estaban arriba (`env_file` se inyecta al crear el
contenedor, no en un simple restart de uno ya existente) — sin este aviso, alguien que agrega
la key después se quedaría preguntándose por qué sigue en modo de prueba.

**No se tocó `api/.env.example`.** Se consideró cambiar su default de `LLM_PROVIDER=fake` a
`groq` para que baste editar una sola línea (la key) en vez de dos. Se descartó: con
`LLM_PROVIDER=groq` y `LLM_API_KEY=changeme` (el placeholder que trae el ejemplo), `Settings`
**rechaza el arranque** (`test_groq_rejects_changeme_api_key`) — quien olvide reemplazar la
key no vería el sistema en modo de prueba, vería la aplicación caerse. Mantener `fake` como
default de `.env.example` es justamente lo que evita que un olvido se convierta en un
arranque roto; el README ahora sólo dice que hay que editar las dos líneas juntas.

**Otras correcciones de paso:** la sección de resguardo local decía `ollama pull phi3.5` —
el resguardo real desde el 8 de agosto es `llama3.2:3b` (mismo error de nombre de modelo que
apareció y se corrigió en `final-report.md`/`docs/prompt-config-appendix.md`/`CLAUDE.md` en
tareas anteriores; este era un cuarto lugar con el dato viejo, no encontrado hasta ahora
porque nadie había grepeado "phi3.5" específicamente en `README.md`). Se separó además la
sección de "Probar con el modelo real" del original en dos: la key de Groq (ahora en el
arranque) y el resguardo Ollama (que sigue siendo opcional, movido a la sección de detalles).

Verificación: sin `<repo-url>` residual, sin menciones de `fake`/`phi3.5` fuera de contexto
técnico correcto (grep explícito de ambos), 14 fences de código (7 pares, balanceado), 
estructura de encabezados revisada. Sin cambios en `api/app`/`api/tests`/`web/src` — solo
`README.md`.

## 9.38 G2 realmente roto: un clon limpio de verdad no arrancaba — dos bugs, no uno

**Cómo se encontró.** El usuario corrió el comando exacto del README en su propia terminal
(`git clone ... && ./levantar_app.sh`) y reportó que terminó "rapidísimo", preguntando si de
verdad se instaló todo. La respuesta correcta no era confiar en la salida — fue confirmar
contra estado real: `docker ps` mostró que los contenedores de **esta misma sesión de
trabajo** (`source-meridian-agent-api-1`/`web-1`) seguían ocupando los puertos 49317/49318
desde hacía 10 minutos. El script de su clon nuevo hizo `curl` a esos puertos, los encontró
sanos, y dijo "ya está en ejecución" — **nunca tocó el clon nuevo**. Puertos son globales al
host, no por carpeta. El resultado "rápido" no validó nada; fue un falso positivo causado por
el propio entorno de desarrollo de esta sesión.

**La prueba real exigió reproducirla de verdad**, no confiar en el reporte del usuario ni en
una corrida aparentemente exitosa: se detuvieron los contenedores propios (liberando los
puertos) y se clonó el repo en un directorio nuevo bajo control directo, cronometrado. Esa
prueba **también falló**, y encontró dos bugs reales, distintos, que un jurado con una
máquina limpia habría encontrado exactamente igual — G2 (arranque ≤15 min) estaba roto de
verdad, no solo el reporte del usuario había sido un falso positivo:

**Bug 1 — `docker compose` exige `api/.env`, que nunca existe en un clon nuevo.**
`docker-compose.yml` declara `env_file: ./api/.env`; Compose trata un `env_file`
declarado-pero-ausente como error **fatal** para *cualquier* subcomando (`ps`, `images`,
`up`), no solo como "sin variables extra". Como `api/.env` está en `.gitignore` (es donde
vive la API key real, nunca se commitea), **todo clon nuevo lo dispara**. Sin el fix, el
comando del README moría en menos de un segundo con `env file .../api/.env not found`, un
mensaje que ni siquiera llega a imprimirse en el log del launcher (Compose lo escribe antes
de que el script pueda capturarlo con su propio manejo de errores).

Fix de dos capas:
- `levantar_app.sh`: si `api/.env` no existe, lo copia automáticamente desde
  `api/.env.example` (que ya trae el proveedor `fake`, seguro, sin credenciales) antes de
  llamar a cualquier `docker compose`. Restaura la promesa real de "un solo comando" sin
  exigir un paso manual antes de la primera corrida.
- `docker-compose.yml`: `env_file` pasa a `- path: ./api/.env` con `required: false`
  (sintaxis soportada desde Compose ~2.24; verificada contra v2.40.3 instalada). Cubre a
  quien use `docker compose up` directo — la ruta manual que el propio README documenta y
  que no pasa por el launcher.

**Bug 2 — `web/public/` está vacío desde el 23 de julio y por eso nunca quedó en git.**
Git no rastrea directorios vacíos — sólo blobs. Cuando se eliminó una imagen sin licencia de
`web/public/` en la fase de preparación (`CLAUDE.md`: "imagen sin licencia eliminada"), el
directorio quedó vacío y **git dejó de rastrearlo por completo**, sin ningún error ni aviso.
En el disco de esta sesión de trabajo el directorio vacío sigue existiendo (el filesystem no
borra directorios vacíos solo), así que **todas las corridas de Docker de esta sesión
funcionaron sin problema** — el bug era invisible desde la propia máquina de desarrollo.
Un clon nuevo, en cambio, no recibe `web/public/` en absoluto: `web/Dockerfile` hace
`COPY --from=builder /app/public ./public` en la etapa final de la imagen `web`, y esa copia
falla con `"/app/public": not found` porque el directorio fuente no existe — la imagen `web`
completa no se puede construir. Este es el hallazgo más serio de los dos: sin él, *ningún*
clon nuevo del repositorio público podía levantar el frontend, sin importar si `api/.env`
estaba bien configurado o no.

Fix: `web/public/.gitkeep` (archivo vacío, convención estándar para forzar a git a rastrear
un directorio sin contenido real).

**Depuración de la prueba misma, documentada porque llevó a un callejón sin salida real:**
la primera reconstrucción del bug, con `bash -x`, mostraba la traza deteniéndose justo
después de calcular `running_count=0`, sin error visible ni línea siguiente — parecía que el
propio conteo de contenedores/imágenes existentes fallaba bajo `set -euo pipefail`. Varias
reproducciones manuales de esa lógica exacta (incluida una réplica exacta de la función con
`local` + los mismos comandos `docker compose ps/images` bajo bash 3.2, la versión que trae
macOS por defecto) funcionaron perfectamente, sin reproducir el fallo — lo cual, en
retrospectiva, era la pista correcta: si la lógica en sí nunca fallaba aislada, el problema
tenía que estar en otro lado. Insertar `echo`/exit-code explícitos línea por línea en una
copia real del script (no una reproducción) finalmente lo mostró: el intento de depuración
inicial había copiado el script fuera del directorio del proyecto, rompiendo la resolución de
`$ROOT_DIR` (que depende de `dirname "${BASH_SOURCE[0]}"`) — un error de metodología de
prueba, no un bug del script. Corregido el placement, la instrumentación mostró la ejecución
real llegando limpiamente hasta `docker compose up -d --build`, que fue cuando apareció el
Bug 2 (`web/public` faltante) por primera vez de forma reproducible.

**Verificación final, de punta a punta, con los dos fixes aplicados:** clon fresco → build
completo (`api` con caché de capas de Docker de esta sesión — un juez con máquina 100%
virgen tardaría más aquí, la descarga de dataset/corpus no se ve afectada por esto; `web`
sin caché desde `COPY . .` en adelante, por el archivo nuevo) → volumen
`care-companion-clean-test_care_companion_data` genuinamente nuevo (nombre de proyecto
Compose distinto al de esta sesión, cero superposición) → bootstrap del dataset+corpus
oficial completo, ~110-120s (mismo rango medido en corridas anteriores de esta auditoría) →
`GET /health` 200, **107 documentos indexados** (corpus oficial completo) y **44 casos**
(40 pacientes reales + 4 sintéticos de prueba) — confirmado contra el sistema recién
construido, no asumido. Contenedores y volumen de prueba destruidos al terminar; el stack de
desarrollo de esta sesión, restaurado.

**Alcance de lo verificado vs. lo no verificado:** esta prueba confirma que el clon público
arranca y sirve datos reales de punta a punta. No mide el tiempo de descarga de las imágenes
base (`python:3.11-slim`, `node:22-slim`) ni de `apt-get`/`uv sync`/`pnpm install` sin ningún
caché de Docker — eso depende de la velocidad de red del jurado y no se puede medir desde
esta máquina. El presupuesto de 15 minutos de G2 tiene margen amplio incluso así: build
completo sin caché documentado en corridas anteriores del orden de minutos, no de la ventana
completa.

**Confirmación independiente, en la máquina del usuario (no la de esta sesión).** Con los
fixes ya en `main`, el usuario repitió el experimento en su propia terminal, cronometrado con
`time`: `git clone ... && cd care-companion && ./levantar_app.sh` → **1 min 44,85 s** de
punta a punta (clon + build + bootstrap completo + health-check listo). El build mostró
`CACHED` en las 11 capas de `api` y las 10 de `web`, incluida
`[web runner 5/5] COPY --from=builder /app/public ./public` — confirma que el fix de
`web/public/.gitkeep` resuelve el Bug 2 también fuera de esta máquina, no sólo en la prueba
propia. Configuración por defecto (LLM y embeddings `fake`) — distinto del `9 min 50 s`
histórico de §9.19, que medía con embeddings reales (BGE-M3) configurados a mano; no son
la misma medición y `docs/final-report.md` ahora reporta ambas por separado, sin que una
reemplace a la otra.
