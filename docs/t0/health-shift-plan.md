# Plan de salud y turnos — 7 al 10 de agosto

> v0.1 · 23 de julio de 2026 · Ticket: PRE-036

## 0. Regla dura

**No se planea trabajo continuo de 72 horas.** Cada noche del reto tiene un bloque de sueño mínimo de 6 horas. Esta es la aceptación explícita de PRE-036 en `plan.md` §4 y se aplica sin excepción salvo un blocker P0 documentado en el buffer de contingencia de C5 (`plan.md` FIN-011), nunca como rutina.

La hora exacta de T0 se confirma el 7 de agosto (`plan.md` línea 99); este plan usa **offsets relativos a T0** (`T+Xh`) superpuestos a un calendario de 4 días (7, 8, 9 y 10 de agosto), no horas de reloj fijas. Al confirmarse T0 real, este plan se ancla a hora de reloj sin cambiar su estructura.

## 1. Mapeo a los sprints de construcción (`plan.md` §5)

| Sprint | Ventana relativa | Duración |
|---|---|---|
| C0 Intake | T0 → T+~2h40m | ~2.7h (ver `docs/t0/agenda-t0.md` sobre la discrepancia de timebox) |
| C1 Vertical Slice | T+2h → T+12h | 10h |
| C2 Clinical Core | T+12h → T+28h | 16h |
| C3 Experience | T+28h → T+44h | 16h |
| C4 Evidence | T+44h → T+58h | 14h |
| C5 Release | últimas 6h antes del cierre | 6h |

Sobre ~64 horas de construcción activa repartidas en 3–4 días de calendario, con sueño y comidas intercalados — no 64 horas continuas de trabajo.

## 2. Estructura de bloques de foco

- **Bloques de foco: 90–120 minutos**, alineados a la duración de 1–2 tickets del plan (la mayoría de tickets C1–C4 estiman 30–75 min, ver `plan.md` §5).
- **Descanso entre bloques: 10–15 minutos**, lejos de la pantalla — levantarse, estirar, hidratarse.
- Cada 3–4 bloques de foco (≈6–8h), **descanso más largo de 30–45 minutos** que incluye una comida.
- Ningún bloque de foco arranca un ticket nuevo si quedan menos de 45 minutos antes del siguiente descanso planeado — evita dejar tickets a medias por interrupción de calendario (distinto de la regla de timebox agotado, que es sobre el contenido del ticket, no sobre el reloj de descanso).

## 3. Comidas

- 3 comidas principales por día de calendario (desayuno, almuerzo, cena), a horas fijas relativas al ciclo de sueño, no al progreso del sprint — comer no espera a "terminar el ticket".
- 1–2 snacks ligeros entre bloques largos (evitar snacks pesados que induzcan somnolencia durante bloques de foco).
- Hidratación visible/programada, no solo café — la fatiga por deshidratación se confunde fácilmente con fatiga por falta de sueño.

## 4. Sueño mínimo por noche

- **Mínimo 6 horas de sueño cada noche del 7 al 10 de agosto** (3 noches: 7→8, 8→9, 9→10).
- El bloque de sueño se protege como un ticket P0 más: no se recorta para "adelantar" un sprint, salvo blocker documentado en el buffer de C5.
- Idealmente 7–8h si el ritmo de sprints lo permite (especialmente la noche antes de C4/C5, donde se requiere juicio fino para evals, seguridad y release).
- Si un sprint se atrasa y compite con la hora de dormir, se aplica primero la regla de `plan.md` §2.5 (adoptar la opción más simple / orden de sacrificio de `plan.md` §5) antes que recortar sueño.

## 5. Buffers alineados a transiciones de sprint

- **Buffer de 30 min al cierre de cada sprint C0–C4** para registrar evidencia, checkpoint estable y retrospectiva corta, antes de iniciar el siguiente sprint — evita arrastrar deuda de evidencia a costa de horas de sueño más adelante.
- **Feature freeze 12h antes del cierre** (ya definido en `plan.md` §15) coincide con el inicio de C4 tardío/C5 — usar ese punto como ancla para planear la última noche de sueño antes del release final.
- **1 hora mínima de buffer no comprometido** antes del envío final (`plan.md` §15) — no se programa ninguna tarea nueva en esa hora, ni de código ni de descanso extra: es margen puro para imprevistos de envío.

## 6. Señales de fatiga (auto-chequeo, no delegable)

Revisar al cierre de cada bloque de foco, no esperar al final del día:

- errores repetidos en tareas simples (typos, comandos mal copiados, tests que fallan por descuido);
- dificultad para sostener atención más de 20–30 min dentro de un bloque de 90–120 min;
- decisiones que se posponen una y otra vez sin razón técnica clara;
- irritabilidad o impaciencia notable frente a bloqueos menores;
- microsueños o parpadeo prolongado frente a la pantalla;
- perder la cuenta de en qué ticket se está trabajando (señal de WIP fuera de control, cruza con la regla de `plan.md` §2.5).

## 7. Regla de parada

Si aparecen **dos o más señales de fatiga de la sección 6** dentro del mismo bloque de foco:

1. detener el ticket actual (registrar estado parcial en la evidencia del ticket, no forzar el cierre);
2. tomar el descanso largo de la sección 2 aunque no toque según el calendario;
3. si las señales persisten después del descanso largo, adelantar el bloque de sueño de esa noche en vez de forzar otro bloque de foco — dormir mal un ticket es preferible a que un ticket de seguridad clínica (SAFE-*, RAG-*) se construya con juicio degradado;
4. registrar la pausa como evento en el ledger de gestión (`plan.md` §14), no ocultarla.

Esta regla tiene precedencia sobre el cronograma de sprints — es la aplicación directa, a nivel humano, del principio "safety before fluency" de `architecture.md` §3: un ticket construido con juicio degradado es un riesgo mayor que un sprint que se alarga.
