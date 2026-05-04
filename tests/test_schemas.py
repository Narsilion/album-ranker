from __future__ import annotations

import pytest
from pydantic import ValidationError

from album_ranker.schemas import AlbumUpsert, ArtistUpsert, GenreUpsert, OverviewSaveRequest, WriteupSaveRequest


def test_artist_and_genre_names_have_length_limits() -> None:
    too_long = "x" * 501

    with pytest.raises(ValidationError):
        ArtistUpsert(name=too_long)
    with pytest.raises(ValidationError):
        GenreUpsert(name=too_long)


def test_album_main_strings_have_length_limits() -> None:
    with pytest.raises(ValidationError):
        AlbumUpsert(
            artist_name="Artist",
            title="x" * 501,
            album_external_url="https://example.com/" + ("x" * 2_048),
            notes="ok",
            tracks=[],
        )

    with pytest.raises(ValidationError):
        AlbumUpsert(
            artist_name="Artist",
            title="Album",
            notes="x" * 32_001,
            tracks=[],
        )


def test_writeup_save_payloads_have_length_limits() -> None:
    too_long = "x" * 32_001

    with pytest.raises(ValidationError):
        WriteupSaveRequest(writeup=too_long)
    with pytest.raises(ValidationError):
        OverviewSaveRequest(overview=too_long)
