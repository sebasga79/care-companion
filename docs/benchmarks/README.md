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
