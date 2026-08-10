# Benchmarks — artefactos históricos de desarrollo

> No constituyen una evaluación representativa del modelo final ni son la
> fuente de las métricas declaradas para la entrega.

`api/scripts/benchmark.py` se construyó para reproducir conversaciones del
dataset y detectar regresiones durante el desarrollo. Las corridas JSON de
esta carpeta se conservan por transparencia, pero mezclan configuraciones,
modelos y condiciones de cuota distintas:

- `capa1-groq.json`: modelo Groq anterior al modelo final;
- `capa1-groq-70b.json`: solo 3 casos/16 turnos y caída parcial al resguardo
  local al agotarse la cuota gratuita;
- `groq-latency.json`: llamadas aisladas, no latencia voz-a-voz.

Por ese motivo no se derivan porcentajes generales de sensibilidad,
especificidad ni desempeño clínico. La muestra final no es equilibrada ni
suficiente para sostenerlos.

## Fuente canónica de la entrega

Las métricas exigidas por la rúbrica salen de la aplicación:

- `GET /api/v1/metrics`;
- vista `/audit`;
- eventos SQLite por sesión y `correlation_id`;
- medición del navegador `client.voice_latency_reported`.

Tokens, consultas RAG y costo se limitan a sesiones cerradas con proveedor y
modelo reales; la respuesta incluye denominador, ventana y desglose por
proveedor/modelo. La latencia voz-a-voz se reporta con su tamaño de muestra.

## Uso opcional del arnés

El script sigue siendo útil para desarrollo exploratorio, no como gate:

```bash
cd api
uv run python scripts/benchmark.py --help
```

Antes de interpretar una corrida hay que registrar proveedor, modelo,
resguardo, embeddings, configuración, fecha, casos esperados/observados y
errores de cuota. Nunca se deben mezclar sus resultados con las métricas vivas
sin declarar el cambio de universo.
