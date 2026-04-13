# Album Ranker — Application Specification

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Data Model](#3-data-model)
4. [Pages and UI](#4-pages-and-ui)
   - 4.1 [Albums](#41-albums)
   - 4.2 [Album Detail](#42-album-detail)
   - 4.3 [Artists](#43-artists)
   - 4.4 [Artist Detail](#44-artist-detail)
   - 4.5 [Lists](#45-lists)
   - 4.6 [List Detail](#46-list-detail)
   - 4.7 [Genres](#47-genres)
   - 4.8 [Settings](#48-settings)
5. [Import Pipeline](#5-import-pipeline)
   - 5.1 [Artist Import](#51-artist-import)
   - 5.2 [Album Import](#52-album-import)
   - 5.3 [Source Adapters](#53-source-adapters)
   - 5.4 [AI Enrichment](#54-ai-enrichment)
6. [Ranking Lists](#6-ranking-lists)
   - 6.1 [Manual Lists](#61-manual-lists)
   - 6.2 [Automatic Best-Rated Lists](#62-automatic-best-rated-lists)
7. [REST API](#7-rest-api)
8. [Backup](#8-backup)
9. [Configuration](#9-configuration)
10. [Testing](#10-testing)

---

## 1. Overview

Album Ranker is a **local-first** web application for building and curating a personal music library. It runs as a single-process FastAPI server backed by a SQLite database. All data stays on the user's machine.

Core capabilities:

- Maintain a catalog of **artists** and their **albums** with metadata (year, genre, rating, duration, tracklist, cover art).
- **Import** metadata from external sources with optional AI enrichment (OpenAI).
- **Rate** albums on a 1–10 star scale.
- Build **ranked lists** of albums manually or automatically from the catalog.
- **Search and filter** the library by title, artist, genre, and year.
- **Back up** the SQLite database on a schedule.

The UI is rendered server-side as HTML f-strings (no separate frontend build step). All interactivity is plain JavaScript embedded in the rendered page.

---

## 2. Architecture

```
album-ranker/
├── src/album_ranker/
│   ├── main.py          — CLI entry point (uvicorn launcher)
│   ├── app.py           — FastAPI application factory, all routes
│   ├── db.py            — Database class, all SQL queries, schema migrations
│   ├── schemas.py       — Pydantic models (request/response/record types)
│   ├── ui.py            — HTML rendering functions (server-side templates)
│   ├── importer.py      — Metadata fetch, source adapters, AI draft creation
│   ├── openai_client.py — OpenAI structured-output wrapper
│   ├── settings.py      — Settings dataclass, environment variable resolution
│   ├── backup.py        — SQLite backup utility (CLI + library)
│   └── __init__.py
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_backup.py
│   ├── test_db.py
│   ├── test_importer.py
│   └── test_settings.py
├── pyproject.toml
└── SPEC.md
```

**Runtime stack:**

| Component | Technology |
|---|---|
| HTTP server | FastAPI + Uvicorn |
| Database | SQLite (single file) |
| HTML templates | Python f-strings in `ui.py` |
| AI enrichment | OpenAI Chat Completions (structured output / JSON schema) |
| Cover images | Downloaded and stored as local files under `.data/covers/` |
| Static files | Served by FastAPI `StaticFiles` from `.data/` |

**Default URL:** `http://127.0.0.1:8780`  
**Default DB path:** `.data/album-ranker.db` (relative to project root or `ALBUM_RANKER_DB_PATH`)

---

## 3. Data Model

### 3.1 `artists`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE | |
| `slug` | TEXT UNIQUE | URL-safe, auto-generated from name |
| `description` | TEXT | Bio / background text |
| `description_source_url` | TEXT | Where the description was sourced |
| `description_source_label` | TEXT | Human-readable label for the source |
| `external_url` | TEXT | Official site, Wikipedia, etc. |
| `origin` | TEXT | Country of origin first, e.g. "UK, London" or "USA, Nashville" |
| `created_at` | TEXT | ISO 8601 UTC |
| `updated_at` | TEXT | ISO 8601 UTC |

### 3.2 `albums`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `artist_id` | INTEGER FK → artists | CASCADE DELETE |
| `title` | TEXT | |
| `release_year` | INTEGER | 1000–9999 |
| `genre` | TEXT | |
| `rating` | INTEGER | 1–10 |
| `duration_seconds` | INTEGER | Total album length |
| `cover_image_path` | TEXT | Local filesystem path |
| `cover_source_url` | TEXT | URL the cover was fetched from |
| `album_external_url` | TEXT | Source page (Metal-Archives, Bandcamp, etc.) |
| `album_stream_url` | TEXT | Streaming link (YouTube Music, Spotify, etc.) |
| `album_type` | TEXT | Release type: Full Length, EP, Single, etc. |
| `notes` | TEXT | Album-specific description / notes |
| `artist_description` | TEXT | Carried over from import; stored but not shown on album page |
| `artist_description_source_url` | TEXT | |
| `artist_description_source_label` | TEXT | |
| `artist_origin` | TEXT | Origin carried over from artist at import time |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

### 3.3 `tracks`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `album_id` | INTEGER FK → albums | CASCADE DELETE |
| `track_number` | INTEGER | 1-based |
| `title` | TEXT | |
| `duration_seconds` | INTEGER | |
| `position` | INTEGER | Sort order (default 0) |

### 3.4 `album_lists`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT | |
| `description` | TEXT | |
| `year` | INTEGER | Optional year filter used when auto-generated |
| `genre_filter_hint` | TEXT | Optional genre filter used when auto-generated |
| `is_auto` | INTEGER | 1 = auto-generated (Best Rated wizard), 0 = manual |
| `auto_limit` | INTEGER | Max entries for auto lists |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

### 3.5 `list_items`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `list_id` | INTEGER FK → album_lists | CASCADE DELETE |
| `album_id` | INTEGER FK → albums | CASCADE DELETE |
| `rank_position` | INTEGER | 1-based rank within the list |

UNIQUE constraints: `(list_id, album_id)` and `(list_id, rank_position)`.

### 3.6 `import_jobs`

Tracks AI import drafts awaiting user confirmation.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `target_type` | TEXT | `"artist"` or `"album"` |
| `requested_artist_name` | TEXT | |
| `requested_album_title` | TEXT | |
| `requested_source_url` | TEXT | |
| `chosen_source_url` | TEXT | |
| `status` | TEXT | `"draft"` / `"confirmed"` / `"rejected"` |
| `draft_payload_json` | TEXT | JSON blob of the draft |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

### 3.7 `genres`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE | |
| `created_at` | TEXT | |
| `updated_at` | TEXT | |

### 3.8 `app_settings`

Key/value store for persisted application settings (e.g. `active_model`).

---

## 4. Pages and UI

Navigation: persistent top navbar with links to Albums, Artists, Lists, Genres, Settings.

### 4.1 Albums

**URL:** `/albums`

Displays all albums as a responsive grid of cover-art cards. Each card shows:
- Cover image
- Album title
- Artist name and release year
- Genre
- Star rating (filled stars up to the album's rating)

**Filters panel:**
- Text search — filters visible cards by title or artist name (live, client-side)
- Genre dropdown
- Year dropdown
- Artist dropdown

All filters are combined (AND logic). Filtering is purely client-side using `data-*` attributes on each card.

### 4.2 Album Detail

**URL:** `/albums/{id}`

Full-page view of a single album. Sections:

- **Cover** — click to upload a local replacement image (JPEG, PNG, WebP)
- **Star rating widget** — 10-star interactive row; click to rate; PATCH persists immediately
- **Source / Play links** — tag-style buttons for `album_external_url` and `album_stream_url`
- **Metadata sidebar** — Length, Genre, Type
- **Edit Album Metadata** button — expands an inline editor with fields: Album Name, Year, Genre, Length, Stream URL, Type, Album Description, Notes, Tracklist. Artist and Artist Origin are stored as hidden fields and not editable here.

  Tracklist textarea accepts two formats:
  - **Human-friendly (preferred):** `1. Track Name  3:45` — number with optional `.`, then title, then optional duration at end
  - **Pipe-separated (legacy / import-filled):** `1|Track Name|3:45`
- **Description section** — shows `album.notes` only (labelled "Album Description"); "No description yet." if empty
- **Tracklist** — numbered rows with title and duration
- **Back to Artist** link

The inline editor has Save and Cancel buttons. Cancel closes without saving.

### 4.3 Artists

**URL:** `/artists`

Lists all artists as cards. Each card has Edit and Delete buttons.

- **Artist Tools panel** (collapsed by default when artists exist) — contains:
  - **Artist Import** form: Source URL input (with × clear button) → "Populate With AI" → review/confirm draft
  - **Manual Artist** form: Name, Origin, Description, Artist Page URL
- **Search Artists** — text input above the library list; filters cards by name (live, client-side)

### 4.4 Artist Detail

**URL:** `/artists/{id}`

Shows the artist bio, origin, and all their albums as a grid.

- **Artist Overview** panel — description text (clamp/expand), origin, source link
- **Album panel** — two tabs:
  - **Import from URL** — Source URL input (with × clear button) → "Populate With AI" → pre-filled confirm form
  - **Manual** — direct entry form: Album Name, Year, Genre, Length, Type, Cover Source URL, Album External URL, Album Description, Tracklist; submits directly to `POST /api/albums`
- Album grid — same card format as the Albums page

### 4.5 Lists

**URL:** `/lists`

Shows all ranked lists. Each list is a collapsible block:
- List header: name, year/genre hint, **AUTO** badge (if `is_auto = 1`), expand/collapse chevron
- List body: ranked items with cover thumbnail, title, artist, year, star rating, and Up/Down/Remove controls
- Footer: Save order, Regenerate (auto lists only), Delete List

**Search** — text input above the lists grid; filters visible list blocks by name (live, client-side).

**Create List panel** with two tabs:
- **Manual** — Name, Description, Year, Genre fields
- **⭐ Best Rated** — Name, Year filter, Genre filter, Limit fields; creates an auto-generated sorted list

After clicking Regenerate, the page reloads with the regenerated list scrolled into view and expanded.

### 4.6 List Detail

**URL:** `/lists/{id}`

Standalone page for a single list. Shows the ranked album list and an "Add album" selector. Includes a Back to Lists link.

### 4.7 Genres

**URL:** `/genres`

CRUD table for genres. Genres are used as a freeform tag on albums and as a filter on lists and the albums page.

### 4.8 Settings

**URL:** `/settings`

- AI model selector (persisted to `app_settings`)
- AI status indicator (ready / key missing / last request failed)
- Last import diagnostics (expandable JSON)
- OpenAI API key configuration status

---

## 5. Import Pipeline

The import pipeline fetches metadata from an external URL, optionally enriches it with AI, and stores a draft for the user to review and confirm.

### 5.1 Artist Import

1. User submits a Source URL on the Artists page or Artist Detail page.
2. `POST /api/import/artist` is called with `{ source_url, artist_name }`.
3. `MetadataImporter.create_artist_draft()` fetches the page and builds an `ArtistDraftData`.
4. If OpenAI is configured, the AI fills in `artist_name`, `description`, `origin`, `external_url`, `description_source_url`, `description_source_label`.
5. A draft `import_job` row is created (status = `"draft"`).
6. The UI shows a pre-filled confirmation form.
7. User edits if needed and submits `POST /api/import/{draft_id}/confirm`.
8. The artist is created or updated; the draft status is set to `"confirmed"`.

### 5.2 Album Import

Same flow as artist import but targets `POST /api/import/album`. The confirmation form includes all album fields (title, year, genre, tracklist, cover, notes, stream URL). On confirm the album (and artist if new) is created.

Cover images are automatically downloaded from `cover_source_url` and stored locally.

### 5.3 Source Adapters

`importer.py` routes URLs to specialised parsers before falling back to AI:

| Source | Adapter | What is extracted |
|---|---|---|
| `www.encyclopaedia-metallum.com` | `_metal_archives_album_draft` | Title, artist, year, tracklist with durations, cover, **release type → `album_type`**, label/format/catalog-id → `notes`; `artist_description` is not set (og:description is redundant noise) |
| `*.bandcamp.com` | `_bandcamp_album_draft` | ld+json `MusicAlbum` schema: title, artist, tracklist (ISO 8601 durations), cover, release date |
| `*.wikipedia.org` | `_wikipedia_album_draft` | Infobox: title, artist, release year, genre, total length; tracklist table |
| `music.youtube.com` | `_youtube_music_album_draft` | Title, artist, release year from `initialData` subtitle; tracklist from `www.youtube.com/playlist` `ytInitialData`; cover from `og:image` |
| `facebook.com` | _(fallback + FB UA)_ | Fetched with `facebookexternalhit/1.1` UA to bypass blocking; og:title + og:description passed to AI |
| Any other URL | _(generic fallback)_ | `og:title`, `og:description`, `og:image` |

**YouTube Music specifics:**

- The music.youtube.com page is fetched with `Accept-Language: en-US` for English metadata.
- `initialData.push()` payloads are hex-decoded; the `subtitle.runs` field yields `["Album", " • ", "2026"]` (release year).
- Tracklist is fetched from `https://www.youtube.com/playlist?list={id}` (full page, no truncation) and parsed from the `ytInitialData` JSON blob embedded in the page source.
- Track duration format is `M.SS` (dot separator, e.g. `4.10` = 4 min 10 sec); handled by `_parse_yt_duration()`.
- Total album duration is computed by summing individual track durations.
- Cover images from `lh3.googleusercontent.com` and `*.ytimg.com` are accepted even without a file extension.

### 5.4 AI Enrichment

When `OPENAI_API_KEY` is set, `OpenAIClient.generate_json()` is called with a strict JSON schema. The model is selected from `app_settings.active_model`.

The prompt includes:
- Page title and description from og/meta tags
- Stripped page text excerpt (up to 4 000 chars)
- Host label

AI output is merged with data from the source adapter; adapter data takes precedence for structured fields (tracklist, year, cover URL, `album_type`, `notes`). Specifically:
- `album_type`: fallback (adapter) value always wins over AI
- `notes`: fallback structured notes win if present; AI fills in only when the adapter produced nothing
- All other fields: first non-null value between AI and fallback is used

---

## 6. Ranking Lists

### 6.1 Manual Lists

- Created from the Lists page, Manual tab.
- User provides name, optional description, optional year and genre hints.
- Albums are added one at a time from a selector on the List Detail page.
- Items can be reordered with Up/Down buttons; order is saved with the Save button.
- Individual items can be removed with the − button.

### 6.2 Automatic Best-Rated Lists

- Created from the Lists page, ⭐ Best Rated tab.
- Parameters: name, year filter (optional), genre filter (optional), limit (number of albums).
- The list is populated by querying albums ordered by rating descending, filtered by year and genre.
- Marked with `is_auto = 1`; shown with an **AUTO** pill badge.
- **Regenerate** re-runs the query with the same stored parameters, replacing all items. After regeneration the page reloads with the list expanded and scrolled into view.
- Parameters (year, genre, limit) are persisted in `album_lists` and reapplied on every regeneration.

---

## 7. REST API

All endpoints are under the FastAPI app. HTML pages are served at `/`, `/artists`, `/albums`, etc. JSON API endpoints are under `/api/`.

### Artists

| Method | Path | Description |
|---|---|---|
| GET | `/api/artists` | List all artists |
| POST | `/api/artists` | Create artist |
| PUT | `/api/artists/{id}` | Update artist |
| DELETE | `/api/artists/{id}` | Delete artist (cascades to albums) |

### Albums

| Method | Path | Description |
|---|---|---|
| GET | `/api/albums` | List all albums |
| POST | `/api/albums` | Create album |
| GET | `/api/albums/{id}` | Get album detail |
| PUT | `/api/albums/{id}` | Update album |
| PATCH | `/api/albums/{id}/rating` | Update rating only |
| POST | `/api/albums/{id}/cover` | Upload cover image (multipart) |
| DELETE | `/api/albums/{id}` | Delete album |

### Lists

| Method | Path | Description |
|---|---|---|
| GET | `/api/lists` | List all ranked lists |
| POST | `/api/lists` | Create list |
| PUT | `/api/lists/{id}` | Update list metadata |
| DELETE | `/api/lists/{id}` | Delete list |
| POST | `/api/lists/{id}/items` | Add album to list |
| POST | `/api/lists/{id}/items/reorder` | Reorder all items |
| DELETE | `/api/lists/{id}/items/{item_id}` | Remove item from list |
| POST | `/api/auto-lists/best-rated` | Create or regenerate a Best Rated auto list |

### Genres

| Method | Path | Description |
|---|---|---|
| GET | `/api/genres` | List genres |
| POST | `/api/genres` | Create genre |
| PUT | `/api/genres/{id}` | Update genre |
| DELETE | `/api/genres/{id}` | Delete genre |

### Import

| Method | Path | Description |
|---|---|---|
| POST | `/api/import/artist` | Start artist import draft |
| POST | `/api/import/album` | Start album import draft |
| POST | `/api/import/{draft_id}/confirm` | Confirm and persist a draft |

### Settings & Health

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Returns `{ "now": "<ISO timestamp>" }` |
| GET | `/api/settings` | Get current settings |
| PUT | `/api/settings` | Update active model |

---

## 8. Backup

The `album-ranker-backup` CLI command creates a dated SQLite backup using the native `sqlite3.backup()` API.

```
album-ranker-backup [--backup-dir PATH] [--retention-days N]
```

- Default backup directory: `.data/backups/` (next to the database).
- Default retention: 30 daily backups; older files are pruned automatically.
- Filename format: `album-ranker-YYYY-MM-DD.db`.

**iCloud backup (macOS launchd):**

A sample `launchd` plist is provided at `launchd/com.darkcreation.album-ranker-backup.plist`. To install:

```sh
cp launchd/com.darkcreation.album-ranker-backup.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.darkcreation.album-ranker-backup.plist
```

Set `--backup-dir` to `~/Library/Mobile Documents/com~apple~CloudDocs/album-ranker-backups/` to have backups synced to iCloud automatically.

---

## 9. Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `ALBUM_RANKER_DB_PATH` | `./.data/album-ranker.db` | Path to the SQLite database |
| `ALBUM_RANKER_HOST` | `127.0.0.1` | Bind host for Uvicorn |
| `ALBUM_RANKER_PORT` | `8780` | Bind port for Uvicorn |
| `ALBUM_RANKER_MODEL` | `gpt-5` | Default OpenAI model |
| `OPENAI_API_KEY` | _(unset)_ | Enables AI enrichment; import works without it (metadata-only fallback) |

The active model can also be changed at runtime via the Settings page (persisted to `app_settings`).

---

## 10. Testing

Test suite: `pytest` with `httpx` for API integration tests.

```sh
.venv/bin/python -m pytest tests/ -q
```

Test files:

| File | Coverage |
|---|---|
| `test_api.py` | Full HTTP round-trips for artists, albums, lists, genres, import, rating, cover upload, settings |
| `test_db.py` | Database layer: CRUD, migrations, auto-list generation |
| `test_importer.py` | Source adapters (Metal-Archives, Bandcamp, Wikipedia, YouTube Music), duration parsing, cover URL normalisation |
| `test_backup.py` | Backup creation, retention pruning |
| `test_settings.py` | Settings loading from environment |

All tests use in-memory or `tmp_path` databases; no network calls in the test suite.
