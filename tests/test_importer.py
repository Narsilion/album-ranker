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


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("England", "UK"),
        ("England, London", "UK, London"),
        ("London, England", "UK, London"),
    ],
)
def test_common_import_origin_replacements(origin: str, expected: str) -> None:
    assert importer._normalize_imported_origin(origin) == expected


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

        def generate_album_writeup(self, album, *, language, model, limit_for_telegram=True):
            self.writeup_called = True
            return f"{album.artist_name} - {album.title}"

        def generate_artist_description(self, artist_name, *, origin, album_title, genre, source_url, model, release_year=None):
            return f"Description of {artist_name}"

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


def test_artist_description_generator_uses_source_context_and_selected_model(monkeypatch) -> None:
    excerpts = {
        "https://example.com/the-haunted-youth": "Belgian dream pop project led by Joachim Liebens.",
    }
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: excerpts.get(url, ""))
    captured = {}

    class FakeClient:
        def generate_json_with_web_search(self, **kwargs):
            captured.update(kwargs)
            return (
                {
                    "description": "The Haunted Youth is a Belgian dream-pop project.",
                    "sources": [
                        {"title": "Official artist", "url": "https://thehauntedyouth.com"},
                        {"title": "Invalid", "url": "javascript:alert(1)"},
                    ],
                },
                [{"title": "Artist source", "url": "https://example.com/the-haunted-youth"}],
            )

    generator = importer.AlbumWriteupGenerator(FakeClient())
    description = generator.generate_artist_description(
        "The Haunted Youth",
        origin="Belgium",
        album_title="Boys Cry Too",
        genre="Dream Pop",
        source_url="https://example.com/the-haunted-youth",
        model="gpt-5.4-mini",
    )

    assert description == "The Haunted Youth is a Belgian Dream-Pop project."
    assert captured["model"] == "gpt-5.4-mini"
    assert captured["schema_name"] == "artist_description"
    assert "Belgian dream pop project" in captured["user_prompt"]
    assert "Use web search" in captured["system_prompt"]
    assert "Search the web for the exact band" in captured["user_prompt"]
    assert "quote the artist name" in captured["user_prompt"]
    assert "60 to 90 words" in captured["user_prompt"]
    assert "listener, follower, or play counts" in captured["user_prompt"]
    assert "capitalizing every word and every hyphenated part" in captured["user_prompt"]
    assert "Heavy Psych-Rock" in captured["user_prompt"]
    assert "Do not write genre names in all caps" in captured["user_prompt"]
    assert "Do not use Reddit" in captured["user_prompt"]
    assert "Imported album: Boys Cry Too" in captured["user_prompt"]
    assert generator.last_artist_description_sources == [
        {"title": "Official artist", "url": "https://thehauntedyouth.com"},
        {"title": "Artist source", "url": "https://example.com/the-haunted-youth"},
    ]


def test_titlecase_known_genres_handles_multiple_and_hyphenated_names() -> None:
    description = "The band plays atmospheric black metal with dream-pop and heavy psych-rock textures."

    assert importer._titlecase_known_genres(
        description,
        "Atmospheric Black Metal / Dream Pop / Heavy Psych-Rock",
    ) == (
        "The band plays Atmospheric Black Metal with Dream-Pop and Heavy Psych-Rock textures."
    )


def test_album_writeup_strips_inline_web_citations() -> None:
    text = (
        "A factual sentence. ([Example](https://example.com/review?utm_source=openai))\n\n"
        "🎧 Listen:\n[Spotify](https://open.spotify.com/album/test)"
    )

    assert importer._strip_inline_web_citations(text) == (
        "A factual sentence.\n\n🎧 Listen:\n[Spotify](https://open.spotify.com/album/test)"
    )


def test_album_writeup_appends_missing_listen_block_deterministically() -> None:
    result = importer._ensure_writeup_listen_links(
        "🎸 Альбом: Grimveil — Beneath the Veil of Silent Woods\n\n📌 Описание:\nТекст.",
        youtube_music_url="https://music.youtube.com/playlist?list=album",
        spotify_url="https://open.spotify.com/search/album-query/albums",
        language="ru",
    )

    assert result.endswith(
        "🎧 Слушать:\n"
        "[YouTube Music](https://music.youtube.com/playlist?list=album) | "
        "[Spotify](https://open.spotify.com/search/album-query/albums)"
    )


def test_album_writeup_replaces_incomplete_listen_block_deterministically() -> None:
    result = importer._ensure_writeup_listen_links(
        "Write-up.\n\n🎧 Listen:\nYouTube Music | Spotify",
        youtube_music_url="https://music.youtube.com/playlist?list=album",
        spotify_url="https://open.spotify.com/album/exact",
        language="en",
    )

    assert result == (
        "Write-up.\n\n🎧 Listen:\n"
        "[YouTube Music](https://music.youtube.com/playlist?list=album) | "
        "[Spotify](https://open.spotify.com/album/exact)"
    )


def test_album_writeup_prompt_links_youtube_music_when_stream_url_is_youtube(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    monkeypatch.setattr(importer, "_find_spotify_album_url", lambda artist_name, album_title: None)
    captured = {}

    class FakeClient:
        def generate_json_with_web_search(self, **kwargs):
            captured["prompt"] = kwargs["user_prompt"]
            return (
                {
                    "overview": "Generated write-up.",
                    "sources": [{"title": "Album review", "url": "https://example.com/review"}],
                },
                [],
            )

    generator = importer.AlbumWriteupGenerator(FakeClient())
    generator.generate_album_writeup(
        AlbumDetailRecord(
            id=1,
            artist_id=1,
            artist_name="Band",
            title="Album",
            album_stream_url="https://music.youtube.com/playlist?list=test",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        language="en",
        model="gpt-5",
    )

    prompt = captured["prompt"]
    spotify_search_url = "https://open.spotify.com/search/album%3A%22Album%22%20artist%3A%22Band%22/albums"
    assert f"[YouTube Music](https://music.youtube.com/playlist?list=test) | [Spotify]({spotify_search_url})" in prompt
    assert f"Spotify album search URL: {spotify_search_url}" in prompt
    assert "When only YouTube Music is known, write '[YouTube Music](url) | Spotify'." in prompt
    assert "Research public user/community ratings" in prompt
    assert "Do not use Sputnikmusic" in prompt
    assert "explicitly check the exact album's reviews on Encyclopaedia Metallum" in prompt
    assert "Metal Archives reviews: NN% (N reviews)" in prompt
    assert "Do not convert scales" in prompt
    assert "exact page supporting every reported rating" in prompt
    assert "do not put inline citations" in prompt
    assert generator.last_album_writeup_sources == [
        {"title": "Album review", "url": "https://example.com/review"}
    ]


def test_album_writeup_prompt_links_spotify_when_stream_url_is_spotify(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    captured = {}

    class FakeClient:
        def generate_json(self, **kwargs):
            captured["prompt"] = kwargs["user_prompt"]
            return {"overview": "Generated write-up."}

    generator = importer.AlbumWriteupGenerator(FakeClient())
    generator.generate_album_writeup(
        AlbumDetailRecord(
            id=1,
            artist_id=1,
            artist_name="Band",
            title="Album",
            album_stream_url="https://open.spotify.com/album/test",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        language="en",
        model="gpt-5",
    )

    prompt = captured["prompt"]
    assert (
        "[YouTube Music](https://music.youtube.com/search?q=Band+Album) | "
        "[Spotify](https://open.spotify.com/album/test)"
    ) in prompt
    assert "When only Spotify is known, write 'YouTube Music | [Spotify](url)'." in prompt
    assert "YouTube Music album search URL: https://music.youtube.com/search?q=Band+Album" in prompt


def test_extract_spotify_album_url_from_search_redirect() -> None:
    html = """
    <a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopen.spotify.com%2Falbum%2F4LH4d3cOWNNsVw41Gqt2kv%3Fsi%3Dtest">
      Pink Floyd - The Dark Side of the Moon
    </a>
    """

    assert importer._extract_spotify_album_url(html) == (
        "https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv"
    )


def test_find_spotify_album_url_uses_spotify_api_when_configured(monkeypatch) -> None:
    requests = []

    def fake_spotify_json_request(url, *, data=None, headers=None):
        requests.append((url, data, headers))
        if url == "https://accounts.spotify.com/api/token":
            return {"access_token": "token"}
        return {
            "albums": {
                "items": [
                    {
                        "name": "Arbor",
                        "artists": [{"name": "Wazzara"}],
                        "external_urls": {
                            "spotify": "https://open.spotify.com/album/abc123?si=test",
                        },
                    }
                ]
            }
        }

    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(importer, "_spotify_json_request", fake_spotify_json_request)

    assert importer._find_spotify_album_url("Wazzara", "Arbor") == "https://open.spotify.com/album/abc123"
    assert requests[0][0] == "https://accounts.spotify.com/api/token"
    assert requests[1][0].startswith("https://api.spotify.com/v1/search?")


def test_find_spotify_album_url_falls_back_to_search_html(monkeypatch) -> None:
    search_html = """
    <a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fopen.spotify.com%2Falbum%2Ffallback123">
      Wazzara - Arbor
    </a>
    """

    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(importer, "_fetch_with_urllib", lambda url: (search_html, "text/html"))

    assert importer._find_spotify_album_url("Wazzara", "Arbor") == "https://open.spotify.com/album/fallback123"


def test_album_writeup_adds_spotify_search_result_to_prompt_and_output(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    spotify_url = "https://open.spotify.com/album/4LH4d3cOWNNsVw41Gqt2kv"
    monkeypatch.setattr(importer, "_find_spotify_album_url", lambda artist_name, album_title: spotify_url)
    captured = {}

    class FakeClient:
        def generate_json(self, **kwargs):
            captured["prompt"] = kwargs["user_prompt"]
            return {
                "overview": (
                    "🎸 Album: Pink Floyd — The Dark Side of the Moon\n\n"
                    "🎧 Listen:\n"
                    "[YouTube Music](https://music.youtube.com/playlist?list=test) | Spotify"
                )
            }

    generator = importer.AlbumWriteupGenerator(FakeClient())
    result = generator.generate_album_writeup(
        AlbumDetailRecord(
            id=1,
            artist_id=1,
            artist_name="Pink Floyd",
            title="The Dark Side of the Moon",
            album_stream_url="https://music.youtube.com/playlist?list=test",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        language="en",
        model="gpt-5",
    )

    assert f"Spotify URL found for album: {spotify_url}" in captured["prompt"]
    assert (
        f"[YouTube Music](https://music.youtube.com/playlist?list=test) | [Spotify]({spotify_url})"
        in captured["prompt"]
    )
    assert f"| [Spotify]({spotify_url})" in result


@pytest.mark.parametrize("youtube_url", [None, "https://music.youtube.com/playlist?list=album549"])
def test_album_writeup_uses_metadata_or_search_for_youtube_music(monkeypatch, youtube_url) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    captured = {}

    class FakeClient:
        def generate_json(self, **kwargs):
            captured["prompt"] = kwargs["user_prompt"]
            return {"overview": "Album description.\n\n🎧 Listen:\nYouTube Music | Spotify"}

    album = AlbumDetailRecord(
        id=549, artist_id=475, artist_name="The XCERTS",
        title="I think I want to go home now.",
        album_stream_url="https://open.spotify.com/album/11vZ8gOVgAq5Txx9Eo76hl",
        album_external_url=youtube_url,
        created_at="2026-01-01", updated_at="2026-01-01",
    )
    result = importer.AlbumWriteupGenerator(FakeClient()).generate_album_writeup(
        album, language="en", model="gpt-5",
    )
    expected = youtube_url or (
        "https://music.youtube.com/search?q=The+XCERTS+I+think+I+want+to+go+home+now."
    )
    assert expected in captured["prompt"]
    assert f"[YouTube Music]({expected})" in result
    assert f"[Spotify]({album.album_stream_url})" in result


def test_album_writeup_links_spotify_search_when_exact_album_url_is_unknown(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    monkeypatch.setattr(importer, "_find_spotify_album_url", lambda artist_name, album_title: None)
    spotify_search_url = "https://open.spotify.com/search/album%3A%22Arbor%22%20artist%3A%22Wazzara%22/albums"
    captured = {}

    class FakeClient:
        def generate_json(self, **kwargs):
            captured["prompt"] = kwargs["user_prompt"]
            return {
                "overview": (
                    "🎸 Album: Wazzara — Arbor\n\n"
                    "🎧 Listen:\n"
                    "[YouTube Music](https://music.youtube.com/playlist?list=test) | Spotify"
                )
            }

    generator = importer.AlbumWriteupGenerator(FakeClient())
    result = generator.generate_album_writeup(
        AlbumDetailRecord(
            id=153,
            artist_id=142,
            artist_name="Wazzara",
            title="Arbor",
            album_stream_url="https://music.youtube.com/playlist?list=test",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        language="ru",
        model="gpt-5",
    )

    assert f"Spotify album search URL: {spotify_search_url}" in captured["prompt"]
    assert f"| [Spotify]({spotify_search_url})" in result


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
          <dt>Genre:</dt><dd>Gothic Metal/Rock</dd>
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
    assert draft.genre == "Gothic Metal / Rock"


def test_best_effort_artist_draft_uses_metal_archives_band_comment_as_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Beleriand - Encyclopaedia Metallum: The Metal Archives</title>
      </head>
      <body>
        <h1 class="band_name"><a href="/bands/Beleriand/3540468433">Beleriand</a></h1>
        <dl>
          <dt>Country of origin:</dt><dd>Norway</dd>
          <dt>Location:</dt><dd>Tromsø, Troms</dd>
          <dt>Genre:</dt><dd>Epic/Atmospheric Black Metal</dd>
        </dl>
        <div class="band_comment clear">
          Beleriand is named after the north-western region of the Middle-Earth,
          according to the J.R.R. Tolkien's "The Silmarillion"
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            source_url="https://www.metal-archives.com/bands/Beleriand/3540468433",
        )
    )

    assert draft.description == (
        "Beleriand is named after the north-western region of the Middle-Earth, "
        'according to the J.R.R. Tolkien\'s "The Silmarillion"'
    )


def test_metal_archives_artist_draft_normalizes_england_origin_to_uk(monkeypatch) -> None:
    html = """
    <html>
      <head><title>Band - Encyclopaedia Metallum: The Metal Archives</title></head>
      <body>
        <h1 class="band_name"><a href="/bands/Band/1">Band</a></h1>
        <dl>
          <dt>Country of origin:</dt><dd>England</dd>
          <dt>Location:</dt><dd>London</dd>
        </dl>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(source_url="https://www.metal-archives.com/bands/Band/1")
    )

    assert draft.origin == "UK, London"


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


def test_wikipedia_artist_url_from_name_returns_verified_existing_page(monkeypatch) -> None:
    monkeypatch.setattr(
        importer,
        "_fetch_wikipedia_page_info",
        lambda title: {
            "title": "The Smashing Pumpkins",
            "fullurl": "https://en.wikipedia.org/wiki/The_Smashing_Pumpkins",
            "pageprops": {"wikibase-shortdesc": "American alternative rock band"},
        },
    )
    monkeypatch.setattr(importer, "_fetch_wikipedia_search_titles", lambda artist_name: [])

    assert importer.wikipedia_artist_url_from_name("The Smashing Pumpkins") == "https://en.wikipedia.org/wiki/The_Smashing_Pumpkins"


def test_wikipedia_artist_url_from_name_returns_none_for_missing_page(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_fetch_wikipedia_page_info", lambda title: None)
    monkeypatch.setattr(importer, "_fetch_wikipedia_search_titles", lambda artist_name: [])

    assert importer.wikipedia_artist_url_from_name("Port Noir") is None


def test_wikipedia_artist_url_from_name_rejects_matching_non_music_page(monkeypatch) -> None:
    def fake_page_info(title: str) -> dict[str, object] | None:
        if title == "Port Noir":
            return None
        if title == "Port-Noir":
            return {
                "title": "Port-Noir",
                "fullurl": "https://en.wikipedia.org/wiki/Port-Noir",
                "pageprops": {"wikibase-shortdesc": "Marina like harbor in Geneva, Switzerland"},
            }
        return None

    monkeypatch.setattr(importer, "_fetch_wikipedia_page_info", fake_page_info)
    monkeypatch.setattr(importer, "_fetch_wikipedia_search_titles", lambda artist_name: ["Port-Noir"])

    assert importer.wikipedia_artist_url_from_name("Port Noir") is None


def test_wikipedia_artist_url_from_name_prefers_band_disambiguation(monkeypatch) -> None:
    def fake_page_info(title: str) -> dict[str, object] | None:
        if title == "Port Noir":
            return None
        if title == "Port Noir (band)":
            return {
                "title": "Port Noir (band)",
                "fullurl": "https://en.wikipedia.org/wiki/Port_Noir_(band)",
                "pageprops": {"wikibase-shortdesc": "Swedish rock band"},
            }
        if title == "Port-Noir":
            return {
                "title": "Port-Noir",
                "fullurl": "https://en.wikipedia.org/wiki/Port-Noir",
                "pageprops": {"wikibase-shortdesc": "Marina like harbor in Geneva, Switzerland"},
            }
        return None

    monkeypatch.setattr(importer, "_fetch_wikipedia_page_info", fake_page_info)
    monkeypatch.setattr(importer, "_fetch_wikipedia_search_titles", lambda artist_name: ["Port-Noir", "Port Noir (band)"])

    assert importer.wikipedia_artist_url_from_name("Port Noir") == "https://en.wikipedia.org/wiki/Port_Noir_(band)"


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

    assert draft.origin == "USA, Edison, New Jersey"


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

    assert draft.origin == "USA, Edison, New Jersey"


def test_wikipedia_artist_draft_prefers_born_location_over_musical_origin(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Stephen Sanchez - Wikipedia</title>
      </head>
      <body>
        <table class="infobox biography vcard">
          <tr>
            <th>Born</th>
            <td>
              Stephen Christopher Sanchez (2002-11-03) November 3, 2002
              (age 23)<sup>[1]</sup><br />
              <a>El Dorado Hills, California</a>, U.S.<sup>[2]</sup>
            </td>
          </tr>
          <tr><th>Origin</th><td><a>Nashville</a>, <a>Tennessee</a><sup>[3]</sup></td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="Stephen Sanchez",
            source_url="https://en.wikipedia.org/wiki/Stephen_Sanchez",
        )
    )

    assert draft.origin == "USA, El Dorado Hills, California"


def test_wikipedia_artist_draft_adds_usa_for_state_only_origin(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Yot Club - Wikipedia</title>
      </head>
      <body>
        <table class="infobox biography vcard">
          <tr><th>Born</th><td>John Ryan Kaiser<sup>[1]</sup></td></tr>
          <tr><th>Origin</th><td><a>Mississippi</a></td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="Yot Club",
            source_url="https://en.wikipedia.org/wiki/Yot_Club",
        )
    )

    assert draft.origin == "USA, Mississippi"


def test_wikipedia_artist_draft_adds_usa_for_city_state_origin(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Band - Wikipedia</title>
      </head>
      <body>
        <table class="infobox vcard">
          <tr><th>Origin</th><td><a>Hattiesburg</a>, <a>Mississippi</a></td></tr>
        </table>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="Band",
            source_url="https://en.wikipedia.org/wiki/Band",
        )
    )

    assert draft.origin == "USA, Hattiesburg, Mississippi"


@pytest.mark.parametrize("comment", ["early", "EARLY", "early work"])
def test_imported_genres_skip_early_comments(comment) -> None:
    assert importer._normalize_imported_genre(
        f"Alternative Rock / Indie Rock / Power Pop / Post-Hardcore ({comment})"
    ) == "Alternative Rock / Indie Rock / Power Pop"
    assert importer._normalize_wikipedia_genres_from_html(
        f"<ul><li>Alternative rock</li><li>Indie rock</li><li>Power pop</li>"
        f"<li>Post-hardcore <small>({comment})</small><sup>[1]</sup></li></ul>"
    ) == "Alternative Rock / Indie Rock / Power Pop"
    assert importer._normalize_imported_genre(f"Post-Hardcore ({comment})") is None
    assert importer._normalize_imported_genre("Early Music / Rock (later)") == "Early Music / Rock (later)"


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


def test_wikipedia_artist_draft_extracts_lead_paragraphs_when_meta_description_is_missing(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>The Lemon Twigs - Wikipedia</title>
      </head>
      <body>
        <div id="mw-content-text" class="mw-body-content">
          <div class="mw-parser-output">
            <div class="shortdescription nomobile noexcerpt noprint searchaux">American rock band</div>
            <table class="infobox vcard">
              <tr><th>Origin</th><td>Hicksville, Long Island, New York, U.S.</td></tr>
              <tr><th>Genres</th><td><a>Power pop</a>, <a>glam rock</a></td></tr>
            </table>
            <p><b>The Lemon Twigs</b> are an American rock band from Hicksville, Long Island, New York.<sup>[1]</sup></p>
            <p>The band's music has been noted for its stylistic roots in 1960s and 1970s pop and rock music. [ 2 ]</p>
            <h2><span>History</span></h2>
            <p>This later section should not be imported.</p>
          </div>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="",
            source_url="https://en.wikipedia.org/wiki/The_Lemon_Twigs",
        )
    )

    assert draft.artist_name == "The Lemon Twigs"
    assert draft.origin == "USA, Hicksville, Long Island, New York"
    assert draft.genre == "Power Pop / Glam Rock"
    assert draft.description == (
        "The Lemon Twigs are an American rock band from Hicksville, Long Island, New York.\n\n"
        "The band's music has been noted for its stylistic roots in 1960s and 1970s pop and rock music."
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


def test_ytm_curl_fallback_preserves_late_metadata_and_reuses_page(monkeypatch) -> None:
    import json
    import subprocess
    from urllib.error import URLError

    data = {"header": {"subtitle": {"runs": [
        {"text": "Album"}, {"text": " • "}, {"text": "2026"},
    ]}}, "contents": [{"musicResponsiveListItemRenderer": {
        "flexColumns": [{"musicResponsiveListItemFlexColumnRenderer": {
            "text": {"runs": [{"text": "Resistance"}]},
        }}],
        "fixedColumns": [{"musicResponsiveListItemFixedColumnRenderer": {
            "text": {"runs": [{"text": "5:02"}]},
        }}],
    }}]}
    encoded = "".join(f"\\x{byte:02x}" for byte in json.dumps(data).encode())
    html = ('<html><head><script>' + 'x' * 90_000 + '</script>'
            + '<meta property="og:title" content="Latent">'
            + '<meta property="og:description" content="Album • Einvigi">'
            + '<meta property="og:image" content="https://example.com/cover.jpg">'
            + f"</head><script>initialData.push({{data: '{encoded}'}});</script></html>")
    monkeypatch.setattr(importer, "_validate_source_url", lambda url: None)

    def fail_urllib(url):
        raise URLError("connection failed")

    calls = []

    def curl(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=html)

    monkeypatch.setattr(importer, "_fetch_with_urllib", fail_urllib)
    monkeypatch.setattr(importer.subprocess, "run", curl)
    draft = importer.SourceMetadataImporter().create_album_draft(
        ImportRequest(source_url="https://music.youtube.com/playlist?list=OLAK5uy_lgSZm2091sEvuJKzjV_5Oy9Y4in5yTMVI&si=kHnCXJo-wwKtzhsI"),
        model="unused",
    )
    assert draft.album_title == "Latent"
    assert draft.artist_name == "Einvigi"
    assert draft.release_year == 2026
    assert draft.tracks[0].title == "Resistance"
    assert draft.duration_seconds == 302
    assert draft.cover_source_url == "https://example.com/cover.jpg"
    assert len(calls) == 1


def test_ytm_recovers_metadata_from_second_fetch(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_page_metadata", lambda url: {})
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: (
        '<meta property="og:title" content="Latent">'
        '<meta property="og:description" content="Album • Einvigi">'
        '<meta property="og:image" content="https://example.com/cover.jpg">'
    ))
    monkeypatch.setattr(importer, "_extract_yt_playlist_tracks", lambda pid: [])
    draft = importer.SourceMetadataImporter().create_album_draft(
        ImportRequest(source_url="https://music.youtube.com/playlist?list=album"), model="unused",
    )
    assert draft.album_title == "Latent"
    assert draft.artist_name == "Einvigi"
    assert draft.cover_source_url == "https://example.com/cover.jpg"


def test_ytm_failed_fetch_does_not_return_empty_draft(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_page_metadata", lambda url: {})
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: "")
    monkeypatch.setattr(importer, "_extract_yt_playlist_tracks", lambda pid: [])
    source = importer.SourceMetadataImporter()
    with pytest.raises(ValueError, match="YouTube Music did not return album metadata"):
        source.create_album_draft(
            ImportRequest(source_url="https://music.youtube.com/playlist?list=unavailable"), model="unused",
        )
    assert source.last_request_failed


def test_ytm_album_draft_extracts_artist_from_current_metadata_shape(monkeypatch) -> None:
    og_html = """
    <html>
      <head>
        <meta property="og:title" content="South of Here">
        <meta property="og:description" content="Album • Nathaniel Rateliff &amp; The Night Sweats">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (og_html, "text/html"))
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: "")
    monkeypatch.setattr(importer, "_extract_yt_playlist_tracks", lambda pid: [])

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_khCwUHay5bEvkwb_3ZkyUx-JflMifEThc",
        )
    )

    assert draft.album_title == "South of Here"
    assert draft.artist_name == "Nathaniel Rateliff & The Night Sweats"


def test_ytm_browse_album_draft_discards_type_and_artist_label_from_notes() -> None:
    draft = importer._youtube_music_album_draft_from_browse(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/watch?v=xUG2IuSpLqI",
        ),
        {
            "microformat": {
                "microformatDataRenderer": {
                    "title": "Example Album - Album by Example Artist",
                    "description": "Album \u2022 Example Artist",
                }
            }
        },
        "https://music.youtube.com/watch?v=xUG2IuSpLqI",
    )

    assert draft is not None
    assert draft.notes is None


def test_ytm_artist_draft_extracts_artist_from_current_metadata_shape(monkeypatch) -> None:
    og_html = """
    <html>
      <head>
        <meta property="og:title" content="South of Here">
        <meta property="og:description" content="Album • Nathaniel Rateliff &amp; The Night Sweats">
      </head>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (og_html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_khCwUHay5bEvkwb_3ZkyUx-JflMifEThc",
        )
    )

    assert draft.artist_name == "Nathaniel Rateliff & The Night Sweats"


def test_ytm_album_draft_decodes_album_data_with_escaped_quotes(monkeypatch) -> None:
    og_html = """
    <html>
      <head>
        <meta property="og:title" content="Angel Face - Album by Stephen Sanchez">
        <meta property="og:image" content="https://lh3.googleusercontent.com/cover.jpg">
      </head>
    </html>
    """
    import json as _json

    album_obj = {
        "header": {
            "subtitle": {"runs": [{"text": "Album"}, {"text": " \u2022 "}, {"text": "2023"}]},
            "description": {
                "runs": [
                    {
                        "text": (
                            'The album was preceded by three singles: "Evangeline", '
                            '"Only Girl" and "Be More".'
                        )
                    }
                ]
            },
        },
        "musicShelfRenderer": {
            "contents": [
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Something About Her", "3:44")},
                {"musicResponsiveListItemRenderer": _make_ytm_renderer("Evangeline", "2:57")},
            ]
        },
    }

    def _js_data_literal(obj: dict) -> str:
        raw = _json.dumps(obj).replace("/", r"\/")
        return raw.replace(r"\"", r"\\\x22").replace('"', r'\x22')

    ytm_page = f"initialData.push({{data: '{_js_data_literal(album_obj)}'}});\n"

    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (og_html, "text/html"))
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: ytm_page)
    monkeypatch.setattr(importer, "_extract_yt_playlist_tracks", lambda pid: [])

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_lr8rVu4_hwNrG3Xjs1YzRZgp7hPbBKGnE",
        )
    )

    assert draft.album_title == "Angel Face"
    assert draft.artist_name == "Stephen Sanchez"
    assert draft.release_year == 2023
    assert [track.title for track in draft.tracks] == ["Something About Her", "Evangeline"]


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
    assert draft.notes == "Album description."
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


def test_bandcamp_artist_draft_moves_location_out_of_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <title>Music | Witch Fever</title>
        <meta name="description" content="
Witch Fever.
Manchester, UK.
">
        <meta property="og:title" content="Witch Fever">
        <meta property="og:description" content="">
      </head>
      <body>
        <p id="band-name-location">
          <span class="title">Witch Fever</span>
          <span class="location secondaryText">Manchester, UK</span>
        </p>
        <div class="signed-out-artists-bio-text"></div>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(source_url="https://witchfever.bandcamp.com/music")
    )

    assert draft.artist_name == "Witch Fever"
    assert draft.origin == "UK, Manchester"
    assert draft.description is None
    assert draft.external_url == "https://witchfever.bandcamp.com/music"


def test_bandcamp_artist_draft_keeps_real_bio_description(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Example Band">
        <meta name="description" content="Example Band. Leeds, UK.">
      </head>
      <body>
        <span class="location secondaryText">Leeds, UK</span>
        <div class="signed-out-artists-bio-text">
          Noisy post-punk from northern England.
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(source_url="https://exampleband.bandcamp.com/music")
    )

    assert draft.artist_name == "Example Band"
    assert draft.origin == "UK, Leeds"
    assert draft.description == "Noisy post-punk from northern England."


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


def test_alterportal_album_draft_parses_current_wrapped_fields_and_track_durations(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="The Haunted Youth - Boys Cry Too (2026)">
        <meta property="og:image" content="https://i.ibb.co/sphL1BHj/600px-cover.jpg">
      </head>
      <body>
        <b><span style="color:#00FF00">Стиль</span></b>: <b>Indie Rock / Dream Pop</b><br>
        <b><span style="color:#00FF00">Страна</span></b>: <b>Hasselt, Belgium</b><br>
        <b><span style="color:#00FF00">Формат</span></b>: <b>MP3 CBR 320Kbps</b><br>
        <b><span style="color:#00FF00">Дата релиза</span></b>: <b>08.05.2026</b><br><br>
        <b>Треклист</b>:<br>
        1. in my head [08:05]<br>
        2. castlevania [04:03]<br>
        3. deathwish [03:27]<br>
        <br>
        <b>Download:</b><br>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_album_draft(
        ImportRequest(
            artist_name="",
            source_url="https://alterportal.net/2026_albums/189159-the-haunted-youth-boys-cry-too-2026.html",
        )
    )

    assert draft.artist_name == "The Haunted Youth"
    assert draft.album_title == "Boys Cry Too"
    assert draft.release_year == 2026
    assert draft.genre == "Indie Rock"
    assert draft.duration_seconds == 15 * 60 + 35
    assert draft.cover_source_url == "https://i.ibb.co/sphL1BHj/600px-cover.jpg"
    assert draft.notes == "Format: MP3 CBR 320Kbps"
    assert [track.title for track in draft.tracks] == ["In my head", "Castlevania", "Deathwish"]
    assert [track.duration_seconds for track in draft.tracks] == [8 * 60 + 5, 4 * 60 + 3, 3 * 60 + 27]


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


def test_alterportal_artist_draft_parses_artist_from_album_url_without_explicit_name(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="The Haunted Youth - Boys Cry Too (2026)">
      </head>
      <body>
        <b><span style="color:#00FF00">Стиль</span></b>: <b>Indie Rock / Dream Pop</b><br>
        <b><span style="color:#00FF00">Страна</span></b>: <b>Hasselt, Belgium</b><br>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(
            source_url="https://alterportal.net/2026_albums/189159-the-haunted-youth-boys-cry-too-2026.html",
        )
    )

    assert draft.artist_name == "The Haunted Youth"
    assert draft.origin == "Belgium, Hasselt"
    assert draft.genre == "Indie Rock"


def test_alterportal_artist_draft_normalizes_england_origin_to_uk(monkeypatch) -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Band - Album (2026)">
      </head>
      <body>
        <b><span style="color:#00FF00">Стиль</span></b>: <b>Alternative Rock</b><br>
        <b><span style="color:#00FF00">Страна</span></b>: <b>London, England</b><br>
      </body>
    </html>
    """
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    draft = importer._best_effort_artist_draft(
        ImportRequest(source_url="https://alterportal.net/2026_albums/1-band-album-2026.html")
    )

    assert draft.origin == "UK, London"


@pytest.mark.parametrize('path', ['album', 'intl-de/album', 'embed/album'])
def test_spotify_album_import_from_embed(monkeypatch, path) -> None:
    from pathlib import Path

    html = (Path(__file__).parent / 'fixtures/spotify_album_embed.html').read_text()
    monkeypatch.setattr(importer, '_fetch_url_document', lambda url: (html if '/embed/' in url else '', 'text/html'))
    source = f'https://open.spotify.com/{path}/3hHJYONrtR5FxTrOe78qNL?si=shared'
    draft = importer.SourceMetadataImporter().create_album_draft(ImportRequest(source_url=source), model='unused')
    assert draft.artist_name == 'Arab Strap'
    assert draft.album_title == 'Half-Told Tales'
    assert len(draft.tracks) == 14
    assert draft.tracks[0].duration_seconds == 203
    assert draft.tracks[-1].title == 'Beats Per Minute'
    assert draft.duration_seconds == sum(t.duration_seconds for t in draft.tracks)
    assert draft.album_stream_url == 'https://open.spotify.com/album/3hHJYONrtR5FxTrOe78qNL'
    assert importer._normalize_cover_source_url(draft.cover_source_url, source) == draft.cover_source_url
    assert '0000b273' in draft.cover_source_url
    artist = importer._best_effort_artist_draft(ImportRequest(source_url=source))
    assert artist.artist_name == 'Arab Strap'
    assert artist.description is None


def test_spotify_album_uses_metadata_when_embed_unavailable(monkeypatch) -> None:
    html = '<meta property="og:title" content="Half-Told Tales - Album by Arab Strap | Spotify"><meta property="og:description" content="Arab Strap · Album · 2025 · 14 songs.">'
    monkeypatch.setattr(importer, '_fetch_url_document', lambda url: ('<script id="__NEXT_DATA__">broken</script>' if '/embed/' in url else html, 'text/html'))
    draft = importer._best_effort_album_draft(ImportRequest(source_url='https://open.spotify.com/album/abc'))
    assert draft.artist_name == 'Arab Strap'
    assert draft.album_title == 'Half-Told Tales'
    assert draft.release_year == 2025
    assert draft.album_type == 'Full-length'
    assert draft.tracks == []
    assert 'Spotify tracklist unavailable' in draft.notes


@pytest.mark.parametrize('initial_embed', ['', '<script id="__NEXT_DATA__">broken</script>'])
def test_spotify_album_retries_missing_tracklist(monkeypatch, initial_embed) -> None:
    from pathlib import Path

    embed = (Path(__file__).parent / 'fixtures/spotify_deafheaven_embed.html').read_text()
    calls = []

    def fetch(url):
        calls.append(url)
        if 'utm_source=oembed' in url:
            return embed, 'text/html'
        if '/embed/' in url:
            return initial_embed, 'text/html'
        return '<meta property="og:title" content="At Work In The Fields Of The Bomb - EP by Deafheaven | Spotify">', 'text/html'

    monkeypatch.setattr(importer, '_fetch_url_document', fetch)
    draft = importer.SourceMetadataImporter().create_album_draft(
        ImportRequest(source_url='https://open.spotify.com/album/7tIVbLtTqWrlTnoPiLLA1R?si=shared'), model='unused'
    )
    assert [track.title for track in draft.tracks] == ['Hunter', 'Three Princes', 'Sorry Laid The Hearth']
    assert [track.duration_seconds for track in draft.tracks] == [436, 175, 767]
    assert draft.duration_seconds == 1378
    assert draft.notes is None
    assert calls[-1].endswith('?utm_source=oembed')


def test_spotify_album_unavailable_raises(monkeypatch) -> None:
    monkeypatch.setattr(importer, '_fetch_url_document', lambda url: ('<title>Spotify</title>', 'text/html'))
    with pytest.raises(ValueError, match='Could not read Spotify album metadata'):
        importer._best_effort_album_draft(ImportRequest(source_url='https://open.spotify.com/album/abc'))


@pytest.mark.parametrize('metadata_description', [False, True])
def test_artist_description_has_no_spaces_before_punctuation(monkeypatch, metadata_description) -> None:
    description = (
        'Arab Strap are a Scottish indie rock band whose core members are '
        '<a>Aidan Moffat</a> and <a>Malcolm Middleton</a>.<sup>[1]</sup> '
        'The band were signed to independent record label <a>Chemikal Underground</a>, '
        'split in 2006 and reformed in 2016. '
        'The band signed to <a>Rock Action Records</a>&nbsp;[2] in 2020.'
    )
    if metadata_description:
        html = '<meta name="description" content="Arab Strap are a Scottish indie rock band . They signed to Chemikal Underground , then Rock Action Records .">'
        expected = 'Arab Strap are a Scottish indie rock band. They signed to Chemikal Underground, then Rock Action Records.'
    else:
        html = '<body><p>' + description + '</p></body>'
        expected = (
            'Arab Strap are a Scottish indie rock band whose core members are Aidan Moffat and Malcolm Middleton. '
            'The band were signed to independent record label Chemikal Underground, split in 2006 and reformed in 2016. '
            'The band signed to Rock Action Records in 2020.'
        )
    monkeypatch.setattr(importer, '_fetch_url_document', lambda url: (html, 'text/html'))
    draft = importer.SourceMetadataImporter().create_artist_draft(
        ImportRequest(artist_name='Arab Strap', source_url='https://en.wikipedia.org/wiki/Arab_Strap'), model='unused'
    )
    assert draft.description == expected


def test_wikipedia_citation_removal_preserves_punctuation_spacing() -> None:
    assert importer._clean_wikipedia_text('A band [1], formed in 1996 [ 2 ].') == 'A band, formed in 1996.'


@pytest.mark.parametrize('date_attribute', ['name', 'property'])
def test_spotify_shared_album_year_from_canonical_release_date(monkeypatch, date_attribute) -> None:
    from pathlib import Path

    embed = (Path(__file__).parent / 'fixtures/spotify_album_embed.html').read_text()
    canonical = 'https://open.spotify.com/album/3hHJYONrtR5FxTrOe78qNL'
    def fetch(url):
        if '/embed/' in url:
            return embed, 'text/html'
        if url == canonical:
            return f'<meta {date_attribute}="music:release_date" content="2026-09-04">', 'text/html'
        return '<title>Spotify</title>', 'text/html'
    monkeypatch.setattr(importer, '_fetch_url_document', fetch)
    draft = importer.SourceMetadataImporter().create_album_draft(
        ImportRequest(source_url=canonical + '?si=shared'), model='unused'
    )
    assert draft.release_year == 2026
    assert len(draft.tracks) == 14


def test_spotify_year_does_not_use_numbers_in_artist_name(monkeypatch) -> None:
    html = '<meta property="og:title" content="Example - Album by The 1975 | Spotify"><meta property="og:description" content="The 1975 · Album · 2026 · 14 songs">'
    monkeypatch.setattr(importer, '_fetch_url_document', lambda url: (html, 'text/html'))
    draft = importer._best_effort_album_draft(ImportRequest(source_url='https://open.spotify.com/album/abc'))
    assert draft.release_year == 2026


def test_spotify_album_fetch_requests_public_preview_metadata(monkeypatch) -> None:
    monkeypatch.setattr(importer, '_validate_source_url', lambda url: None)
    calls = []
    def fetch(url, user_agent):
        calls.append((url, user_agent))
        return '<meta name="music:release_date" content="2026-09-04">', 'text/html'
    monkeypatch.setattr(importer, '_fetch_with_curl_ua', fetch)
    monkeypatch.setattr(importer, '_fetch_with_urllib', lambda url: pytest.fail('Browser page omits release metadata'))
    metadata = importer._page_metadata('https://open.spotify.com/intl-de/album/abc?si=shared')
    assert calls == [('https://open.spotify.com/album/abc', 'Twitterbot/1.0')]
    assert '2026-09-04' in metadata['html']


def test_album_description_generator_researches_release_and_filters_sources(monkeypatch) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "Recorded in Helsinki.")
    captured = {}

    class FakeClient:
        def generate_json_with_web_search(self, **kwargs):
            captured.update(kwargs)
            return {"description": "A black metal album.", "sources": [
                {"title": "Label", "url": "https://example.com/album"},
                {"title": "Bad", "url": "javascript:alert(1)"},
            ]}, [{"title": "Label", "url": "https://example.com/album"}]

    generator = importer.AlbumWriteupGenerator(FakeClient())
    description, sources = generator.generate_album_description(
        "Band", album_title="Album", release_year=2026, origin=None, genre="Black Metal",
        source_url="https://example.com/album", model="selected-model",
    )
    assert description == "A Black Metal album."
    assert sources == [{"title": "Label", "url": "https://example.com/album"}]
    assert captured["model"] == "selected-model"
    assert captured["schema_name"] == "album_description"
    assert "not an artist biography" in captured["user_prompt"]
    assert "Album: Album" in captured["user_prompt"]
    assert "Release year: 2026" in captured["user_prompt"]
    assert "Recorded in Helsinki." in captured["user_prompt"]


def test_album_description_generator_rejects_empty_result() -> None:
    class FakeClient:
        def generate_json_with_web_search(self, **kwargs):
            return {"description": " ", "sources": []}, []

    with pytest.raises(importer.AIClientError, match="empty album description"):
        importer.AlbumWriteupGenerator(FakeClient()).generate_album_description(
            "Band", album_title="Album", release_year=None, origin=None, genre=None,
            source_url=None, model="selected-model",
        )


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("limited", [True, False])
def test_writeup_telegram_limit_enforced_after_listening_links(monkeypatch, language, limited) -> None:
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    monkeypatch.setattr(importer, "_find_spotify_album_url", lambda *args: None)
    captured = {}
    original = "Band — Album\n\n" + "Музыка 🎶 with detail. " * 400

    class FakeClient:
        def generate_json_with_web_search(self, **kwargs):
            captured["prompt"] = kwargs["user_prompt"]
            return {"overview": original + "\n\nTracklist:\n1. Unwanted track\n2. Another track", "sources": []}, []

    generator = importer.AlbumWriteupGenerator(FakeClient())
    album = AlbumDetailRecord(
        id=1, artist_id=1, artist_name="Band", title="Album",
        album_stream_url="https://music.youtube.com/playlist?list=test",
        created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
    )
    kwargs = {} if limited else {"limit_for_telegram": False}
    result = generator.generate_album_writeup(album, language=language, model="gpt-5", **kwargs)
    assert (len(result.encode("utf-16-le")) // 2 <= 4096) is limited
    assert ("entire post must fit within 4096" in captured["prompt"]) is limited
    assert "[YouTube Music](https://music.youtube.com/playlist?list=test)" in result
    assert "[Spotify](https://open.spotify.com/search/" in result
    assert result.startswith("Band — Album")
    assert "Tracklist:" not in result
    assert "Unwanted track" not in result
    assert "Never include a tracklist" in captured["prompt"]
    assert "STRICT FORMAT" in captured["prompt"]
    if not limited:
        assert result.startswith(original.rstrip())


def test_telegram_limit_leaves_short_writeup_unchanged() -> None:
    text = "Band — Album\n\nShort description.\n\n🎧 Listen:\n[Spotify](https://example.com)"
    assert importer._limit_telegram_writeup(text) == text


@pytest.mark.parametrize("heading", ["Tracklist:", "## Track listing", "**Tracks:**", "🎶 Трек-лист:", "Список композиций:"])
def test_writeup_removes_tracklist_but_keeps_ratings_and_listen(heading) -> None:
    before = "🎸 Album: Band — Album\n\n📌 Description:\nThe song First is a highlight."
    after = "⭐ User ratings:\nRYM: 4/5 (100 ratings)\n\n🎧 Listen:\n[Spotify](https://example.com)"
    draft = f"{before}\n\n{heading}\n1. First 3:00\n2. Second 4:00\n\n{after}"
    assert importer._clean_writeup_format(draft) == f"{before}\n\n{after}"


@pytest.mark.parametrize("extra", ["Tracklist:\n- First\n- Second", "1. First 3:00\n2. Second 4:00", "Bonus tracks:\nUnwanted outro"])
def test_writeup_listen_is_last_section(extra) -> None:
    expected = "📌 Description:\nAlbum prose.\n\n🎧 Слушать:\n[Spotify](https://example.com)"
    assert importer._clean_writeup_format(f"{expected}\n\n{extra}") == expected


def test_writeup_removes_bare_numbered_tracklist_without_listen() -> None:
    draft = "📌 Description:\nAlbum prose.\n\n1. First\n2. Second\n"
    assert importer._clean_writeup_format(draft) == "📌 Description:\nAlbum prose."


def test_artist_bio_returns_album_era_genre_even_when_prose_omits_it(monkeypatch):
    monkeypatch.setattr(importer, "_fetch_url_excerpt", lambda url: "")
    captured = {}

    class FakeClient:
        def generate_json_with_web_search(self, **kwargs):
            captured.update(kwargs)
            return {"description": "A band whose sound changed over time.",
                    "genre": "Death Metal", "origin": "Hobart, Tasmania, Australia", "origin_country": "Australia", "sources": []}, []

    generator = importer.AlbumWriteupGenerator(FakeClient())
    description = generator.generate_artist_description(
        "Changing Band", origin=None, album_title="Early Album", release_year=1992,
        genre="Progressive Rock", source_url=None, model="test",
    )
    assert generator.last_artist_description_genre == "Death Metal"
    assert generator.last_artist_description_origin == "Australia, Hobart, Tasmania"
    assert "origin" in captured["schema"]["required"]
    assert "Death Metal" in description
    assert "Early Album" in description
    assert "Album release year: 1992" in captured["user_prompt"]
    assert "not the artist's current or best-known style" in captured["user_prompt"]
    assert "original release era rather than a reissue date" in captured["user_prompt"]
    assert "genre" in captured["schema"]["required"]


def test_ytm_retries_shell_with_initial_data_but_no_album_metadata(monkeypatch):
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parent / "fixtures" / "ytm_in_throes_album.json").read_text())
    shell = "initialData.push({data: '" + json.dumps({"guide": {}}) + "'});"
    full = "initialData.push({data: '" + json.dumps(data) + "'});"
    monkeypatch.setattr(importer, "_fetch_ytm_full_page", lambda url: full)
    draft = importer._youtube_music_album_draft(
        ImportRequest(source_url="https://music.youtube.com/playlist?list=OLAK5uy_mgdC0vetcaMyZCUjWD7NvR1A9l-hde8qA"),
        shell, {"title": "Sink Towards the Light", "description": "Album • In Throes"},
    )
    assert draft.release_year == 2026
    assert len(draft.tracks) == 7
    assert draft.duration_seconds == 2507
