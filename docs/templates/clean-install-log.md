# Plantilla — Log de instalación limpia

> v0.1 · 23 de julio de 2026 · Ticket: PRE-011

Plantilla para medir el tiempo de instalación limpia (T0 → sistema listo) y verificar el criterio de la rúbrica "Repositorio y proceso": **≤ 15 minutos**, sin pasos manuales ocultos. Se usa en PRE-011 (ensayo genérico), REL-001 (medición oficial durante el concurso) y FIN-002 (clean-room final).

Copiar este archivo a `docs/evidence/<TICKET-ID>/clean-install-log-<fecha>.md` y completarlo durante la corrida, no después de memoria.

---

## 1. Checklist previo (antes de iniciar el cronómetro)

- [ ] VM o contenedor limpio (sin caches de builds previos, sin `node_modules`, sin `.venv`, sin volúmenes Docker reutilizados).
- [ ] Sin variables de entorno ni credenciales preconfiguradas en el sistema fuera de lo que el README pide crear.
- [ ] Sin imágenes Docker precargadas que el README no mencione explícitamente como prerequisito autorizado.
- [ ] Cronómetro visible y sincronizado (o grabación con timestamp) listo para iniciar en el primer comando.
- [ ] Copia exacta del repositorio en el estado a evaluar (commit/tag conocido).
- [ ] Conexión de red en el estado esperado para la corrida (documentar si es limitada u offline).

Si alguno de estos puntos no se puede garantizar, la corrida no cuenta como "clean install" — se registra como ensayo informal.

## 2. Datos de la corrida

| Campo | Valor |
|---|---|
| Ticket | |
| Fecha | |
| Máquina / SO | |
| RAM / CPU | |
| Commit SHA evaluado | |
| Rama / tag | |
| Tipo de entorno | VM limpia / contenedor / equipo físico reseteado |
| Conexión de red | |
| Ejecutor | |

## 3. Tabla de pasos

| # | Timestamp | Paso | Comando | Duración | Resultado |
|---|---|---|---|---:|---|
| 1 | | | | | ✅ / ❌ |
| 2 | | | | | ✅ / ❌ |
| 3 | | | | | ✅ / ❌ |
| 4 | | | | | ✅ / ❌ |
| 5 | | | | | ✅ / ❌ |

Reglas de registro:

- Un renglón por comando o acción manual observable (no agrupar pasos distintos en uno solo).
- `Timestamp` es el reloj de pared (hh:mm:ss) al iniciar el paso, no un cálculo posterior.
- `Duración` es el tiempo real transcurrido en ese paso, medido con cronómetro o derivado de timestamps consecutivos.
- `Resultado` registra ✅ si el paso terminó sin intervención adicional, o ❌ con una nota breve del error si falló o requirió un paso no documentado en el README.
- Cualquier paso manual no descrito en el README (editar un archivo a mano, buscar una versión, reiniciar un servicio) cuenta como hallazgo, no se omite del log.

## 4. Totales

| Métrica | Valor |
|---|---|
| Hora de inicio (T0) | |
| Hora de "listo" (ready) | |
| Duración total | |
| Número de pasos manuales no documentados | |
| Número de fallas / reintentos | |

## 5. Criterio pasa/falla

- **Pasa:** duración total ≤ 15:00 minutos, cero pasos manuales no documentados en el README, cero fallas que requieran intervención fuera del script/documentación.
- **Falla:** duración total > 15:00 minutos, o cualquier paso manual oculto, o cualquier falla no resuelta por el propio README/script.

Resultado final de esta corrida: **PASA / FALLA** — completar con justificación breve si falla.

## 6. Notas y hallazgos

Espacio libre para anotar cuellos de botella, pasos candidatos a automatizar, o dependencias que se descargan lento y podrían cachearse (solo si las reglas del reto lo permiten).
