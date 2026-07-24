# Nota de compromiso — Stop-work preinicio

> v0.1 · 23 de julio de 2026 · Ticket: PRE-037

## Declaración

Yo, SG, propietario y ejecutor individual del proyecto Care Companion para el Source Meridian Tech Sphere Challenge 2026 (Voice Agent Edition), declaro que **no construyo ninguna solución final ni código de la solución del reto antes de T0 (7 de agosto)**.

Este compromiso existe para preservar la equidad de arranque simultáneo del concurso: todos los participantes empiezan la construcción el mismo día, con el mismo starter, dataset y modelo obligatorio, sin ventaja derivada de trabajo material-específico realizado antes de tiempo.

## Qué SÍ está permitido antes de T0

Según `plan.md` §4 ("Fase P — Preparación previa"):

> "Esta fase respeta el propósito del concurso de iniciar con el mismo starter/dataset/modelo el 7 de agosto. Se limita a planeación, ambiente, plantillas, checklists y ensayos genéricos desechables. No incorpora materiales no publicados ni pretende entregar una solución anticipada."

Concretamente, sí está permitido y es lo que ocupa los sprints P0–P3 (`plan.md` §4):

- documentación de planeación (SDD, spec, arquitectura, plan — ya v0.1, Sprint P0);
- preparación de ambiente y estación de trabajo (Docker, Python, Node, Git, audio/cámara — Sprint P1);
- plantillas reutilizables (ADR, evidencia, convenciones Git, gestión de secretos — Sprint P1);
- checklists genéricos (dependencias, casos conversacionales ficticios abstractos, glosario no clínico — Sprint P1);
- ensayos desechables de proceso, demo, video, red y micrófono, usando un **proyecto toy** que no se incorpora al entregable final (Sprint P2, explícito en PRE-020: *"código no se incorpora si reglas no lo permiten"*);
- matrices de decisión con criterios y metodología definidos, pero **scores vacíos** hasta T0 (Sprint P3, este mismo batch de tickets);
- planeación de agenda, salud, turnos y freeze de baseline (Sprint P3).

## Qué NO está permitido antes de T0

- **código de la solución real** de Care Companion (RAG, orquestador, agentes, voz, UI de producto) — ni siquiera un borrador "para adelantar";
- **incorporar material no publicado** del reto (starter, dataset, ficha técnica, credenciales) antes de que se publique oficialmente;
- tomar como definitivas las decisiones reservadas para el 7 de agosto (modelo, voz, RAG, dataset, métricas, deadline exacto) — las matrices y agendas de este batch preparan esas decisiones, no las toman;
- cualquier commit al repositorio del entregable que contenga lógica de producto material-específica antes de T0;
- usar en el entregable final artefactos de los ensayos desechables de la Fase P (Sprint P2) — esos ensayos existen para practicar el proceso, no para convertirse en código de producción.

## Alcance de este compromiso

Este stop-work aplica exclusivamente a la construcción de la solución (código de producto, contenido específico del reto). No aplica a la preparación documentada arriba, que continúa según el cronograma de `plan.md` §3 (Sprints P1–P3, 25 de julio – 6 de agosto).

## Fecha y firma

23 de julio de 2026 — SG
