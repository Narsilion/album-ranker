#!/bin/zsh

set -e

APP_URL="http://127.0.0.1:8780"
HEALTH_URL="${APP_URL}/api/health"
SERVICE_LABEL="com.darkcreation.album-ranker"
DOMAIN="gui/$(id -u)"
LOG_DIR="${HOME}/Library/Logs/Album Ranker"
LAUNCHER_LOG="${LOG_DIR}/launcher.log"

mkdir -p "${LOG_DIR}"
exec >> "${LAUNCHER_LOG}" 2>&1

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"Album Ranker\"" >/dev/null 2>&1 || true
}

health_ok() {
  /usr/bin/curl -fsS --max-time 2 "${HEALTH_URL}" >/dev/null
}

wait_for_health() {
  local attempt
  for attempt in {1..30}; do
    if health_ok; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

log "Launcher invoked"

if health_ok; then
  log "Server already running"
  log "Opening ${APP_URL}"
  /usr/bin/open "${APP_URL}"
  exit 0
fi

if ! launchctl print "${DOMAIN}/${SERVICE_LABEL}" >/dev/null 2>&1; then
  log "Service is not installed"
  notify "Album Ranker service is not installed. Run scripts/install_album_ranker_service.sh."
  exit 1
fi

log "Starting Album Ranker launchd service"
notify "Starting local server..."
launchctl kickstart -k "${DOMAIN}/${SERVICE_LABEL}"
if ! wait_for_health; then
  log "Server did not become healthy; see ${LOG_DIR}/server.log"
  notify "Could not start. Check ~/Library/Logs/Album Ranker/server.log."
  exit 1
fi

log "Opening ${APP_URL}"
/usr/bin/open "${APP_URL}"
