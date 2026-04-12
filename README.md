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

## Setup

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

## Reinstall After Code Changes

This repo is often run from a non-editable install in the local `.venv`. If a UI or backend change does not appear in the running app, reinstall the package:

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
python -m pip install .
album-ranker
```

## Configuration

Environment variables:

- `OPENAI_API_KEY`
  optional, only needed for real AI-assisted import
- `ALBUM_RANKER_MODEL`
  default: `gpt-5`
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

## Current Implementation Notes

- album import is scoped to the dedicated artist page, not the shared artists index
- genres shown in the album filter are managed only from `/genres`
- genre filtering is substring-based, not exact-match
- album descriptions on the details page prefer album notes and render imported metadata on separate lines
- ranking lists have dedicated detail pages; add/remove/reorder actions happen there
