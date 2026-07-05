#!/bin/zsh

set -e

PROJECT_DIR="/Users/darkcreation/Documents/git_repos/album-ranker"
APP_DIR="${HOME}/Applications/Album Ranker.app"
LAUNCHER_SCRIPT="${PROJECT_DIR}/scripts/launch_album_ranker.sh"

mkdir -p "${HOME}/Applications"
rm -rf "${APP_DIR}"

chmod +x "${LAUNCHER_SCRIPT}"
/usr/bin/osacompile -o "${APP_DIR}" -e "do shell script quoted form of \"${LAUNCHER_SCRIPT}\""

echo "Installed ${APP_DIR}"
echo "Open it from Spotlight by searching for: Album Ranker"
