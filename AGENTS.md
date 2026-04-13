# Codex Instructions

## Purpose

Use this file to avoid re-discovering the project structure on every task.

## Start Here

- app entrypoint: `src/album_ranker/main.py`
- FastAPI route wiring: `src/album_ranker/app.py`
- HTML, CSS, and client-side JS: `src/album_ranker/ui.py`
- database schema and CRUD: `src/album_ranker/db.py`
- import logic and source parsing: `src/album_ranker/importer.py`
- models/schemas: `src/album_ranker/schemas.py`
- configuration: `src/album_ranker/settings.py`

## High-Value Repo Facts

- This is a server-rendered FastAPI app, not a React app.
- Most UI behavior is implemented as inline JavaScript inside `ui.py`.
- The database is SQLite and is initialized/migrated in `Database.initialize()` in `db.py`.
- The app commonly runs from a non-editable install in `.venv`, so code changes often require:
  ```bash
  source .venv/bin/activate
  python -m pip install .
  ```
- Daily DB backup command: `album-ranker-backup`
- Daily backup `launchd` template: `launchd/com.darkcreation.album-ranker-backup.plist`
- Generated code under `build/lib/album_ranker/` should not be edited.

## Current Page Model

- `/albums`
  album grid, filters, manual album create
- `/artists`
  artist index only
- `/artists/{id}`
  dedicated artist page, artist-scoped album import
- `/albums/{id}`
  album details page
- `/lists`
  list index and list creation
- `/lists/{id}`
  list detail page, add/remove/reorder items, rename list
- `/genres`
  manual genre management page
- `/settings`
  model/runtime settings

## User Expectations Established In This Repo

- Dark theme everywhere.
- Shared index pages should not expose detail-page-only tools.
- Tool panels should usually be collapsed by default when data already exists.
- Album import belongs on the dedicated artist page, not the shared artists page or albums page.
- Genre filter values are manually curated from `/genres`, not inferred from album data.
- Genre matching on the albums page is substring-based.
- List item removal should remove the album from the list only, not from the library.
- Imported album metadata notes should display on separate lines on the album details page.

## Test Workflow

Run:

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
pytest
```

Important tests:

- `tests/test_api.py`
  end-to-end UI/API behavior and regressions
- `tests/test_db.py`
  persistence logic
- `tests/test_importer.py`
  metadata extraction/import behavior

## When Editing

- Prefer changing `ui.py` and `app.py` together for routed UI behavior.
- For new persisted concepts, update all of:
  - `schemas.py`
  - `db.py`
  - `app.py`
  - `ui.py`
  - tests
- If a UI feature appears correct in code but not in the browser, the installed package is probably stale.

## Fast Investigation Checklist

1. Identify the page route in `app.py`.
2. Open the corresponding renderer in `ui.py`.
3. If data is missing, inspect the record shape in `schemas.py`.
4. Then inspect the DB query/CRUD path in `db.py`.
5. Finish by updating or adding a regression in `tests/test_api.py`.
