# PRE-010 — Verificación de estación de trabajo

> Evidencia parcial (parte automatizable) · 23 de julio de 2026 · máquina: macOS, 18 GB RAM

## Herramientas verificadas ✅

| Herramienta | Versión | Estado |
|---|---|---|
| git | 2.47.0 | ✅ |
| Docker CLI | 29.1.2 (build 890dcca) | ✅ |
| Docker Compose | v2.40.3-desktop.1 | ✅ |
| Python | 3.11.9 | ✅ |
| Node.js | v25.0.0 | ✅ |
| pnpm | 10.11.0 | ✅ (npm emite warning de config `public-hoist-pattern`, no bloqueante) |
| uv | 0.9.18 | ✅ |
| ffmpeg | 8.0.1 | ✅ (útil para captura/procesado de video de demo) |

## Observaciones

- **Docker daemon:** el CLI responde pero `docker info` no devolvió versión de servidor en esta corrida — confirmar que Docker Desktop arranca y ejecutar `docker run hello-world` manualmente.
- **Disco:** `df` sobre el volumen sellado reporta ~15 GiB disponibles en `/`; verificar espacio real en `/System/Volumes/Data` (se recomienda ≥40 GB libres para images de Docker + grabaciones de video).

## Pendiente humano (no automatizable) ⬜

- [ ] Micrófono: prueba de captura y niveles (auriculares recomendados, ver PRE-023)
- [ ] Cámara: prueba de video para grabación final
- [ ] Software de grabación de pantalla+cámara probado (PRE-021)
- [ ] Navegador con permisos de micrófono verificados
- [ ] GitHub: auth (`gh auth status` / SSH) y acceso al repo de entrega
- [ ] Espacio físico de trabajo para los 4 días del reto
- [ ] Plan B documentado: segunda máquina o VM ante fallo de hardware
