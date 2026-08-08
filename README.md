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

## Arquitectura (resumen)

Monolito modular: un backend **FastAPI + SQLite (WAL)** y un frontend
**Next.js/React/TypeScript**. La orquestación es una **máquina de estados
tipada** que coordina agentes de responsabilidad única (`Interview`, `Triage`,
`Response`) — los agentes nunca se llaman entre sí. RAG híbrido (**FTS5 + coseno
+ RRF**) con evidence gate. Todo proveedor externo (LLM, STT, TTS, embeddings,
datos) entra por **puertos/adaptadores**; hoy corren adapters `fake`
deterministas para pruebas, **Groq/Llama 3.1 70B** como opción competitiva primaria
y **Ollama/Phi-3.5 Mini** como resguardo local, sin tocar el dominio (ver
`docs/adr/ADR-001`).

Detalle en [`docs/architecture.md`](docs/architecture.md).

## Requisitos

Ruta recomendada para el jurado:

- **Docker + Docker Compose**.
- conexión a internet en la primera ejecución para descargar el kit público (~127 MB).

Ruta local alternativa, útil para desarrollo:

- **Python 3.11 o 3.12 + [uv](https://docs.astral.sh/uv/)**;
- **Node 22 + pnpm**.

No se necesitan credenciales para correr el prototipo: usa el proveedor LLM
`fake` determinista. No hay secretos en el repositorio.

> **Puertos:** el proyecto usa puertos altos e inusuales para no chocar con
> otros servicios locales — backend **49317**, frontend **49318**.

### Probar con el modelo real (Groq)

Por defecto todo corre con `fake` (determinista, sin red). Para hablar de
verdad con Llama 3.1 70B vía Groq:

1. Crea una API key gratis en <https://console.groq.com/keys>.
2. `cp api/.env.example api/.env` y edita dos líneas:
   ```bash
   LLM_PROVIDER=groq
   LLM_API_KEY=gsk_tu_api_key_real
   ```
   `LLM_BASE_URL`/`LLM_MODEL` se completan solos con los defaults de Groq
   (`app/core/config.py`) — no hace falta tocarlos.
3. (Opcional) resguardo local con [Ollama](https://ollama.com/): instala,
   `ollama pull phi3.5`, y agrega `LLM_FALLBACK_PROVIDER=ollama` al `.env` —
   si Groq falla/no responde, el turno sigue con el modelo local en vez de
   quedarse sin respuesta.
4. Reinicia el backend (`./levantar_app.sh --reinstall` o `uv run uvicorn
   app.main:app --port 49317` si corres manual).

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
3. Reinicia el backend. **Si ya habías cargado documentos con `fake`**, los
   vectores viejos quedan en otra dimensión — borra la base
   (`./levantar_app.sh --clean`) y vuelve a cargar el conocimiento.

Nunca commitees `api/.env` (ya está en `.gitignore`); la key real solo vive
ahí, en tu máquina.

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

## Arranque recomendado: un solo comando

```bash
git clone <repo-url> care-companion && cd care-companion
./levantar_app.sh
```

El launcher detecta el estado automáticamente:

- primera ejecución: construye las imágenes, instala dependencias, descarga el kit oficial
  e indexa el corpus dentro del volumen Docker (puede tardar varios minutos);
- ejecuciones posteriores: inicia los contenedores existentes sin reinstalar;
- si la aplicación ya está funcionando: únicamente abre la página;
- siempre espera el health-check antes de abrir el navegador.

Comandos disponibles:

```bash
./levantar_app.sh --stop       # detener sin borrar datos
./levantar_app.sh --logs       # ver logs
./levantar_app.sh --rebuild    # aplicar cambios de código/dependencias
./levantar_app.sh --no-open    # levantar sin abrir el navegador
./levantar_app.sh --local      # desarrollo sin Docker, con hot reload
```

- Frontend: <http://localhost:49318> (redirige a `/call`)
- API + OpenAPI: <http://localhost:49317/docs>
- Health: <http://localhost:49317/health>

### Equivalente manual con Docker Compose

```bash
docker compose up -d --build
```

Mismos puertos host (49318 frontend, 49317 API). El comando anterior usa el adapter
determinista `fake` para comprobar instalación y flujo sin secretos. Para ejecutar con el
modelo permitido elegido para el concurso:

```bash
LLM_PROVIDER=groq LLM_API_KEY=gsk_tu_api_key_real ./levantar_app.sh --rebuild
```

No se debe publicar una API key en el repositorio.

## Arranque local manual (sin script ni Docker)

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
