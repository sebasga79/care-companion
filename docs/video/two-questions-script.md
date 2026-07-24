# Guion v0 — Las dos preguntas del video final

> v0.1 · 23 de julio de 2026 · Ticket: PRE-024

## 0. Marco

El video final (`plan.md` DOC-006, FIN-005) debe responder dos preguntas en ≤90 segundos hablados cada una (~220 palabras a ritmo de habla natural en español, ~150 palabras/minuto). Este es un guion **v0**: la estructura y el tono están listos para ensayo; los contenidos que dependen de la ficha técnica del 7 de agosto están marcados `[PENDIENTE-T0]` y no deben leerse en voz alta hasta reemplazarse con datos reales. Ensayar con marcadores visibles, no rellenarlos con suposiciones.

---

## Pregunta 1 — ¿Cuál es el problema y el valor de Care Companion?

### Guion hablado (~220 palabras / ≤90s)

> Care Companion es un agente de voz en español que acompaña a un paciente durante las primeras horas después de un procedimiento quirúrgico. El problema real es simple: cuando alguien sale de cirugía y llega a casa, tiene preguntas — "¿esto que siento es normal?", "¿necesito ir a urgencias?" — y no siempre hay alguien disponible para responderlas con criterio clínico y a tiempo.
>
> Care Companion conversa por voz, en español natural, entiende expresiones ambiguas o regionales sin asumir un diagnóstico, y hace preguntas adaptativas según lo que el paciente va reportando. Cada afirmación clínica que da está respaldada por documentos autorizados y citables — no improvisa desde conocimiento general. Si detecta una señal de alarma, no la minimiza ni la decide el modelo de lenguaje: reglas deterministas, no degradables, escalan el caso a revisión humana, con una explicación clara de qué se observó y por qué.
>
> El valor no es reemplazar a una enfermera o a un médico — es reducir el tiempo entre "algo no se siente bien" y que una persona con criterio lo sepa, mientras deja un resumen estructurado y trazable de la llamada. Es un sistema de apoyo y escalamiento, no un dispositivo médico ni un servicio de urgencias.

*(≈195 palabras — margen para pausas y respiración dentro de 90s.)*

### Versión bullet para ensayo

- Problema: pacientes post-alta tienen dudas y no siempre hay alguien disponible a tiempo.
- Qué hace: conversación de voz en español, natural, con preguntas adaptativas.
- Entiende ambigüedad regional sin asumir diagnóstico.
- Toda afirmación clínica tiene cita/fuente autorizada — no improvisa.
- Señales de alarma: reglas deterministas, no las decide el LLM; escalan a humano.
- Cierre: resumen estructurado y trazable; apoyo y escalamiento, no reemplazo clínico.

---

## Pregunta 2 — Decisión técnica principal, opciones descartadas, riesgos, y qué haría con 2 semanas más

### Guion hablado (~220 palabras / ≤90s) — plantilla con marcadores

> La decisión técnica principal fue [PENDIENTE-T0: nombre de la decisión — probablemente la estrategia de voz elegida en CH-007, p. ej. "pipeline WebSocket con STT, el modelo obligatorio y TTS por separado" o "la API realtime del proveedor"]. La elegí frente a [PENDIENTE-T0: opción descartada] porque [PENDIENTE-T0: razón concreta de la matriz de decisión — compatibilidad con el modelo obligatorio, latencia medida, o riesgo de fallo en demo].
>
> El riesgo más grande que identifiqué fue [PENDIENTE-T0: riesgo principal, probablemente relacionado con latencia de voz, falsos negativos clínicos, o borrado verificable del RAG — ver `plan.md` §13]. Lo mitigué con [PENDIENTE-T0: mitigación aplicada, p. ej. reglas deterministas no degradables, evidence gate, o presupuesto de latencia con fallback a texto].
>
> Con dos semanas más, lo primero que haría es [PENDIENTE-T0: siguiente paso técnico real, probablemente ligado a lo que quedó en el "orden de sacrificio" de `plan.md` §5 — p. ej. reranker adicional, responsive móvil completo, o reconexión más sofisticada]. Después de eso, invertiría en [PENDIENTE-T0: segunda prioridad — validación clínica más profunda, cobertura de más procedimientos, o observabilidad de nivel producción], porque [PENDIENTE-T0: por qué es la siguiente prioridad real, no la más vistosa].

*(La plantilla mide ≈150 palabras de texto fijo + espacio para ~70 palabras de contenido real una vez resueltos los marcadores, para no exceder 90s.)*

### Versión bullet para ensayo (estructura fija, contenido pendiente)

- Decisión técnica principal: [PENDIENTE-T0].
- Opción descartada y por qué: [PENDIENTE-T0].
- Riesgo principal identificado: [PENDIENTE-T0].
- Cómo se mitigó: [PENDIENTE-T0].
- Con 2 semanas más — prioridad 1: [PENDIENTE-T0].
- Con 2 semanas más — prioridad 2 y por qué: [PENDIENTE-T0].

---

## 1. Notas de ensayo

- Cronometrar cada respuesta en voz alta, no en lectura silenciosa — el ritmo real de habla varía por persona.
- La Pregunta 1 puede ensayarse completa desde ahora porque no depende de la ficha técnica.
- La Pregunta 2 se ensaya con los marcadores leídos tal cual ("pendiente de T0, decisión de voz") para practicar el ritmo y las pausas, sin inventar contenido de relleno.
- Al llenar los `[PENDIENTE-T0]` en el concurso, revalidar el conteo de palabras — no asumir que el reemplazo cabe en el mismo espacio.
