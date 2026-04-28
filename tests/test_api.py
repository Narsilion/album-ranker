from __future__ import annotations

import re

from fastapi.testclient import TestClient

from album_ranker.app import create_app
from album_ranker.importer import CoverDownloader, MetadataImporter
from album_ranker.schemas import AlbumDetailRecord, AlbumDraftData, ArtistDraftData


# ── helpers ───────────────────────────────────────────────────────────────────

def _script_blocks(html: str) -> str:
    """Return concatenated content of all <script> blocks in an HTML page."""
    return "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL))


def _create_album(client, *, artist_name="Band", title="Album", description="A description.\nWith newlines & \"quotes\".") -> dict:
    return client.post(
        "/api/albums",
        json={
            "artist_name": artist_name,
            "artist_description": description,
            "title": title,
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1800,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()


class SparseAlbumImporter(MetadataImporter):
    def __init__(self) -> None:
        super().__init__(client=None)

    def create_album_draft(self, request, *, model):  # type: ignore[override]
        return AlbumDraftData(
            artist_name="",
            album_title="",
            album_external_url=request.source_url,
            notes="For My Pain... - Encyclopaedia Metallum: The Metal Archives",
        )

    def create_artist_draft(self, request, *, model):  # type: ignore[override]
        return ArtistDraftData(
            artist_name=request.artist_name or "For My Pain...",
            description=None,
            description_source_url=request.source_url,
            description_source_label="www.metal-archives.com",
            external_url=request.source_url,
            origin="Finland, Oulu",
            genre="Gothic Metal/Rock",
        )

    def generate_album_overview(self, album: AlbumDetailRecord, *, language: str, model: str) -> str:  # type: ignore[override]
        return ""


def test_manual_album_create_and_render_pages(client) -> None:
    genre_response = client.post("/api/genres", json={"name": "Black Metal"})
    assert genre_response.status_code == 200

    response = client.post(
        "/api/albums",
        json={
            "artist_name": "Scythe of Mephisto",
            "artist_description": "Atmospheric black metal band.",
            "artist_description_source_url": "https://example.com/wiki",
            "artist_description_source_label": "Wikipedia",
            "album_external_url": "https://example.com/album",
            "title": "Till Life Do Us Part - EP",
            "release_year": 2026,
            "genre": "Black Metal",
            "rating": 8,
            "duration_seconds": 2540,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": "Debut EP",
            "tracks": [
                {"track_number": 1, "title": "Ashen Dawn", "duration_seconds": 180, "position": 1},
                {"track_number": 2, "title": "Night Procession", "duration_seconds": 166, "position": 2},
            ],
        },
    )

    assert response.status_code == 200
    album_id = response.json()["id"]

    albums_page = client.get("/albums")
    details_page = client.get(f"/albums/{album_id}")
    artists_page = client.get("/artists")
    genres_page = client.get("/genres")
    artists_api = client.get("/api/artists").json()
    artist_id = artists_api[0]["id"]
    artist_detail_page = client.get(f"/artists/{artist_id}")

    assert albums_page.status_code == 200
    assert 'href="/bookmarks"' in albums_page.text
    assert "Genre" in albums_page.text
    assert '<option value="Black Metal">Black Metal</option>' in albums_page.text
    assert "Till Life Do Us Part - EP" in albums_page.text
    assert "Scythe of Mephisto • 2026" in albums_page.text
    assert "Black Metal" in albums_page.text
    assert "8/10" in albums_page.text
    assert details_page.status_code == 200
    assert "Tracklist" in details_page.text
    assert "Night Procession" in details_page.text
    assert "Album Description" in details_page.text
    assert "Debut EP" in details_page.text
    assert "8/10" in details_page.text
    assert 'class="secondary album-bookmark-toggle"' in details_page.text
    assert f'href="/artists/{artist_id}"' in details_page.text
    assert artists_page.status_code == 200
    assert genres_page.status_code == 200
    assert "Managed Genres" in genres_page.text
    assert "Black Metal" in genres_page.text
    assert artist_detail_page.status_code == 200
    assert "MORE" in artists_page.text
    assert "Scythe of Mephisto" in artists_page.text
    assert 'class="artist-card"' in artists_page.text
    assert "Album Details" not in artists_page.text
    assert f'href="/artists/{artist_id}"' in artists_page.text
    assert "Album Import" in artist_detail_page.text
    assert ".aa-tab.active" in artist_detail_page.text
    assert 'class="aa-tab secondary active" data-tab="import" aria-pressed="true"' in artist_detail_page.text
    assert 'class="aa-tab secondary" data-tab="manual" aria-pressed="false"' in artist_detail_page.text
    assert "Please provide a proper Metal Archives album URL" in artist_detail_page.text
    assert "Use a Metal Archives album page URL from /albums/" in artist_detail_page.text
    assert "Album Import" not in albums_page.text
    assert "Album Import" not in artists_page.text
    assert 'class="secondary album-bookmark-toggle"' in albums_page.text
    assert f'href="/albums/{album_id}"' in artist_detail_page.text
    assert "artistAlbumImportForm.addEventListener" not in artists_page.text


def test_album_detail_refresh_source_url_is_hidden_until_refresh_panel_opens(client) -> None:
    album = _create_album(client, artist_name="Vanir", title="Wyrd")
    page = client.get(f"/albums/{album['id']}")

    assert page.status_code == 200
    assert 'id="albumRefreshBtn"' in page.text
    assert 'id="albumRefreshSourcePanel" class="hidden"' in page.text
    assert 'id="albumRefreshUrlInput"' in page.text


def test_albums_page_initially_shows_only_20_most_recently_added(client) -> None:
    for index in range(21):
        _create_album(client, artist_name="Band", title=f"Album {index:02d}")

    page = client.get("/albums")

    assert page.status_code == 200
    assert 'id="albumRecentHint"' in page.text
    assert page.text.count('class="album-card hidden"') == 1
    assert 'data-recent-index="0"' in page.text
    assert 'data-recent-index="20"' in page.text


def test_artists_page_initially_shows_only_20_most_recently_added(client) -> None:
    for index in range(21):
        _create_album(client, artist_name=f"Band {index:02d}", title="Debut")

    page = client.get("/artists")

    assert page.status_code == 200
    assert 'id="artistFilterHint"' in page.text
    assert page.text.count('class="artist-card hidden"') == 1
    assert 'data-recent-index="0"' in page.text
    assert 'data-recent-index="20"' in page.text


def test_genres_page_supports_manual_create_and_delete(client) -> None:
    created = client.post("/api/genres", json={"name": "Gothic Metal"})

    assert created.status_code == 200
    genre_id = created.json()["id"]
    assert client.get("/genres").status_code == 200
    assert client.get("/api/genres").json()[0]["name"] == "Gothic Metal"

    deleted = client.delete(f"/api/genres/{genre_id}")

    assert deleted.status_code == 200
    assert client.get("/api/genres").json() == []


def test_genres_can_be_renamed(client) -> None:
    created = client.post("/api/genres", json={"name": "Gothic Metal"})
    genre_id = created.json()["id"]

    updated = client.put(f"/api/genres/{genre_id}", json={"name": "Dark Metal"})

    assert updated.status_code == 200
    assert updated.json()["name"] == "Dark Metal"
    assert client.get("/api/genres").json()[0]["name"] == "Dark Metal"


def test_artist_page_album_import_rejects_metal_archives_artist_url(client) -> None:
    response = client.post(
        "/api/import/album",
        json={
            "artist_name": "For My Pain...",
            "album_title": None,
            "source_url": "https://www.metal-archives.com/bands/For_My_Pain.../6406",
        },
    )

    assert response.status_code == 400
    assert "Metal Archives album URL" in response.text
    assert "/albums/" in response.text


def test_import_confirm_uses_edited_payload_and_downloads_cover(client) -> None:
    draft_response = client.post(
        "/api/import/album",
        json={
            "artist_name": "Scythe of Mephisto",
            "album_title": "Till Life Do Us Part - EP",
            "source_url": "https://example.com/wiki",
        },
    )

    assert draft_response.status_code == 200
    draft = draft_response.json()["draft"]
    confirm = client.post(
        f"/api/import/{draft['id']}/confirm",
        json={
            "target_type": "album",
            "chosen_source_url": "https://example.com/wiki",
            "payload": {
                "artist_name": "Scythe of Mephisto",
                "artist_description": "Edited description from user review",
                "artist_description_source_url": "https://example.com/wiki",
                "artist_description_source_label": "Wikipedia",
                "album_external_url": "https://example.com/album",
                "title": "Till Life Do Us Part - EP",
                "release_year": 2026,
                "genre": "Alternative Rock",
                "duration_seconds": 1999,
                "cover_image_path": None,
                "cover_source_url": "https://example.com/cover.jpg",
                "notes": "Edited notes",
                "tracks": [
                    {"track_number": 1, "title": "Edited Track", "duration_seconds": 150, "position": 1}
                ],
            },
        },
    )

    assert confirm.status_code == 200
    payload = confirm.json()
    assert payload["draft"]["status"] == "confirmed"
    assert payload["album"]["genre"] == "Alternative Rock"
    assert payload["album"]["artist_description"] == "Edited description from user review"
    assert payload["album"]["cover_image_path"].endswith(".jpg")
    assert payload["album"]["tracks"][0]["title"] == "Edited Track"


def test_lists_page_supports_create_add_and_reorder(client) -> None:
    first = client.post(
        "/api/albums",
        json={
            "artist_name": "Band A",
            "title": "Record One",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1000,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    second = client.post(
        "/api/albums",
        json={
            "artist_name": "Band B",
            "title": "Record Two",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1001,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()

    created_list = client.post(
        "/api/lists",
        json={"name": "Top 2026 Black Metal", "description": "Ranking", "year": 2026, "genre_filter_hint": "Black Metal"},
    )
    list_id = created_list.json()["id"]
    client.post(f"/api/lists/{list_id}/items", json={"album_id": first["id"]})
    list_response = client.post(f"/api/lists/{list_id}/items", json={"album_id": second["id"]})

    assert list_response.status_code == 200
    item_ids = [item["id"] for item in list_response.json()["items"]]

    reorder = client.post(f"/api/lists/{list_id}/items/reorder", json={"item_ids": list(reversed(item_ids))})
    lists_page = client.get("/lists")
    list_detail_page = client.get(f"/lists/{list_id}")

    assert reorder.status_code == 200
    assert reorder.json()["items"][0]["album"]["title"] == "Record Two"
    assert lists_page.status_code == 200
    assert list_detail_page.status_code == 200
    assert f'href="/lists/{list_id}"' in lists_page.text
    assert "Add Album To List" not in lists_page.text
    assert "Add Album To List" not in list_detail_page.text
    assert "Save Details" in list_detail_page.text
    assert "Search albums" in lists_page.text
    assert "Save" in list_detail_page.text
    assert "Top 2026 Black Metal" in lists_page.text
    assert 'value="Band B - Record Two"' not in list_detail_page.text


def test_list_details_can_be_renamed(client) -> None:
    created_list = client.post(
        "/api/lists",
        json={"name": "Top 2026 Black Metal", "description": "Ranking", "year": 2026, "genre_filter_hint": "Black Metal"},
    )
    list_id = created_list.json()["id"]

    updated = client.put(
        f"/api/lists/{list_id}",
        json={"name": "Top 2026 Gothic Metal", "description": "Updated", "year": 2026, "genre_filter_hint": "Gothic Metal"},
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == "Top 2026 Gothic Metal"
    assert client.get(f"/lists/{list_id}").status_code == 200


def test_album_description_renders_imported_notes_on_separate_lines(client) -> None:
    response = client.post(
        "/api/albums",
        json={
            "artist_name": "Vanir",
            "title": "Wyrd",
            "release_year": 2026,
            "genre": "Folk Metal",
            "duration_seconds": 2725,
            "cover_image_path": None,
            "cover_source_url": None,
            "album_external_url": "https://example.com/album",
            "notes": "Type: Full-length; Release date: April 3rd, 2026; Label: Target Records. Recording information: Mixed and mastered at Demigod Recordings.",
            "tracks": [],
        },
    )

    album_id = response.json()["id"]
    details_page = client.get(f"/albums/{album_id}")

    assert details_page.status_code == 200
    assert "Type: Full-length;\nRelease date: April 3rd, 2026;" in details_page.text
    assert "Label: Target Records.\nRecording information: Mixed and mastered at Demigod Recordings." in details_page.text


def test_list_item_can_be_removed_and_positions_are_compacted(client) -> None:
    first = client.post(
        "/api/albums",
        json={
            "artist_name": "Band A",
            "title": "Record One",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1000,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    second = client.post(
        "/api/albums",
        json={
            "artist_name": "Band B",
            "title": "Record Two",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1001,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    created_list = client.post(
        "/api/lists",
        json={"name": "Top 2026 Black Metal", "description": "Ranking", "year": 2026, "genre_filter_hint": "Black Metal"},
    )
    list_id = created_list.json()["id"]
    client.post(f"/api/lists/{list_id}/items", json={"album_id": first["id"]})
    list_response = client.post(f"/api/lists/{list_id}/items", json={"album_id": second["id"]})
    first_item_id = list_response.json()["items"][0]["id"]

    removed = client.delete(f"/api/lists/{list_id}/items/{first_item_id}")

    assert removed.status_code == 200
    items = removed.json()["items"]
    assert len(items) == 1
    assert items[0]["album"]["title"] == "Record Two"
    assert items[0]["rank_position"] == 1


def test_settings_page_updates_active_model(client) -> None:
    settings_response = client.put("/api/settings", json={"active_model": "gpt-5.4-mini"})
    settings_page = client.get("/settings")

    assert settings_response.status_code == 200
    assert settings_response.json()["active_model"] == "gpt-5.4-mini"
    assert settings_page.status_code == 200
    assert "gpt-5.4-mini" in settings_page.text


def test_patch_album_rating(client) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Vanir",
            "title": "Wyrd",
            "release_year": 2026,
            "genre": "Folk Metal",
            "duration_seconds": 2725,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    album_id = album["id"]

    patched = client.patch(f"/api/albums/{album_id}/rating", json={"rating": 9})
    assert patched.status_code == 200
    assert patched.json()["rating"] == 9

    cleared = client.patch(f"/api/albums/{album_id}/rating", json={"rating": None})
    assert cleared.status_code == 200
    assert cleared.json()["rating"] is None


def test_bookmarks_page_and_listened_workflow(client) -> None:
    album = _create_album(client, artist_name="Vanir", title="Wyrd")
    album_id = album["id"]

    bookmarked = client.patch(f"/api/albums/{album_id}/bookmark", json={"bookmarked": True})
    bookmarks_page = client.get("/bookmarks")

    assert bookmarked.status_code == 200
    assert bookmarked.json()["bookmarked_at"] is not None
    assert bookmarked.json()["listened_at"] is None
    assert bookmarks_page.status_code == 200
    assert "Wyrd" in bookmarks_page.text
    assert 'data-remove-on-listened="true"' in bookmarks_page.text
    assert 'class="secondary album-bookmark-toggle"' not in bookmarks_page.text
    assert "move-up" not in bookmarks_page.text
    assert "Album Import" not in bookmarks_page.text

    listened = client.patch(f"/api/albums/{album_id}/listened", json={"listened": True})
    bookmarks_after_listened = client.get("/bookmarks")
    album_after_listened = client.get(f"/api/albums/{album_id}").json()

    assert listened.status_code == 200
    assert listened.json()["listened_at"] is not None
    assert listened.json()["bookmarked_at"] is not None
    assert album_after_listened["title"] == "Wyrd"
    assert "Wyrd" not in bookmarks_after_listened.text
    assert "No bookmarked albums yet" in bookmarks_after_listened.text

    unlistened = client.patch(f"/api/albums/{album_id}/listened", json={"listened": False})
    assert unlistened.status_code == 200
    assert unlistened.json()["listened_at"] is None
    assert unlistened.json()["bookmarked_at"] is not None
    assert "Wyrd" in client.get("/bookmarks").text

    unbookmarked = client.patch(f"/api/albums/{album_id}/bookmark", json={"bookmarked": False})
    assert unbookmarked.status_code == 200
    assert unbookmarked.json()["bookmarked_at"] is None
    assert "Wyrd" not in client.get("/bookmarks").text


def test_bookmark_and_listened_missing_album_returns_404(client) -> None:
    bookmark = client.patch("/api/albums/99999/bookmark", json={"bookmarked": True})
    listened = client.patch("/api/albums/99999/listened", json={"listened": True})

    assert bookmark.status_code == 404
    assert listened.status_code == 404


def test_bookmarked_album_detail_shows_single_mark_listened_action(client) -> None:
    album = _create_album(client, artist_name="Vanir", title="Wyrd")
    album_id = album["id"]
    client.patch(f"/api/albums/{album_id}/bookmark", json={"bookmarked": True})

    page = client.get(f"/albums/{album_id}")

    assert page.status_code == 200
    assert 'class="secondary album-listened-toggle"' in page.text
    assert 'class="secondary album-bookmark-toggle"' not in page.text
    assert "Mark Listened" in page.text


def test_list_pages_expose_album_bookmark_controls(client) -> None:
    album = _create_album(client, artist_name="Vanir", title="Wyrd")
    created_list = client.post("/api/lists", json={"name": "Listen Soon"})
    list_id = created_list.json()["id"]
    client.post(f"/api/lists/{list_id}/items", json={"album_id": album["id"]})

    lists_page = client.get("/lists")
    list_detail_page = client.get(f"/lists/{list_id}")

    assert lists_page.status_code == 200
    assert list_detail_page.status_code == 200
    assert 'class="secondary album-bookmark-toggle"' in lists_page.text
    assert 'class="secondary album-bookmark-toggle"' in list_detail_page.text


def test_upload_album_cover(client, tmp_path) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Scythe of Mephisto",
            "title": "Primeval Rites",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1800,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    album_id = album["id"]

    fake_image = b"\xff\xd8\xff\xe0fake-jpeg-content"
    response = client.post(
        f"/api/albums/{album_id}/cover",
        files={"file": ("cover.jpg", fake_image, "image/jpeg")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["cover_image_path"] is not None
    assert data["cover_image_path"].endswith(".jpg")


def test_album_detail_cover_hover_label_matches_cover_state(client) -> None:
    missing_cover_album = _create_album(client, artist_name="Band X", title="No Cover")
    existing_cover_album = client.post(
        "/api/albums",
        json={
            "artist_name": "Band Y",
            "title": "Has Cover",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 1800,
            "cover_image_path": "/tmp/album-cover.jpg",
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()

    missing_cover_page = client.get(f"/albums/{missing_cover_album['id']}")
    existing_cover_page = client.get(f"/albums/{existing_cover_album['id']}")

    assert missing_cover_page.status_code == 200
    assert existing_cover_page.status_code == 200
    assert "Upload cover" in missing_cover_page.text
    assert "Change cover" in existing_cover_page.text


def test_upload_album_cover_rejects_unsupported_type(client) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Band X",
            "title": "Demo",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 600,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()

    response = client.post(
        f"/api/albums/{album['id']}/cover",
        files={"file": ("cover.gif", b"GIF89a", "image/gif")},
    )

    assert response.status_code == 400


def test_artist_origin_is_stored_and_returned(client) -> None:
    response = client.post(
        "/api/artists",
        json={
            "name": "Mumford & Sons",
            "description": "British folk rock band.",
            "description_source_url": "https://en.wikipedia.org/wiki/Mumford_%26_Sons",
            "description_source_label": "Wikipedia",
            "external_url": "https://mumfordandsons.com",
            "origin": "London, UK",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["origin"] == "London, UK"

    fetched = next(a for a in client.get("/api/artists").json() if a["id"] == data["id"])
    assert fetched["origin"] == "London, UK"

    updated = client.put(
        f"/api/artists/{data['id']}",
        json={
            "name": "Mumford & Sons",
            "description": "British folk rock band.",
            "description_source_url": None,
            "description_source_label": None,
            "external_url": None,
            "origin": "London, England",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["origin"] == "London, England"

    artist_detail_page = client.get(f"/artists/{data['id']}")
    assert "London, England" in artist_detail_page.text

def test_confirm_artist_import_updates_existing_artist_instead_of_crashing(client) -> None:
    existing = client.post(
        "/api/artists",
        json={
            "name": "Vanir",
            "description": "Existing description",
            "description_source_url": "https://example.com/old",
            "description_source_label": "old",
            "external_url": "https://example.com/old-artist",
        },
    )
    assert existing.status_code == 200

    draft_response = client.post(
        "/api/import/artist",
        json={
            "artist_name": "Vanir",
            "source_url": "https://example.com/new",
        },
    )
    draft_id = draft_response.json()["draft"]["id"]

    confirm = client.post(
        f"/api/import/{draft_id}/confirm",
        json={
            "target_type": "artist",
            "chosen_source_url": "https://example.com/new",
            "payload": {
                "name": "Vanir",
                "description": "Updated description",
                "description_source_url": "https://example.com/new",
                "description_source_label": "new",
                "external_url": "https://example.com/new-artist",
            },
        },
    )

    assert confirm.status_code == 200
    assert confirm.json()["artist"]["name"] == "Vanir"
    assert confirm.json()["artist"]["description"] == "Updated description"


def test_confirm_album_import_derives_cover_from_album_external_url(client, monkeypatch) -> None:
    draft_response = client.post(
        "/api/import/album",
        json={
            "artist_name": "Vanir",
            "album_title": "Wyrd",
            "source_url": "https://example.com/album-page",
        },
    )
    draft_id = draft_response.json()["draft"]["id"]

    import album_ranker.app as app_module

    monkeypatch.setattr(
        app_module,
        "infer_cover_source_url_from_album_url",
        lambda url: "https://example.com/discovered-cover.jpg",
    )

    confirm = client.post(
        f"/api/import/{draft_id}/confirm",
        json={
            "target_type": "album",
            "chosen_source_url": "https://example.com/album-page",
            "payload": {
                "artist_name": "Vanir",
                "artist_description": None,
                "artist_description_source_url": "https://example.com/album-page",
                "artist_description_source_label": "example.com",
                "album_external_url": "https://example.com/album-page",
                "title": "Wyrd",
                "release_year": 2026,
                "genre": "Black Metal",
                "duration_seconds": 1000,
                "cover_image_path": None,
                "cover_source_url": None,
                "notes": None,
                "tracks": [],
            },
        },
    )

    assert confirm.status_code == 200
    assert confirm.json()["album"]["cover_source_url"] == "https://example.com/discovered-cover.jpg"
    assert confirm.json()["album"]["cover_image_path"].endswith(".jpg")


def test_manual_album_create_derives_cover_from_album_external_url(client, monkeypatch) -> None:
    import album_ranker.app as app_module

    monkeypatch.setattr(
        app_module,
        "infer_cover_source_url_from_album_url",
        lambda url: "https://example.com/manual-cover.jpg",
    )

    response = client.post(
        "/api/albums",
        json={
            "artist_name": "Vanir",
            "title": "Wyrd",
            "release_year": 2026,
            "genre": "Black Metal",
            "duration_seconds": 2725,
            "album_external_url": "https://example.com/album-page",
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["cover_source_url"] == "https://example.com/manual-cover.jpg"
    assert response.json()["cover_image_path"].endswith(".jpg")


def test_confirm_album_import_updates_existing_album_instead_of_creating_duplicate(client) -> None:
    existing = client.post(
        "/api/albums",
        json={
            "artist_name": "Vanir",
            "title": "Wyrd",
            "release_year": 2026,
            "genre": None,
            "duration_seconds": None,
            "album_external_url": "https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    )
    assert existing.status_code == 200
    existing_id = existing.json()["id"]

    draft_response = client.post(
        "/api/import/album",
        json={
            "artist_name": "Vanir",
            "album_title": "Wyrd",
            "source_url": "https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
        },
    )
    draft_id = draft_response.json()["draft"]["id"]

    confirm = client.post(
        f"/api/import/{draft_id}/confirm",
        json={
            "target_type": "album",
            "chosen_source_url": "https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
            "payload": {
                "artist_name": "Vanir",
                "artist_description": None,
                "artist_description_source_url": "https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
                "artist_description_source_label": "www.metal-archives.com",
                "album_external_url": "https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
                "title": "Wyrd",
                "release_year": 2026,
                "genre": "Folk Metal",
                "duration_seconds": 2725,
                "cover_image_path": None,
                "cover_source_url": "https://example.com/cover.jpg",
                "notes": "Updated import",
                "tracks": [{"track_number": 1, "title": "Against the Storm", "duration_seconds": 234, "position": 1}],
            },
        },
    )

    assert confirm.status_code == 200
    assert confirm.json()["album"]["id"] == existing_id
    albums = client.get("/api/albums").json()
    assert len(albums) == 1


def test_delete_album_removes_existing_record(client) -> None:
    created = client.post(
        "/api/albums",
        json={
            "artist_name": "Vanir",
            "title": "Wyrd",
            "release_year": 2026,
            "genre": "Folk Metal",
            "duration_seconds": 2725,
            "album_external_url": None,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    )
    album_id = created.json()["id"]

    deleted = client.delete(f"/api/albums/{album_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get(f"/api/albums/{album_id}").status_code == 404


def test_delete_artist_removes_existing_artist_and_albums(client) -> None:
    created = client.post(
        "/api/albums",
        json={
            "artist_name": "Vanir",
            "title": "Wyrd",
            "release_year": 2026,
            "genre": "Folk Metal",
            "duration_seconds": 2725,
            "album_external_url": None,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    )
    album_id = created.json()["id"]
    artist_id = client.get("/api/artists").json()[0]["id"]

    # Cannot delete artist while albums exist
    blocked = client.delete(f"/api/artists/{artist_id}")
    assert blocked.status_code == 409
    assert "album" in blocked.json()["detail"].lower()

    # Delete the album first, then the artist
    client.delete(f"/api/albums/{album_id}")
    deleted = client.delete(f"/api/artists/{artist_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get("/api/artists").json() == []


def test_delete_list_removes_existing_list(client) -> None:
    created_list = client.post(
        "/api/lists",
        json={"name": "Top 2026 Black Metal", "description": "Ranking", "year": 2026, "genre_filter_hint": "Black Metal"},
    )
    list_id = created_list.json()["id"]

    deleted = client.delete(f"/api/lists/{list_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get("/api/lists").json() == []


# ── JS safety: no raw _escape() injected into script blocks ──────────────────

def test_album_detail_page_script_blocks_are_valid_when_description_has_special_chars(client) -> None:
    """Artist description with newlines / quotes must not break JS on the album detail page."""
    album = _create_album(
        client,
        artist_name='Band "With" Quotes',
        title="My Album",
        description='Line one.\nLine two with "quotes" and \\backslashes\\.',
    )
    page = client.get(f"/albums/{album['id']}")
    assert page.status_code == 200
    scripts = _script_blocks(page.text)
    assert 'Line one.\nLine two' not in scripts


def test_artist_detail_page_script_blocks_are_valid_when_description_has_special_chars(client) -> None:
    """Artist description with newlines and double-quotes must not break JS on the artist detail page."""
    album = _create_album(
        client,
        artist_name='Band "Tricky"',
        description='Line one.\nLine two.\n"Quoted section".',
    )
    artists = client.get("/api/artists").json()
    artist_id = artists[0]["id"]

    page = client.get(f"/artists/{artist_id}")
    assert page.status_code == 200
    scripts = _script_blocks(page.text)
    assert 'Line one.\nLine two' not in scripts


# ── import-confirm redirects to album page ────────────────────────────────────

def test_import_confirm_album_returns_album_id_for_redirect(client) -> None:
    """Confirm response must include album.id so the UI can navigate to /albums/{id}."""
    draft = client.post(
        "/api/import/album",
        json={
            "artist_name": "Scythe of Mephisto",
            "album_title": "Till Life Do Us Part - EP",
            "source_url": "https://example.com/album",
        },
    ).json()["draft"]

    confirm = client.post(
        f"/api/import/{draft['id']}/confirm",
        json={
            "target_type": "album",
            "chosen_source_url": "https://example.com/album",
            "payload": {
                "artist_name": "Scythe of Mephisto",
                "artist_description": None,
                "artist_description_source_url": None,
                "artist_description_source_label": None,
                "album_external_url": "https://example.com/album",
                "title": "Till Life Do Us Part - EP",
                "release_year": 2026,
                "genre": "Black Metal",
                "duration_seconds": 1800,
                "cover_image_path": None,
                "cover_source_url": None,
                "notes": None,
                "tracks": [],
            },
        },
    )

    assert confirm.status_code == 200
    body = confirm.json()
    assert body["album"] is not None
    assert isinstance(body["album"]["id"], int)
    album_page = client.get(f"/albums/{body['album']['id']}")
    assert album_page.status_code == 200


def test_album_with_missing_artist_import_returns_two_drafts(client, monkeypatch) -> None:
    import album_ranker.app as app_module
    from album_ranker.schemas import AlbumDraftData

    monkeypatch.setattr(
        app_module,
        "metal_archives_artist_url_from_album_url",
        lambda url: "https://www.metal-archives.com/bands/For_My_Pain.../1020",
    )
    monkeypatch.setattr(
        app_module,
        "metal_archives_album_draft_from_url",
        lambda request: AlbumDraftData(
            artist_name="For My Pain...",
            album_external_url=request.source_url,
            album_type="Full-length",
            album_title="Buried Blue",
            release_year=2026,
            duration_seconds=3092,
            cover_source_url="https://www.metal-archives.com/images/1/3/9/1/1391127.jpg?3823",
            notes="Label: Rainheart Productions\nFormat: Digital",
            tracks=[
                {"track_number": 1, "title": "Hungry for Desire", "duration_seconds": 251},
                {"track_number": 2, "title": "Windows Are Weeping", "duration_seconds": 271},
            ],
        ),
    )

    response = client.post(
        "/api/import/album-with-artist",
        json={
            "artist_name": "",
            "album_title": None,
            "source_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artist_exists"] is False
    assert body["artist_source_url"] == "https://www.metal-archives.com/bands/For_My_Pain.../1020"
    assert body["artist_draft"]["target_type"] == "artist"
    assert body["artist_draft"]["draft_payload"]["artist_name"] == "For My Pain..."
    assert body["artist_draft"]["draft_payload"]["genre"] == "Gothic Metal"
    assert body["album_draft"]["target_type"] == "album"
    assert body["album_draft"]["draft_payload"]["artist_name"] == "For My Pain..."
    assert body["album_draft"]["draft_payload"]["album_title"] == "Buried Blue"
    assert body["album_draft"]["draft_payload"]["release_year"] == 2026
    assert body["album_draft"]["draft_payload"]["duration_seconds"] == 3092
    assert body["album_draft"]["draft_payload"]["album_type"] == "Full-length"
    assert body["album_draft"]["draft_payload"]["notes"] == "Label: Rainheart Productions\nFormat: Digital"
    assert body["album_draft"]["draft_payload"]["tracks"][0]["title"] == "Hungry for Desire"


def test_album_with_artist_import_repairs_sparse_ai_draft_with_real_metal_archives_html(settings, monkeypatch) -> None:
    import album_ranker.importer as importer_module

    album_url = "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127"
    artist_url = "https://www.metal-archives.com/bands/For_My_Pain.../6406"
    album_html = """
    <html>
      <head><title>For My Pain... - Buried Blue - Encyclopaedia Metallum: The Metal Archives</title></head>
      <body>
        <a class="image" id="cover" href="https://www.metal-archives.com/images/1/3/9/1/1391127.jpg?3823">
          <img src="https://www.metal-archives.com/images/1/3/9/1/1391127.jpg?3823" />
        </a>
        <div id="album_info">
          <h1 class="album_name"><a href="https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127">Buried Blue</a></h1>
          <h2 class="band_name"><a href="https://www.metal-archives.com/bands/For_My_Pain.../6406">For My Pain...</a></h2>
          <dl class="float_left">
            <dt>Type:</dt><dd>Full-length</dd>
            <dt>Release date:</dt><dd>January 9th, 2026</dd>
          </dl>
          <dl class="float_right">
            <dt>Label:</dt><dd>Rainheart Productions</dd>
            <dt>Format:</dt><dd>Digital</dd>
          </dl>
        </div>
        <table class="display table_lyrics">
          <tr class="even"><td width="20"><a name="8038837" class="anchor"> </a>1.</td><td class="wrapWords">Hungry for Desire</td><td align="right">04:11</td><td></td></tr>
          <tr class="odd"><td width="20"><a name="8038838" class="anchor"> </a>2.</td><td class="wrapWords">Windows Are Weeping</td><td align="right">04:31</td><td></td></tr>
          <tr><td colspan="2"></td><td align="right"><strong>51:32</strong></td><td></td></tr>
        </table>
      </body>
    </html>
    """
    artist_html = """
    <html>
      <head><title>For My Pain... - Encyclopaedia Metallum: The Metal Archives</title></head>
      <body>
        <h1 class="band_name"><a href="/bands/For_My_Pain.../6406">For My Pain...</a></h1>
        <dl><dt>Genre:</dt><dd>Gothic Metal/Rock</dd></dl>
      </body>
    </html>
    """

    def fake_fetch(url: str) -> tuple[str, str]:
        if url == album_url:
            return album_html, "text/html"
        if url == artist_url:
            return artist_html, "text/html"
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(importer_module, "_fetch_url_document", fake_fetch)
    app = create_app(settings, importer=SparseAlbumImporter(), cover_downloader=CoverDownloader(settings.cover_dir))
    local_client = TestClient(app)

    response = local_client.post(
        "/api/import/album-with-artist",
        json={"artist_name": "", "album_title": None, "source_url": album_url},
    )

    assert response.status_code == 200
    payload = response.json()["album_draft"]["draft_payload"]
    assert payload["artist_name"] == "For My Pain..."
    assert payload["album_title"] == "Buried Blue"
    assert payload["release_year"] == 2026
    assert payload["duration_seconds"] == 3092
    assert payload["cover_source_url"] == "https://www.metal-archives.com/images/1/3/9/1/1391127.jpg?3823"
    assert payload["album_type"] == "Full-length"
    assert payload["genre"] == "Gothic Metal/Rock"
    assert payload["notes"] == "Label: Rainheart Productions\nFormat: Digital"
    assert payload["tracks"][0]["title"] == "Hungry for Desire"


def test_album_with_artist_import_rejects_metal_archives_artist_url(client) -> None:
    response = client.post(
        "/api/import/album-with-artist",
        json={
            "artist_name": "",
            "album_title": None,
            "source_url": "https://www.metal-archives.com/bands/For_My_Pain.../6406",
        },
    )

    assert response.status_code == 400
    assert "/albums/" in response.text


def test_album_with_existing_artist_import_skips_artist_draft(client, monkeypatch) -> None:
    import album_ranker.app as app_module

    client.post(
        "/api/artists",
        json={
            "name": "For My Pain...",
            "description": None,
            "description_source_url": None,
            "description_source_label": None,
            "external_url": "https://www.metal-archives.com/bands/For_My_Pain.../1020",
            "origin": None,
        },
    )
    monkeypatch.setattr(
        app_module,
        "metal_archives_artist_url_from_album_url",
        lambda url: "https://www.metal-archives.com/bands/For_My_Pain.../1020",
    )

    response = client.post(
        "/api/import/album-with-artist",
        json={
            "artist_name": "",
            "album_title": None,
            "source_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artist_exists"] is True
    assert body["artist_draft"] is None
    assert body["album_draft"]["draft_payload"]["artist_name"] == "For My Pain..."


def test_album_with_artist_confirm_creates_artist_and_album(client, monkeypatch) -> None:
    import album_ranker.app as app_module

    monkeypatch.setattr(
        app_module,
        "metal_archives_artist_url_from_album_url",
        lambda url: "https://www.metal-archives.com/bands/For_My_Pain.../1020",
    )
    draft_response = client.post(
        "/api/import/album-with-artist",
        json={
            "artist_name": "",
            "album_title": None,
            "source_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
        },
    ).json()

    confirm = client.post(
        "/api/import/album-with-artist/confirm",
        json={
            "artist_draft_id": draft_response["artist_draft"]["id"],
            "artist_chosen_source_url": "https://www.metal-archives.com/bands/For_My_Pain.../1020",
            "artist_payload": {
                "name": "For My Pain...",
                "description": "Edited artist description",
                "description_source_url": "https://www.metal-archives.com/bands/For_My_Pain.../1020",
                "description_source_label": "www.metal-archives.com",
                "external_url": "https://www.metal-archives.com/bands/For_My_Pain.../1020",
                "origin": "Finland, Oulu",
            },
            "album_draft_id": draft_response["album_draft"]["id"],
            "album_chosen_source_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
            "album_payload": {
                "artist_name": "For My Pain...",
                "artist_description": "Edited artist description",
                "artist_description_source_url": "https://www.metal-archives.com/bands/For_My_Pain.../1020",
                "artist_description_source_label": "www.metal-archives.com",
                "album_external_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
                "album_stream_url": None,
                "album_type": "Single",
                "title": "Buried Blue",
                "release_year": 2026,
                "genre": "Gothic Metal",
                "rating": None,
                "duration_seconds": 2520,
                "cover_image_path": None,
                "cover_source_url": None,
                "notes": "Imported",
                "tracks": [],
            },
        },
    )

    assert confirm.status_code == 200
    body = confirm.json()
    assert body["artist"]["external_url"] == "https://www.metal-archives.com/bands/For_My_Pain.../1020"
    assert body["album"]["id"]
    assert body["album"]["artist_name"] == "For My Pain..."
    assert client.get(f"/albums/{body['album']['id']}").status_code == 200


def test_album_with_artist_confirm_updates_existing_album(client, monkeypatch) -> None:
    import album_ranker.app as app_module

    existing = client.post(
        "/api/albums",
        json={
            "artist_name": "For My Pain...",
            "title": "Buried Blue",
            "release_year": 2025,
            "genre": "Gothic Metal",
            "duration_seconds": 200,
            "album_external_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": "Old",
            "tracks": [],
        },
    ).json()
    monkeypatch.setattr(
        app_module,
        "metal_archives_artist_url_from_album_url",
        lambda url: "https://www.metal-archives.com/bands/For_My_Pain.../1020",
    )
    draft_response = client.post(
        "/api/import/album-with-artist",
        json={
            "artist_name": "",
            "album_title": None,
            "source_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
        },
    ).json()

    confirm = client.post(
        "/api/import/album-with-artist/confirm",
        json={
            "album_draft_id": draft_response["album_draft"]["id"],
            "album_chosen_source_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
            "album_payload": {
                "artist_name": "For My Pain...",
                "artist_description": None,
                "artist_description_source_url": None,
                "artist_description_source_label": None,
                "album_external_url": "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
                "album_stream_url": None,
                "album_type": "Single",
                "title": "Buried Blue",
                "release_year": 2026,
                "genre": "Gothic Metal",
                "rating": None,
                "duration_seconds": 2520,
                "cover_image_path": None,
                "cover_source_url": None,
                "notes": "Updated",
                "tracks": [],
            },
        },
    )

    assert confirm.status_code == 200
    assert confirm.json()["album"]["id"] == existing["id"]
    assert confirm.json()["album"]["notes"] == "Updated"
    assert len(client.get("/api/albums").json()) == 1


def test_imports_page_renders_bundle_flow(client) -> None:
    page = client.get("/imports")

    assert page.status_code == 200
    assert 'href="/imports"' in page.text
    assert "Album URL Import" in page.text
    assert "Artist Draft" in page.text
    assert "Album Draft" in page.text
    assert "album.genre || artistGenre" in page.text
    assert 'id="bundleArtistName" name="artist_name" required disabled' in page.text
    assert "setArtistDraftEnabled(Boolean(artistDraft))" in page.text
    assert 'value("bundleArtistDraftId")' in page.text
    assert "Please provide a proper Metal Archives album URL" in page.text
    assert "Use the album page URL" in page.text
    assert "/api/import/album-with-artist" in page.text


# ── album refresh via import draft ───────────────────────────────────────────

def test_album_refresh_via_import_draft_then_put(client) -> None:
    """Simulates the new refresh flow: POST /api/import/album → review → PUT /api/albums/{id}."""
    album = _create_album(client, artist_name="Vanir", title="Wyrd")
    album_id = album["id"]

    draft_resp = client.post(
        "/api/import/album",
        json={"artist_name": "Vanir", "album_title": "Wyrd", "source_url": "https://example.com/album"},
    )
    assert draft_resp.status_code == 200
    draft_payload = draft_resp.json()["draft"]["draft_payload"]
    assert draft_payload["album_title"]

    updated = client.put(
        f"/api/albums/{album_id}",
        json={
            "artist_name": "Vanir",
            "title": draft_payload["album_title"],
            "release_year": draft_payload.get("release_year") or 2026,
            "genre": draft_payload.get("genre") or "Folk Metal",
            "duration_seconds": draft_payload.get("duration_seconds"),
            "album_type": draft_payload.get("album_type"),
            "cover_source_url": draft_payload.get("cover_source_url"),
            "cover_image_path": None,
            "album_external_url": draft_payload.get("album_external_url"),
            "album_stream_url": None,
            "artist_description": draft_payload.get("artist_description"),
            "artist_description_source_url": draft_payload.get("artist_description_source_url"),
            "artist_description_source_label": draft_payload.get("artist_description_source_label"),
            "artist_origin": None,
            "rating": None,
            "notes": draft_payload.get("notes"),
            "tracks": draft_payload.get("tracks") or [],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["title"] == draft_payload["album_title"]


# ── artist refresh via import draft ──────────────────────────────────────────

def test_artist_refresh_via_import_draft_then_put(client) -> None:
    """Simulates the new refresh flow: POST /api/import/artist → review → PUT /api/artists/{id}."""
    _create_album(client, artist_name="Vanir")
    artist_id = client.get("/api/artists").json()[0]["id"]

    draft_resp = client.post(
        "/api/import/artist",
        json={"artist_name": "Vanir", "source_url": "https://example.com/artist"},
    )
    assert draft_resp.status_code == 200
    draft_payload = draft_resp.json()["draft"]["draft_payload"]
    assert draft_payload["artist_name"]

    updated = client.put(
        f"/api/artists/{artist_id}",
        json={
            "name": draft_payload["artist_name"],
            "description": draft_payload.get("description"),
            "description_source_url": draft_payload.get("description_source_url"),
            "description_source_label": draft_payload.get("description_source_label"),
            "external_url": draft_payload.get("external_url"),
            "origin": draft_payload.get("origin"),
        },
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == draft_payload["artist_name"]


def test_generate_overview_returns_draft_text(client) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Green Carnation",
            "title": "A Dark Poem",
            "release_year": 2026,
            "genre": "Progressive Metal",
            "duration_seconds": 2200,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    album_id = album["id"]

    resp = client.post(
        f"/api/albums/{album_id}/overview/draft",
        json={"language": "en"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "overview" in data
    assert len(data["overview"]) > 0
    assert "Green Carnation" in data["overview"]


def test_generate_overview_invalid_language(client) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Test Band",
            "title": "Test Album",
            "release_year": 2025,
            "genre": "Metal",
            "duration_seconds": 1800,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    album_id = album["id"]

    resp = client.post(
        f"/api/albums/{album_id}/overview/draft",
        json={"language": "fr"},
    )
    assert resp.status_code == 422


def test_save_overview_persists_and_renders(client) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Opeth",
            "title": "Blackwater Park",
            "release_year": 2001,
            "genre": "Progressive Death Metal",
            "duration_seconds": 4000,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    album_id = album["id"]

    overview_text = "🎸 Album: Opeth — Blackwater Park\n\n📌 Description:\nA landmark album."
    patch_resp = client.patch(
        f"/api/albums/{album_id}/overview",
        json={"overview": overview_text},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["overview"] == overview_text

    page = client.get(f"/albums/{album_id}")
    assert page.status_code == 200
    assert "Blackwater Park" in page.text
    assert "A landmark album." in page.text


def test_save_overview_null_clears_it(client) -> None:
    album = client.post(
        "/api/albums",
        json={
            "artist_name": "Katatonia",
            "title": "The Great Cold Distance",
            "release_year": 2006,
            "genre": "Gothic Metal",
            "duration_seconds": 2800,
            "cover_image_path": None,
            "cover_source_url": None,
            "notes": None,
            "tracks": [],
        },
    ).json()
    album_id = album["id"]

    # Save an overview first
    client.patch(f"/api/albums/{album_id}/overview", json={"overview": "Some overview text."})

    # Now clear it
    patch_resp = client.patch(f"/api/albums/{album_id}/overview", json={"overview": None})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["overview"] is None

    page = client.get(f"/albums/{album_id}")
    assert page.status_code == 200
    assert "Some overview text." not in page.text


def test_generate_overview_missing_album(client) -> None:
    resp = client.post(
        "/api/albums/99999/overview/draft",
        json={"language": "en"},
    )
    assert resp.status_code == 404
