# Borrador — Correo de preguntas al organizador

> v0.1 · 23 de julio de 2026 · Ticket: PRE-026

## 0. Marco

Este borrador consolida **únicamente** preguntas sobre información que el reto aún no ha publicado, derivadas de las preguntas abiertas OQ-001…OQ-010 (`spec.md` §13). No solicita material anticipado, ventajas, ni información que rompa la equidad de arranque simultáneo el 7 de agosto. Máximo 8 preguntas numeradas, consolidando las 10 OQ donde es razonable agruparlas.

---

## Asunto sugerido

**Preguntas de preparación — Tech Sphere Challenge 2026 (Voice Agent Edition)**

## Cuerpo del correo

Estimado equipo organizador,

Estamos en fase de preparación para el Tech Sphere Challenge 2026 (Voice Agent Edition) y queremos llegar el 7 de agosto con el menor número de supuestos posible. A continuación, un conjunto breve de preguntas sobre información operativa que no hemos encontrado publicada. No solicitamos material del reto de forma anticipada — solo aclaraciones sobre el proceso y las reglas para poder planear nuestro entorno y cronograma con precisión.

1. **Deadline y formato de entrega:** ¿Cuál es la fecha, hora exacta y zona horaria del cierre de entrega, y cuál es el canal/formulario exacto por el que debe enviarse el proyecto final?

2. **Modelo obligatorio:** ¿Qué modelo único deben usar todos los participantes, y qué modalidades soporta de forma oficial (texto, voz nativa/realtime, function calling, salida estructurada)?

3. **Proveedor de voz:** ¿Se permite usar un proveedor externo de STT/TTS junto con el modelo obligatorio, o el reto exige un proveedor de voz específico?

4. **Dataset (Delta Sharing):** ¿Cuál es el schema, el volumen aproximado y la licencia de uso del dataset que se compartirá el 7 de agosto?

5. **Corpus clínico y documentos base:** ¿Qué procedimientos y tipos de documento cubre el corpus provisto, y bajo qué licencia pueden incluirse (o referenciarse) esos documentos en un repositorio público?

6. **Compuertas y métricas oficiales:** ¿Existe una especificación detallada de las cinco compuertas eliminatorias y sus criterios de test, y cuál es el formato exacto exigido para reportar latencia P50/P95, tokens y costo por llamada?

7. **Credenciales en repositorio público:** ¿Qué implica exactamente el requisito de que las credenciales de acceso estén "incluidas" en un repositorio público — se refiere a instrucciones de obtención, a un mecanismo de inyección en tiempo de ejecución, o a algo distinto?

8. **Disclosure de asistencia de IA:** ¿Se permite el uso de asistentes de código como Claude o Codex durante la construcción, y si es así, qué nivel de disclosure se exige en el informe final sobre su uso?

Agradecemos cualquier aclaración que puedan compartir antes del inicio. Quedamos atentos.

Saludos cordiales,
SG

---

## 1. Trazabilidad a OQ (spec.md §13)

| Pregunta del correo | OQ cubiertas |
|---|---|
| 1. Deadline y formato de entrega | OQ-007 |
| 2. Modelo obligatorio | OQ-001 |
| 3. Proveedor de voz | OQ-008 |
| 4. Dataset (Delta Sharing) | OQ-003 |
| 5. Corpus clínico y documentos base | OQ-004, OQ-010 (parcial: licencia de documentos) |
| 6. Compuertas y métricas oficiales | OQ-002, OQ-005 |
| 7. Credenciales en repositorio público | OQ-006 |
| 8. Disclosure de asistencia de IA | OQ-009 |

Nota: OQ-010 (licencia de dataset/documentos/starter) queda cubierta parcialmente por la pregunta 5 (documentos) y por la pregunta 4 (dataset); la licencia del starter en sí no se pregunta por separado para mantener el máximo de 8 preguntas — si el organizador no la aclara espontáneamente, queda como seguimiento post-envío.
