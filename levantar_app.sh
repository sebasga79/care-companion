#!/usr/bin/env bash
#
# Launcher único de Care Companion.
#
# El modo predeterminado usa Docker Compose. La primera ejecución construye
# las imágenes; las siguientes inician lo ya creado sin reinstalar.
# `--local` conserva el modo de desarrollo con Uvicorn/Next.js y hot reload.
#
# Puertos deliberadamente altos e inusuales para no chocar con otros
# proyectos locales. Overridables: API_PORT=... WEB_PORT=... ./levantar_app.sh
#
# Uso:
#   ./levantar_app.sh                 # primera vez construye; después solo inicia
#   ./levantar_app.sh --rebuild       # reconstruye tras cambios de código
#   ./levantar_app.sh --stop          # detiene Docker sin borrar datos
#   ./levantar_app.sh --logs          # sigue los logs de Docker
#   ./levantar_app.sh --no-open       # no abre el navegador
#   ./levantar_app.sh --local         # desarrollo sin Docker
#   ./levantar_app.sh --local --reinstall
#   ./levantar_app.sh --local --clean

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

MODE="docker"
ACTION="up"
REBUILD=false
NO_OPEN=false
REINSTALL=false
CLEAN_DB=false

usage() {
  printf '%s\n' \
    "Uso: ./levantar_app.sh [opción]" \
    "" \
    "Sin opciones       Primera vez construye Docker; después solo inicia." \
    "--rebuild          Reconstruye tras cambios de código." \
    "--stop             Detiene Docker sin borrar imágenes ni datos." \
    "--logs             Sigue los logs de Docker." \
    "--no-open          No abre el navegador." \
    "--clean            Borra el volumen Docker (base, dataset e índice) y reconstruye." \
    "--local            Desarrollo sin Docker y con hot reload." \
    "--local --reinstall  Reinstala dependencias locales." \
    "--local --clean      Borra la base local antes de arrancar."
}

for arg in "$@"; do
  case "$arg" in
    --local)       MODE="local" ;;
    --rebuild)     REBUILD=true ;;
    --stop)        ACTION="stop" ;;
    --logs)        ACTION="logs" ;;
    --no-open)     NO_OPEN=true ;;
    --reinstall) REINSTALL=true ;;
    --clean)     CLEAN_DB=true ;;
    -h|--help)   usage; exit 0 ;;
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

open_browser() {
  [ "$NO_OPEN" = true ] && return 0
  case "$(uname -s)" in
    Darwin) open "${WEB_URL}/call" >/dev/null 2>&1 || true ;;
    Linux) command -v xdg-open >/dev/null 2>&1 \
      && xdg-open "${WEB_URL}/call" >/dev/null 2>&1 || true ;;
  esac
}

wait_for_stack() {
  local timeout_seconds="${STARTUP_TIMEOUT_SECONDS:-900}"
  log "Esperando a que API y frontend estén listos…"
  for attempt in $(seq 1 "$timeout_seconds"); do
    if curl -fsS "${API_URL}/health" >/dev/null 2>&1 \
      && curl -fsS "${WEB_URL}/call" >/dev/null 2>&1; then
      log "Aplicación lista."
      return 0
    fi
    if [ $((attempt % 15)) -eq 0 ]; then
      echo "  Primera preparación o arranque en curso (${attempt}s); dataset y corpus se guardan una sola vez…"
    fi
    sleep 1
  done
  err "La aplicación no respondió a tiempo. Ejecuta ./levantar_app.sh --logs."
  docker compose logs --tail=40 api >&2 || true
  return 1
}

run_docker_launcher() {
  # Si Docker o el modo local ya sirven una instancia sana, no reinstala ni
  # reinicia nada: muestra las URLs y abre el navegador.
  if [ "$ACTION" = "up" ] \
    && [ "$REBUILD" = false ] \
    && [ "$REINSTALL" = false ] \
    && [ "$CLEAN_DB" = false ] \
    && curl -fsS "${API_URL}/health" >/dev/null 2>&1 \
    && curl -fsS "${WEB_URL}/call" >/dev/null 2>&1; then
    log "Care Companion ya está en ejecución."
    echo "  Frontend: ${WEB_URL}/call"
    echo "  API/docs: ${API_URL}/docs"
    open_browser
    return 0
  fi

  require docker "Instala Docker Desktop y vuelve a ejecutar este comando."
  if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose no está disponible. Actualiza Docker Desktop."
    return 1
  fi

  if ! docker info >/dev/null 2>&1; then
    if [ "$(uname -s)" = "Darwin" ] && open -Ra Docker >/dev/null 2>&1; then
      log "Iniciando Docker Desktop…"
      open -a Docker
      for attempt in $(seq 1 45); do
        docker info >/dev/null 2>&1 && break
        sleep 1
      done
    fi
  fi
  if ! docker info >/dev/null 2>&1; then
    err "Docker está instalado, pero el motor no está activo. Inicia Docker Desktop."
    return 1
  fi

  case "$ACTION" in
    stop)
      log "Deteniendo Care Companion…"
      docker compose stop
      log "Servicios detenidos; imágenes y datos se conservan."
      return 0
      ;;
    logs)
      docker compose logs -f
      return 0
      ;;
  esac

  if [ "$CLEAN_DB" = true ]; then
    warn "--clean eliminará base, dataset e índice persistidos; el kit se descargará de nuevo."
    docker compose down --volumes
    REBUILD=true
  fi

  if [ "$REBUILD" = true ] || [ "$REINSTALL" = true ]; then
    log "Reconstruyendo imágenes y recreando servicios…"
    docker compose up -d --build --force-recreate
  else
    local running_count existing_count image_count
    running_count=$(docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
    existing_count=$(docker compose ps -a -q 2>/dev/null | wc -l | tr -d ' ')
    image_count=$(docker compose images -q 2>/dev/null | sort -u | sed '/^$/d' | wc -l | tr -d ' ')

    if [ "$running_count" -ge 2 ]; then
      log "Los servicios Docker ya están activos."
    elif [ "$existing_count" -ge 2 ]; then
      log "Iniciando contenedores existentes, sin reinstalar…"
      docker compose start
    elif [ "$image_count" -ge 2 ]; then
      log "Creando contenedores desde imágenes existentes, sin reconstruir…"
      docker compose up -d --no-build
    else
      log "Primera ejecución: construyendo imágenes e instalando dependencias…"
      docker compose up -d --build
    fi
  fi

  wait_for_stack
  echo
  echo "  Care Companion está arriba"
  echo "  Frontend: ${WEB_URL}/call"
  echo "  API/docs: ${API_URL}/docs"
  echo "  Detener  : ./levantar_app.sh --stop"
  echo "  Logs     : ./levantar_app.sh --logs"
  open_browser
}

if [ "$MODE" = "docker" ]; then
  run_docker_launcher
  exit $?
fi

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
  # En desarrollo, recargar el backend cuando cambia Python. Sin `--reload`,
  # el frontend sí reflejaba sus cambios en caliente pero la API conservaba
  # el código cargado al arrancar, produciendo transcripciones de una versión
  # anterior durante la validación manual.
  exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$API_PORT"
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
