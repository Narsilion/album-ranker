#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR:h}"
RUNTIME_ROOT="${HOME}/Library/Application Support/Album Ranker"
RUNTIME_APP="${RUNTIME_ROOT}/app"
RUNTIME_DATA="${RUNTIME_ROOT}/Data"
RUNTIME_VENV="${RUNTIME_ROOT}/venv"
PYTHON_BIN="/usr/local/bin/python3"
LOG_DIR="${HOME}/Library/Logs/Album Ranker"
AGENT_DIR="${HOME}/Library/LaunchAgents"
SERVICE_LABEL="com.darkcreation.album-ranker"
BACKUP_LABEL="com.darkcreation.album-ranker-backup"
SERVICE_PLIST="${AGENT_DIR}/${SERVICE_LABEL}.plist"
BACKUP_PLIST="${AGENT_DIR}/${BACKUP_LABEL}.plist"
DOMAIN="gui/$(id -u)"

mkdir -p "${RUNTIME_ROOT}" "${RUNTIME_APP}" "${RUNTIME_DATA}" "${LOG_DIR}" "${AGENT_DIR}"

if [[ ! -x "${RUNTIME_VENV}/bin/python" ]] || \
   ! env PYTHONPATH= "${RUNTIME_VENV}/bin/python" -c "import fastapi, pydantic, uvicorn" 2>/dev/null; then
  if [[ -e "${RUNTIME_VENV}" ]]; then
    mv "${RUNTIME_VENV}" "${RUNTIME_ROOT}/venv.incomplete.$(date +%Y%m%d%H%M%S)"
  fi
  "${PYTHON_BIN}" -m venv "${RUNTIME_VENV}"
  "${RUNTIME_VENV}/bin/python" -m pip install --no-cache-dir "${PROJECT_DIR}"
fi

/usr/bin/ditto "${PROJECT_DIR}/src/album_ranker" "${RUNTIME_APP}/album_ranker"
/usr/bin/ditto "${PROJECT_DIR}/scripts/album_ranker_service_runner.py" "${RUNTIME_ROOT}/service_runner.py"

# Migrate the existing library on first install only. Later deployments never
# overwrite the live runtime database or its cover files.
if [[ ! -f "${RUNTIME_DATA}/album-ranker.db" ]]; then
  /usr/bin/ditto "${PROJECT_DIR}/.data/album-ranker.db" "${RUNTIME_DATA}/album-ranker.db"
  if [[ -d "${PROJECT_DIR}/.data/covers" ]]; then
    /usr/bin/ditto "${PROJECT_DIR}/.data/covers" "${RUNTIME_DATA}/covers"
  fi
fi

render_plist() {
  local template="$1"
  local destination="$2"
  /usr/bin/sed \
    -e "s|__RUNTIME_ROOT__|${RUNTIME_ROOT}|g" \
    -e "s|__LOG_DIR__|${LOG_DIR}|g" \
    -e "s|__BACKUP_DIR__|${HOME}/Library/Mobile Documents/com~apple~CloudDocs/album-ranker-backups|g" \
    "${template}" > "${destination}"
  /usr/bin/plutil -lint "${destination}" >/dev/null
}

render_plist "${PROJECT_DIR}/launchd/com.darkcreation.album-ranker.plist.template" "${SERVICE_PLIST}"
render_plist "${PROJECT_DIR}/launchd/com.darkcreation.album-ranker-backup.plist.template" "${BACKUP_PLIST}"

launchctl bootout "${DOMAIN}/${SERVICE_LABEL}" 2>/dev/null || true
launchctl bootout "${DOMAIN}/${BACKUP_LABEL}" 2>/dev/null || true
sleep 1

bootstrap_agent() {
  local plist="$1"
  local attempt
  for attempt in 1 2 3; do
    if launchctl bootstrap "${DOMAIN}" "${plist}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

bootstrap_agent "${SERVICE_PLIST}"
bootstrap_agent "${BACKUP_PLIST}"
launchctl kickstart -k "${DOMAIN}/${SERVICE_LABEL}"

echo "Installed ${SERVICE_LABEL}"
echo "Runtime: ${RUNTIME_ROOT}"
echo "Logs: ${LOG_DIR}"
