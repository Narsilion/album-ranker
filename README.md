# Album Ranker

Local-first FastAPI + SQLite web app for collecting albums, browsing artists, opening album detail pages, and building ranked album lists.

## What It Does

- stores artists, albums, tracks, ranking lists, and manually managed genres in SQLite
- renders a dark-theme web UI from server-side HTML
- supports manual create/edit/delete flows
- supports optional AI-assisted import with review before save
- downloads cover images into local app storage
- runs fully on the local machine

## Main Pages

- `/albums`
  visual album grid with manual genre/year/artist filtering
- `/artists`
  artist index only
- `/artists/{id}`
  dedicated artist page with album grid and artist-scoped album import
- `/albums/{id}`
  album details, tracklist, metadata editing
- `/lists`
  list index and list creation
- `/lists/{id}`
  dedicated ranking page with add/remove/reorder actions
- `/genres`
  manually curated genre filter list
- `/settings`
  model selection and runtime info

## Tech Stack

- Python 3.11+
- FastAPI
- SQLite
- Pydantic v2
- Uvicorn
- plain HTML/CSS/JavaScript rendered from `src/album_ranker/ui.py`

## Project Layout

```text
src/album_ranker/
  app.py          FastAPI routes and app wiring
  db.py           SQLite schema and persistence layer
  importer.py     AI import flow, metadata extraction, cover inference
  openai_client.py
  schemas.py      Pydantic models
  settings.py     env/config loading
  ui.py           all page rendering and client-side JS
  main.py         CLI entrypoint

tests/
  test_api.py
  test_db.py
  test_importer.py
  conftest.py
```

Important:

- edit files under `src/album_ranker/`
- ignore `build/lib/album_ranker/`; it is generated output
- app data lives under `.data/` by default

## Local Setup

This repo is normally run from the existing local `.venv`.

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
```

Only create a new virtual environment when setting up a fresh checkout or intentionally rebuilding the environment.

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Run

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
album-ranker
```

Default URL:

```text
http://127.0.0.1:8780
```

## Spotlight Launcher

Install the persistent macOS service and Spotlight launcher once:

```bash
scripts/install_album_ranker_service.sh
scripts/install_spotlight_launcher.sh
```

The service runs from `~/Library/Application Support/Album Ranker` so macOS does not block its access to a repository under `Documents`. On first install, the script copies the existing database and covers into that runtime directory. Launchd starts it at login and restarts it after an unexpected exit.

After that, press Spotlight, type `Album Ranker`, and press Enter. The launcher ensures the service is running and opens `http://127.0.0.1:8780`.

Logs are written under `~/Library/Logs/Album Ranker`. Server logs rotate at 5 MB with three retained backups.

## Deploy and Restart After Code Changes

Deploy current source and restart the persistent service:

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
scripts/restart_album_ranker.sh
```

Use `scripts/install_album_ranker_service.sh` only for the initial service
installation or when its launchd configuration changes.

## Configuration

Environment variables:

- `OPENAI_API_KEY`
  optional, only needed for real AI-assisted import
- `ALBUM_RANKER_MODEL`
  default: `gpt-5.6-terra`
- `ALBUM_RANKER_HOST`
  default: `127.0.0.1`
- `ALBUM_RANKER_PORT`
  default: `8780`
- `ALBUM_RANKER_DB_PATH`
  default: `./.data/album-ranker.db`

## Tests

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
pytest
```

## Daily Backup

The repo includes a backup command and a macOS `launchd` job definition.

### Manual backup

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
album-ranker-backup
```

By default this writes to `.data/backups/` inside the project.

### Backup to iCloud Drive

Pass `--backup-dir` to write directly into iCloud:

```bash
album-ranker-backup \
  --backup-dir "$HOME/Library/Mobile Documents/com~apple~CloudDocs/album-ranker-backups" \
  --retention-days 30
```

Backups are dated SQLite files, e.g. `album-ranker-2026-04-13.db`.  
iCloud syncs them automatically — open them in any SQLite viewer on any signed-in device.

### Scheduled backup (launchd)

The service installer also registers a backup job that runs daily at 03:00 and writes to iCloud:

```text
scripts/install_album_ranker_service.sh
```

**Install or update both jobs:**

```bash
scripts/install_album_ranker_service.sh
```

**Check status:**

```bash
launchctl print gui/$(id -u)/com.darkcreation.album-ranker-backup
```

**View the log** (stdout + stderr go to the same file):

```bash
tail -50 "$HOME/Library/Logs/Album Ranker/backup.log"
```

**Run the job immediately** (without waiting for 03:00):

```bash
launchctl kickstart -k gui/$(id -u)/com.darkcreation.album-ranker-backup
```

**Unload the job** (stops scheduling):

```bash
launchctl bootout gui/$(id -u)/com.darkcreation.album-ranker-backup
```

**Change the backup directory or retention** — edit the plist `ProgramArguments`, then reload:

```bash
launchctl bootout gui/$(id -u)/com.darkcreation.album-ranker-backup
# edit ~/Library/LaunchAgents/com.darkcreation.album-ranker-backup.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.darkcreation.album-ranker-backup.plist
```

### Backup files location

| Location | Path |
|---|---|
| Default local | `~/Library/Application Support/Album Ranker/Data/backups/album-ranker-YYYY-MM-DD.db` |
| iCloud (plist default) | `~/Library/Mobile Documents/com~apple~CloudDocs/album-ranker-backups/` |
| Log | `~/Library/Logs/Album Ranker/backup.log` |

Each backup is a complete, standalone SQLite file — open it directly with any SQLite browser to inspect or restore data.

## Current Implementation Notes

- album import is scoped to the dedicated artist page, not the shared artists index
- genres shown in the album filter are managed only from `/genres`
- genre filtering is substring-based, not exact-match
- album descriptions on the details page prefer album notes and render imported metadata on separate lines
- ranking lists have dedicated detail pages; add/remove/reorder actions happen there
