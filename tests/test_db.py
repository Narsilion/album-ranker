from __future__ import annotations

import sqlite3

import pytest

from album_ranker.db import Database
from album_ranker.schemas import (
    AlbumListUpsert,
    AlbumUpsert,
    ArtistUpsert,
    AutoListBestRatedRequest,
    GenreUpsert,
    ImportRequest,
    ReorderListItemsRequest,
)


def test_database_initializes_and_reorders_list_items(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    first = db.create_album(
        AlbumUpsert(
            artist_name="Scythe of Mephisto",
            title="Till Life Do Us Part",
            release_year=2026,
            genre="Black Metal",
            rating=9,
            duration_seconds=1800,
            tracks=[],
        )
    )
    second = db.create_album(
        AlbumUpsert(
            artist_name="Scythe of Mephisto",
            title="Another Night",
            release_year=2025,
            genre="Black Metal",
            duration_seconds=1700,
            tracks=[],
        )
    )
    created_list = db.create_list(
        AlbumListUpsert(name="Top 2026 Black Metal", description="Best of the year", year=2026, genres=["Black Metal"])
    )
    db.add_album_to_list(created_list.id, first.id)
    ranked = db.add_album_to_list(created_list.id, second.id)

    assert [item.rank_position for item in ranked.items] == [1, 2]

    reordered = db.reorder_list_items(
        created_list.id,
        ReorderListItemsRequest(item_ids=[ranked.items[1].id, ranked.items[0].id]),
    )

    assert [item.album.title for item in reordered.items] == ["Another Night", "Till Life Do Us Part"]
    assert [item.rank_position for item in reordered.items] == [1, 2]
    assert db.get_album(first.id).rating == 9

    other_list = db.create_list(AlbumListUpsert(name="Other List", description="Do not scan for this one"))
    requested = db.get_list(created_list.id)

    assert requested.id == created_list.id
    assert requested.name == "Top 2026 Black Metal"
    assert [item.album.title for item in requested.items] == ["Another Night", "Till Life Do Us Part"]
    assert other_list.id != requested.id

    try:
        db.get_list(99999)
    except KeyError as exc:
        assert "Unknown list 99999" in str(exc)
    else:
        raise AssertionError("Missing list lookup should raise KeyError")


def test_list_import_jobs_returns_rows_after_id_gaps(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    first = db.create_import_job(
        "artist",
        ImportRequest(artist_name="First", source_url="https://example.com/first"),
        {"artist_name": "First", "external_url": "https://example.com/first"},
    )
    second = db.create_import_job(
        "album",
        ImportRequest(artist_name="Second", album_title="Second Album", source_url="https://example.com/second"),
        {
            "artist_name": "Second",
            "album_title": "Second Album",
            "album_external_url": "https://example.com/second",
        },
    )
    third = db.create_import_job(
        "artist",
        ImportRequest(artist_name="Third", source_url="https://example.com/third"),
        {"artist_name": "Third", "external_url": "https://example.com/third"},
    )

    with db.connection() as connection:
        connection.execute("DELETE FROM import_jobs WHERE id = ?", (second.id,))

    drafts = db.list_import_jobs()

    assert [draft.id for draft in drafts] == [first.id, third.id]
    assert [draft.draft_payload for draft in drafts] == [
        {"artist_name": "First", "external_url": "https://example.com/first"},
        {"artist_name": "Third", "external_url": "https://example.com/third"},
    ]


def test_database_initialize_creates_expected_indexes(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    with db.connection() as connection:
        rows = connection.execute(
            """
            SELECT name, tbl_name
            FROM sqlite_master
            WHERE type = 'index' AND name LIKE 'idx_%'
            """
        ).fetchall()

    indexes = {row["name"]: row["tbl_name"] for row in rows}

    assert indexes["idx_albums_artist_id"] == "albums"
    assert indexes["idx_albums_release_year"] == "albums"
    assert indexes["idx_albums_genre_normalized"] == "albums"
    assert indexes["idx_artists_slug"] == "artists"
    assert indexes["idx_list_items_list_id"] == "list_items"
    assert indexes["idx_list_items_album_id"] == "list_items"


def test_database_initialize_migrates_genre_index_after_column_exists(settings) -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE artists (
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
            CREATE TABLE albums (
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
                album_stream_url TEXT,
                album_type TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO artists(name, slug, created_at, updated_at)
            VALUES ('Ahab', 'ahab', 'now', 'now');
            INSERT INTO albums(artist_id, title, genre, created_at, updated_at)
            VALUES (1, 'The Call of the Wretched Sea', 'Funeral Doom Metal', 'now', 'now');
            """
        )
        connection.commit()
    finally:
        connection.close()

    db = Database(settings.db_path)
    db.initialize()

    with db.connection() as migrated:
        album_columns = {row["name"] for row in migrated.execute("PRAGMA table_info(albums)").fetchall()}
        index = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_albums_genre_normalized'"
        ).fetchone()
        row = migrated.execute("SELECT genre_normalized FROM albums WHERE id = 1").fetchone()

    assert "genre_normalized" in album_columns
    assert index is not None
    assert row["genre_normalized"] == "funeral doom metal"


def test_album_genre_normalized_column_tracks_create_update_and_auto_lists(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    album = db.create_album(
        AlbumUpsert(
            artist_name="Katatonia",
            title="Brave Murder Day",
            album_type="Full-length",
            release_year=1996,
            genre="  Death   Doom Metal  ",
            rating=10,
            tracks=[],
        )
    )
    db.create_album(
        AlbumUpsert(
            artist_name="Katatonia",
            title="Discouraged Ones",
            album_type="Full-length",
            release_year=1998,
            genre="Depressive Rock",
            rating=8,
            tracks=[],
        )
    )

    with db.connection() as connection:
        row = connection.execute(
            "SELECT genre_normalized FROM albums WHERE id = ?",
            (album.id,),
        ).fetchone()
    assert row["genre_normalized"] == "death doom metal"

    generated = db.auto_list_best_rated(
        AutoListBestRatedRequest(name="Best Doom", genres=["doom metal"], limit=10)
    )
    assert [item.album.title for item in generated.items] == ["Brave Murder Day"]

    db.update_album(
        album.id,
        AlbumUpsert(
            artist_name="Katatonia",
            title="Brave Murder Day",
            release_year=1996,
            genre="Black Metal",
            rating=10,
            tracks=[],
        ),
    )

    with db.connection() as connection:
        updated_row = connection.execute(
            "SELECT genre_normalized FROM albums WHERE id = ?",
            (album.id,),
        ).fetchone()
    assert updated_row["genre_normalized"] == "black metal"


def test_best_rated_auto_list_can_include_only_full_length_albums(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    db.create_album(
        AlbumUpsert(
            artist_name="Band",
            title="Full Album",
            album_type="Full-length",
            rating=9,
            tracks=[],
        )
    )
    db.create_album(
        AlbumUpsert(
            artist_name="Band",
            title="Higher Rated EP",
            album_type="EP",
            rating=10,
            tracks=[],
        )
    )

    generated = db.auto_list_best_rated(
        AutoListBestRatedRequest(
            name="Best Full-Lengths",
            limit=10,
            full_length_only=True,
        )
    )

    assert generated.auto_full_length_only is True
    assert [item.album.title for item in generated.items] == ["Full Album"]

    regenerated = db.auto_list_best_rated(
        AutoListBestRatedRequest(
            name="Best Full-Lengths",
            limit=10,
            full_length_only=False,
            update_existing=True,
        )
    )

    assert regenerated.auto_full_length_only is False
    assert [item.album.title for item in regenerated.items] == ["Higher Rated EP", "Full Album"]


def test_artist_create_update_delete_and_album_delete_cascade(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    artist = db.create_artist(
        ArtistUpsert(
            name="Wyrd",
            description="Finnish metal",
            external_url="https://example.com/wyrd",
            origin="Finland",
        )
    )
    updated = db.update_artist(
        artist.id,
        ArtistUpsert(name="Wyrd Band", description="Updated", external_url=None, origin="Finland, Hyvinkaa"),
    )
    album = db.create_album(
        AlbumUpsert(
            artist_name=updated.name,
            title="Huldrafolk",
            release_year=2002,
            genre="Black Metal",
            rating=8,
            tracks=[],
        )
    )

    with pytest.raises(ValueError, match="Cannot delete this artist"):
        db.delete_artist(updated.id)

    db.delete_album(album.id)
    db.delete_artist(updated.id)

    with pytest.raises(KeyError, match=f"Unknown artist {updated.id}"):
        db.get_artist(updated.id)
    with pytest.raises(KeyError, match=f"Unknown album {album.id}"):
        db.get_album(album.id)


def test_album_create_update_delete_replaces_tracks_and_list_items(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    album = db.create_album(
        AlbumUpsert(
            artist_name="October Tide",
            title="Rain Without End",
            release_year=1997,
            genre="Death Doom Metal",
            rating=9,
            tracks=[
                {"track_number": 1, "title": "12 Days of Rain", "duration_seconds": 395},
                {"track_number": 2, "title": "Ephemeral", "duration_seconds": 410},
            ],
        )
    )
    assert [track.title for track in album.tracks] == ["12 Days of Rain", "Ephemeral"]

    updated = db.update_album(
        album.id,
        AlbumUpsert(
            artist_name="October Tide",
            title="Rain Without End",
            release_year=1997,
            genre="Death Doom Metal",
            rating=10,
            notes="Updated notes",
            tracks=[{"track_number": 1, "title": "Losing Tomorrow", "duration_seconds": 369}],
        ),
    )
    assert updated.rating == 10
    assert updated.notes == "Updated notes"
    assert [track.title for track in updated.tracks] == ["Losing Tomorrow"]

    album_list = db.create_list(AlbumListUpsert(name="Death Doom", genres=["Doom"]))
    listed = db.add_album_to_list(album_list.id, album.id)
    assert [item.album_id for item in listed.items] == [album.id]

    db.delete_album(album.id)
    assert db.get_list(album_list.id).items == []


def test_genre_create_conflict_update_and_delete(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    genre = db.create_genre(GenreUpsert(name="Black Metal"))
    duplicate = db.create_genre(GenreUpsert(name="black metal"))
    assert duplicate.id == genre.id
    assert db.list_genres() == [genre]

    doom = db.create_genre(GenreUpsert(name="Doom Metal"))
    with pytest.raises(ValueError, match="already exists"):
        db.update_genre(doom.id, GenreUpsert(name="BLACK METAL"))

    updated = db.update_genre(doom.id, GenreUpsert(name="Death Doom Metal"))
    assert updated.name == "Death Doom Metal"

    db.delete_genre(updated.id)
    with pytest.raises(KeyError, match=f"Unknown genre {updated.id}"):
        db.get_genre(updated.id)


def test_import_job_lifecycle_create_update_delete(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    draft = db.create_import_job(
        "album",
        ImportRequest(
            artist_name="Shape of Despair",
            album_title="Angels of Distress",
            source_url="https://example.com/album",
        ),
        {"artist_name": "Shape of Despair", "album_title": "Angels of Distress"},
    )
    assert draft.status == "draft"
    assert draft.chosen_source_url == "https://example.com/album"

    updated = db.update_import_job(
        draft.id,
        payload={"artist_name": "Shape of Despair", "album_title": "Angels of Distress", "release_year": 2001},
        chosen_source_url="https://example.com/updated",
        status="confirmed",
    )
    assert updated.status == "confirmed"
    assert updated.chosen_source_url == "https://example.com/updated"
    assert updated.draft_payload["release_year"] == 2001

    db.delete_import_job(updated.id)
    assert db.list_import_jobs() == []
    with pytest.raises(KeyError, match=f"Unknown import draft {updated.id}"):
        db.get_import_job(updated.id)


def test_unique_slug_collision_resolution(settings) -> None:
    db = Database(settings.db_path)
    db.initialize()

    first = db.create_artist(ArtistUpsert(name="Wyrd"))
    second = db.create_artist(ArtistUpsert(name="Wyrd!"))

    assert first.slug == "wyrd"
    assert second.slug == "wyrd-2"
