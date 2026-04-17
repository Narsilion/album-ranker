from __future__ import annotations

import re


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
    assert f'href="/artists/{artist_id}"' in details_page.text
    assert artists_page.status_code == 200
    assert genres_page.status_code == 200
    assert "Managed Genres" in genres_page.text
    assert "Black Metal" in genres_page.text
    assert artist_detail_page.status_code == 200
    assert "MORE" in artists_page.text
    assert "Scythe of Mephisto" in artists_page.text
    assert "Album Details" not in artists_page.text
    assert f'href="/artists/{artist_id}"' in artists_page.text
    assert "Album Import" in artist_detail_page.text
    assert "Album Import" not in albums_page.text
    assert "Album Import" not in artists_page.text
    assert f'href="/albums/{album_id}"' in artist_detail_page.text
    assert "artistAlbumImportForm.addEventListener" not in artists_page.text


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

