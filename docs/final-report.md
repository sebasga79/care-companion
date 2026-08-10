# Care Companion — Informe final

> v2.0 · 9 de agosto de 2026 · Source Meridian Tech Sphere Challenge 2026
> Estado: implementación integrada y ejecutable con el kit oficial.

## 1. Problema y propuesta de valor

El seguimiento postoperatorio depende de llamadas humanas que consumen tiempo
y pueden perder señales relevantes entre contactos. Care Companion realiza una
llamada de voz en español con el paciente o, cuando aplica, su
familiar/cuidador; conoce el procedimiento y la evolución histórica, pregunta
de forma adaptativa, recupera evidencia clínica citable y registra un resumen
estructurado para revisión humana.

No diagnostica ni prescribe. El valor es reducir el tiempo entre un síntoma
reportado y una revisión humana informada, sin delegar la decisión clínica a un
modelo de lenguaje. Todos los pacientes y datos del reto son sintéticos.

## 2. Arquitectura y decisiones

La solución es un monolito modular: FastAPI + SQLite WAL y una interfaz
Next.js. El detalle está en [`architecture.md`](architecture.md) y
[`architecture-diagram.md`](architecture-diagram.md).

| Decisión | Alternativa evaluada | Razón |
|---|---|---|
| Máquina de estados tipada | Superprompt único | Estados, fallos y cierres auditables |
| Agentes con responsabilidad única | Agente monolítico/malla | Aislar entrevista, triage y respuesta; ningún agente llama a otro |
| Reglas deterministas + reducción no degradable | Riesgo decidido solo por LLM | Un hallazgo duro nunca puede ser rebajado por el modelo |
| SQLite FTS5 + coseno + RRF | Servicio vectorial externo | Arranque reproducible, learn/forget transaccional y una sola persistencia |
| Paciente como entidad longitudinal | Elegir paciente por día | El agente recibe los cuatro antecedentes 1/3/7/14 y continúa el seguimiento |
| Web Speech API | Telefonía/proveedor adicional | Voz desde navegador, barge-in y medición voz-a-voz sin otra credencial |
| Groq detrás de `LLMPort` | SDK acoplado | Configuración verificable y resguardo local opcional sin tocar el dominio |

## 3. Modelo declarado — compuerta G3

**Modelo principal: `llama-3.3-70b-versatile`, familia Meta Llama, servido
por Groq en su nivel gratuito.** La configuración se encuentra en
`api/app/core/config.py` y `api/.env.example`; cada invocación registra
`provider` y `model` en `events`.

El documento oficial fija familias, no identificadores congelados, y autoriza
la versión vigente de Llama disponible en Groq cuando el snapshot de referencia
ha sido retirado. Llama 3.3 70B conserva la familia y el proveedor permitidos,
y mostró mejor seguimiento de instrucciones que la alternativa 8B durante las
pruebas conversacionales.

Como resguardo opcional se admite únicamente `llama3.2:3b` vía Ollama, también
de una familia permitida. No existe un proveedor simulado en la configuración
de runtime. Los dobles deterministas permanecen confinados a la suite para no
consumir cuota ni hacer los tests dependientes de la red.

La credencial Groq no se publica: `./levantar_app.sh` la solicita con entrada
oculta en el primer arranque y la guarda en `api/.env`, ignorado por Git. Esto
concilia reproducibilidad con el requisito de cero secretos versionados.

## 4. Implementación observable

| Área | Implementación/evidencia |
|---|---|
| Voz en tiempo real | Micrófono y TTS en Chrome, supresión de eco, barge-in y cierre hablado |
| Conversación | Apertura contextual, preguntas adaptativas, microtriaje y cierre automático |
| Memoria longitudinal | 40 pacientes; 160 episodios históricos 1/3/7/14 consolidados por entidad |
| RAG vivo | 107 documentos, learn/retrieve/forget, citas, versión y evidence gate |
| Decisión | Reglas `rules-v2`, detector sobre texto crudo y `reduce_decision` no degradable |
| Escalamiento | Registro idempotente, teléfonos principal/alterno y handoff humano visible |
| Resumen | `CallSummary`/`followup_record` v1.2 con seis ejes clínicos y próximos pasos |
| Auditoría | Sesiones, paciente, procedimiento, eventos, decisiones, citas, contactos y métricas |
| Reproducibilidad | Docker Compose + `./levantar_app.sh`; clon limpio observado en 1 min 45 s |

### Evidencia audiovisual

- Demo funcional publicada: [MVP Concurso Tech Sphere Challenge
  2026](https://youtu.be/wKgmlhy0Txo).
- Video de argumentación frente a cámara y respuestas a las dos preguntas de
  cierre: [Respuestas preguntas concurso Source
  Meridian](https://youtu.be/cez5dnn9KEA).

## 5. Métricas exigidas

La fuente canónica es `GET /api/v1/metrics`, reflejada en `/audit`. La latencia
voz-a-voz se mide desde el final del habla del paciente hasta el inicio del
audio del agente y se persiste como `client.voice_latency_reported`.

Muestras manuales reales del 9 de agosto, Chrome + micrófono + Groq/Llama 3.3
70B:

| Métrica | Resultado | Alcance |
|---|---:|---|
| Voz-a-voz P50 | 6154 ms (6,154 s) | n=4 |
| Voz-a-voz P95 | 6507 ms (6,507 s) | n=4 |
| Tokens entrada/salida por turno | 2 993,6 / 344,6 | 25 turnos; modelo final |
| Tokens entrada/salida por llamada | 12 473,5 / 1 435,7 | 6 llamadas cerradas |
| Invocaciones LLM por turno | 2,08 | 52 invocaciones |
| Consultas RAG por llamada | 2,83 | 17 consultas |
| Costo estimado por llamada | US$0,0085 | tarifas Groq declaradas |

El tamaño de muestra es pequeño y se declara como tal. **2,5 s no es un
umbral oficial:** fue una meta interna anterior al kit. La rúbrica exige
reportar P50/P95 y que coincidan con la sesión y los logs.

Snapshot del 9 de agosto de 2026, ventana UTC
`2026-08-09T01:06:23`–`2026-08-09T20:48:00`. Tokens, invocaciones LLM,
consultas RAG y costo usan solo sesiones cerradas de
`groq/llama-3.3-70b-versatile`. La API devuelve el número de llamadas, la
ventana temporal y el desglose por proveedor/modelo; excluye sesiones
abiertas, pruebas y eventos no verificables. El costo de Groq se estima con
US$0,59/1M tokens de entrada y US$0,79/1M de salida, dividido entre las
llamadas cerradas que realmente usaron Groq. Los tokens de Ollama no se
cobran con tarifa Groq ni se mezclan con la muestra final; quedan visibles en
`scope.excluded_other_model_tokens` (5850 en este snapshot).

El arnés en `api/scripts/benchmark.py` y sus artefactos se conservan como
evidencia histórica de desarrollo, pero no se usan para afirmar sensibilidad
o especificidad del modelo final: la cuota gratuita impidió reunir una muestra
equilibrada suficiente. La defensa clínica se apoya en reglas deterministas,
tests adversariales y trazas de la aplicación, no en porcentajes inestables.

## 6. Seguridad y límites

- Sin evidencia activa y aplicable no hay afirmación clínica: se aclara,
  abstiene o escala.
- Las red flags deterministas tienen precedencia sobre el LLM.
- Silencio, ambigüedad o dato ausente nunca equivalen a negación.
- Ante fallo de modelo, RAG o persistencia con riesgo, el estado seguro es
  abstención/escalamiento.
- Los documentos recuperados se tratan como datos no confiables, no como
  instrucciones.
- No se guarda audio bruto ni chain-of-thought; el repositorio no contiene
  credenciales.
- Es un prototipo de concurso con datos sintéticos, no un dispositivo médico,
  servicio de urgencias ni integración hospitalaria real.

## 7. Reproducibilidad y trazabilidad

- Arranque: [`README.md`](../README.md) y `./levantar_app.sh`.
- Arquitectura: [`architecture.md`](architecture.md).
- Prompts/configuración: [`prompt-config-appendix.md`](prompt-config-appendix.md).
- Matriz requisito→código→prueba: [`traceability.md`](traceability.md).
- Dependencias/licencias: [`NOTICE`](../NOTICE).
- Proceso y decisiones: [`CLAUDE.md`](../CLAUDE.md), [`plan.md`](plan.md) y
  ADRs.
