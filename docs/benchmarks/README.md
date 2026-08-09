# Benchmarks — evaluación automatizada contra el dataset real

Este directorio contiene las corridas del arnés de evaluación
([`api/scripts/benchmark.py`](../../api/scripts/benchmark.py)) y sus
hallazgos. Sustituye la prueba manual caso por caso: el dataset oficial trae
**3.991 turnos reales** de 160 casos con criticidad de referencia, así que la
evaluación puede ser reproducible y no anecdótica.

## Qué mide y por qué

| Métrica | Por qué está |
|---|---|
| **Falsos negativos** (caso `rojo` que no escaló) | La rúbrica la llama *la falla catastrófica*: "un falso negativo en un escenario donde escalar era claramente lo correcto limita severamente la calificación… y la reincidencia puede anularla". Es el número que manda. |
| **Falsos positivos** (caso `verde` que escaló) | La rúbrica evalúa el comportamiento "en situaciones donde claramente no lo es". Menos grave que el anterior, pero un sistema que alerta por todo es inútil. |
| **Latencia P50/P95** por turno | Obligatoria en el README (rúbrica §5). |
| **Tokens entrada/salida**, invocaciones LLM/turno, consultas RAG/llamada | Obligatorias en el README (rúbrica §5). |

`amarillo` se reporta aparte y **no cuenta como acierto ni error**: el propio
kit lo describe como zona gris, y forzar una respuesta correcta ahí sería
inventar un criterio que el dataset no fija.

## Cómo se corre

```bash
cd api
uv run python scripts/benchmark.py --limit 12 --capa capa1_limpia --pause 8 \
    --out ../docs/benchmarks/capa1-groq.json
uv run python scripts/benchmark.py --limit 12 --capa capa2_ruidosa --pause 8 \
    --out ../docs/benchmarks/capa2-groq.json
```

Usa el proveedor configurado en `api/.env`. Con `LLM_PROVIDER=fake` es
instantáneo y determinista (sirve para verificar el arnés, **no** para medir
el sistema).

### Cómo se resolvió el límite del nivel gratuito

El primer intento de medir contra Groq fue inválido y conviene dejar
registrado por qué: el nivel gratuito son **6.000 tokens/minuto** y cada caso
consume ~5 turnos × 3 agentes. La corrida acumuló **8 rate limits y 4 caídas
al resguardo**, así que la latencia medida era la de Ollama local (unas 20×
más lenta) y el modelo evaluado ya no era el declarado para G3. Los números
no describían nada.

La causa era nuestra, no del proveedor: Groq responde 429 indicando
exactamente cuánto esperar (cabecera `retry-after` y texto *"Please try again
in 3.73s"*), y lo estábamos ignorando. Ahora `OpenAICompatLLM` puede esperar
ese tiempo y reintentar **con el mismo modelo**:

| Contexto | `LLM_RATE_LIMIT_MAX_RETRIES` | Por qué |
|---|---|---|
| Conversación en vivo | `0` (default) | Hacer esperar segundos a un paciente es peor que responder con el resguardo |
| Benchmark | `6`, hasta 70 s | No hay nadie al teléfono; lo que importa es medir el modelo declarado |

El benchmark activa esos valores por sí solo. Con eso, `--pause` ya no es
necesario para respetar la cuota (sigue disponible para espaciar a mano).

**Consecuencia metodológica:** una corrida de 12 casos tarda 15–25 minutos
porque incluye las esperas del proveedor. Es el precio de que los números
sean del sistema real y no del resguardo.

### Latencia: se mide aparte

`groq-latency.json` se obtiene con llamadas **aisladas y espaciadas**, no
dentro del benchmark de decisión. Medir latencia mientras se compite contra
la propia cuota daría tiempos de contención, no de servicio.

## Decisiones de diseño del arnés

- **Muestra estratificada, no secuencial.** Sólo 12 de los 160 casos son
  `rojo`, y son los que más importan. Una muestra por orden de aparición
  podría no incluir ninguno y dar un 0 % de falsos negativos vacío de
  significado. El arnés intercala `rojo`/`amarillo`/`verde`.
- **Se reproducen los turnos del *paciente*, no los del agente.** Las
  respuestas del agente en `dataset_final.xlsx` son de otro sistema; aquí el
  agente es el que está bajo prueba.
- **El uso se lee de los eventos persistidos**, no se estima: los mismos
  registros que alimentan `/api/v1/metrics` y que el jurado puede auditar.

## Límite conocido

El arnés mide **la decisión y el coste**, no la calidad conversacional ni la
groundedness de las citas. Un caso puede escalar correctamente y aun así
haber conversado mal. Esa parte sigue evaluándose a mano y con la sesión en
vivo del jurado.

---

## Resultados

Ver los archivos `*.json` de este directorio y la sección de hallazgos en
[`docs/final-report.md`](../final-report.md).

### `capa1-groq.json` — corrida completa, 2026-08-08

12 casos (4 rojo / 4 amarillo / 4 verde), 62 turnos, contra Groq real
(`llama-3.1-8b-instant`), conversación completa (hasta 8 turnos por caso).

| Métrica | Valor |
|---|---|
| Falsos negativos | 1 de 4 rojos evaluados (sensibilidad 75 %) |
| Falsos positivos | 0 de 6 verdes evaluados (especificidad 100 %) |
| Latencia p50 / p95 | 1.093 ms / 3.267 ms (≈1,1 s / ≈3,3 s) |
| Tokens por turno | 2.493 entrada · 290 salida |
| Invocaciones LLM / consultas RAG por turno | 1,58 · 1,5 |

**El máximo de latencia (24,5 s) no es tiempo de servicio**: coincide con
una espera de cuota de 18 s que el adapter respetó dentro del mismo turno
(`llm_rate_limited_waiting wait_s=18.00`). El benchmark mide el turno de
punta a punta a propósito — es el tiempo real que tarda en responder bajo
el nivel gratuito — pero al reportar p50/p95 al jurado conviene aclarar que
la cola de la distribución refleja cuota compartida, no el modelo.

**Cómo se llegó a estos números** (documentado porque cada paso encontró un
bug real, no solo una configuración):

1. Cuatro intentos anteriores de correr esto contra Groq se colgaron. La
   causa no era la cuota: las conversaciones se ejecutaban por `TestClient`
   + WebSocket, y una espera larga dentro del handler bloquea el ciclo de
   eventos que ese WebSocket necesita para entregar mensajes. Se corrigió
   llamando al orquestador directo (`run_case` en `scripts/benchmark.py`) y
   respetando la cuota con `TokenBudget`, una ventana deslizante que
   *reserva* presupuesto antes de cada turno en vez de reaccionar al 429.
2. Con `--max-turns 3` en un intento previo, un caso `rojo` dio falso
   negativo porque el síntoma decisivo (secreción de la herida) estaba en
   el turno 4 — nunca se lo dimos al agente. Subido a 8 turnos (conversación
   completa).
3. La corrida encontró un falso positivo real: un caso `verde` (dolor 2/10)
   escaló por `PAIN_WORSENING` a partir de "estoy preocupado de que **pueda**
   empeorar" — temor a futuro, no un reporte de empeoramiento. Corregido en
   `app/domain/safety_signals.py` (`_is_hypothetical_worry`), con test de
   regresión. El mismo fix resolvió además uno de los dos falsos negativos
   que había en la corrida anterior — el detector determinista ya no
   interfería con la síntesis de señales blandas que el LLM sí hacía bien.

**Falso negativo restante** (`caso_tray_pac_42_00017_7`, sin resolver): el
paciente minimiza verbalmente todo el reporte ("tranquila, nada del otro
mundo", "yo creo que es normal") sin dar un dato objetivo inequívoco —
temperatura vaga ("37 y algo"), herida "un poquito rojita" sin secreción.
Es un caso diseñado para poner a prueba si el sistema detecta un patrón de
minimización, no un síntoma aislado. Queda documentado como limitación
conocida: intentar una heurística de "tono minimizador" a dos días del
plazo tiene más riesgo de introducir un falso positivo nuevo que beneficio
de cerrar este único caso.

### `capa1-groq-70b.json` — corrida corta, 2026-08-09, modelo actual

Esta corrida existe por un motivo distinto a la de arriba: **el default de
`api/.env`/`config.py` cambió de `llama-3.1-8b-instant` a
`llama-3.3-70b-versatile` el 8 de agosto** (más capacidad por minuto, ver
`docs/auditoria-kit-oficial-2026-08-07.md` §9.20-9.21), así que los números
de la corrida de arriba ya no describen el modelo que el jurado va a
ejercitar. La rúbrica es explícita sobre esto: *"lo que reportes se
contrasta con lo que ocurre en la sesión de evaluación... reportar números
que no se sostienen es peor que no reportarlos"* — así que hacía falta
volver a medir, no reescribir la tabla vieja con el modelo nuevo de nombre.

3 casos (1 rojo / 1 amarillo / 1 verde), 16 turnos, **deliberadamente corta**
— no busca sensibilidad/especificidad estadísticamente sólida (para eso
sigue vigente la corrida de 12 casos de arriba), busca únicamente refrescar
latencia/tokens/costo contra el modelo real desplegado sin gastar los
15-25 minutos de una corrida completa.

| Métrica | Valor |
|---|---|
| Latencia P50 / P95 (14 turnos limpios, ver nota) | 3.782 ms / 5.139 ms |
| Latencia P50 / P95 (16 turnos, cruda) | 4.044,6 ms / 13.984,6 ms |
| Tokens por turno (limpio) | 3.590,7 entrada · 407,3 salida |
| Invocaciones LLM / consultas RAG por turno (limpio) | 2,29 · 3,33/llamada |
| Costo estimado por llamada (sólo tokens Groq) | US$0,0114 |

**Hallazgo nuevo: la cuota diaria (TPD) de Groq, no sólo la de minuto
(TPM), se agota con uso acumulado real.** A mitad del turno 5 del tercer
caso, Groq empezó a responder 429 con
`"Rate limit reached ... tokens per day (TPD): Limit 100000, Used 99659"`.
El adapter (`OpenAICompatLLM` + `FallbackLLM`) hizo exactamente lo que debía
—reintentar, agotar los reintentos, caer al resguardo local (Ollama)— y la
conversación terminó sin caerse. Pero eso significa que los turnos 5 y 6 de
ese caso no midieron a Groq: midieron reintentos 429 y la latencia del
modelo local. Verificado por proveedor consultando directamente la tabla
`events` (payload de cada `agent.*.completed` trae `provider`): de 36
invocaciones a agentes en toda la corrida, 32 fueron `groq` y 3 `ollama`
—las 3 últimas de la sesión `verde`, ni una antes—. La tabla de arriba
separa ambos números en vez de promediarlos.

**Consecuencia práctica para la sesión de evaluación del jurado:** el
presupuesto diario de este modelo en el nivel gratuito (100.000 tokens) es
compartido con todo el desarrollo/pruebas del día. Si el jurado agenda la
sesión el mismo día que hubo desarrollo activo, existe riesgo real de
toparse con el mismo 429→resguardo — el sistema no se cae (ese es
justamente el propósito del resguardo), pero la voz suena con el modelo
local, más lento. Mitigación simple y ya disponible: generar una API key de
Groq nueva (cuota propia) para el día de la evaluación, o evaluar temprano
en el día antes de que el desarrollo consuma cuota.

**El único falso positivo de esta corrida** (`caso_tray_pac_42_00000_1`,
`verde` → `DATA_INTEGRITY_FAILURE`) ocurrió en el turno 6, exactamente el
turno servido por el resguardo local tras el agotamiento de cuota — no se
cuenta como hallazgo de precisión del modelo primario sin volver a
verificarlo con cuota Groq disponible. Con sólo 1 caso `verde` en la
muestra tampoco alcanza para una lectura de especificidad; para eso sigue
siendo autoridad la corrida de 12 casos de arriba.
