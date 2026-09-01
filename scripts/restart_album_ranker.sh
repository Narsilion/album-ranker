#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR:h}"
RUNTIME_ROOT="${HOME}/Library/Application Support/Album Ranker"
RUNTIME_APP="${RUNTIME_ROOT}/app"
SERVICE_LABEL="com.darkcreation.album-ranker"
DOMAIN="gui/$(id -u)"
HEALTH_URL="http://127.0.0.1:8780/api/health"

if ! launchctl print "${DOMAIN}/${SERVICE_LABEL}" >/dev/null 2>&1; then
  echo "Album Ranker service is not installed. Run scripts/install_album_ranker_service.sh first." >&2
  exit 1
fi

mkdir -p "${RUNTIME_APP}"
/usr/bin/ditto "${PROJECT_DIR}/src/album_ranker" "${RUNTIME_APP}/album_ranker"
/usr/bin/ditto "${PROJECT_DIR}/scripts/album_ranker_service_runner.py" "${RUNTIME_ROOT}/service_runner.py"

launchctl kickstart -k "${DOMAIN}/${SERVICE_LABEL}"

for attempt in {1..30}; do
  if /usr/bin/curl -fsS --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "Album Ranker deployed and restarted: http://127.0.0.1:8780"
    exit 0
  fi
  sleep 0.5
done

echo "Album Ranker did not become healthy. Check ~/Library/Logs/Album Ranker/server.log." >&2
exit 1
