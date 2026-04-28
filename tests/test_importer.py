from __future__ import annotations

import pytest

from album_ranker import importer
from album_ranker.schemas import ImportRequest


# ── _fix_allcaps ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("EXHALE THE PAST // INHALE THE FUTURE", "Exhale The Past // Inhale The Future"),
    ("LITTLE GIRL", "Little Girl"),
    ("PREDATOR", "Predator"),
    ("Burn The Ships", "Burn The Ships"),
    ("In Flames", "In Flames"),
    ("WYRD", "Wyrd"),
    ("", ""),
    ("ABCDEf", "ABCDEf"),
])
def test_fix_allcaps(text: str, expected: str) -> None:
    assert importer._fix_allcaps(text) == expected


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


def test_allcaps_album_title_via_ai_merge_is_normalised(monkeypatch) -> None:
    html = "<html><head></head><body></body></html>"
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    class FakeClient:
        def generate_json(self, **kwargs):
            return {
                "artist_name": "HIMITZU",
                "artist_description": None,
                "artist_description_source_url": None,
                "artist_description_source_label": None,
                "album_external_url": None,
                "album_title": "EXHALE THE PAST // INHALE THE FUTURE",
                "release_year": 2026,
                "genre": None,
                "duration_seconds": None,
                "cover_source_url": None,
                "album_type": None,
                "notes": None,
                "tracks": [
                    {"track_number": 1, "title": "LITTLE GIRL", "duration_seconds": 178},
                    {"track_number": 2, "title": "PREDATOR", "duration_seconds": 236},
                ],
            }

    metadata_importer = importer.MetadataImporter(FakeClient())
    draft = metadata_importer.create_album_draft(
        ImportRequest(
            artist_name="HIMITZU",
            album_title="",
            source_url="https://music.youtube.com/playlist?list=OLAK5uy_example",
        ),
        model="gpt-5",
    )

    assert draft.album_title == "Exhale The Past // Inhale The Future"
    assert draft.tracks[0].title == "Little Girl"
    assert draft.tracks[1].title == "Predator"


def test_mixed_case_title_is_left_unchanged_by_ai_merge(monkeypatch) -> None:
    html = "<html><head></head><body></body></html>"
    monkeypatch.setattr(importer, "_fetch_url_document", lambda url: (html, "text/html"))

    class FakeClient:
        def generate_json(self, **kwargs):
            return {
                "artist_name": "In Flames",
                "artist_description": None,
                "artist_description_source_url": None,
                "artist_description_source_label": None,
                "album_external_url": None,
                "album_title": "Come Clarity",
                "release_year": 2006,
                "genre": None,
                "duration_seconds": None,
                "cover_source_url": None,
                "album_type": None,
                "notes": None,
                "tracks": [
                    {"track_number": 1, "title": "Take This Life", "duration_seconds": 200},
                ],
            }

    metadata_importer = importer.MetadataImporter(FakeClient())
    draft = metadata_importer.create_album_draft(
        ImportRequest(
            artist_name="In Flames",
            album_title="Come Clarity",
            source_url="https://example.com/in-flames",
        ),
        model="gpt-5",
    )

    assert draft.album_title == "Come Clarity"
    assert draft.tracks[0].title == "Take This Life"


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
    assert draft.description_source_label == "www.metal-archives.com"
    assert draft.origin == "Finland, Oulu"
    assert draft.genre == "Gothic Metal"


def test_best_effort_artist_draft_uses_metal_archives_genre_when_no_meta_description(monkeypatch) -> None:
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

    assert draft.description.startswith("Genre: Gothic Metal")


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
