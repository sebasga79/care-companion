# Matriz de decisión — Pipeline de voz (CH-007 / ADR-007)

> v0.1 · 23 de julio de 2026 · Ticket: PRE-032

## 0. Propósito y regla dura

Esta matriz **prepara** la decisión de voz del ticket CH-007; **no la toma**. Los scores de esta plantilla están intencionalmente vacíos y se llenan en T0 con datos reales de la ficha técnica (modelo obligatorio, proveedor permitido, credenciales). Nadie debe completar los scores antes del 7 de agosto.

Decisión a tomar: **Opción A — pipeline WebSocket (STT → modelo obligatorio → TTS, orquestado por Care Companion)** vs **Opción B — API realtime del proveedor del modelo obligatorio** (si existe y la ficha la permite).

Referencia arquitectónica: `architecture.md` §10.2 ("Decisión diferida al 7 de agosto") y ADR-007 (`architecture.md` §17, estado actual: *pendiente*). El resultado final de esta matriz, con los scores reales, es el insumo directo para redactar ADR-007.

Presupuesto de tiempo: decidible en **≤90 minutos** de spike (ver nota de timebox en `docs/t0/agenda-t0.md` — el timebox oficial de CH-007 en `plan.md` es 25 min; esta matriz está diseñada para poder ejecutarse en ese margen si es necesario, con el spike de 90 min como techo teórico de `architecture.md`).

## 1. Criterios ponderados

Los pesos son parte de la preparación (metodología de evaluación), no de la decisión de voz en sí. Son ajustables en T0 si la ficha técnica prioriza algo distinto (p. ej. si el proveedor obligatorio no ofrece Opción B en absoluto, este criterio deja de ser comparativo).

| Criterio | Peso | Qué mide |
|---|---:|---|
| Compatibilidad con el modelo obligatorio | 25% | ¿La opción funciona con el modelo/proveedor único que exige la ficha, sin fallback a otro LLM? |
| Latencia primer audio | 20% | Tiempo desde fin de habla del paciente hasta el primer byte de audio de respuesta (objetivo interno `architecture.md` §10.3: ≤2.5s P95, sujeto a métricas oficiales) |
| Viabilidad de barge-in ≤250ms | 20% | ¿La opción permite cancelar TTS en curso al detectar nueva voz, dentro de ≤250ms P95 (NFR-003)? |
| Complejidad de implementación en 72h | 15% | Cuánto código/integración nuevo exige construir y estabilizar dentro de la ventana del concurso |
| Riesgo de fallo en demo | 15% | Probabilidad de fallo no recuperable durante la grabación/demo en vivo (dependencias externas, rate limits, inestabilidad) |
| Costo | 5% | Costo por llamada/token/minuto de audio, si es relevante bajo el presupuesto del reto |

**Suma de pesos: 100%.**

## 2. Tabla de scoring (VACÍA — llenar en T0)

Escala 1–5 por opción y criterio (1 = muy desfavorable, 5 = muy favorable). Score ponderado = score × peso.

| Criterio | Peso | Score Opción A (WebSocket) | Ponderado A | Score Opción B (Realtime API) | Ponderado B |
|---|---:|:---:|:---:|:---:|:---:|
| Compatibilidad con el modelo obligatorio | 25% | ☐ | | ☐ | |
| Latencia primer audio | 20% | ☐ | | ☐ | |
| Viabilidad de barge-in ≤250ms | 20% | ☐ | | ☐ | |
| Complejidad de implementación en 72h | 15% | ☐ | | ☐ | |
| Riesgo de fallo en demo | 15% | ☐ | | ☐ | |
| Costo | 5% | ☐ | | ☐ | |
| **Total ponderado** | 100% | | **☐** | | **☐** |

## 3. Spike mínimo por opción — qué medir y cómo

Ambos spikes usan el mismo enunciado/audio de prueba fijo (fixture desechable, no clínico) y el mismo número de repeticiones, para que los resultados sean comparables.

### Opción A — Pipeline WebSocket (STT → LLM → TTS)

**Qué armar:** script mínimo que abre un stream de audio (mic o fixture grabado), lo envía en chunks al proveedor STT disponible bajo el stack permitido, pasa el texto final al adapter del modelo obligatorio, y transmite la respuesta al proveedor TTS en streaming.

**Qué medir (N=5 corridas, mismo enunciado):**
- tiempo desde fin de habla (VAD) hasta primer transcript parcial de STT;
- tiempo desde transcript final hasta primer token del modelo;
- tiempo desde primer token del modelo hasta primer byte de audio TTS;
- latencia de cancelación: al inyectar una segunda voz simulada mientras TTS reproduce, tiempo hasta que el audio se corta.

**Cómo:** instrumentar cada salto con timestamps y un `correlation_id` común; registrar P50/P95 de las 5 corridas.

### Opción B — API realtime del proveedor del modelo obligatorio

**Qué armar:** conexión mínima a la API realtime del proveedor (si existe para el modelo obligatorio), usando el SDK oficial, con el mismo enunciado/audio de prueba.

**Qué medir (N=5 corridas, mismo enunciado):**
- ¿la API soporta el modelo obligatorio exacto exigido por la ficha, o solo una variante distinta? (bloqueante si no coincide);
- tiempo desde fin de habla hasta primer byte de audio de respuesta;
- ¿la API soporta interrupción/barge-in nativo? Si sí, latencia de cancelación medida igual que en Opción A;
- ¿la API permite salida estructurada (JSON) en paralelo a la voz, necesaria para triage/citas, o solo texto/audio libre?

**Cómo:** mismo instrumento de timestamps y `correlation_id`; P50/P95 de las 5 corridas.

## 4. Umbral de decisión

- Si una opción **no cumple compatibilidad con el modelo obligatorio** (score 1 en ese criterio), queda descalificada sin importar el resto — este criterio actúa como gate binario antes de sumar el ponderado total.
- Entre las opciones que sí califican, gana el **mayor total ponderado**.
- Si la diferencia entre los totales ponderados de A y B es **menor a 0.3 puntos** (sobre una escala 1–5), se considera empate técnico y se aplica la regla de desempate.

## 5. Regla de desempate

**Ante empate técnico (diferencia < 0.3 puntos en el total ponderado), gana la opción con menor riesgo de fallo en demo**, independientemente del resto de criterios — es decir, se usa como criterio de desempate el score individual del criterio "Riesgo de fallo en demo" (mayor score = menor riesgo = gana). Justificación: la demo en vivo/grabada es una compuerta eliminatoria (rúbrica "Video y demo", 15 puntos, y NFR sobre recuperación de voz), y un fallo no recuperable durante la grabación es peor que una diferencia marginal de latencia o complejidad.

## 6. Salida esperada

El resultado (opción elegida, scores, justificación del umbral/desempate si aplica) se transcribe a **ADR-007** en `architecture.md` §17, reemplazando su estado actual "pendiente del 7 de agosto" por "aceptada" con fecha y ticket CH-007.
