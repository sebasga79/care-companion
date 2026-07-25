#!/usr/bin/env bash
#
# Care Companion — arranque de todo el stack en local.
#
#   Backend  : FastAPI (uvicorn)      → http://localhost:49317  (/docs, /health)
#   Frontend : Next.js (dev server)   → http://localhost:49318  (redirige a /call)
#   Base de  : SQLite (WAL) — sin servidor; el schema se aplica solo al
#   datos      arrancar el backend (create_app → apply_schema).
#
# Puertos deliberadamente altos e inusuales para no chocar con otros
# proyectos locales. Overridables: API_PORT=... WEB_PORT=... ./levantar_app.sh
#
# Uso:
#   ./levantar_app.sh                 # instala deps la primera vez y levanta todo
#   ./levantar_app.sh --reinstall     # fuerza reinstalar dependencias
#   ./levantar_app.sh --clean         # borra la base de datos local antes de arrancar
#
# Ctrl+C detiene backend y frontend de forma limpia.

set -euo pipefail

# --- Configuración -----------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT_DIR/api"
WEB_DIR="$ROOT_DIR/web"
LOG_DIR="$ROOT_DIR/.run/logs"

API_PORT="${API_PORT:-49317}"
WEB_PORT="${WEB_PORT:-49318}"
API_URL="http://localhost:${API_PORT}"
WEB_URL="http://localhost:${WEB_PORT}"

REINSTALL=false
CLEAN_DB=false
for arg in "$@"; do
  case "$arg" in
    --reinstall) REINSTALL=true ;;
    --clean)     CLEAN_DB=true ;;
    -h|--help)   grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Argumento desconocido: $arg (usa --help)"; exit 2 ;;
  esac
done

# --- Colores -----------------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi
log()  { echo "${GREEN}${BOLD}==>${RESET} $*"; }
warn() { echo "${YELLOW}${BOLD}warn:${RESET} $*"; }
err()  { echo "${RED}${BOLD}error:${RESET} $*" >&2; }

# --- Prerrequisitos ----------------------------------------------------------
require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Falta '$1'. $2"
    exit 1
  fi
}
log "Verificando prerrequisitos…"
require uv   "Instala uv: https://docs.astral.sh/uv/getting-started/installation/"
require node "Instala Node 20+ : https://nodejs.org/"
require pnpm "Instala pnpm: https://pnpm.io/installation (o 'corepack enable')"

# --- Limpieza / procesos hijos ----------------------------------------------
API_PID=""
WEB_PID=""
TAIL_PID=""
CLEANED=false

# Mata un PID y todos sus descendientes (Next.js deja un `next-server` hijo
# que sobrevive si solo se mata el `pnpm`).
kill_tree() {
  local pid="$1"
  [ -z "$pid" ] && return 0
  # Descendientes primero (pgrep -P por nivel; suficiente para nuestro árbol).
  local children
  children=$(pgrep -P "$pid" 2>/dev/null || true)
  for c in $children; do kill_tree "$c"; done
  kill "$pid" 2>/dev/null || true
}

# Red de seguridad: libera un puerto matando a quien lo escuche. Escala a
# SIGKILL si el proceso no cede con SIGTERM (Next deja un `next-server` lento).
kill_port() {
  local port="$1" pids
  command -v lsof >/dev/null 2>&1 || return 0
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  [ -z "$pids" ] && return 0
  kill $pids 2>/dev/null || true
  sleep 1
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
}

cleanup() {
  # El trap EXIT + INT/TERM puede dispararse dos veces; ejecutar una sola vez.
  [ "$CLEANED" = true ] && return 0
  CLEANED=true
  echo
  log "Deteniendo servicios…"
  [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null || true
  kill_tree "$WEB_PID"
  kill_tree "$API_PID"
  sleep 1
  # Por si algún hijo quedó huérfano, liberar los puertos explícitamente.
  kill_port "$WEB_PORT"
  kill_port "$API_PORT"
  wait 2>/dev/null || true
  log "Listo. Hasta luego."
}
trap cleanup INT TERM EXIT

# Si algún puerto está ocupado, avisar claramente en vez de fallar opaco.
port_busy() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}
for p in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$p"; then
    err "El puerto $p ya está en uso. Cierra el proceso que lo ocupa o exporta API_PORT/WEB_PORT."
    exit 1
  fi
done

mkdir -p "$LOG_DIR"

# --- Base de datos (SQLite, sin servidor) -----------------------------------
mkdir -p "$API_DIR/data"
if [ "$CLEAN_DB" = true ]; then
  warn "Borrando base de datos local (--clean)…"
  rm -f "$API_DIR/data/"*.db "$API_DIR/data/"*.db-wal "$API_DIR/data/"*.db-shm 2>/dev/null || true
fi

# --- Dependencias ------------------------------------------------------------
log "Instalando dependencias del backend (uv)…"
if [ "$REINSTALL" = true ] || [ ! -d "$API_DIR/.venv" ]; then
  ( cd "$API_DIR" && uv sync )
else
  echo "${DIM}   .venv ya existe; usa --reinstall para forzar.${RESET}"
fi

log "Instalando dependencias del frontend (pnpm)…"
if [ "$REINSTALL" = true ] || [ ! -d "$WEB_DIR/node_modules" ]; then
  ( cd "$WEB_DIR" && pnpm install )
else
  echo "${DIM}   node_modules ya existe; usa --reinstall para forzar.${RESET}"
fi

# --- Backend -----------------------------------------------------------------
log "Arrancando backend en ${API_URL} …"
(
  cd "$API_DIR"
  exec uv run uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT"
) >"$LOG_DIR/api.log" 2>&1 &
API_PID=$!

# Esperar a que /health responda (máx ~30 s).
log "Esperando a que el backend esté listo…"
for i in $(seq 1 30); do
  if curl -fsS "${API_URL}/health" >/dev/null 2>&1; then
    log "Backend listo (${API_URL}/health)."
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    err "El backend murió al arrancar. Últimas líneas de $LOG_DIR/api.log:"
    tail -n 20 "$LOG_DIR/api.log" >&2 || true
    exit 1
  fi
  sleep 1
  [ "$i" = 30 ] && { err "Timeout esperando el backend. Ver $LOG_DIR/api.log"; exit 1; }
done

# --- Frontend ----------------------------------------------------------------
log "Arrancando frontend en ${WEB_URL} …"
(
  cd "$WEB_DIR"
  export NEXT_PUBLIC_API_URL="$API_URL"
  exec pnpm dev --port "$WEB_PORT"
) >"$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!

# Esperar a que el frontend responda (máx ~40 s; Next tarda en compilar).
log "Esperando a que el frontend compile…"
for i in $(seq 1 40); do
  if curl -fsS "${WEB_URL}" >/dev/null 2>&1; then
    log "Frontend listo."
    break
  fi
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    err "El frontend murió al arrancar. Últimas líneas de $LOG_DIR/web.log:"
    tail -n 20 "$LOG_DIR/web.log" >&2 || true
    exit 1
  fi
  sleep 1
done

# --- Resumen -----------------------------------------------------------------
echo
echo "${GREEN}${BOLD}  Care Companion está arriba${RESET}"
echo "  ${BOLD}Frontend:${RESET} ${WEB_URL}      ${DIM}(vista /call)${RESET}"
echo "  ${BOLD}API/docs:${RESET} ${API_URL}/docs"
echo "  ${BOLD}Health  :${RESET} ${API_URL}/health"
echo "  ${DIM}Logs: $LOG_DIR/{api,web}.log${RESET}"
echo "  ${DIM}Base de datos: $API_DIR/data/ (SQLite)${RESET}"
echo
echo "  ${YELLOW}Ctrl+C para detener todo.${RESET}"
echo

# Seguir los logs en vivo hasta que el usuario interrumpa.
tail -n 0 -f "$LOG_DIR/api.log" "$LOG_DIR/web.log" &
TAIL_PID=$!

# Bucle de espera sensible a señales: bash evalúa los traps (INT/TERM) entre
# comandos, así que un bucle con `sleep` reacciona a Ctrl+C de forma fiable
# (más que un `wait PID` bloqueante). Si cualquiera de los dos servicios muere
# por su cuenta, salimos y el trap limpia el otro.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done

warn "Uno de los servicios se detuvo; cerrando el resto."
