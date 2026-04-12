from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from album_ranker.schemas import (
    AlbumCardRecord,
    AlbumDetailRecord,
    AlbumListItemRecord,
    AlbumListRecord,
    AlbumListUpsert,
    AlbumUpsert,
    AutoListBestRatedRequest,
    GenreRecord,
    GenreUpsert,
    ArtistRecord,
    ArtistUpsert,
    ArtistWithAlbumsRecord,
    ImportDraftRecord,
    ImportRequest,
    ReorderListItemsRequest,
    SettingsRecord,
    SettingsUpdateRequest,
    TrackRecord,
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "artist"


@dataclass(slots=True)
class Database:
    db_path: Path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS artists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    slug TEXT NOT NULL UNIQUE,
                    description TEXT,
                    description_source_url TEXT,
                    description_source_label TEXT,
                    external_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS albums (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    release_year INTEGER,
                    genre TEXT,
                    rating INTEGER,
                    duration_seconds INTEGER,
                    cover_image_path TEXT,
                    cover_source_url TEXT,
                    album_external_url TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(artist_id) REFERENCES artists(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    album_id INTEGER NOT NULL,
                    track_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    duration_seconds INTEGER,
                    position INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(album_id) REFERENCES albums(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS album_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    year INTEGER,
                    genre_filter_hint TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS list_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_id INTEGER NOT NULL,
                    album_id INTEGER NOT NULL,
                    rank_position INTEGER NOT NULL,
                    UNIQUE(list_id, album_id),
                    UNIQUE(list_id, rank_position),
                    FOREIGN KEY(list_id) REFERENCES album_lists(id) ON DELETE CASCADE,
                    FOREIGN KEY(album_id) REFERENCES albums(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS import_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT NOT NULL,
                    requested_artist_name TEXT NOT NULL,
                    requested_album_title TEXT,
                    requested_source_url TEXT,
                    chosen_source_url TEXT,
                    status TEXT NOT NULL,
                    draft_payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS genres (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO app_settings(key, value) VALUES('schema_version', '1')"
            )
            album_columns = {row["name"] for row in connection.execute("PRAGMA table_info(albums)").fetchall()}
            if "album_external_url" not in album_columns:
                connection.execute("ALTER TABLE albums ADD COLUMN album_external_url TEXT")
            if "rating" not in album_columns:
                connection.execute("ALTER TABLE albums ADD COLUMN rating INTEGER")

    @contextmanager
    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def get_app_setting(self, key: str, default: str | None = None) -> str | None:
        with self.connection() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])

    def set_app_setting(self, key: str, value: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO app_settings(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_active_model(self, default_model: str) -> str:
        return self.get_app_setting("active_model", default_model) or default_model

    def build_settings_record(
        self,
        *,
        default_model: str,
        available_models: list[str],
        host: str,
        port: int,
        openai_api_key_configured: bool,
        ai_status: str,
        ai_status_detail: str | None,
        last_import_diagnostics: dict[str, object] | None,
    ) -> SettingsRecord:
        return SettingsRecord(
            model=default_model,
            active_model=self.get_active_model(default_model),
            available_models=available_models,
            openai_api_key_configured=openai_api_key_configured,
            ai_status=ai_status,
            ai_status_detail=ai_status_detail,
            last_import_diagnostics=last_import_diagnostics,
            host=host,
            port=port,
        )

    def update_settings(self, payload: SettingsUpdateRequest) -> None:
        self.set_app_setting("active_model", payload.active_model)

    def list_genres(self) -> list[GenreRecord]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM genres ORDER BY name COLLATE NOCASE").fetchall()
        return [GenreRecord.model_validate(dict(row)) for row in rows]

    def create_genre(self, payload: GenreUpsert) -> GenreRecord:
        now = utc_now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO genres(name, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (payload.name, now, now),
            )
            genre_id = int(cursor.lastrowid or connection.execute(
                "SELECT id FROM genres WHERE lower(name) = lower(?)",
                (payload.name,),
            ).fetchone()["id"])
        return self.get_genre(genre_id)

    def get_genre(self, genre_id: int) -> GenreRecord:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM genres WHERE id = ?", (genre_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown genre {genre_id}")
        return GenreRecord.model_validate(dict(row))

    def update_genre(self, genre_id: int, payload: GenreUpsert) -> GenreRecord:
        self.get_genre(genre_id)
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE genres
                SET name = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload.name, utc_now_iso(), genre_id),
            )
        return self.get_genre(genre_id)

    def delete_genre(self, genre_id: int) -> None:
        self.get_genre(genre_id)
        with self.connection() as connection:
            connection.execute("DELETE FROM genres WHERE id = ?", (genre_id,))

    def list_artists(self) -> list[ArtistWithAlbumsRecord]:
        with self.connection() as connection:
            artist_rows = connection.execute("SELECT * FROM artists ORDER BY name COLLATE NOCASE").fetchall()
            album_rows = connection.execute(
                """
                SELECT albums.*, artists.name AS artist_name
                FROM albums
                JOIN artists ON artists.id = albums.artist_id
                ORDER BY artists.name COLLATE NOCASE, albums.release_year DESC, albums.title COLLATE NOCASE
                """
            ).fetchall()
        albums_by_artist: dict[int, list[AlbumCardRecord]] = {}
        for row in album_rows:
            card = self._album_card_from_row(row)
            albums_by_artist.setdefault(card.artist_id, []).append(card)
        return [
            ArtistWithAlbumsRecord.model_validate(
                {
                    **dict(row),
                    "albums": [album.model_dump() for album in albums_by_artist.get(int(row["id"]), [])],
                }
            )
            for row in artist_rows
        ]

    def get_artist(self, artist_id: int) -> ArtistRecord:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM artists WHERE id = ?", (artist_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown artist {artist_id}")
        return ArtistRecord.model_validate(dict(row))

    def get_artist_with_albums(self, artist_id: int) -> ArtistWithAlbumsRecord:
        artist = self.get_artist(artist_id)
        albums = [album for album in self.list_albums() if album.artist_id == artist_id]
        return ArtistWithAlbumsRecord.model_validate(
            {
                **artist.model_dump(mode="json"),
                "albums": [album.model_dump(mode="json") for album in albums],
            }
        )

    def get_artist_by_name(self, name: str) -> ArtistRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM artists WHERE lower(name) = lower(?)",
                (name,),
            ).fetchone()
        if row is None:
            return None
        return ArtistRecord.model_validate(dict(row))

    def create_artist(self, payload: ArtistUpsert) -> ArtistRecord:
        existing = self.get_artist_by_name(payload.name)
        if existing is not None:
            merged = ArtistUpsert(
                name=payload.name,
                description=payload.description or existing.description,
                description_source_url=payload.description_source_url or existing.description_source_url,
                description_source_label=payload.description_source_label or existing.description_source_label,
                external_url=payload.external_url or existing.external_url,
            )
            return self.update_artist(existing.id, merged)
        slug = self._unique_slug(slugify(payload.name))
        now = utc_now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO artists(
                    name, slug, description, description_source_url, description_source_label,
                    external_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name,
                    slug,
                    payload.description,
                    payload.description_source_url,
                    payload.description_source_label,
                    payload.external_url,
                    now,
                    now,
                ),
            )
            artist_id = int(cursor.lastrowid)
        return self.get_artist(artist_id)

    def update_artist(self, artist_id: int, payload: ArtistUpsert) -> ArtistRecord:
        existing = self.get_artist(artist_id)
        slug = existing.slug if existing.name == payload.name else self._unique_slug(slugify(payload.name), exclude_id=artist_id)
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE artists
                SET name = ?, slug = ?, description = ?, description_source_url = ?,
                    description_source_label = ?, external_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.name,
                    slug,
                    payload.description,
                    payload.description_source_url,
                    payload.description_source_label,
                    payload.external_url,
                    utc_now_iso(),
                    artist_id,
                ),
            )
        return self.get_artist(artist_id)

    def delete_artist(self, artist_id: int) -> None:
        self.get_artist(artist_id)
        with self.connection() as connection:
            connection.execute("DELETE FROM artists WHERE id = ?", (artist_id,))

    def list_albums(self) -> list[AlbumCardRecord]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT albums.*, artists.name AS artist_name
                FROM albums
                JOIN artists ON artists.id = albums.artist_id
                ORDER BY COALESCE(albums.release_year, 0) DESC, albums.title COLLATE NOCASE
                """
            ).fetchall()
        return [self._album_card_from_row(row) for row in rows]

    def get_album(self, album_id: int) -> AlbumDetailRecord:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT albums.*, artists.name AS artist_name, artists.description AS artist_description,
                       artists.description_source_url AS artist_description_source_url,
                       artists.description_source_label AS artist_description_source_label,
                       artists.external_url AS artist_external_url
                FROM albums
                JOIN artists ON artists.id = albums.artist_id
                WHERE albums.id = ?
                """,
                (album_id,),
            ).fetchone()
            track_rows = connection.execute(
                "SELECT * FROM tracks WHERE album_id = ? ORDER BY position ASC, track_number ASC, id ASC",
                (album_id,),
            ).fetchall()
        if row is None:
            raise KeyError(f"Unknown album {album_id}")
        return AlbumDetailRecord.model_validate(
            {
                **dict(row),
                "tracks": [TrackRecord.model_validate(dict(track)) for track in track_rows],
            }
        )

    def get_album_by_artist_and_title(self, artist_name: str, title: str) -> AlbumDetailRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT albums.id
                FROM albums
                JOIN artists ON artists.id = albums.artist_id
                WHERE lower(artists.name) = lower(?) AND lower(albums.title) = lower(?)
                ORDER BY albums.id ASC
                LIMIT 1
                """,
                (artist_name, title),
            ).fetchone()
        if row is None:
            return None
        return self.get_album(int(row["id"]))

    def create_album(self, payload: AlbumUpsert) -> AlbumDetailRecord:
        artist_id = self._get_or_create_artist(payload)
        now = utc_now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO albums(
                    artist_id, title, release_year, genre, rating, duration_seconds, cover_image_path,
                    cover_source_url, album_external_url, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artist_id,
                    payload.title,
                    payload.release_year,
                    payload.genre,
                    payload.rating,
                    payload.duration_seconds,
                    payload.cover_image_path,
                    payload.cover_source_url,
                    payload.album_external_url,
                    payload.notes,
                    now,
                    now,
                ),
            )
            album_id = int(cursor.lastrowid)
            self._replace_tracks(connection, album_id, payload)
        return self.get_album(album_id)

    def update_album(self, album_id: int, payload: AlbumUpsert) -> AlbumDetailRecord:
        self.get_album(album_id)
        artist_id = self._get_or_create_artist(payload)
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE albums
                SET artist_id = ?, title = ?, release_year = ?, genre = ?, rating = ?, duration_seconds = ?,
                    cover_image_path = ?, cover_source_url = ?, album_external_url = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    artist_id,
                    payload.title,
                    payload.release_year,
                    payload.genre,
                    payload.rating,
                    payload.duration_seconds,
                    payload.cover_image_path,
                    payload.cover_source_url,
                    payload.album_external_url,
                    payload.notes,
                    utc_now_iso(),
                    album_id,
                ),
            )
            self._replace_tracks(connection, album_id, payload)
        return self.get_album(album_id)

    def patch_album_rating(self, album_id: int, rating: int | None) -> AlbumDetailRecord:
        self.get_album(album_id)
        with self.connection() as connection:
            connection.execute(
                "UPDATE albums SET rating = ?, updated_at = ? WHERE id = ?",
                (rating, utc_now_iso(), album_id),
            )
        return self.get_album(album_id)

    def delete_album(self, album_id: int) -> None:
        self.get_album(album_id)
        with self.connection() as connection:
            connection.execute("DELETE FROM albums WHERE id = ?", (album_id,))

    def list_lists(self) -> list[AlbumListRecord]:
        with self.connection() as connection:
            list_rows = connection.execute(
                "SELECT * FROM album_lists ORDER BY updated_at DESC, id DESC"
            ).fetchall()
            item_rows = connection.execute(
                """
                SELECT list_items.id, list_items.list_id, list_items.album_id, list_items.rank_position,
                       albums.artist_id, albums.title, albums.release_year, albums.genre, albums.rating, albums.duration_seconds,
                       albums.cover_image_path, albums.cover_source_url, albums.notes, albums.created_at, albums.updated_at,
                       artists.name AS artist_name
                FROM list_items
                JOIN albums ON albums.id = list_items.album_id
                JOIN artists ON artists.id = albums.artist_id
                ORDER BY list_items.rank_position ASC, list_items.id ASC
                """
            ).fetchall()
        items_by_list: dict[int, list[AlbumListItemRecord]] = {}
        for row in item_rows:
            album = AlbumCardRecord.model_validate(
                {
                    "id": row["album_id"],
                    "artist_id": row["artist_id"],
                    "artist_name": row["artist_name"],
                    "title": row["title"],
                    "release_year": row["release_year"],
                    "genre": row["genre"],
                    "rating": row["rating"],
                    "duration_seconds": row["duration_seconds"],
                    "cover_image_path": row["cover_image_path"],
                    "cover_source_url": row["cover_source_url"],
                    "notes": row["notes"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
            item = AlbumListItemRecord(
                id=row["id"],
                list_id=row["list_id"],
                album_id=row["album_id"],
                rank_position=row["rank_position"],
                album=album,
            )
            items_by_list.setdefault(item.list_id, []).append(item)
        return [
            AlbumListRecord.model_validate(
                {
                    **dict(row),
                    "items": [item.model_dump() for item in items_by_list.get(int(row["id"]), [])],
                }
            )
            for row in list_rows
        ]

    def get_list(self, list_id: int) -> AlbumListRecord:
        for record in self.list_lists():
            if record.id == list_id:
                return record
        raise KeyError(f"Unknown list {list_id}")

    def create_list(self, payload: AlbumListUpsert) -> AlbumListRecord:
        now = utc_now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO album_lists(name, description, year, genre_filter_hint, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payload.name, payload.description, payload.year, payload.genre_filter_hint, now, now),
            )
            list_id = int(cursor.lastrowid)
        return self.get_list(list_id)

    def update_list(self, list_id: int, payload: AlbumListUpsert) -> AlbumListRecord:
        self.get_list(list_id)
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE album_lists
                SET name = ?, description = ?, year = ?, genre_filter_hint = ?, updated_at = ?
                WHERE id = ?
                """,
                (payload.name, payload.description, payload.year, payload.genre_filter_hint, utc_now_iso(), list_id),
            )
        return self.get_list(list_id)

    def delete_list(self, list_id: int) -> None:
        self.get_list(list_id)
        with self.connection() as connection:
            connection.execute("DELETE FROM album_lists WHERE id = ?", (list_id,))

    def add_album_to_list(self, list_id: int, album_id: int) -> AlbumListRecord:
        self.get_album(album_id)
        self.get_list(list_id)
        with self.connection() as connection:
            next_rank = connection.execute(
                "SELECT COALESCE(MAX(rank_position), 0) + 1 AS next_rank FROM list_items WHERE list_id = ?",
                (list_id,),
            ).fetchone()["next_rank"]
            connection.execute(
                """
                INSERT INTO list_items(list_id, album_id, rank_position)
                VALUES (?, ?, ?)
                ON CONFLICT(list_id, album_id) DO NOTHING
                """,
                (list_id, album_id, next_rank),
            )
            connection.execute(
                "UPDATE album_lists SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), list_id),
            )
        return self.get_list(list_id)

    def reorder_list_items(self, list_id: int, payload: ReorderListItemsRequest) -> AlbumListRecord:
        current = self.get_list(list_id)
        current_ids = [item.id for item in current.items]
        if sorted(current_ids) != sorted(payload.item_ids):
            raise ValueError("Reorder payload must include every current item exactly once")
        with self.connection() as connection:
            offset = len(payload.item_ids) + 10
            for position, item_id in enumerate(payload.item_ids, start=1):
                connection.execute(
                    "UPDATE list_items SET rank_position = ? WHERE id = ? AND list_id = ?",
                    (position + offset, item_id, list_id),
                )
            for position, item_id in enumerate(payload.item_ids, start=1):
                connection.execute(
                    "UPDATE list_items SET rank_position = ? WHERE id = ? AND list_id = ?",
                    (position, item_id, list_id),
                )
            connection.execute(
                "UPDATE album_lists SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), list_id),
            )
        return self.get_list(list_id)

    def remove_list_item(self, list_id: int, item_id: int) -> AlbumListRecord:
        current = self.get_list(list_id)
        if not any(item.id == item_id for item in current.items):
            raise KeyError(f"Unknown list item {item_id} for list {list_id}")
        with self.connection() as connection:
            connection.execute("DELETE FROM list_items WHERE id = ? AND list_id = ?", (item_id, list_id))
            remaining_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM list_items WHERE list_id = ? ORDER BY rank_position ASC, id ASC",
                    (list_id,),
                ).fetchall()
            ]
            for position, remaining_item_id in enumerate(remaining_ids, start=1):
                connection.execute(
                    "UPDATE list_items SET rank_position = ? WHERE id = ? AND list_id = ?",
                    (position, remaining_item_id, list_id),
                )
            connection.execute(
                "UPDATE album_lists SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), list_id),
            )
        return self.get_list(list_id)

    def auto_list_best_rated(self, payload: AutoListBestRatedRequest) -> AlbumListRecord:
        filters = ["rating IS NOT NULL"]
        params: list[object] = []
        if payload.year is not None:
            filters.append("release_year = ?")
            params.append(payload.year)
        if payload.genre:
            filters.append("LOWER(genre) LIKE LOWER(?)")
            params.append(f"%{payload.genre}%")
        where = " AND ".join(filters)
        params.append(payload.limit)
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT albums.id
                FROM albums
                WHERE {where}
                ORDER BY
                    rating DESC,
                    CASE WHEN LOWER(title) LIKE 'the %' THEN SUBSTR(title, 5)
                         WHEN LOWER(title) LIKE 'a %' THEN SUBSTR(title, 3)
                         WHEN LOWER(title) LIKE 'an %' THEN SUBSTR(title, 4)
                         ELSE title END COLLATE NOCASE ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
            album_ids = [row["id"] for row in rows]
            existing = connection.execute(
                "SELECT id, name FROM album_lists WHERE name = ?", (payload.name,)
            ).fetchone()
            if existing and payload.update_existing:
                list_id = existing["id"]
                connection.execute(
                    "UPDATE album_lists SET updated_at = ? WHERE id = ?",
                    (utc_now_iso(), list_id),
                )
                connection.execute("DELETE FROM list_items WHERE list_id = ?", (list_id,))
            elif existing and not payload.update_existing:
                raise ValueError(f"A list named '{payload.name}' already exists")
            else:
                now = utc_now_iso()
                cursor = connection.execute(
                    "INSERT INTO album_lists(name, created_at, updated_at) VALUES (?, ?, ?)",
                    (payload.name, now, now),
                )
                list_id = int(cursor.lastrowid)
            for rank, album_id in enumerate(album_ids, start=1):
                connection.execute(
                    "INSERT INTO list_items(list_id, album_id, rank_position) VALUES (?, ?, ?)",
                    (list_id, album_id, rank),
                )
        return self.get_list(list_id)

    def create_import_job(self, target_type: str, request: ImportRequest, draft_payload: dict[str, object]) -> ImportDraftRecord:
        now = utc_now_iso()
        chosen_source_url = None
        if target_type == "artist":
            chosen_source_url = str(draft_payload.get("description_source_url") or request.source_url or "")
        if target_type == "album":
            chosen_source_url = str(
                draft_payload.get("artist_description_source_url") or request.source_url or ""
            )
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO import_jobs(
                    target_type, requested_artist_name, requested_album_title, requested_source_url,
                    chosen_source_url, status, draft_payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?)
                """,
                (
                    target_type,
                    request.artist_name,
                    request.album_title,
                    request.source_url,
                    chosen_source_url or None,
                    json.dumps(draft_payload),
                    now,
                    now,
                ),
            )
            draft_id = int(cursor.lastrowid)
        return self.get_import_job(draft_id)

    def get_import_job(self, draft_id: int) -> ImportDraftRecord:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM import_jobs WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown import draft {draft_id}")
        return ImportDraftRecord.model_validate(
            {
                **dict(row),
                "draft_payload": json.loads(row["draft_payload_json"]),
            }
        )

    def update_import_job(
        self,
        draft_id: int,
        *,
        payload: dict[str, object],
        chosen_source_url: str | None,
        status: str,
    ) -> ImportDraftRecord:
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE import_jobs
                SET draft_payload_json = ?, chosen_source_url = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(payload), chosen_source_url, status, utc_now_iso(), draft_id),
            )
        return self.get_import_job(draft_id)

    def _replace_tracks(self, connection: sqlite3.Connection, album_id: int, payload: AlbumUpsert) -> None:
        connection.execute("DELETE FROM tracks WHERE album_id = ?", (album_id,))
        for index, track in enumerate(payload.tracks, start=1):
            connection.execute(
                """
                INSERT INTO tracks(album_id, track_number, title, duration_seconds, position)
                VALUES (?, ?, ?, ?, ?)
                """,
                (album_id, track.track_number, track.title, track.duration_seconds, track.position or index),
            )

    def _get_or_create_artist(self, payload: AlbumUpsert) -> int:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT id FROM artists WHERE lower(name) = lower(?)",
                (payload.artist_name,),
            ).fetchone()
            if row is not None:
                artist_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE artists
                    SET description = COALESCE(?, description),
                        description_source_url = COALESCE(?, description_source_url),
                        description_source_label = COALESCE(?, description_source_label),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload.artist_description,
                        payload.artist_description_source_url,
                        payload.artist_description_source_label,
                        utc_now_iso(),
                        artist_id,
                    ),
                )
                return artist_id
            slug = self._unique_slug(slugify(payload.artist_name))
            now = utc_now_iso()
            cursor = connection.execute(
                """
                INSERT INTO artists(
                    name, slug, description, description_source_url, description_source_label,
                    external_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.artist_name,
                    slug,
                    payload.artist_description,
                    payload.artist_description_source_url,
                    payload.artist_description_source_label,
                    None,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def _album_card_from_row(self, row: sqlite3.Row) -> AlbumCardRecord:
        return AlbumCardRecord.model_validate(dict(row))

    def _unique_slug(self, base: str, *, exclude_id: int | None = None) -> str:
        slug = base
        suffix = 2
        while True:
            with self.connection() as connection:
                if exclude_id is None:
                    row = connection.execute("SELECT id FROM artists WHERE slug = ?", (slug,)).fetchone()
                else:
                    row = connection.execute(
                        "SELECT id FROM artists WHERE slug = ? AND id != ?",
                        (slug, exclude_id),
                    ).fetchone()
            if row is None:
                return slug
            slug = f"{base}-{suffix}"
            suffix += 1
