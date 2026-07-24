# Política de dependencias

> v0.1 · 23 de julio de 2026 · Ticket: PRE-016

Regla base (`plan.md` PRE-016 y `spec.md` §11.2): **dependencia nueva exige necesidad demostrada y licencia compatible; nada se agrega por preferencia personal.** Esta política aplica a toda dependencia de código (Python/`uv`, Node/`pnpm`) y a herramientas/imágenes usadas en el flujo de instalación limpia.

## 1. Criterios para agregar una dependencia nueva

Una dependencia solo se agrega si cumple **todos** los siguientes puntos:

1. **Necesidad demostrada:** existe un requisito o ticket concreto que no se puede resolver razonablemente con la librería estándar, una dependencia ya presente, o unas pocas líneas propias. "Es más cómodo" o "la conozco mejor" no es justificación suficiente.
2. **Licencia compatible con MIT** (ver §2).
3. **Mantenimiento activo:** repositorio con actividad reciente razonable, sin señales de abandono (issues críticos sin respuesta por años, sin releases en mucho tiempo sobre un proyecto que las requiere).
4. **Sin CVEs críticos/altos sin parchear** conocidos al momento de agregarla (verificar con el scanner de SEC-004 o equivalente antes de fijar la versión).

Si alguno de los cuatro criterios falla, la dependencia no se agrega — se busca alternativa o se implementa la porción mínima necesaria.

## 2. Licencias

### 2.1 Permitidas

- MIT
- BSD (2-Clause / 3-Clause)
- Apache-2.0
- ISC

Estas son compatibles con la licencia MIT del proyecto (`DOC-007`) y no imponen obligaciones de copyleft sobre el código propio.

### 2.2 Prohibidas o que requieren revisión explícita antes de usar

- **GPL / AGPL** (cualquier versión): copyleft fuerte, riesgo de contaminar la licencia del repositorio entregable. No se agregan sin decisión humana explícita y documentada (ADR), y en la práctica se evitan por completo dado el requisito de entrega bajo MIT.
- **Sin licencia declarada** ("unlicensed" / repositorio sin archivo `LICENSE`/campo `license` en su manifiesto): tratar como no utilizable — no hay base legal clara para redistribuir.
- **Licencias no estándar o con cláusulas restrictivas** (uso no comercial, cláusulas de atribución inusuales, "field of use" restringido): requieren revisión humana explícita antes de usarse, incluso si a primera vista parecen permisivas.

Cualquier duda sobre una licencia se resuelve **antes** de instalar la dependencia, no después.

## 3. Lockfiles obligatorios

- **Python (control-plane y servicios de dominio):** `uv.lock` se mantiene actualizado y se comitea junto con cualquier cambio a `pyproject.toml`.
- **Node/frontend:** `pnpm-lock.yaml` se mantiene actualizado y se comitea junto con cualquier cambio a `package.json`.
- Ninguna instalación se considera reproducible sin lockfile — es prerequisito para el criterio de instalación limpia ≤15 min (`REP-003`, `REL-001`).
- No se edita un lockfile a mano; se regenera con la herramienta correspondiente (`uv lock`, `pnpm install`).

## 4. Proceso de remoción

Una dependencia se retira cuando:

- deja de usarse en el código (verificar con búsqueda de imports/uso real, no solo revisar el manifiesto);
- se reemplaza por una alternativa que cumple mejor los criterios de §1;
- aparece un CVE crítico sin parche disponible y sin mitigación razonable;
- cambia su licencia a una no permitida (§2.2) en una actualización futura.

Pasos:

1. Confirmar que ningún módulo activo la importa (no solo el punto de entrada evaluado manualmente).
2. Remover la entrada del manifiesto (`pyproject.toml` / `package.json`).
3. Regenerar el lockfile correspondiente.
4. Ejecutar los checks del ticket (build/tests) para confirmar que la remoción no rompe nada.
5. Registrar el cambio en un commit dedicado (`TICKET-ID: remueve dependencia <nombre>`, con el motivo en el cuerpo, según `CONTRIBUTING.md`).

## 5. Verificación periódica

- `SEC-004` (Sprint C4) ejecuta el escaneo formal de licencias y CVEs sobre el estado final antes de release, y genera el reporte/`NOTICE` requerido por `DOC-007`.
- Antes de eso, cualquier dependencia agregada durante P1–C3 debe poder justificarse contra §1 si se pregunta en revisión — no se espera hasta C4 para tener la justificación lista.

## 6. Resumen ejecutable

Antes de correr `uv add <paquete>` o `pnpm add <paquete>`, quien ejecuta el cambio (humano o asistente de IA bajo `spec.md` §11) confirma explícitamente:

- [ ] Hay una necesidad concreta ligada a un ticket, no preferencia personal.
- [ ] La licencia está en la lista permitida de §2.1, o fue revisada y aprobada explícitamente.
- [ ] El proyecto está activamente mantenido.
- [ ] No tiene CVEs críticos/altos conocidos sin parchear.
- [ ] El lockfile correspondiente se regenera y se comitea junto con el manifiesto.
