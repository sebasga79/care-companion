# Care Companion — Política de gestión de secretos

> v0.1 · 23 de julio de 2026 · Ticket: PRE-012

Deriva de `spec.md` §11 (reglas operativas) y `plan.md` PRE-012 (Sprint P1). Aplica a todo secreto usado durante la fase de preparación y durante el concurso: API keys de modelo, tokens Delta Share, credenciales de base de datos, tokens de servicios de voz, y cualquier valor equivalente.

## 1. Principio general

Ningún secreto se copia a `docs/`, a Git (working tree o historial), a logs, a capturas de pantalla ni a video. El único lugar donde un secreto vive en texto claro es el password manager y, en tiempo de ejecución, variables de entorno no versionadas.

## 2. Fuente única de verdad

- El **password manager** (gestor ya usado por el propietario, fuera de este repo) es la única fuente autorizada de valores reales de secretos.
- Ningún secreto se transcribe en notas, tickets, ADRs, mensajes de commit, nombres de rama, prompts guardados o transcripciones de demo.
- Si un secreto debe compartirse (p. ej. con un colaborador autorizado), se comparte a través del mecanismo de compartición del propio password manager, nunca por chat, correo o archivo plano.

## 3. Convención `.env` / `.env.example`

- Cada servicio que requiera secretos define un archivo `.env` (no versionado) y un `.env.example` (versionado) en el mismo directorio.
- `.env.example` lista **todas** las variables requeridas con nombres reales y valores placeholder no funcionales (`changeme`, `your-key-here`, `xxxxxxxx`). Nunca un valor real, ni siquiera de un entorno de prueba desechable.
- `.env` se agrega a `.gitignore` en la raíz del repo (o del servicio) antes de crear el primer archivo real con valores.
- Al agregar una variable nueva a un servicio: primero se agrega a `.env.example` con placeholder, luego se documenta su propósito en el README del servicio, y solo después se agrega el valor real al `.env` local (nunca al revés).
- Ningún script de setup ni migración imprime el valor de una variable de entorno sensible en stdout/logs.

## 4. Plan de rotación si un secreto se expone

Si se detecta o sospecha que un secreto quedó expuesto (commit, log, captura, video, mensaje, historial de shell compartido):

1. **Contener** — detener inmediatamente cualquier push, deploy o compartición en curso que involucre el artefacto expuesto.
2. **Revocar** — invalidar/rotar el secreto en el proveedor de origen (regenerar API key, rotar token, cambiar credencial de base de datos) antes de cualquier otro paso. Un secreto expuesto se asume comprometido de inmediato, sin esperar confirmación de uso indebido.
3. **Reemplazar** — actualizar el valor en el password manager y en los `.env` locales que lo consuman; nunca reutilizar el valor anterior.
4. **Purgar del repo** — si el secreto llegó a un commit (working tree o historial), eliminarlo del working tree y, si ya fue confirmado en historial, reescribir el historial afectado (p. ej. `git filter-repo` o equivalente) antes de cualquier push posterior; si ya fue empujado a un remoto compartido, coordinar con el propietario del remoto antes de forzar cambios de historial.
5. **Registrar** — documentar el incidente en el registro de riesgos operativo (`plan.md` §13, patrón `RK-009`): trigger, secreto afectado (por nombre de variable, no por valor), acción tomada, fecha/hora.
6. **Verificar** — correr el scanner de secretos (ver §5) sobre el estado final del repo para confirmar cero hallazgos antes de reanudar trabajo normal.

Ningún paso de este plan requiere copiar el valor real del secreto a un documento, ticket o mensaje; toda referencia se hace por nombre de variable o por huella (hash truncado) si es estrictamente necesario para trazabilidad.

## 5. Scanner en pre-commit y CI

- Se usa un scanner de secretos basado en reglas (p. ej. gitleaks, ver `.gitleaks.toml` en la raíz del repo) configurado con las reglas por defecto del scanner más una allowlist mínima para placeholders conocidos (`.env.example`, patrones tipo `changeme`/`your-key-here`).
- **Pre-commit:** el scanner corre como hook local antes de cada commit; un hallazgo bloquea el commit hasta que se remueva el secreto o se confirme que es un falso positivo evaluado explícitamente (nunca silenciado por defecto).
- **CI:** el mismo scanner corre en el pipeline de integración continua sobre el diff del pull request y, periódicamente, sobre el historial completo; un hallazgo bloquea el merge.
- El scanner nunca se desactiva para "hacer pasar" un check (regla general de `spec.md` §11.2: no desactivar checks de seguridad).
- Cualquier ajuste a la allowlist del scanner requiere justificar por qué el patrón es un falso positivo genuino (placeholder, no secreto real) y no una excepción de conveniencia.

## 6. Qué nunca ocurre

- Secretos en código fuente, fixtures, tests, seeds o datos de demo.
- Secretos en nombres de archivo, nombres de rama o mensajes de commit.
- Secretos visibles en capturas de pantalla o grabaciones de video (incluye notificaciones del sistema, terminales abiertas, gestores de contraseñas en pantalla).
- Reutilización del mismo secreto entre entorno de desarrollo y cualquier entorno del reto una vez detectada una exposición.
