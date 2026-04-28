from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from album_ranker.app import create_app
from album_ranker.importer import CoverDownloader, MetadataImporter
from album_ranker.openai_client import OpenAIClientError
from album_ranker.schemas import AlbumDetailRecord, AlbumDraftData, ArtistDraftData, ImportRequest
from album_ranker.settings import Settings


class FakeImporter(MetadataImporter):
    def __init__(self) -> None:
        super().__init__(client=None)

    def create_artist_draft(self, request: ImportRequest, *, model: str):  # type: ignore[override]
        return ArtistDraftData(
            artist_name=request.artist_name or "For My Pain...",
            description="Genre: Gothic Metal\nA precise artist description",
            description_source_url=request.source_url or "https://example.com/artist",
            description_source_label="example.com",
            external_url=request.source_url or "https://example.com/artist",
            origin="Finland, Oulu",
            genre="Gothic Metal",
        )

    def create_album_draft(self, request: ImportRequest, *, model: str):  # type: ignore[override]
        return AlbumDraftData(
            artist_name=request.artist_name or "For My Pain...",
            artist_description="A precise description",
            artist_description_source_url=request.source_url or "https://example.com/source",
            artist_description_source_label="example.com",
            album_external_url="https://example.com/album",
            album_title=request.album_title or "Untitled",
            release_year=2026,
            genre="Black Metal",
            duration_seconds=2520,
            cover_source_url="https://example.com/cover.jpg",
            notes="Imported draft notes",
            tracks=[
                {"track_number": 1, "title": "First Track", "duration_seconds": 180},
                {"track_number": 2, "title": "Second Track", "duration_seconds": 220},
            ],
        )

    def generate_album_overview(self, album: AlbumDetailRecord, *, language: str, model: str) -> str:  # type: ignore[override]
        lang_tag = "RU" if language == "ru" else "EN"
        return (
            f"🎸 Album: {album.artist_name} — {album.title}\n\n"
            f"📅 Release date: {album.release_year or 'unknown'}\n\n"
            f"🎶 Genre: {album.genre or 'unknown'}\n\n"
            f"📌 Description:\nTest overview in {lang_tag}."
        )


class FakeCoverDownloader(CoverDownloader):
    def __init__(self, cover_dir: Path) -> None:
        super().__init__(cover_dir)

    def download(self, url: str | None, *, stem: str) -> str | None:  # type: ignore[override]
        if not url:
            return None
        self.cover_dir.mkdir(parents=True, exist_ok=True)
        target = self.cover_dir / f"{stem}.jpg"
        target.write_bytes(b"cover")
        return str(target)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / ".data"
    return Settings(
        project_root=tmp_path,
        db_path=data_dir / "album-ranker.db",
        data_dir=data_dir,
        cover_dir=data_dir / "covers",
        host="127.0.0.1",
        port=8780,
        openai_api_key=None,
        model="gpt-5",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(
        settings,
        importer=FakeImporter(),
        cover_downloader=FakeCoverDownloader(settings.cover_dir),
    )
    return TestClient(app)
