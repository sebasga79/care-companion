# Care Companion — Frontend

Interfaz del agente de voz postoperatorio Care Companion. Next.js 16 (App
Router) + React + TypeScript, sin librería de componentes de terceros. Ver
`../README.md` para el arranque recomendado (`./levantar_app.sh`, Docker) y
`../docs/architecture.md`/`../docs/design.md` para el diseño y el alcance.

## Desarrollo local

```bash
cd web
pnpm install
NEXT_PUBLIC_API_URL=http://localhost:49317 pnpm dev --port 49318
```

O desde la raíz del repo: `./levantar_app.sh --local` (backend + frontend,
hot reload, sin Docker).

## Tests y lint

```bash
pnpm exec tsc --noEmit   # type-check
pnpm lint                # eslint
pnpm build                # build de producción (incluye type-check)
```

## Estructura

```
src/
  app/            rutas del App Router: /call, /knowledge, /audit
  components/     CallModal, VoiceOrb, TranscriptPanel, EvidencePanel,
                  RiskPanel, MetricsBand, StatusBanner, ConfirmDialog...
  lib/            api.ts (cliente REST/WS tipado), useVoiceSession.ts
                  (STT/TTS del navegador con barge-in), knowledge.ts
```

`CallModal` concentra toda la lógica de una llamada (WebSocket, voz,
turnos) para que `/call` y `/knowledge` la reutilicen igual, en vez de
duplicarla — ver `docs/auditoria-kit-oficial-2026-08-07.md` §9.22.
