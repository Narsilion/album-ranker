# Backend Improvement Plan

## Summary

Targeted improvements to the server-side code across performance, correctness,
security, and test coverage. The app's architecture (SQLite, FastAPI, single-file
modules) stays unchanged. No new dependencies beyond what is already in
`pyproject.toml` should be added unless a specific item calls for it.

## Product Constraint: AI Scope

AI should be used only for album write-up / Telegram post generation. The
generated text can also be shown inside Album Ranker as album context. All other
flows should be deterministic:

- no AI artist import;
- no AI album metadata import;
- no AI metadata refresh;
- no AI-generated list creation;
- no AI-assisted settings/status concepts except what is needed to generate and
  save album write-ups / Telegram post drafts.

Backend cleanup should move toward a smaller AI boundary: one write-up generation
service, one write-up draft endpoint, and one save endpoint. The existing
`overview` storage name can remain temporarily as a compatibility detail.

---

## Priority Improvements

### 1. Replace `_all_drafts()` exception-driven loop with a SQL query. **Implemented 2026-05-03.**

**File:** `app.py` (L934–941), `db.py`

`_all_drafts()` increments a counter from 1 until `get_import_job()` raises
`KeyError`, treating sequential IDs as the iteration boundary. This is called on
every `/artists` and `/imports` page load.

Problems:
- If a draft with ID 5 is deleted, iteration stops at 4 — drafts 6, 7, … are
  silently lost.
- Each loop body issues a separate SQL `SELECT`. Fetching N drafts costs N round
  trips.

Fix: add `Database.list_import_jobs()` that returns all rows in a single
`SELECT * FROM import_jobs` and replace the loop in `app.py` with a call to it.

---

### 2. Add missing database indexes. **Implemented 2026-05-03.**

**File:** `db.py` — `Database.initialize()`

No `CREATE INDEX` statements exist. Table scans on `albums.artist_id`,
`artists.slug`, and `lists.id` become noticeable as the library grows.

Add during `initialize()`:

```sql
CREATE INDEX IF NOT EXISTS idx_albums_artist_id  ON albums(artist_id);
CREATE INDEX IF NOT EXISTS idx_albums_release_year ON albums(release_year);
CREATE INDEX IF NOT EXISTS idx_list_items_list_id ON album_list_items(list_id);
CREATE INDEX IF NOT EXISTS idx_artists_slug       ON artists(slug);
```

---

### 3. Replace `get_list()` linear scan with a direct query. **Implemented 2026-05-03.**

**File:** `db.py` (L714–719)

`get_list(list_id)` calls `list_lists()` — which fetches **all** lists and all
their items — then iterates in Python until it finds the matching ID. This loads
unbounded data to return one record.

Fix: implement a direct `SELECT … WHERE id = ?` path in `get_list()`, reusing
the same item hydration logic already used in `list_lists()`.

---

### 4. Prevent SSRF in the importer. **Implemented 2026-05-03.**

**File:** `importer.py` — `_fetch_url_document()` (L66–77)

User-supplied URLs are fetched without checking whether they resolve to private
or loopback addresses. An attacker with import access could probe the local
network.

Fix: before fetching, resolve the hostname and reject any address in
`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, and `::1`.
Allow only `http` and `https` schemes.

---

### 5. Remove mutable global AI status and scope AI state to album write-ups. **Implemented 2026-05-03.**

**File:** `app.py` (L201–204)

`ai_state` is a module-level dict mutated during import requests. Since AI is no
longer part of import or metadata refresh, this state should not exist as a
general app-wide import status.

Fix: remove import-related AI status writes. If status is still needed, keep it
request-local for `/api/albums/{id}/overview/draft` and return errors directly
from that endpoint. Persist only the saved album write-up text on the album
record.

---

### 6. Add indexes and a direct query for genre list lookups — **Implemented 2026-05-03**

**File:** `db.py`

`LOWER(genre) LIKE LOWER(?)` in the album filter cannot use an index. Adding a
generated lowercase column or a functional index speeds up filtered listing.

Additionally, consider storing genre on albums as a case-normalised value at
write time (`genre.lower().title()`) so plain `=` comparisons can use an index.
This is a one-migration change with no API surface change.

---

### 7. Validate port and model name at startup — **Implemented 2026-05-03**

**File:** `settings.py`

`ALBUM_RANKER_PORT` is cast to `int()` with no bounds check — a value of 0 or
65536 silently starts on a privileged or invalid port. `ALBUM_RANKER_MODEL` is
stored as a raw string with no format check.

Fix: add validation in `load_settings()` that raises `SystemExit` with a clear
message for out-of-range port values, and that rejects obviously malformed model
name strings (empty, >200 chars, non-printable characters).

---

### 8. Simplify the AI client boundary around album write-ups — **Implemented 2026-05-03**

**File:** `openai_client.py`

The two client classes share ~95% of their code. `generate_json()` and
`list_models()` differ only in the base URL and the Authorization header prefix.

Fix: first confirm whether GitHub Models is still required for album write-up /
Telegram post generation. If not, remove `GitHubModelsClient` and keep one small
`AlbumWriteupAIClient`. If both providers remain useful, extract a
`_BaseAIClient` with `base_url` and `auth_header` as constructor parameters.
Either way, this module should expose album write-up generation only, not generic
metadata import.

---

### 9. Add max-length constraints to string fields in schemas — **Implemented 2026-05-03**

**File:** `schemas.py`

No field declares a maximum length. An artist name of 1 MB or a notes field
containing 10 MB of text will be accepted, stored, and returned on every page
load that includes that artist.

Add `max_length` to the main string fields:
- `name` on `ArtistUpsert` and `GenreUpsert`: 500 chars
- `title` on `AlbumUpsert`: 500 chars
- `description`, `notes`, `overview` on upsert models: 32 000 chars
- `external_url`, `album_stream_url`, `cover_source_url`: 2 048 chars

---

### 10. Extend test coverage for the database layer — **Implemented 2026-05-03**

**File:** `tests/test_db.py`

`test_db.py` currently has one test (list reorder). Core CRUD paths have no
direct coverage.

Add tests for:
- Artist create / update / delete with cascade behaviour
- Album create / update / delete
- Genre create, conflict handling (same name, different case)
- Import job lifecycle: create → update → delete
- `_unique_slug()` collision resolution (two artists with the same name)
- `auto_list_best_rated()` with genre filter

---

## Additional Suggestions

### 11. Remove AI from import and refresh endpoints. **Implemented 2026-05-03.**

**Files:** `app.py`, `importer.py`, `ui.py`, `tests/test_api.py`,
`tests/test_importer.py`

The codebase still has AI paths for artist import, album import,
album-with-artist import, artist refresh, and album metadata refresh. That
conflicts with the current product direction.

Fix:
- Make import endpoints use source adapters and best-effort parsing only.
- Keep review-before-save drafts, but treat them as parsed metadata drafts, not
  AI drafts.
- Remove prompts and schema calls from `create_artist_draft()` and
  `create_album_draft()`.
- Keep album write-up / Telegram post draft generation as the only AI-backed endpoint.
- Update UI copy from "AI import" / "generating metadata" to "fetching source" /
  "parsed draft" where the workflow remains.

### 12. Rename "overview" to "write-up" / "Telegram post" or document compatibility. **Implemented 2026-05-03.**

**Files:** `schemas.py`, `db.py`, `app.py`, `ui.py`, tests

The app currently stores and exposes `overview`, but the product language is
"album write-ups" or "Telegram posts". Pick one backend term to reduce
confusion. Avoid "review" as the primary term because this text is not only a
critical review; it is generated channel content that can also appear in the app.

Conservative path:
- Keep the database column as `overview` to avoid a migration.
- Rename route/UI/service concepts to "write-up" for the in-app feature and
  "Telegram post" for publishing-specific UI.
- Add comments or schema aliases where `overview` remains for compatibility.

Full cleanup path:
- Add an `album_writeup` or `telegram_post` column.
- Migrate existing `overview` values.
- Remove old references once tests pass.

### 13. Split `MetadataImporter` responsibilities. **Implemented 2026-05-03.**

**File:** `importer.py`

`MetadataImporter` currently mixes URL fetching, source parsing, draft creation,
AI metadata generation, diagnostics, and album write-up generation. That makes it
hard to enforce the "AI only for album write-ups / Telegram posts" rule.

Fix:
- `SourceMetadataImporter`: deterministic source fetching and parsing.
- `AlbumWriteupGenerator`: AI-only album write-up / Telegram post generation.
- `CoverDownloader`: remains separate.

This can be done without moving to a package structure immediately, but separate
classes make tests and dependency injection clearer.

### 14. Add regression tests that forbid AI calls outside album write-ups. **Implemented 2026-05-03.**

**Files:** `tests/test_api.py`, `tests/test_importer.py`

Add tests with a fake AI client that raises if called. Then exercise:
- artist import;
- album import;
- album-with-artist import;
- artist refresh;
- album metadata refresh.

Those flows should still return deterministic drafts or validation errors, and
the fake client should never be invoked. Keep separate tests proving
`/api/albums/{id}/write-up/draft` does call the write-up generator.

### 15. Normalize app settings around write-up generation. **Implemented 2026-05-03.**

**Files:** `settings.py`, `schemas.py`, `db.py`, `app.py`, `ui.py`

Settings still describe a general AI capability. Narrow them to write-up /
Telegram post generation:
- `active_model` becomes `writeup_model` or is clearly labelled as write-up only.
- OpenAI key status is shown only where write-up generation is configured.
- Remove import diagnostics from settings if they only existed for AI import
  debugging.

### 16. Add request-size and timeout guardrails for source fetching. **Implemented 2026-05-03.**

**File:** `importer.py`

Even after AI import removal, deterministic source parsing still fetches
user-supplied URLs. Combine this with the SSRF item:
- allow only `http`/`https`;
- block private, loopback, link-local, and multicast IPs;
- enforce a maximum response size;
- enforce a timeout;
- reject unexpected content types where possible.

---

## Out of Scope

- Migrating from SQLite to a client-server database
- Adding authentication or multi-user support
- Switching from inline HTML rendering in `ui.py` to a template engine
- Replacing `urllib` / `subprocess(curl)` with a third-party HTTP library
- Adding AI features beyond album write-up / Telegram post generation

## Test Plan

Run the existing suite after each change:

```bash
cd /Users/darkcreation/Documents/git_repos/album-ranker
source .venv/bin/activate
pytest
```

For database migration changes, verify the app starts cleanly against an
existing database before running tests.
