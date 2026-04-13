from __future__ import annotations

from album_ranker import importer
from album_ranker.schemas import ImportRequest


def test_best_effort_album_draft_extracts_html_metadata(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Till Life Do Us Part - EP - Scythe of Mephisto</title>
        <meta property="og:description" content="A black metal release with atmospheric textures.">
        <meta property="og:image" content="https://example.com/cover.jpg">
      </head>
    </html>
    """

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="Scythe of Mephisto",
            album_title="Till Life Do Us Part - EP",
            source_url="https://example.com/wiki",
        )
    )

    assert draft.artist_name == "Scythe of Mephisto"
    assert draft.album_title == "Till Life Do Us Part - EP"
    assert draft.artist_description == "A black metal release with atmospheric textures."
    assert draft.cover_source_url == "https://example.com/cover.jpg"
    assert draft.artist_description_source_url == "https://example.com/wiki"
    assert draft.artist_description_source_label == "example.com"


def test_best_effort_album_draft_parses_metal_archives_page(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Vanir - Wyrd - Encyclopaedia Metallum: The Metal Archives</title>
      </head>
      <body>
        <a class="image" id="cover" href="https://www.metal-archives.com/images/1/3/9/6/1396086.jpg?1852">
          <img src="https://www.metal-archives.com/images/1/3/9/6/1396086.jpg?1852" />
        </a>
        <div id="album_info">
          <h1 class="album_name"><a href="/albums/Vanir/Wyrd/1396086">Wyrd</a></h1>
          <h2 class="band_name"><a href="/bands/Vanir/3540326149">Vanir</a></h2>
          <dl class="float_left">
            <dt>Type:</dt><dd>Full-length</dd>
            <dt>Release date:</dt><dd>April 3rd, 2026</dd>
            <dt>Catalog ID:</dt><dd>N/A</dd>
            <dt>Version desc.:</dt><dd>Bandcamp</dd>
          </dl>
          <dl class="float_right">
            <dt>Label:</dt><dd><a href="/labels/Target_Records/1635">Target Records</a></dd>
            <dt>Format:</dt><dd>Digital</dd>
          </dl>
        </div>
        <table class="display table_lyrics">
          <tr class="even"><td width="20">1.</td><td class="wrapWords">Against the Storm</td><td align="right">03:54</td><td></td></tr>
          <tr class="odd"><td width="20">2.</td><td class="wrapWords">Never Surrender</td><td align="right">04:37</td><td></td></tr>
          <tr><td colspan="2"></td><td align="right"><strong>45:25</strong></td><td></td></tr>
        </table>
      </body>
    </html>
    """

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="Vanir",
            album_title="Wyrd",
            source_url="https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
        )
    )

    assert draft.artist_name == "Vanir"
    assert draft.album_title == "Wyrd"
    assert draft.release_year == 2026
    assert draft.duration_seconds == 2725
    assert draft.cover_source_url == "https://www.metal-archives.com/images/1/3/9/6/1396086.jpg?1852"
    assert len(draft.tracks) == 2
    assert draft.tracks[0].title == "Against the Storm"
    assert draft.album_type == "Full-length"
    assert draft.notes == "Label: Target Records | Format: Digital | Version desc.: Bandcamp | Catalog ID: N/A"


def test_best_effort_artist_draft_extracts_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta name="description" content="Scythe of Mephisto is a Serbian black metal project.">
      </head>
    </html>
    """

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(artist_name="Scythe of Mephisto", source_url="https://example.com/artist")
    )

    assert draft.artist_name == "Scythe of Mephisto"
    assert draft.description == "Scythe of Mephisto is a Serbian black metal project."
    assert draft.description_source_url == "https://example.com/artist"
    assert draft.description_source_label == "example.com"


def test_best_effort_artist_draft_can_infer_name_from_page_title(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Vanir - Encyclopaedia Metallum: The Metal Archives</title>
        <meta name="description" content="Vanir is a Danish metal band.">
      </head>
    </html>
    """

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(source_url="https://www.metal-archives.com/bands/Vanir/3540326149")
    )

    assert draft.artist_name == "Vanir"
    assert draft.description == "Vanir is a Danish metal band."


def test_ai_album_draft_is_enriched_with_fallback_when_ai_returns_source_page_as_cover(monkeypatch) -> None:
    html = """
    <html>
      <body>
        <a class="image" id="cover" href="https://www.metal-archives.com/images/1/3/9/6/1396086.jpg?1852">
          <img src="https://www.metal-archives.com/images/1/3/9/6/1396086.jpg?1852" />
        </a>
        <div id="album_info">
          <h1 class="album_name"><a href="/albums/Vanir/Wyrd/1396086">Wyrd</a></h1>
          <h2 class="band_name"><a href="/bands/Vanir/3540326149">Vanir</a></h2>
          <dl class="float_left">
            <dt>Release date:</dt><dd>April 3rd, 2026</dd>
          </dl>
        </div>
        <table class="display table_lyrics">
          <tr class="even"><td width="20">1.</td><td class="wrapWords">Against the Storm</td><td align="right">03:54</td><td></td></tr>
          <tr><td colspan="2"></td><td align="right"><strong>45:25</strong></td><td></td></tr>
        </table>
      </body>
    </html>
    """

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    class FakeClient:
        def generate_json(self, **kwargs):
            return {
                "artist_name": "Vanir",
                "artist_description": None,
                "artist_description_source_url": None,
                "artist_description_source_label": None,
                "album_external_url": None,
                "album_title": "Wyrd",
                "release_year": None,
                "genre": None,
                "duration_seconds": None,
                "cover_source_url": "https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
                "notes": None,
                "tracks": [],
            }

    metadata_importer = importer.MetadataImporter(FakeClient())
    draft = metadata_importer.create_album_draft(
        ImportRequest(
            artist_name="Vanir",
            album_title="Wyrd",
            source_url="https://www.metal-archives.com/albums/Vanir/Wyrd/1396086",
        ),
        model="gpt-5",
    )

    assert draft.cover_source_url == "https://www.metal-archives.com/images/1/3/9/6/1396086.jpg?1852"
    assert draft.release_year == 2026
    assert draft.duration_seconds == 2725
    assert len(draft.tracks) == 1
