from __future__ import annotations

from album_ranker.db import Database
from album_ranker.schemas import AlbumListUpsert, AlbumUpsert, ReorderListItemsRequest


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
        AlbumListUpsert(name="Top 2026 Black Metal", description="Best of the year", year=2026, genre_filter_hint="Black Metal")
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
