# Care Companion

Agente de voz para seguimiento postoperatorio pediátrico en español, con
conocimiento clínico vivo (RAG), decisión no degradable y supervisión humana.
Entrada al **Source Meridian Tech Sphere Challenge 2026**.

> **Prototipo clínico.** No diagnostica ni prescribe. No reemplaza el juicio
> profesional. Usa solo datos sintéticos.

---

## Qué hace

Una **llamada clínica** en la que un cuidador responde por el paciente. El
sistema entrevista, recupera evidencia citable, decide un nivel de riesgo que
las reglas deterministas **nunca** dejan rebajar por el modelo, responde en
español y, cuando corresponde, escala a una persona. Todo queda auditado.

Tres vistas: **`/call`** (llamada en vivo), **`/knowledge`** (conocimiento vivo
con aprendizaje/olvido demostrable) y **`/audit`** (traza de decisiones,
fuentes y métricas).

---

## Arranque en un solo comando

```bash
git clone https://github.com/sebasga79/care-companion.git && cd care-companion
./levantar_app.sh
```

Requiere **Docker Desktop** instalado y corriendo. El comando construye las
imágenes, descarga el dataset y corpus oficial del reto (~127 MB, solo la
primera vez), los indexa, levanta backend y frontend, y abre `/call` en el
navegador — nada manual de por medio. Primera vez toma unos minutos
(descarga + indexado); ejecuciones siguientes son casi instantáneas.

**Antes de correrlo por primera vez**, para que el agente hable con el
modelo real del concurso — Groq — en vez de quedarse en un modo de prueba
sin red:

1. Crea una API key gratis en [console.groq.com/keys](https://console.groq.com/keys) — sin tarjeta, menos de un minuto.
2. `cp api/.env.example api/.env` y edita dos líneas:
   ```bash
   LLM_PROVIDER=groq
   LLM_API_KEY=gsk_tu_api_key_real
   ```

Si ya corriste `./levantar_app.sh` una vez sin la key, agrégala y vuelve a
correr con `./levantar_app.sh --rebuild` (el simple no reconstruye
contenedores ya levantados).

- Frontend: <http://localhost:49318> (redirige a `/call`)
- API + OpenAPI: <http://localhost:49317/docs>
- Health: <http://localhost:49317/health>

Comandos disponibles:

```bash
./levantar_app.sh --stop       # detener sin borrar datos
./levantar_app.sh --logs       # ver logs
./levantar_app.sh --rebuild    # aplicar cambios de código/dependencias/api/.env
./levantar_app.sh --no-open    # levantar sin abrir el navegador
./levantar_app.sh --local      # desarrollo sin Docker, con hot reload
```

---

## Arquitectura (resumen)

Monolito modular: un backend **FastAPI + SQLite (WAL)** y un frontend
**Next.js/React/TypeScript**. La orquestación es una **máquina de estados
tipada** que coordina agentes de responsabilidad única (`Interview`, `Triage`,
`Response`) — los agentes nunca se llaman entre sí. RAG híbrido (**FTS5 + coseno + RRF**) con evidence gate. Todo proveedor externo (LLM, STT, TTS, embeddings,
datos) entra por **puertos/adaptadores**: **Groq/Llama 3.3 70B Versatile**
como modelo primario del concurso, **Ollama/Llama 3.2 3B** como resguardo
local si Groq falla, y un adapter `fake` determinista reservado para tests
automatizados — sin tocar el dominio (ver `docs/adr/ADR-001`).

Detalle en [`docs/architecture.md`](docs/architecture.md) y el diagrama en
[`docs/architecture-diagram.md`](docs/architecture-diagram.md).

---

Todo lo que sigue es información adicional — detalle para leer con más
tiempo, no hace falta para levantar el sistema.

## Requisitos y detalles del arranque

- **Docker + Docker Compose** (ruta recomendada, ver arriba).
- Conexión a internet en la primera ejecución para descargar el kit público
  (~127 MB) y, si configuras Groq, para las llamadas al modelo.

Ruta local alternativa, útil para desarrollo (sin Docker):

- **Python 3.11 o 3.12 + [uv](https://docs.astral.sh/uv/)**;
- **Node 22 + pnpm**.

> **Puertos:** el proyecto usa puertos altos e inusuales para no chocar con
> otros servicios locales — backend **49317**, frontend **49318**.

Nunca commitees `api/.env` (ya está en `.gitignore`); la key real solo vive
ahí, en tu máquina. No hay secretos en el repositorio.

### Resguardo local opcional (Ollama)

Si quieres que la llamada siga funcionando aunque Groq falle o no responda
durante la sesión de evaluación, en vez de quedarse sin respuesta:

1. Instala [Ollama](https://ollama.com/) y corre `ollama pull llama3.2:3b`.
2. Agrega `LLM_FALLBACK_PROVIDER=ollama` a `api/.env`.
3. `./levantar_app.sh --rebuild`.

### Embeddings reales para el RAG (Ollama + BGE-M3)

Por defecto el RAG usa `FakeEmbeddings` (hashing de n-gramas — sin
dependencias, pero sin semántica real: no entiende sinónimos ni
regionalismos). Para embeddings semánticos de verdad:

1. Instala [Ollama](https://ollama.com/) (si no lo hiciste ya para el
   resguardo del LLM) y corre `ollama pull bge-m3`.
2. En `api/.env`, agrega:
   ```bash
   EMBEDDINGS_PROVIDER=ollama
   ```
   `EMBEDDINGS_BASE_URL`/`EMBEDDINGS_MODEL` se completan solos
   (`http://localhost:11434/v1` / `bge-m3`).
3. `./levantar_app.sh --rebuild`. **Si ya habías cargado documentos con
   embeddings `fake`**, los vectores viejos quedan en otra dimensión — borra
   la base (`./levantar_app.sh --clean`) y vuelve a cargar el conocimiento.

### Dataset y corpus clínico real del reto

La ruta recomendada con Docker no requiere pasos manuales. En el primer
`./levantar_app.sh`, el contenedor API descarga los 4 `.xlsx` y 107 PDF del kit
oficial (~127 MB), valida que estén completos y carga el corpus al RAG **antes**
de exponer el backend. Dataset, índice y base quedan en el volumen persistente
`care_companion_data`; detener o volver a levantar la aplicación no los descarga
ni los procesa otra vez.

En desarrollo local sin Docker, los comandos equivalentes son:

```bash
cd api
export RAG_ALLOW_EMPTY_PDF_PASSWORD=true # solo para el corpus oficial auditado
uv run python scripts/fetch_dataset.py   # 4 .xlsx + 107 PDFs a ./data/dataset
uv run python scripts/ocr_scanned_pdf.py \
  --input "data/dataset/textos/Appendicitis/REVISIÓN DE LA LITERATURA SOBRE LAAPENDICITIS AGUDA PEDIATRICA NO ESPECIFICADA EN EL PERI000 2000-2021.pdf" \
  --output data/dataset/ocr/appendicitis-literature-review-ocr.txt
uv run python scripts/load_corpus.py     # los carga al RAG (misma consola /knowledge)
```

La ruta local del OCR requiere `pdftoppm` y `tesseract` instalados en el
sistema; la imagen Docker ya los incluye junto con el paquete de idioma
español. La apertura de los tres PDF protegidos es una opción explícita para
este corpus oficial, con contraseña de usuario vacía conocida: no se adivinan
contraseñas ni se eliminan restricciones del archivo original.

Con esto: `/call` muestra **40 pacientes únicos** como tarjetas con nombre,
cirugía y fecha. Cada entidad consolida sus cuatro seguimientos históricos
(días 1, 3, 7 y 14), manteniendo los 160 episodios originales disponibles
internamente para trazabilidad (`DatasetCaseAdapter`; el fallback a fixtures
solo se conserva para desarrollo local sin dataset). El RAG queda poblado
con los 106 PDF reales con texto más un documento de texto generado por OCR
para el escaneo (107 documentos indexados en total). Los tres PDF protegidos
se abren únicamente con contraseña de usuario vacía; el escaneo se rasteriza
con Poppler y se reconoce con Tesseract. El PDF original se conserva intacto
y el `.txt` OCR queda en el volumen Docker. Cada documento queda
etiquetado por procedimiento (`applicability.procedure`), así que el
retrieval de una llamada solo usa evidencia del procedimiento del caso en
curso, no de los otros cuatro.

`fetch_dataset.py --no-textos` descarga solo los `.xlsx` (rápido) si no
necesitas el corpus PDF todavía.

### Equivalente manual con Docker Compose

```bash
docker compose up -d --build
```

Mismos puertos host (49318 frontend, 49317 API). Lee `api/.env` igual que
`./levantar_app.sh` — configúralo primero (ver arriba) para correr con Groq
en vez del adapter `fake` reservado para tests.

No se debe publicar una API key en el repositorio.

### Arranque local manual (sin script ni Docker)

```bash
# Backend
cd api && uv sync
uv run uvicorn app.main:app --port 49317

# Frontend (otra terminal)
cd web && pnpm install
NEXT_PUBLIC_API_URL=http://localhost:49317 pnpm dev --port 49318
```

## Probar que funciona

**Demo de la llamada (`/call`):**
1. Elige una de las 40 tarjetas de paciente y pulsa **Iniciar llamada**. El agente
   recibe su perfil, cirugía y evolución histórica de los días 1/3/7/14.
2. Habla por el micrófono. El campo de texto aparece únicamente como fallback si el
   navegador no ofrece reconocimiento de voz.
3. Observa en vivo: estado de la máquina, respuesta del agente, **nivel de
   decisión** y evidencia citada.

Cada llamada terminada materializa además un `followup_record` semiestructurado
en SQLite con dolor y temperatura normalizados, movilidad, herida, ingesta, sueño, decisión y
bandera de alerta. No se requiere Redis: los perfiles del kit se transforman
en objetos Pydantic en memoria y SQLite conserva el historial operativo y
auditable.

**Base clínica (`/knowledge`):** el corpus oficial ya indexado está identificado y
protegido contra borrado. Para demostrar la compuerta learn/retrieve/forget, sube
un `.txt`/`.md`/`.pdf` de prueba, verifica automáticamente que aparece, bórralo y
confirma que desaparece. El `knowledge_version` cambia en cada operación.

**Auditoría (`/audit`):** cada sesión identifica paciente y procedimiento y muestra
el seguimiento clínico consolidado, nivel de decisión, fuentes, escalamiento y
métricas honestas (medidas o `pendiente`).

## Métricas (rúbrica §5)

Obligatorias por rúbrica: latencia P50/P95, consumo de tokens y costo estimado
por llamada. Metodología completa, corridas anteriores y hallazgos en
[`docs/benchmarks/README.md`](docs/benchmarks/README.md); JSON crudo en
[`docs/benchmarks/capa1-groq-70b.json`](docs/benchmarks/capa1-groq-70b.json).

**Corrida `capa1-groq-70b.json` (9 ago, 3 casos reales del dataset — 1 rojo /
1 amarillo / 1 verde, 16 turnos, contra Groq real `llama-3.3-70b-versatile`,
el modelo desplegado por defecto):**

| Métrica | Valor |
|---|---|
| Latencia P50 / P95 (servidor, ver nota) | **3.782 ms / 5.139 ms** (14 turnos limpios) |
| Tokens de entrada / salida por turno | 3.590,7 / 407,3 |
| Tokens por llamada (promedio) | 18.657,3 |
| Invocaciones al modelo por turno | 2,29 |
| Consultas al RAG por llamada | 3,33 |
| Costo estimado por llamada | **US$ 0,0114** |

**Cómo se calculó el costo:** Groq on-demand para `llama-3.3-70b-versatile`
(consultado en [groq.com/pricing](https://groq.com/pricing), ago 2026):
US$0,59 / millón de tokens de entrada, US$0,79 / millón de salida. En
desarrollo se usa el nivel gratuito (US$0 real), así que el costo se
extrapola desde los tokens realmente consumidos por llamada, tal como pide
la rúbrica.

**Nota metodológica — dos números, honestos ambos.** La corrida completa
(16 turnos) incluyó los últimos 2 turnos de la conversación `verde`, donde
la cuota **diaria** de Groq (TPD, 100.000 tokens/día para este modelo) se
agotó a mitad de la medición: 3 llamadas cayeron al resguardo local
(Ollama) tras reintentos 429. Esos 2 turnos miden tiempo de reintento y
degradación al resguardo, no el modelo bajo prueba — igual que el máximo de
24,5s de la corrida anterior (ver `docs/benchmarks/README.md`), se separan
en vez de mezclarlos:

| | Turnos | P50 | P95 | Máx |
|---|---|---|---|---|
| **Limpia** (Groq puro) | 14 | 3.782 ms | 5.139 ms | 6.540 ms |
| Cruda (incluye agotamiento de cuota) | 16 | 4.044,6 ms | 13.984,6 ms | 14.726,4 ms |

Con 14-16 muestras el P95 es indicativo, no una medición robusta — una
corrida más larga da un percentil más estable, pero agotaría la cuota
diaria compartida con el resto del desarrollo y no aporta un número más
honesto, sólo más impreciso mientras el resguardo interfiere. Tokens,
llamadas e invocaciones RAG de la tabla principal usan sólo los 14 turnos
limpios (Groq real), para no atribuirle a Groq consumo que en realidad
sirvió el modelo local gratuito.

**Latencia voz-a-voz** (definición exacta de la rúbrica: desde que el
paciente termina de hablar hasta que empieza a sonar el audio del agente)
está **instrumentada en vivo** en `/call` y `/knowledge` — aparece junto al
micrófono durante la llamada apenas hay una muestra. STT y TTS corren
enteramente en el navegador (Web Speech API), así que la única forma de
medirla es una llamada real con micrófono — no un script.

**Primeras 3 muestras reales, navegador real (9 ago), llamada de voz
completa contra Groq:**

| Métrica | Valor |
|---|---|
| Latencia voz-a-voz P50 / P95 | **6.154 ms / 6.507 ms** (n=3) |

Con sólo 3 muestras el número es preliminar, no una distribución estable —
se reporta igual, sin esperar a tener más, porque un número real con
muestra chica es más honesto que "pendiente" indefinidamente (rúbrica:
"reportar números que no se sostienen es peor que no reportarlos", pero
lo contrario también aplica — un real pequeño no es un número que no se
sostenga, es evidencia genuina con su límite declarado). Por encima del
objetivo interno de ≤2,5s P95 (spec.md NFR-002): el turno más lento de
las 3 muestras hizo la cadena completa (entrevista → RAG con embeddings
reales → triage → respuesta, 4 llamadas al modelo/embeddings en un solo
turno) — el proxy de servidor de la tabla principal (~3,8s P50 medido en
`capa1-groq-70b.json`, sección anterior) no incluye esa latencia de RAG
semántico real ni el tránsito de red del WebSocket, así que subestima la
experiencia real de punta a punta. Queda como límite conocido en
"Límites y trabajo pendiente" del informe final, no oculto.

La cifra del proxy de servidor (tabla principal de arriba) sigue siendo
útil aparte: mide sólo el tiempo de cómputo del backend, sin ruido de
red/TTS, así que aísla mejor si una regresión futura es del modelo o de
la capa de transporte.

Cada muestra que el navegador mide queda además **persistida como evento
auditable** (`POST /api/v1/sessions/{id}/voice-latency` →
`client.voice_latency_reported` en `events`), no sólo en memoria de la
pestaña — el jurado puede corroborarlo por sus propios medios sin depender
de que alguien le pase un número a mano: `GET /api/v1/metrics` expone
`latency_voice` (P50/P95 reales, separados del proxy de servidor de arriba)
y `/audit` lo muestra como quinta tarjeta junto a P50/P95/tokens/costo. El
costo por llamada de esta sección se calcula igual: `LLM_COST_PER_MILLION_*`
está configurado con el precio real de Groq, así que `/api/v1/metrics`
también lo computa solo, en vivo, sobre datos reales — no un cálculo hecho
una vez y pegado aquí. El costo cuenta sólo los tokens del proveedor
primario (`by_provider` en `AuditRepository.usage_summary`): si una llamada
cae al resguardo local por cuota agotada, esos tokens no se cobran al
precio de Groq (auditoría §9.35).

### Cómo verificar estas cifras en los logs

La rúbrica lo pide de forma explícita en varios puntos: las métricas deben
ser "verificables en los logs" y "se contrastan con lo que ocurre en la
sesión de evaluación y con tus logs" — reportar un número que no se
sostiene ahí es peor que no reportarlo. Hay **dos capas reales**, no una
sola, y conviene no confundirlas:

**1. Logs de proceso** (`./levantar_app.sh --logs`, o `docker compose
logs -f`): la salida estándar de los contenedores, persistida por Docker
desde que arrancan (no sólo lo reciente). Cada línea de la API es JSON
estructurado con `correlation_id`, y la primera línea de arranque delata
el proveedor real en uso —
`care_companion_app_ready ... llm_provider=groq` (o `fake` si no
configuraste una key) — así que no hay forma de que el sistema diga una
cosa y corra otra sin que quede escrito ahí mismo. Lo que **no** está en
estos logs: el desglose de tokens/proveedor por llamada individual — eso
vive en la capa 2.

**2. Traza estructurada** (`/audit`, y `GET /api/v1/metrics`/
`GET /api/v1/audit/sessions/{id}/trace`): los datos granulares detrás de
cada número de la tabla de arriba — tokens de entrada/salida y proveedor
real por invocación, consultas RAG, latencia por turno — se escriben en la
tabla `events` de SQLite, no en la salida estándar. `/audit` los muestra
por sesión, con **`correlation_id` visible en cada evento** de la línea de
tiempo: el mismo valor que aparece en los logs de proceso, para poder
ubicar un evento puntual de la traza dentro del log de terminal y
confirmar que son la misma ejecución, no dos historias distintas.

## Tests y calidad

```bash
make verify          # backend: ruff + pytest (suite completa)
cd web && pnpm build # frontend: type-check + build
```

`make verify` es la compuerta local: lint + toda la suite de backend. El
frontend valida con `tsc --noEmit` (incluido en `pnpm build`) y `pnpm lint`.

## Estructura

```
api/    Backend FastAPI (dominio, puertos, adapters, orquestador, RAG, WS)
web/    Frontend Next.js (rutas /call, /knowledge, /audit)
docs/   SDD: spec, architecture, plan, design, traceability, ADRs, evidencia
```

## Seguridad clínica (no negociable)

- Sin evidencia activa aplicable **no hay respuesta clínica** — se aclara,
  abstiene o escala.
- Las reglas deterministas de red flags **no son degradables** por el modelo.
- Silencio o dato ambiguo **nunca** equivale a negación.
- Ante fallo de modelo/RAG/persistencia con riesgo, el estado seguro es
  abstenerse/escalar.

## Licencia

MIT; texto completo disponible en [`LICENSE`](LICENSE).

---

> Estado: implementación funcional integrada con el kit oficial del 7 de agosto.
> Ver [`docs/plan.md`](docs/plan.md) y
> [`docs/auditoria-kit-oficial-2026-08-07.md`](docs/auditoria-kit-oficial-2026-08-07.md).
