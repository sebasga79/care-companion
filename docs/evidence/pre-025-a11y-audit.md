# PRE-025 — Auditoría de accesibilidad del mockup (Family-first Pediatric)

> v0.1 · 23 de julio de 2026 · Ticket: PRE-025

**Insumos auditados:** `docs/dashboard.tsx`, `docs/globals (1).css`, `docs/design.md`, `docs/care-companion-family-first-handoff.md`.
**Naturaleza del hallazgo:** el mockup es material de referencia visual, no código de producción. El objetivo de esta auditoría es detectar deuda de accesibilidad **antes** de que `/call`, `/knowledge` y `/audit` se conviertan en código real durante el concurso.

---

## 1. Contraste (WCAG 2.1 AA)

Ratios calculados con la fórmula de luminancia relativa WCAG (sRGB → linealizado → `L = 0.2126R + 0.7152G + 0.0722B`; `ratio = (L1+0.05)/(L2+0.05)`), no estimados a ojo. Umbrales: texto normal ≥4.5:1, texto grande (≥24px regular o ≥18.66px negrita) ≥3:1, componentes UI/gráficos significativos ≥3:1.

### 1.1 Texto base (tinta sobre superficies claras)

| Par | Hex fg / bg | Ratio | Uso | Veredicto |
|---|---|---|---|---|
| `--ink` / blanco | `#13365f` / `#ffffff` | 12.21:1 | Cuerpo de texto, transcripción | PASA |
| `--ink-strong` / blanco | `#073b78` / `#ffffff` | 11.02:1 | `h1`, `h2`, marca | PASA |
| `--ink-muted` / blanco | `#61758a` / `#ffffff` | 4.75:1 | Texto secundario (`small`) | PASA (margen estrecho) |
| `--ink-muted` / `--canvas` | `#61758a` / `#f7fafc` | 4.53:1 | Footer | PASA (margen muy estrecho) |
| `--ink-muted` / `#edf3f7` | `#61758a` / `#edf3f7` | 4.25:1 | Numeral en `pipeline-list li` (estado por defecto) | **FALLA** |

### 1.2 Familia aqua-deep (texto de estado, muy reutilizada — incluida en la primera vista)

| Par | Hex fg / bg | Ratio | Uso real (no decorativo) | Veredicto |
|---|---|---|---|---|
| aqua-deep / blanco | `#0b8f96` / `#ffffff` | 3.90:1 | `.eyebrow` ("Conversación de seguimiento", "Acompañamiento", etc.), `.nav-item.active` ("Llamada") | **FALLA** |
| aqua-deep / aqua-soft | `#0b8f96` / `#e9fafa` | 3.63:1 | `.call-status` ("En llamada · 04:32"), `.assistant-message .speaker-label` ("Asistente · 04:18") | **FALLA** |
| aqua-deep / blanco | `#0b8f96` / `#ffffff` | 3.90:1 | `pipeline-list li.active > span` (numeral "3") | **FALLA** |

### 1.3 Familia dorada (chips y speaker-label paciente)

| Par | Hex fg / bg | Ratio | Uso | Veredicto |
|---|---|---|---|---|
| `#a77603` / gold-soft | `#a77603` / `#fff4cf` | 3.65:1 | `.patient-message .speaker-label` ("Valentina · 04:24") | **FALLA** |
| `#a77603` / gradiente claro | `#a77603` / `#fffaf0` | 3.86:1 | Idem, extremo más claro del degradado | **FALLA** |
| `#9c7000` / gold-soft | `#9c7000` / `#fff4cf` | 4.04:1 | `.review-chip` ("Revisión en curso") | **FALLA** |
| `#916903` / gold-soft | `#916903` / `#fff4cf` | 4.52:1 | `.document-status.is-new` ("Nueva") | PASA (margen mínimo) |
| `#8b6608` / gold-soft | `#8b6608` / `#fff4cf` | 4.77:1 | `.simulation-chip` | PASA |

### 1.4 Familia verde/lima (chips de estado saludable)

| Par | Hex fg / bg | Ratio | Uso | Veredicto |
|---|---|---|---|---|
| `#5d8b1b` / lime-soft | `#5d8b1b` / `#eff8df` | 3.70:1 | `.healthy-chip` ("Saludable", "4/4 completos"), `.document-status` ("Verificada"), `pipeline-list li.done > span` | **FALLA** |
| `#637454` / lime-soft | `#637454` / `#eff8df` | 4.61:1 | `.prepared-banner small` | PASA (margen estrecho) |
| `#416976` / aqua-soft | `#416976` / `#e9fafa` | 5.57:1 | `.audit-note p` | PASA |

### 1.5 Botones (texto blanco sobre relleno de color)

| Par | Hex fg / bg | Ratio | Uso | Veredicto |
|---|---|---|---|---|
| blanco / coral (extremo oscuro) | `#ffffff` / `#e85f57` | 3.38:1 | `.alert-copy button` ("Alertar al equipo") | **FALLA** |
| blanco / coral (extremo claro del degradado) | `#ffffff` / `#f06b63` | 3.01:1 | Idem, peor caso del `linear-gradient` | **FALLA** |
| blanco / blue (extremo oscuro) | `#ffffff` / `#004b8d` | 8.78:1 | `.primary-action` | PASA |
| blanco / blue (extremo claro) | `#ffffff` / `#0b68a4` | 5.95:1 | Idem, peor caso | PASA |
| blanco / `#6b9a27` | `#ffffff` / `#6b9a27` | 3.35:1 | `.success-action` | Falla el umbral, pero el botón está `disabled` → exento por la excepción de "componentes inactivos" de la SC 1.4.3/1.4.11 |
| blanco / `#c83e37` (coral-deep, texto no botón) | `#ffffff` / `#c83e37` | — | (no aplica; coral-deep se usa como texto, no fondo) | — |

**El caso más grave es 1.5, fila 1–2:** es el único botón de acción clínica real de la vista `/call` (`.alert-copy button`, "Alertar al equipo" / handoff simulado) y su texto queda entre 3.01:1 y 3.38:1 — muy por debajo del 4.5:1 exigido para texto de 14px/900 (no califica como "texto grande": 14px en negrita necesita ≥18.66px para bajar el umbral a 3:1).

### 1.6 Íconos decorativos (`aria-hidden="true"`, umbral 3:1 no-texto)

Glifos como `context-icon`, `stat-icon`, `document-icon`, `alert-icon`, `mic-symbol`, `canary-result > span` están todos marcados `aria-hidden` y acompañados de texto equivalente. Sus ratios (3.38–8.78:1) **pasan** el umbral no-texto de 3:1 en todos los casos revisados. No se reportan como bloqueo porque no son el único canal de información.

---

## 2. Foco visible

- Sí existe una regla global: `button:focus-visible, a:focus-visible { outline: 3px solid rgba(34,184,188,.38); outline-offset: 3px; }` (`globals (1).css` líneas 53–57). Se aplica a **todos** los elementos interactivos porque todos son `<button>`/`<a>` reales (ver sección 3).
- **No hay ningún `outline: none` sin reemplazo** en el archivo — se revisó el CSS completo (1795 líneas); no aparece esa declaración en ningún selector.
- **Problema real:** el color del anillo de foco, aplanado sobre blanco, equivale aproximadamente a `#96d5d7` → contraste de **1.64:1** contra fondos claros (blanco, `--canvas`, `--surface`). Muy por debajo del ~3:1 recomendado para que un indicador de foco sea perceptible (SC 1.4.11 aplicado a estados de componentes UI). En la práctica, tabular con teclado por `nav-item`, `mic-button`, `primary-action`, `alert-copy button`, etc. deja un anillo casi invisible sobre las superficies blancas/aqua-soft que dominan el diseño.
- No hay trampas de foco visibles en el marcado (no hay `tabIndex` negativos ni `onKeyDown` que intercepten Tab).

---

## 3. Labels / semántica

- **Todos los elementos interactivos son `<button>` reales** — no se encontró ningún `<div onClick>` en `dashboard.tsx`. Confirmado por lectura completa del archivo (738 líneas).
- Botones solo-ícono tienen `aria-label`: micrófono (`"Pausar escucha del micrófono"` / `"Reanudar escucha del micrófono"`, con `aria-pressed`), botón de marca (`"Ir a la llamada de Care Companion"`).
- Botones con texto visible ("Alertar al equipo", "Simular carga de guía", "Preparar evidencia") no necesitan `aria-label` adicional; correcto.
- **No hay ningún `<input>`, `<select>` ni formulario** en este mockup — la sección "inputs con label" no aplica a este alcance.
- Jerarquía de encabezados: un solo `h1` por vista (`voice-heading`, `knowledge-heading`, `audit-heading`, vinculados vía `aria-labelledby`), y `h2` para subsecciones. No se usa `h3` en ningún punto, así que no hay saltos de nivel, pero tampoco hay verificación de que esto se sostenga cuando el contenido crezca en código real.
- Landmarks presentes: `<header>`, `<nav aria-label="Navegación principal">`, `<main className="app-shell">`, `<footer>`, y `aria-label`/`aria-labelledby` en casi todas las `<section>` (`context-strip`, `voice-card`, `clinical-rail`, `transcript`, `knowledge-heading`, `audit-heading`, `metrics-band`, agentes). Esto es una fortaleza real del mockup.
- **Nota semántica (no bloqueo AA):** las pestañas primarias (`Llamada`/`Conocimiento`/`Auditoría`) usan `aria-pressed` en vez del patrón ARIA `tablist`/`tab`/`aria-selected` o, más simple, `aria-current="page"`. Funciona para lectores de pantalla pero no comunica "pestaña de navegación" de forma idiomática.
- `aria-live="polite"` en `.voice-stage` es correcto para el estado de escucha; el `transcript` no tiene `aria-live`, lo cual es razonable si los turnos nuevos no deben interrumpir al usuario constantemente (design.md sección 12 pide "aria-live separado para transcript parcial, decisión y error" — el mockup solo cubre el estado global de voz, no los tres canales separados que pide el propio contrato).

---

## 4. Color como único canal

- **Alertas de riesgo (`.alert-card` / `.is-alerted`):** correctamente dual-codificado — cambia color, pero también ícono (`!` → `✓`), texto del eyebrow, título y copy. **No es una violación.**
- **`document-status` / `.is-new`:** cambia color de fondo Y el texto (`"Verificada"` vs `"Nueva"`). **No es una violación.**
- **`agent-tag.urgent`:** cambia color, pero el texto del tag (`"Escalar"`) ya lo dice en palabras. **No es una violación.**
- **`audit-timeline li.{aqua|coral|blue|lime}`:** el punto de color es redundante — cada ítem del timeline ya tiene título y detalle en texto explícito (p. ej. "Señal de riesgo detectada"). El color no es el único canal. **No es una violación**, aunque el punto en sí (sin texto adjunto) no sería comprensible aislado.
- **`pipeline-list li.done` / `li.active` (Conocimiento, `dashboard.tsx` líneas 425–454):** **sí es una violación real.** El único indicador de que un paso del pipeline está completado o activo es el color de fondo/borde de la tarjeta y de la burbuja numerada (`lime-soft`+verde para "done", `aqua-soft`+aqua para "active", gris neutro para pendiente). No hay ícono de check, ni texto "Completado"/"En curso", ni `aria-current`. Un usuario con daltonismo o baja visión no puede distinguir qué paso ya ocurrió solo mirando la lista. Contradice explícitamente el propio principio del `design.md` ("Color nunca será el único indicador", sección 5.4) aunque esa regla se escribió pensando en estados de riesgo, no en el pipeline de conocimiento.

---

## 5. Reduced motion

- **Sí existe** un bloque `@media (prefers-reduced-motion: reduce)` (líneas 1786–1795) que neutraliza de forma global `animation-duration`, `animation-iteration-count` y `transition-duration` en `*, *::before, *::after`, más `scroll-behavior: auto`. Es una implementación amplia y correcta — cubre automáticamente toda animación/transición presente sin necesidad de listarlas una por una.
- Animaciones/transiciones detectadas en el CSS (todas cubiertas por la regla anterior):
  - `@keyframes voice-wave` — barras del waveform en `.is-listening .waveform span` (1.3s infinite alternate).
  - `@keyframes live-pulse` — punto de "en vivo" en `.call-status span` / `.live-pill i` (1.8s infinite).
  - `transition: 180ms ease` en `.nav-item::after`, `.mic-button`, `.alert-copy button`, `.primary-action`/`.secondary-action` (hover).
  - `transition: 220ms ease` en `.alert-card` (cambio a `.is-alerted`).
  - `transition: height 240ms ease` en `.waveform span`.
  - `scroll-behavior: smooth` en `html`.
- **Veredicto de esta sección: sin hallazgos.** Es, junto con los landmarks, uno de los aspectos mejor resueltos del mockup.

---

## 6. Veredicto

### Tabla de hallazgos

| # | Hallazgo | Severidad | Dónde aparece |
|---|---|---|---|
| 1 | Botón "Alertar al equipo" (texto blanco sobre gradiente coral): 3.01–3.38:1, requiere 4.5:1 | **Blocker AA** | `/call` (primera vista) — es el CTA de escalamiento clínico |
| 2 | `.eyebrow` y `.nav-item.active` (aqua-deep sobre blanco): 3.90:1, requiere 4.5:1 | **Blocker AA** | `/call` (eyebrows de la vista, pestaña activa del header) |
| 3 | `.call-status` y `.speaker-label` del asistente (aqua-deep sobre aqua-soft): 3.63:1 | **Blocker AA** | `/call` (estado "En llamada", transcripción) |
| 4 | `.speaker-label` del paciente y `.review-chip` (dorado sobre gold-soft): 3.65–4.04:1 | **Blocker AA** | `/call` (transcripción, tarjeta de supervisión) |
| 5 | Anillo de foco con 1.64:1 de contraste sobre fondos claros | **Blocker AA** | Global — todo botón/enlace de las tres vistas |
| 6 | `.healthy-chip` / `.document-status` (verde sobre lime-soft): 3.70:1 | Mayor | `/knowledge`, `/audit` |
| 7 | Estado completado/activo del `pipeline-list` comunicado solo por color (sin ícono ni texto) | Mayor | `/knowledge` |
| 8 | `--ink-muted` sobre blanco/canvas: 4.53–4.75:1, margen mínimo sobre superficies que en producción serán semitransparentes | Menor | Global (labels secundarios, footer) |
| 9 | Pestañas primarias con `aria-pressed` en vez de patrón `tab`/`aria-current` | Menor | Header, las tres vistas |
| 10 | `.document-status.is-new` (4.52:1) y `.simulation-chip` (4.77:1) pasan con margen muy estrecho — mismos tokens dorados que fallan en otros usos | Menor | `/knowledge`, `/audit` |

### Conclusión honesta

**No cumple** el criterio de aceptación "sin blockers AA en primera vista". La vista `/call` (la que se monta por defecto) contiene **5 bloqueos AA reales**, y el más grave recae exactamente sobre el control más importante de la pantalla: el botón de escalamiento a supervisión humana. Todos los bloqueos comparten una causa raíz común y barata de arreglar: los pares "texto oscuro-medio sobre superficie *-soft muy clara" del sistema de tokens (`aqua-deep`/`aqua-soft`, dorados/`gold-soft`, verdes/`lime-soft`) fueron calibrados para verse bien visualmente pero no se validaron contra 4.5:1, y el anillo de foco usa una opacidad demasiado baja del mismo aqua.

Esto no es un fracaso del mockup — es exactamente el tipo de deuda que PRE-025 existe para atrapar antes de escribir código de producción. La dirección visual, la jerarquía semántica, los landmarks y el manejo de `prefers-reduced-motion` están, en cambio, bien resueltos y no requieren rediseño.

### Recomendaciones concretas para UX-008

1. **Oscurecer un escalón los tokens de texto-sobre-`*-soft`**, sin tocar los tokens de fondo/marca: `aqua-deep` a algo ≈`#086b70` (≈4.7:1 sobre `aqua-soft` y sobre blanco), dorado de labels a ≈`#8a6300` (≈4.9:1 sobre `gold-soft`), verde de chips a ≈`#4d7614` (≈4.6:1 sobre `lime-soft`). Mantener los `*-soft` y los tokens de acento (`--aqua`, `--gold`, `--lime`) sin cambios — solo se ajustan las variantes "-deep"/texto que hoy están calibradas por debajo de 4.5:1.
2. **Botón de alerta:** oscurecer el extremo claro del degradado (`#f06b63` → algo ≈`#c94a42`) o subir el peso/tamaño del texto por encima de 18.66px en negrita para calificar como "texto grande" (3:1). La primera opción es más simple y no cambia el layout.
3. **Anillo de foco:** subir la opacidad de `rgba(34,184,188,.38)` a ~0.75–0.85, o pasar a un color sólido (`--aqua-deep` corregido) en vez de rgba — objetivo ≥3:1 sobre blanco y sobre `aqua-soft`.
4. **Pipeline de conocimiento:** añadir un ícono de check (ya aria-hidden, no rompe nada) o un texto visualmente oculto tipo "Completado"/"En curso" a los estados `.done`/`.active`, en línea con el propio principio "color nunca será el único indicador" del `design.md`.
5. Ninguno de estos cambios toca layout, tipografía, radios ni la dirección Family-first Pediatric — son ajustes de valor de color dentro de la misma paleta, compatibles con la regla de "cambio mínimo y explícito" del handoff.
