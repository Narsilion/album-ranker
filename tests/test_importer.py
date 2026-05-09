from __future__ import annotations

import pytest

from album_ranker import importer
from album_ranker.schemas import AlbumDetailRecord, ImportRequest


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html") -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


# ── _fix_allcaps ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("EXHALE THE PAST // INHALE THE FUTURE", "Exhale The Past // Inhale The Future"),
    ("LITTLE GIRL", "Little Girl"),
    ("PREDATOR", "Predator"),
    ("black box", "Black box"),
    ("don't wake me up", "Don't wake me up"),
    ("if i were you", "If I were you"),
    ("i need you (to be wrong)", "I need you (to be wrong)"),
    ("(intro) a song", "(Intro) a song"),
    ("Burn The Ships", "Burn The Ships"),
    ("In Flames", "In Flames"),
    ("WYRD", "Wyrd"),
    ("", ""),
    ("ABCDEf", "ABCDEf"),
])
def test_fix_imported_title(text: str, expected: str) -> None:
    assert importer._fix_imported_title(text) == expected


# ── source fetch guardrails ───────────────────────────────────────────────────

def test_fetch_url_document_rejects_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="Only http and https"):
        importer._fetch_url_document("file:///etc/passwd")


def test_fetch_url_document_rejects_private_network_hosts() -> None:
    with pytest.raises(ValueError, match="private or local"):
        importer._fetch_url_document("http://127.0.0.1/internal")


def test_fetch_with_urllib_rejects_unexpected_content_type(monkeypatch) -> None:
    monkeypatch.setattr(
        importer,
        "urlopen",
        lambda request, timeout: _FakeResponse(b"%PDF-1.7", "application/pdf"),
    )

    with pytest.raises(ValueError, match="Unsupported content type"):
        importer._fetch_with_urllib("https://example.com/file.pdf")


def test_fetch_with_urllib_rejects_oversized_response(monkeypatch) -> None:
    monkeypatch.setattr(
        importer,
        "urlopen",
        lambda request, timeout: _FakeResponse(b"x" * (importer.MAX_SOURCE_BYTES + 1), "text/html"),
    )

    with pytest.raises(ValueError, match="exceeds"):
        importer._fetch_with_urllib("https://example.com/huge")


def test_curl_fetch_uses_timeout_size_and_http_protocol_limits(monkeypatch) -> None:
    captured = {}

    class Result:
        stdout = "<html></html>"

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    body, content_type = importer._fetch_with_curl("https://example.com/page")

    assert body == "<html></html>"
    assert content_type == "text/html"
    assert "--proto" in captured["args"]
    assert "=http,https" in captured["args"]
    assert "--max-time" in captured["args"]
    assert str(importer.SOURCE_FETCH_TIMEOUT_SECONDS) in captured["args"]
    assert "--max-filesize" in captured["args"]
    assert str(importer.MAX_SOURCE_BYTES) in captured["args"]


# ── allcaps normalisation through _best_effort_album_draft ───────────────────

def test_allcaps_album_title_is_normalised_for_generic_source(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="EXHALE THE PAST // INHALE THE FUTURE - Album by HIMITZU">
        <meta property="og:image" content="https://example.com/cover.jpg">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_album_draft(
        ImportRequest(artist_name="HIMITZU", source_url="https://example.com/album")
    )

    assert draft.album_title == "Exhale The Past // Inhale The Future"


def test_allcaps_track_titles_are_normalised_for_metal_archives(monkeypatch) -> None:
    html = """
    <html>
      <head><title>Band - Album - Encyclopaedia Metallum</title></head>
      <body>
        <div id="album_info">
          <h1 class="album_name"><a href="#">Album</a></h1>
          <h2 class="band_name"><a href="#">Band</a></h2>
          <dl class="float_left">
            <dt>Type:</dt><dd>Full-length</dd>
            <dt>Release date:</dt><dd>January 1st, 2026</dd>
          </dl>
        </div>
        <table class="display table_lyrics">
          <tr class="even"><td width="20">1.</td><td class="wrapWords">LITTLE GIRL</td><td align="right">02:58</td><td></td></tr>
          <tr class="odd"><td width="20">2.</td><td class="wrapWords">PREDATOR</td><td align="right">03:56</td><td></td></tr>
          <tr><td colspan="2"></td><td align="right"><strong>06:54</strong></td><td></td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="Band",
            album_title="Album",
            source_url="https://www.metal-archives.com/albums/Band/Album/1",
        )
    )

    assert draft.tracks[0].title == "Little Girl"
    assert draft.tracks[1].title == "Predator"


def test_album_import_does_not_call_ai_client(monkeypatch) -> None:
    html = "<html><head><title>EXHALE THE PAST // INHALE THE FUTURE - HIMITZU</title></head><body></body></html>"
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    class FakeClient:
        def generate_json(self, **kwargs):
            raise AssertionError("AI client should not be used for album metadata import")

    metadata_importer = importer.MetadataImporter(FakeClient())
    draft = metadata_importer.create_album_draft(
        ImportRequest(
            artist_name="HIMITZU",
            album_title="",
            source_url="https://example.com/himitzu",
        ),
        model="gpt-5",
    )

    assert draft.album_title == "Exhale The Past // Inhale The Future"
    assert draft.artist_name == "HIMITZU"
    assert metadata_importer.last_diagnostics["mode"] == "source_parse_only"


def test_artist_import_does_not_call_ai_client(monkeypatch) -> None:
    html = "<html><head><title>In Flames - official</title><meta name='description' content='Swedish metal band'></head><body></body></html>"
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    class FakeClient:
        def generate_json(self, **kwargs):
            raise AssertionError("AI client should not be used for artist metadata import")

    metadata_importer = importer.MetadataImporter(FakeClient())
    draft = metadata_importer.create_artist_draft(
        ImportRequest(
            artist_name="In Flames",
            source_url="https://example.com/in-flames",
        ),
        model="gpt-5",
    )

    assert draft.artist_name == "In Flames"
    assert draft.description == "Swedish metal band"
    assert metadata_importer.last_diagnostics["mode"] == "source_parse_only"


def test_metadata_importer_delegates_source_and_writeup_responsibilities() -> None:
    class FakeSourceImporter:
        last_diagnostics = {"mode": "fake_source"}

        def __init__(self) -> None:
            self.artist_called = False

        def create_artist_draft(self, request, *, model):
            self.artist_called = True
            return importer.ArtistDraftData(artist_name=request.artist_name or "Band")

        def create_album_draft(self, request, *, model):
            raise AssertionError("not used")

    class FakeWriteupGenerator:
        client = None
        last_request_failed = False
        last_error = None

        def __init__(self) -> None:
            self.writeup_called = False

        def generate_album_overview(self, album, *, language, model):
            return self.generate_album_writeup(album, language=language, model=model)

        def generate_album_writeup(self, album, *, language, model):
            self.writeup_called = True
            return f"{album.artist_name} - {album.title}"

    source = FakeSourceImporter()
    writeup = FakeWriteupGenerator()
    metadata_importer = importer.MetadataImporter(
        None,
        source_importer=source,  # type: ignore[arg-type]
        writeup_generator=writeup,  # type: ignore[arg-type]
    )

    artist_draft = metadata_importer.create_artist_draft(
        ImportRequest(artist_name="Delegated Band", source_url="https://example.com"),
        model="gpt-5",
    )
    writeup_text = metadata_importer.generate_album_writeup(
        AlbumDetailRecord(
            id=1,
            artist_id=1,
            artist_name="Delegated Band",
            title="Delegated Album",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        language="en",
        model="gpt-5",
    )

    assert source.artist_called is True
    assert writeup.writeup_called is True
    assert artist_draft.artist_name == "Delegated Band"
    assert writeup_text == "Delegated Band - Delegated Album"
    assert metadata_importer.last_diagnostics == {"mode": "fake_source"}


# ─────────────────────────────────────────────────────────────────────────────

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
    assert draft.notes == "Label: Target Records\nFormat: Digital\nVersion desc.: Bandcamp"


def test_metal_archives_album_page_extracts_artist_url(monkeypatch) -> None:
    html = """
    <html>
      <body>
        <h2 class="band_name"><a href="/bands/For_My_Pain.../1020">For My Pain...</a></h2>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    artist_url = importer.metal_archives_artist_url_from_album_url(
        "https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127"
    )

    assert artist_url == "https://www.metal-archives.com/bands/For_My_Pain.../1020"


def test_metal_archives_album_draft_from_url_uses_deterministic_parser(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>For My Pain... - Buried Blue - Encyclopaedia Metallum: The Metal Archives</title>
      </head>
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
          <tr class="even">
            <td width="20"><a name="8038837" class="anchor"> </a>1.</td>
            <td class="wrapWords">Hungry for Desire</td>
            <td align="right">04:11</td>
            <td></td>
          </tr>
          <tr class="odd">
            <td width="20"><a name="8038838" class="anchor"> </a>2.</td>
            <td class="wrapWords">Windows Are Weeping</td>
            <td align="right">04:31</td>
            <td></td>
          </tr>
          <tr><td colspan="2"></td><td align="right"><strong>51:32</strong></td><td></td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer.metal_archives_album_draft_from_url(
        ImportRequest(
            artist_name="",
            source_url="https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
        )
    )

    assert draft is not None
    assert draft.artist_name == "For My Pain..."
    assert draft.album_title == "Buried Blue"
    assert draft.release_year == 2026
    assert draft.duration_seconds == 3092
    assert draft.album_type == "Full-length"
    assert draft.notes == "Label: Rainheart Productions\nFormat: Digital"
    assert draft.tracks[0].title == "Hungry for Desire"


def test_metal_archives_album_draft_uses_url_names_and_never_page_title_as_notes(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>For My Pain... - Encyclopaedia Metallum: The Metal Archives</title>
      </head>
      <body>
        <div id="band_sidebar">This is an artist page, not an album page.</div>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer.metal_archives_album_draft_from_url(
        ImportRequest(
            artist_name="",
            source_url="https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127",
        )
    )

    assert draft is not None
    assert draft.artist_name == "For My Pain..."
    assert draft.album_title == "Buried Blue"
    assert draft.notes is None


def test_best_effort_artist_draft_parses_metal_archives_band_page(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>For My Pain... - Encyclopaedia Metallum: The Metal Archives</title>
        <meta property="og:description" content="Finnish gothic metal band.">
      </head>
      <body>
        <h1 class="band_name"><a href="/bands/For_My_Pain.../1020">For My Pain...</a></h1>
        <dl class="float_left">
          <dt>Country of origin:</dt><dd>Finland</dd>
          <dt>Location:</dt><dd>Oulu</dd>
          <dt>Genre:</dt><dd>Gothic Metal</dd>
          <dt>Status:</dt><dd>Active</dd>
        </dl>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="For My Pain...",
            source_url="https://www.metal-archives.com/bands/For_My_Pain.../1020",
        )
    )

    assert draft.artist_name == "For My Pain..."
    assert draft.external_url == "https://www.metal-archives.com/bands/For_My_Pain.../1020"
    assert draft.description == "Finnish gothic metal band."
    assert draft.origin == "Finland, Oulu"
    assert draft.genre == "Gothic Metal"


def test_best_effort_artist_draft_keeps_metal_archives_genre_out_of_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>For My Pain... - Encyclopaedia Metallum: The Metal Archives</title>
      </head>
      <body>
        <h1 class="band_name"><a href="/bands/For_My_Pain.../1020">For My Pain...</a></h1>
        <dl class="float_left">
          <dt>Country of origin:</dt><dd>Finland</dd>
          <dt>Location:</dt><dd>Oulu</dd>
          <dt>Genre:</dt><dd>Gothic Metal</dd>
          <dt>Status:</dt><dd>Active</dd>
        </dl>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="For My Pain...",
            source_url="https://www.metal-archives.com/bands/For_My_Pain.../1020",
        )
    )

    assert draft.genre == "Gothic Metal"
    assert draft.description == "Status: Active"
    assert "Genre:" not in draft.description


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


def test_wikipedia_artist_draft_normalizes_origin_country_first(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Halsey (singer) - Wikipedia</title>
        <meta property="og:description" content="American singer and songwriter.">
      </head>
      <body>
        <table class="infobox biography vcard">
          <tr><th>Birthplace</th><td>Edison, New Jersey , US</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="Halsey",
            source_url="https://en.wikipedia.org/wiki/Halsey_(singer)",
        )
    )

    assert draft.origin == "United States, Edison, New Jersey"


def test_wikipedia_artist_draft_normalizes_origin_from_born_field(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Halsey (singer) - Wikipedia</title>
      </head>
      <body>
        <table class="infobox biography vcard">
          <tr><th>Born</th><td>Ashley Nicolette Frangipane September 29, 1994 (age 31) Edison, New Jersey, U.S.</td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="Halsey",
            source_url="https://en.wikipedia.org/wiki/Halsey_(singer)",
        )
    )

    assert draft.origin == "United States, Edison, New Jersey"


def test_wikipedia_artist_draft_formats_genre_list(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Switchfoot - Wikipedia</title>
        <meta property="og:description" content="American alternative rock band.">
      </head>
      <body>
        <table class="infobox vcard">
          <tr><th>Genres</th><td>
            <div class="hlist">
              <ul>
                <li><a>Alternative rock</a><sup>[1]</sup></li>
                <li><a>Art rock</a><sup>[2]</sup></li>
                <li><a>post-grunge</a><sup>[1]</sup></li>
                <li><a>indie rock</a><sup>[3]</sup></li>
                <li><a>gospel</a><sup>[1]</sup></li>
                <li><a>power pop</a><sup>[4]</sup></li>
                <li><a>pop rock</a><sup>[1]</sup></li>
                <li><a>post-punk</a><sup>[4]</sup></li>
                <li><a>punk rock</a><sup>[5]</sup></li>
              </ul>
            </div>
          </td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="Switchfoot",
            source_url="https://en.wikipedia.org/wiki/Switchfoot",
        )
    )

    assert draft.genre == (
        "Alternative Rock / Art Rock / Post-Grunge / Indie Rock / Gospel / "
        "Power Pop / Pop Rock / Post-Punk / Punk Rock"
    )


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
            raise AssertionError("AI client should not be used for album metadata import")

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


# ── YouTube Music track extraction ───────────────────────────────────────────

def _make_ytm_renderer(title: str, duration: str) -> dict:
    """Build a minimal musicResponsiveListItemRenderer for testing."""
    return {
        "flexColumns": [
            {
                "musicResponsiveListItemFlexColumnRenderer": {
                    "text": {"runs": [{"text": title}]},
                }
            }
        ],
        "fixedColumns": [
            {
                "musicResponsiveListItemFixedColumnRenderer": {
                    "text": {"runs": [{"text": duration}]},
                }
            }
        ],
    }


def test_extract_ytm_tracks_from_objects_returns_all_tracks() -> None:
    """_extract_ytm_tracks_from_objects extracts the complete tracklist."""
    objects = [
        # First object has no renderers (e.g. header data)
        {"someOtherKey": "someValue"},
        # Second object has the full tracklist
        {
            "musicShelfRenderer": {
                "contents": [
                    {"musicResponsiveListItemRenderer": _make_ytm_renderer("Track One", "4:30")},
                    {"musicResponsiveListItemRenderer": _make_ytm_renderer("Track Two", "3:15")},
                    {"musicResponsiveListItemRenderer": _make_ytm_renderer("Track Three", "5:00")},
                ]
            }
        },
    ]

    tracks = importer._extract_ytm_tracks_from_objects(objects)

    assert len(tracks) == 3
    assert tracks[0] == {"track_number": 1, "title": "Track One", "duration_seconds": 270}
    assert tracks[1] == {"track_number": 2, "title": "Track Two", "duration_seconds": 195}
    assert tracks[2] == {"track_number": 3, "title": "Track Three", "duration_seconds": 300}


def test_ytm_album_draft_uses_ytm_page_tracks_not_playlist_page(monkeypatch) -> None:
    """Tracks come from the YTM initialData objects, not the lazy-loaded playlist page."""
    og_html = """
    <html>
      <head>
        <meta property="og:title" content="Blackwater Park - Album by Opeth">
        <meta property="og:image" content="https://lh3.googleusercontent.com/cover.jpg">
      </head>
    </html>
    """
    # Build hex-encoded initialData.push block with full tracklist + year subtitle
    import json as _json, re as _re

    tracklist_obj = {
        "musicShelfRenderer": {
            "contents": [
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("The Leper Affinity", "10:24")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Bleak", "9:56")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Harvest", "6:01")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("The Drapery Falls", "10:54")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Dirge for November", "7:44")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("The Funeral Portrait", "8:44")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Patterns in the Ivy", "4:03")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Blackwater Park", "12:08")},
            ]
        }
    }
    year_obj = {
        "header": {
            "subtitle": {"runs": [{"text": "Album"}, {"text": " \u2022 "}, {"text": "2001"}]}
        }
    }

    def _hex_encode(obj: dict) -> str:
        raw = _json.dumps(obj).replace("/", "\\/")
        return "".join(f"\\x{ord(c):02x}" for c in raw)

    ytm_page = (
        f"initialData.push({{data: '{_hex_encode(year_obj)}'}});\n"
        f"initialData.push({{data: '{_hex_encode(tracklist_obj)}'}});\n"
    )

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (og_html, "text/html"))
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: ytm_page)
    # This should NOT be called since YTM page has the full tracklist
    monkeypatch.setattr(
        importer, "_extract_yt_playlist_tracks",
        lambda pid: [{"track_number": 1, "title": "Only One Track", "duration_seconds": 600}],
    )

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_example",
        )
    )

    assert draft.album_title == "Blackwater Park"
    assert draft.artist_name == "Opeth"
    assert draft.release_year == 2001
    assert len(draft.tracks) == 8
    assert draft.tracks[0].title == "The Leper Affinity"
    assert draft.tracks[0].duration_seconds == 624
    assert draft.tracks[7].title == "Blackwater Park"
    assert draft.tracks[7].duration_seconds == 728
    # Total duration should be sum of all tracks
    assert draft.duration_seconds == sum(t.duration_seconds for t in draft.tracks if t.duration_seconds)


def test_ytm_album_draft_sentence_cases_lowercase_track_titles(monkeypatch) -> None:
    og_html = """
    <html>
      <head>
        <meta property="og:title" content="Album - Album by Band">
      </head>
    </html>
    """
    import json as _json

    tracklist_obj = {
        "musicShelfRenderer": {
            "contents": [
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("black box", "3:00")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("don't wake me up", "4:00")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("if i were you", "4:30")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Already Sentence Case", "5:00")},
            ]
        }
    }

    def _hex_encode(obj: dict) -> str:
        raw = _json.dumps(obj).replace("/", "\\/")
        return "".join(f"\\x{ord(c):02x}" for c in raw)

    ytm_page = f"initialData.push({{data: '{_hex_encode(tracklist_obj)}'}});\n"
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (og_html, "text/html"))
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: ytm_page)

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_lowercase",
        )
    )

    assert [track.title for track in draft.tracks] == [
        "Black box",
        "Don't wake me up",
        "If I were you",
        "Already Sentence Case",
    ]


def test_ytm_watch_album_draft_resolves_full_album(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Nobody But You Baby">
        <meta property="og:description" content="The Black Keys">
        <meta property="og:image" content="https://yt3.googleusercontent.com/cover.jpg">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))
    monkeypatch.setattr(
        importer,
        "_fetch_ytm_full_page",
        lambda url: '"INNERTUBE_API_KEY":"test-key","INNERTUBE_CLIENT_VERSION":"1.20260505.09.00"',
    )

    def fake_ytm_api(endpoint: str, payload: dict, api_key: str) -> dict:
        if endpoint == "next":
            return {
                "contents": {
                    "playlistPanelVideoRenderer": {
                        "longBylineText": {
                            "runs": [
                                {"text": "The Black Keys"},
                                {"text": " • "},
                                {
                                    "text": "Peaches!",
                                    "navigationEndpoint": {
                                        "browseEndpoint": {
                                            "browseId": "MPREb_9tCUsvsZddw",
                                            "browseEndpointContextSupportedConfigs": {
                                                "browseEndpointContextMusicConfig": {
                                                    "pageType": "MUSIC_PAGE_TYPE_ALBUM",
                                                }
                                            },
                                        }
                                    },
                                },
                                {"text": " • "},
                                {"text": "2026"},
                            ]
                        }
                    }
                }
            }
        if endpoint == "browse":
            return {
                "microformat": {
                    "microformatDataRenderer": {
                        "urlCanonical": "https://music.youtube.com/playlist?list=OLAK5uy_lC_wziTi5fDBlkEqSexaVeCxLgliVcWtA",
                        "title": "Peaches! - Album by The Black Keys",
                        "description": "Album description.",
                        "thumbnail": {"thumbnails": [{"url": "https://yt3.googleusercontent.com/cover.jpg", "width": 544, "height": 544}]},
                    }
                },
                "contents": {
                    "musicShelfRenderer": {
                        "contents": [
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Where There's Smoke, There's Fire", "5:01")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Stop Arguing Over Me", "4:02")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Who's Been Foolin' You", "4:17")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("It's a Dream", "3:36")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Tomorrow Night", "3:55")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("You Got to Lose", "3:17")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Tell Me You Love Me", "4:27")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("She Does It Right", "3:43")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Fireman Ring the Bell", "5:47")},
                            {"musicResponsiveListItemRenderer": _make_ytm_renderer("Nobody But You Baby", "7:14")},
                        ]
                    },
                    "subtitle": {"runs": [{"text": "Album"}, {"text": " • "}, {"text": "2026"}]},
                },
            }
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr(importer, "_fetch_ytm_api", fake_ytm_api)

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/watch?v=4pWSqz0EZS0&si=w64uCCNQCJmS522Q",
        )
    )

    assert draft.album_title == "Peaches!"
    assert draft.artist_name == "The Black Keys"
    assert draft.album_type == "Full-length"
    assert draft.release_year == 2026
    assert draft.album_external_url == "https://music.youtube.com/playlist?list=OLAK5uy_lC_wziTi5fDBlkEqSexaVeCxLgliVcWtA"
    assert len(draft.tracks) == 10
    assert draft.tracks[0].title == "Where There's Smoke, There's Fire"
    assert draft.tracks[9].title == "Nobody But You Baby"
    assert draft.tracks[9].duration_seconds == 434


def test_ytm_artist_draft_does_not_use_album_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Trying: Season 3 (Apple TV Original Series Soundtrack) - Album by Bear's Den">
        <meta property="og:description" content="Listen to Trying: Season 3 (Apple TV Original Series Soundtrack) by Bear's Den on YouTube Music - a dedicated music app with official songs, music videos, remixes, covers, and more.">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_kh5TKNaYuY9PNFOHik4DO7KyHKBAREDxc",
        )
    )

    assert draft.artist_name == "Bear's Den"
    assert draft.description is None
    assert draft.external_url == "https://music.youtube.com/playlist?list=OLAK5uy_kh5TKNaYuY9PNFOHik4DO7KyHKBAREDxc"


def test_ytm_watch_artist_draft_uses_description_as_artist(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Nobody But You Baby">
        <meta property="og:description" content="The Black Keys">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/watch?v=4pWSqz0EZS0&si=w64uCCNQCJmS522Q",
        )
    )

    assert draft.artist_name == "The Black Keys"
    assert draft.description is None


def test_ytm_artist_draft_uses_artist_page_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Bear's Den - YouTube Music">
        <meta property="og:description" content="Bear's Den are a British folk rock band from London.">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(source_url="https://music.youtube.com/@bearsdenmusic")
    )

    assert draft.artist_name == "Bear's Den"
    assert draft.description == "Bear's Den are a British folk rock band from London."
    assert draft.external_url == "https://music.youtube.com/@bearsdenmusic"


def test_alterportal_album_draft_parses_page(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="EarlyRise - The Flood Is Coming (2026)">
        <meta property="og:image" content="https://i127.fastpic.org/big/2026/0430/cover.jpg">
      </head>
      <body>
        <!--dle_image_begin:...|-->
        <img src="https://i127.fastpic.org/big/2026/0430/cover.jpg" style="max-width:100%;" alt="EarlyRise - The Flood Is Coming (2026)">
        <!--dle_image_end-->
        <br><!--colorstart:#33FFFF--><span style="color:#33FFFF"><!--/colorstart--><b>Стиль:</b><!--colorend--></span><!--/colorend--> Alternative Rock / Alternative Metal / Female Vocals<br>
        <b>Страна:</b> Israel<br>
        <b>Формат:</b> mp3, 320 kbps<br>
        <b>Время звучания:</b> 26 min 49 sec<br><br>
        <b>Треклист:</b><br>
        01. Dance For The Money<br>
        02. All Hail The Mighty Circus<br>
        03. The Bitter Pill<br>
        04. The Flood Is Coming<br>
        05. Paper Empire<br>
        06. Dreaming In Sepia<br>
        07. Rinse And Repeat<br>
        08. Distorted Kingdom<br>
        <br><br>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://alterportal.net/2026_albums/189049-earlyrise-the-flood-is-coming-2026.html",
        )
    )

    assert draft.artist_name == "EarlyRise"
    assert draft.album_title == "The Flood Is Coming"
    assert draft.release_year == 2026
    assert draft.genre == "Alternative Rock"
    assert draft.duration_seconds == 26 * 60 + 49
    assert draft.cover_source_url == "https://i127.fastpic.org/big/2026/0430/cover.jpg"
    assert draft.notes == "Format: mp3, 320 kbps"
    assert len(draft.tracks) == 8
    assert draft.tracks[0].title == "Dance For The Money"
    assert draft.tracks[7].title == "Distorted Kingdom"
    assert draft.album_type == "Full-length"


def test_alterportal_artist_draft_parses_page(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="EarlyRise - The Flood Is Coming (2026)">
      </head>
      <body>
        <b>Стиль:</b> Alternative Rock / Alternative Metal / Female Vocals<br>
        <b>Страна:</b> Israel<br>
        <b>Формат:</b> mp3, 320 kbps<br>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="EarlyRise",
            source_url="https://alterportal.net/2026_albums/189049-earlyrise-the-flood-is-coming-2026.html",
        )
    )

    assert draft.artist_name == "EarlyRise"
    assert draft.origin == "Israel"
    assert draft.genre == "Alternative Rock"
    assert draft.description is None
    assert draft.external_url == "https://alterportal.net/2026_albums/189049-earlyrise-the-flood-is-coming-2026.html"
