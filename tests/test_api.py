from __future__ import annotations


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
    assert details_page.status_code == 200
    assert "Tracklist" in details_page.text
    assert "Night Procession" in details_page.text
    assert "Album Description" in details_page.text
    assert "Debut EP" in details_page.text
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
    assert "Add Album To List" in list_detail_page.text
    assert "Save Details" in list_detail_page.text
    assert "Search and choose album" in list_detail_page.text
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

    deleted = client.delete(f"/api/artists/{artist_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get("/api/artists").json() == []
    assert client.get(f"/api/albums/{album_id}").status_code == 404


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
