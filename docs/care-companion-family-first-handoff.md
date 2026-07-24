# Care Companion — Handoff visual para Codex y Claude Code

> Versión 1.0 · 23 de julio de 2026  
> Dirección aprobada: **Family-first Pediatric**  
> Referencia navegable: https://care-intelligence-studio.sebastian-gaviria-2023.chatgpt.site

## 1. Propósito de este documento

Este archivo es el contrato de implementación visual y de comportamiento para continuar Care Companion con Codex o Claude Code. Debe entregarse al asistente junto con el repositorio.

La propuesta corresponde a una plataforma de seguimiento postoperatorio por voz, con evidencia clínica, agentes de responsabilidad única, supervisión humana y trazabilidad. La interfaz debe ser amable para familias y suficientemente rigurosa para profesionales y jurados.

Principio rector:

> La voz ocupa el centro; evidencia, riesgo y supervisión permanecen visibles sin convertir la experiencia en un dashboard genérico.

## 2. Stack esperado

- Frontend: Next.js, React y TypeScript.
- Backend: Python y FastAPI.
- Persistencia inicial: SQLite.
- Orquestación: un agente orquestador delgado y agentes especializados con responsabilidad única.
- RAG inicial: recuperación híbrida con texto completo y vectores.
- Voz: canal en tiempo real con interrupción o barge-in.

Este documento se concentra en el frontend. No autoriza al asistente a inventar contratos del backend.

## 3. Dirección visual aprobada

### Carácter

- Pediátrica y humana, sin verse infantil.
- Clínica y confiable, sin parecer un sistema administrativo.
- Aireada, con jerarquía tipográfica clara y pocas decisiones visuales fuertes.
- La interfaz debe comunicar calma, escucha y acompañamiento.
- La trazabilidad técnica se muestra como evidencia observable, no como complejidad decorativa.

### Paleta

```css
:root {
  --ink: #13365f;
  --ink-strong: #073b78;
  --ink-muted: #61758a;
  --blue: #004b8d;
  --blue-soft: #eaf4fb;
  --aqua: #22b8bc;
  --aqua-deep: #0b8f96;
  --aqua-soft: #e9fafa;
  --lime: #8bbf38;
  --lime-soft: #eff8df;
  --gold: #d9a326;
  --gold-soft: #fff4cf;
  --coral: #e85f57;
  --coral-deep: #c83e37;
  --coral-soft: #fff1ed;
  --line: #d8e5ee;
  --surface: #ffffff;
  --canvas: #f7fafc;
  --shadow: 0 14px 36px rgba(24, 64, 94, 0.09);
}
```

### Tipografía y geometría

- Display/UI: Nunito Sans; usar Avenir Next, Segoe UI o Arial como fallback.
- Títulos principales: peso 700–800, tracking ligeramente negativo.
- Texto funcional: Inter o la familia del sistema.
- Grid base: 8 px.
- Espaciado interno de tarjetas: 20–32 px.
- Radios principales: 19–28 px.
- Controles interactivos: mínimo 44×44 px.
- Sombras suaves y uniformes; nunca una sombra distinta por categoría.
- Movimiento corto y funcional; respetar `prefers-reduced-motion`.

## 4. Regla antipatrones visuales genéricos

Esta regla es obligatoria.

### No usar

- Franjas superiores o laterales de un color diferente en cada tarjeta.
- El patrón “una tarjeta por métrica + un color por métrica”.
- Gradientes arcoíris para distinguir categorías equivalentes.
- Bordes luminosos, glows o halos decorativos sin significado funcional.
- Exceso de pills o badges como decoración.
- Iconos distintos para datos equivalentes solo para “hacerlos visuales”.
- Cuadrículas de tarjetas idénticas que parezcan una plantilla de dashboard de IA.
- Colores de riesgo aplicados a datos neutrales.

### Usar en su lugar

- Jerarquía por tamaño, peso, alineación y proximidad.
- Una retícula consistente y espacio en blanco.
- Bordes neutrales compartidos.
- Color solo cuando codifica estado real: escucha, evidencia verificada, advertencia o escalamiento.
- Variación de composición únicamente cuando cambia la función del contenido.

Ejemplo correcto para métricas:

```css
.metrics-band {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.metric-card {
  min-height: 130px;
  padding: 21px;
  border: 1px solid var(--line);
  border-radius: 19px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow);
}

.metric-card__label {
  margin: 0 0 7px;
  color: var(--ink-muted);
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.metric-card__value {
  display: block;
  color: var(--ink-strong);
  font-size: 24px;
  letter-spacing: -0.03em;
}

.metric-card__detail {
  display: block;
  margin-top: 8px;
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.4;
}
```

No añadir `::before`, `border-top-color` ni una prop `accent` a este componente.

## 5. Arquitectura de la experiencia

La navegación primaria tiene tres vistas:

| Vista | Objetivo | Contenido mínimo |
|---|---|---|
| Llamada | Mostrar una conversación de seguimiento | estado de voz, waveform, transcripción, evidencia y escalamiento |
| Conocimiento | Demostrar conocimiento gobernado | documentos, versión activa, ingesta, recuperación y eliminación verificable |
| Auditoría | Explicar qué ocurrió | timeline, salidas estructuradas de agentes y métricas |

### Llamada

- La voz y el estado “Escuchando” dominan el viewport.
- El micrófono permite pausar y reanudar.
- La transcripción distingue asistente y paciente ficticio.
- La supervisión humana permanece visible.
- El escalamiento se presenta como handoff simulado.
- Después de alertar debe indicar explícitamente que no se ejecutó una acción hospitalaria real.

### Conocimiento

- Mostrar versión activa de la base.
- Permitir simular la carga de una guía.
- La guía cargada debe aparecer en documentos y participar en nuevas consultas simuladas.
- Permitir eliminarla.
- Después de eliminar, mostrar una prueba canaria con `0 resultados`.
- El flujo debe evidenciar `learn → retrieve → forget`.

### Auditoría

- Mostrar una línea de tiempo del caso ficticio.
- Mostrar resultados estructurados del Orquestador, Safety Agent, Retrieval Agent y Conversation Agent.
- No mostrar cadenas de razonamiento.
- Latencia P50/P95, tokens y costo deben rotularse como objetivos o pendientes hasta tener mediciones reales.
- El paquete de evidencia es una simulación y no debe afirmar que descargó o transmitió datos.

## 6. Componentes React de referencia

```tsx
type MetricProps = {
  label: string;
  value: string;
  detail: string;
};

export function Metric({ label, value, detail }: MetricProps) {
  return (
    <article className="metric-card">
      <p className="metric-card__label">{label}</p>
      <strong className="metric-card__value">{value}</strong>
      <small className="metric-card__detail">{detail}</small>
    </article>
  );
}

export function MetricsBand() {
  return (
    <section className="metrics-band" aria-label="Métricas del concurso">
      <Metric
        label="Latencia P50"
        value="< 1.2 s"
        detail="Objetivo · medir desde el 7 de agosto"
      />
      <Metric
        label="Latencia P95"
        value="< 2.5 s"
        detail="Objetivo · extremo a extremo"
      />
      <Metric
        label="Tokens"
        value="Por turno"
        detail="Trazados · pendiente de medición"
      />
      <Metric
        label="Costo"
        value="Por llamada"
        detail="Estimado · pendiente del LLM obligatorio"
      />
    </section>
  );
}
```

## 7. Reglas de seguridad y honestidad del prototipo

El asistente de código debe:

- usar únicamente datos sintéticos o casos ficticios;
- rotular claramente simulaciones, objetivos y valores pendientes;
- preservar la supervisión humana en decisiones de riesgo;
- tratar el escalamiento como recomendación o handoff, no como atención ya ejecutada;
- conservar documento, sección y versión en la evidencia recuperada;
- registrar entradas, salidas estructuradas, decisiones y referencias;
- aplicar accesibilidad básica, foco visible y reduced motion;
- mantener separadas las responsabilidades de los agentes.

El asistente de código no debe:

- introducir PHI, PII o información real de pacientes;
- emitir diagnóstico, prescripción o garantía clínica;
- afirmar que Care Companion es un producto oficial de Akron Children’s;
- copiar el logotipo, trade dress o componentes del hospital;
- incluir la fotografía institucional en el repositorio o video públicos sin una licencia o autorización adecuada;
- inventar mediciones, resultados de pruebas, costos, latencias o citas;
- mostrar o persistir cadenas privadas de razonamiento;
- ejecutar alertas, mensajes, llamadas o acciones hospitalarias reales;
- acoplar lógica clínica crítica a componentes visuales;
- reemplazar el orquestador delgado por un agente monolítico;
- añadir paquetes, servicios o dependencias sin necesidad demostrable;
- reintroducir franjas de color por tarjeta o patrones visuales genéricos.

## 8. Prompt listo para Codex o Claude Code

Copiar el siguiente bloque al iniciar una sesión sobre el repositorio:

```text
Implementa o continúa Care Companion siguiendo este documento como contrato
visual y funcional.

Objetivo:
Construir una experiencia de seguimiento postoperatorio por voz, pediátrica,
amable, trazable y con supervisión humana visible. Mantén las tres vistas:
Llamada, Conocimiento y Auditoría.

Restricciones visuales:
- Conserva la dirección Family-first Pediatric.
- Usa azul institucional, aqua, lima y amarillo solo con significado funcional.
- No uses franjas superiores/laterales de color en tarjetas.
- No uses una prop accent ni un color distinto por métrica.
- No conviertas la experiencia en un dashboard genérico.
- Construye jerarquía con tipografía, espacio, alineación y contraste.
- Mantén bordes neutrales, radios amplios y sombras discretas.
- Respeta navegación por teclado y prefers-reduced-motion.

Restricciones de producto:
- Usa únicamente casos ficticios y datos sintéticos.
- No afirmes acciones hospitalarias reales.
- No inventes métricas ni resultados; marca objetivos y pendientes.
- No muestres cadenas de razonamiento.
- Mantén el orquestador delgado y agentes de responsabilidad única.
- No cambies contratos de backend sin presentar primero el impacto.
- No añadas dependencias si CSS y React existentes resuelven el requisito.

Flujo de trabajo:
1. Lee architecture.md, design.md, plan.md y spec.md antes de editar.
2. Inspecciona los componentes y estilos existentes; conserva lo que funciona.
3. Propón un cambio mínimo y explícito.
4. Implementa en tickets pequeños y auditables.
5. Ejecuta build, pruebas y validación de accesibilidad pertinentes.
6. Reporta archivos modificados, pruebas realizadas, supuestos y riesgos abiertos.

Criterio de finalización:
La funcionalidad solicitada funciona, el build pasa, no se introdujeron datos
reales ni afirmaciones clínicas, y la interfaz sigue sintiéndose específica de
Care Companion en lugar de una plantilla genérica de IA.
```

## 9. Instrucción adicional para asistentes

Antes de modificar la UI, el asistente debe explicar en una frase qué relación visual o funcional pretende mejorar. Si el cambio es puramente decorativo y no mejora comprensión, accesibilidad, estado o identidad, no debe implementarlo.

Cuando el asistente detecte un patrón genérico existente, debe:

1. identificar el patrón;
2. explicar por qué reduce la identidad del producto;
3. reemplazarlo con una solución basada en jerarquía y función;
4. verificar que no cambió el significado de los estados.

## 10. Criterios de aceptación

- [ ] La llamada sigue siendo el centro de la experiencia.
- [ ] El estado de voz se comprende sin depender únicamente del color.
- [ ] La supervisión y el handoff humano son evidentes.
- [ ] Learn/retrieve/forget puede demostrarse de extremo a extremo.
- [ ] La auditoría muestra evidencia y resultados estructurados, no razonamiento privado.
- [ ] Las métricas neutrales no tienen barras o bordes cromáticos individuales.
- [ ] Los colores de alerta se reservan para estados reales de atención.
- [ ] Los números no medidos se presentan como objetivo o pendiente.
- [ ] No se introdujeron PHI, PII ni acciones hospitalarias reales.
- [ ] La interfaz funciona con teclado y reduced motion.
- [ ] El build y las pruebas pertinentes pasan.

## 11. Archivos de implementación actuales

En la propuesta de referencia:

- `app/page.tsx`: entrada de la aplicación.
- `app/dashboard.tsx`: navegación y vistas Llamada, Conocimiento y Auditoría.
- `app/globals.css`: tokens, composición, estados, responsividad y accesibilidad.

Estos archivos son muestra de implementación, no sustituyen `architecture.md`, `design.md`, `plan.md` ni `spec.md`.
