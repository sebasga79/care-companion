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
deterministas y el modelo obligatorio del 7 de agosto se conecta cambiando un
adapter, sin tocar el dominio (ver `docs/adr/ADR-001`).

Detalle en [`docs/architecture.md`](docs/architecture.md).

## Requisitos

- **Docker + Docker Compose** (ruta recomendada), o
- **Python 3.11 + [uv](https://docs.astral.sh/uv/)** y **Node 22 + pnpm** (ruta local).

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

Nunca commitees `api/.env` (ya está en `.gitignore`); la key real solo vive
ahí, en tu máquina.

## Arranque rápido (un solo script)

```bash
git clone <repo-url> care-companion && cd care-companion
./levantar_app.sh
```

Instala dependencias la primera vez, levanta backend + frontend, espera a que
estén sanos y sigue los logs. **Ctrl+C** detiene todo de forma limpia.
Opciones: `--reinstall` (reinstala deps), `--clean` (borra la BD local).

- Frontend: <http://localhost:49318> (redirige a `/call`)
- API + OpenAPI: <http://localhost:49317/docs>
- Health: <http://localhost:49317/health>

## Arranque con Docker (≤15 min)

```bash
docker compose up --build
```

Mismos puertos host (49318 frontend, 49317 API).

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
1. Elige un caso ficticio y pulsa **Iniciar llamada**.
2. Escribe un turno del paciente (la captura de voz es un ticket posterior; hoy
   la conversación se maneja por texto sobre el mismo WebSocket).
3. Observa en vivo: estado de la máquina, respuesta del agente, **nivel de
   decisión** y evidencia citada.

**Aprendizaje/olvido en vivo (`/knowledge`):** sube un `.txt`/`.md`, verifica con
la consulta canaria que aparece, bórralo y verifica que desaparece. El
`knowledge_version` cambia en cada operación.

**Auditoría (`/audit`):** cada sesión queda con su nivel de decisión, conteo de
fuentes, escalamiento y métricas honestas (medidas o `pendiente`).

## Tests y calidad

```bash
make verify          # backend: ruff + pytest (235 tests)
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

MIT (pendiente de archivo `LICENSE` en el ticket DOC-007).

---

> Estado: construcción anticipada pre-concurso (ADR-001). El modelo obligatorio,
> el dataset (Delta Sharing) y las métricas oficiales se integran el 7 de agosto
> a través de los puertos existentes. Ver [`docs/plan.md`](docs/plan.md).
