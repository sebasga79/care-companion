# Matriz de decisión — Estrategia RAG (CH-008 / ADR-003)

> v0.1 · 23 de julio de 2026 · Ticket: PRE-033

## 0. Propósito y regla dura

Esta matriz **prepara** la decisión de estrategia RAG; **no la toma**. Los scores están vacíos y se llenan en T0 con datos reales del corpus, el dataset y el starter recibidos en CH-002/CH-003/CH-005. Nadie debe completar los scores antes del 7 de agosto.

Decisión a tomar: **mantener el default de `architecture.md` §9.1 — SQLite FTS5 (léxico) + vectores NumPy en BLOB (semántico), fusionados por Reciprocal Rank Fusion** (ADR-003, estado actual: *propuesta*) — **vs. un adapter alterno**, únicamente si el starter o el dataset lo imponen de forma no evitable (p. ej. el starter ya trae un vector store distinto integrado, o el volumen/latencia del corpus real excede lo que SQLite puede sostener en la ventana de 72h).

Presupuesto de tiempo: decidible en **≤45 minutos**, alineado con la aceptación de PRE-033 en `plan.md` §4 ("decisión posible en 45 min"). Insumo directo: el perfil de Delta Share obtenido en CH-005 (schema, volumen, tipos) y la inspección del repo base en CH-004.

## 1. Default explícito

**El default es SQLite FTS5 + vectores NumPy (`architecture.md` §9.1, ADR-003), salvo evidencia concreta en contra.** Esta matriz no busca elegir "la mejor opción en abstracto"; busca decidir si hay evidencia suficiente para **apartarse** del default ya documentado. Si no hay evidencia clara en contra al cerrar los 45 minutos, se adopta el default sin más análisis (consistente con la regla de `plan.md` §2.5: ante timebox agotado, se adopta la opción más simple que cumpla — y el default ya es la opción más simple).

Evidencia en contra que justificaría apartarse del default (no exhaustivo, a confirmar con datos reales de CH-005):
- el starter incluye un vector store/DB ya integrado y reemplazarlo consume más tiempo que adaptarse a él;
- el volumen real del corpus excede lo que un scan NumPy acotado puede resolver dentro de los presupuestos de latencia (NFR-002);
- el dataset exige un motor de búsqueda específico por licencia o por contrato de acceso.

## 2. Criterios ponderados

| Criterio | Peso | Qué mide |
|---|---:|---|
| Volumen del corpus real | 20% | Número de documentos/chunks esperado (de CH-005) vs. lo que SQLite+NumPy puede sostener en memoria/tiempo de consulta dentro de la ventana del reto |
| Tipos de documento | 15% | PDF/TXT/MD y su complejidad de extracción/estructura (tablas, secciones, páginas) frente al pipeline de ingestión de `architecture.md` §9.2 |
| Latencia de retrieval | 20% | Tiempo de consulta híbrida (FTS5 + coseno + RRF) bajo el volumen real, frente a NFR-002 (fin de voz→audio ≤2.5s P95, del cual retrieval es una fracción) |
| Semántica de deletion (gate learn/forget) | 30% | Capacidad de cumplir borrado verificable (`architecture.md` §9.3): transacción, tombstone, `knowledge_version`, consulta canaria negativa — es compuerta eliminatoria (AC-E2E-006) |
| Compatibilidad con starter | 15% | Si el starter impone o sugiere un motor/almacenamiento distinto, y el costo de adaptarlo vs. reemplazarlo |

**Suma de pesos: 100%.** Nota: "Semántica de deletion" tiene el peso más alto porque `learn`/`forget` es una de las cinco compuertas eliminatorias del concurso (`plan.md` §1, `architecture.md` §2.1) — un motor que no pueda demostrar borrado verificable descalifica sin importar el resto, igual que el criterio de compatibilidad de modelo en la matriz de voz.

## 3. Tabla de scoring (VACÍA — llenar en T0)

Escala 1–5 por opción y criterio (1 = muy desfavorable, 5 = muy favorable).

| Criterio | Peso | Score SQLite híbrido (default) | Ponderado | Score Adapter alterno | Ponderado |
|---|---:|:---:|:---:|:---:|:---:|
| Volumen del corpus real | 20% | ☐ | | ☐ | |
| Tipos de documento | 15% | ☐ | | ☐ | |
| Latencia de retrieval | 20% | ☐ | | ☐ | |
| Semántica de deletion (gate learn/forget) | 30% | ☐ | | ☐ | |
| Compatibilidad con starter | 15% | ☐ | | ☐ | |
| **Total ponderado** | 100% | | **☐** | | **☐** |

## 4. Spike mínimo (solo si hay motivo para dudar del default)

Si CH-005 no revela ningún motivo de la sección 1 para apartarse del default, **no se ejecuta spike** — se adopta SQLite híbrido directamente y se documenta la razón ("sin evidencia en contra") en ADR-003.

Si sí hay motivo, spike acotado (dentro del remanente de los 45 minutos):

**Para SQLite híbrido:**
- cargar una muestra representativa de documentos reales (del corpus perfilado en CH-005, no fixtures) en `documents`/`chunks`/FTS5/vectores;
- medir latencia de una consulta híbrida (FTS5 + coseno + RRF) con esa muestra;
- ejecutar un ciclo completo de borrado (`architecture.md` §9.3) sobre un documento cargado y confirmar consulta canaria negativa.

**Para el adapter alterno (solo si el starter lo impone):**
- confirmar que el adapter alterno puede implementar el mismo contrato de borrado verificable (tombstone, `knowledge_version`, canary) sin cambiar la semántica del gate learn/forget;
- medir latencia de una consulta equivalente con la misma muestra de documentos.

## 5. Umbral de decisión

- Si "Semántica de deletion" obtiene score 1–2 en cualquiera de las dos opciones, esa opción queda descalificada — el borrado verificable no es negociable (compuerta eliminatoria).
- Entre opciones que sí califican, se compara el total ponderado; gana el mayor.
- Si no hay evidencia en contra del default (sección 1), se adopta SQLite híbrido sin necesidad de que el total ponderado del adapter alterno supere nada — el default gana por diseño salvo evidencia, no por comparación de scores.

## 6. Salida esperada

El resultado se transcribe a **ADR-003** en `architecture.md` §17, actualizando su estado de "propuesta" a "aceptada" (si se confirma el default) o a una nueva decisión con justificación, fecha y ticket CH-008 (delta de requisitos).
