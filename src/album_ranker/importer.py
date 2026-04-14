from __future__ import annotations

import json
import re
import subprocess
from html import unescape as _html_unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from album_ranker.openai_client import OpenAIClient, OpenAIClientError
from album_ranker.schemas import AlbumDraftData, ArtistDraftData, ImportRequest, display_to_seconds

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html_unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_with_urllib(url: str) -> tuple[str, str]:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(100000).decode("utf-8", errors="ignore")
    return raw, content_type


def _fetch_with_curl(url: str) -> tuple[str, str]:
    result = subprocess.run(
        [
            "curl",
            "-L",
            "-sS",
            "-A",
            DEFAULT_HEADERS["User-Agent"],
            "--max-time",
            "30",
            url,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout[:40000], "text/html"


def _fetch_with_curl_ua(url: str, user_agent: str) -> tuple[str, str]:
    result = subprocess.run(
        ["curl", "-L", "-sS", "-A", user_agent, "--max-time", "30", url],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout[:40000], "text/html"


def _fetch_url_document(url: str) -> tuple[str, str]:
    # Facebook blocks generic crawlers but serves OG metadata to its own externalhit UA
    if "facebook.com/" in url:
        return _fetch_with_curl_ua(url, "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)")
    try:
        return _fetch_with_urllib(url)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return _fetch_with_curl(url)


def _fetch_url_excerpt(url: str) -> str:
    raw, content_type = _fetch_url_document(url)
    if "html" in content_type.lower():
        return _strip_html(raw)[:12000]
    return raw[:12000]


def _host_label(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None


def _extract_title(html: str) -> str | None:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return None
    return _strip_html(match.group(1)) or None


def _extract_meta_content(html: str, key: str, *, attr: str = "property") -> str | None:
    pattern = rf'(?is)<meta[^>]+{attr}\s*=\s*["\']{re.escape(key)}["\'][^>]+content\s*=\s*["\'](.*?)["\']'
    match = re.search(pattern, html)
    if match:
        return _strip_html(match.group(1)) or None
    reverse_pattern = rf'(?is)<meta[^>]+content\s*=\s*["\'](.*?)["\'][^>]+{attr}\s*=\s*["\']{re.escape(key)}["\']'
    match = re.search(reverse_pattern, html)
    if match:
        return _strip_html(match.group(1)) or None
    return None


def _page_metadata(url: str | None) -> dict[str, Any]:
    if not url:
        return {}
    try:
        raw, content_type = _fetch_url_document(url)
        fetch_method = "urllib_or_curl"
        fetch_error = None
    except (HTTPError, URLError, TimeoutError, ValueError, subprocess.CalledProcessError) as exc:
        return {"url": url, "source_label": _host_label(url), "fetch_error": str(exc)}
    if "html" not in content_type.lower():
        return {
            "url": url,
            "source_label": _host_label(url),
            "fetch_error": f"Unsupported content type: {content_type}",
        }
    title = (
        _extract_meta_content(raw, "og:title")
        or _extract_meta_content(raw, "twitter:title", attr="name")
        or _extract_title(raw)
    )
    description = (
        _extract_meta_content(raw, "og:description")
        or _extract_meta_content(raw, "description", attr="name")
        or _extract_meta_content(raw, "twitter:description", attr="name")
    )
    image = (
        _extract_meta_content(raw, "og:image")
        or _extract_meta_content(raw, "twitter:image", attr="name")
    )
    return {
        "title": title,
        "description": description,
        "image": image,
        "html": raw,
        "excerpt": _strip_html(raw)[:4000],
        "fetch_method": fetch_method,
        "fetch_error": fetch_error,
        "url": url,
        "source_label": _host_label(url),
    }


def _extract_anchor_text(html: str, class_name: str) -> str | None:
    pattern = rf'(?is)<h[12][^>]*class=["\']{re.escape(class_name)}["\'][^>]*>.*?<a[^>]*>(.*?)</a>.*?</h[12]>'
    match = re.search(pattern, html)
    if not match:
        return None
    return _strip_html(match.group(1)) or None


def _extract_definition_list(html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in re.finditer(r"(?is)<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", html):
        key = _strip_html(match.group(1)).rstrip(":")
        value = _strip_html(match.group(2))
        if key:
            values[key] = value
    return values


def _extract_metal_archives_tracks(html: str) -> tuple[list[dict[str, Any]], int | None]:
    tracks: list[dict[str, Any]] = []
    for match in re.finditer(
        r'(?is)<tr class="(?:odd|even)">\s*<td[^>]*>\s*(?:<a[^>]*>\s*</a>)?\s*([0-9]+)\.\s*</td>\s*<td[^>]*>\s*(.*?)\s*</td>\s*<td[^>]*>([0-9:]+)</td>',
        html,
    ):
        number = int(match.group(1))
        title = _strip_html(match.group(2))
        duration_text = _strip_html(match.group(3))
        tracks.append(
            {
                "track_number": number,
                "title": title,
                "duration_seconds": display_to_seconds(duration_text),
            }
        )
    total_match = re.search(r"(?is)<td align=\"right\"><strong>([0-9:]+)</strong></td>", html)
    total_seconds = display_to_seconds(_strip_html(total_match.group(1))) if total_match else None
    return tracks, total_seconds


def _extract_metal_archives_cover(html: str) -> str | None:
    match = re.search(r'(?is)<a[^>]+id=["\']cover["\'][^>]+href=["\'](.*?)["\']', html)
    if match:
        return match.group(1).strip()
    match = re.search(r'(?is)<a[^>]+id=["\']cover["\'][^>]*>.*?<img[^>]+src=["\'](.*?)["\']', html)
    if match:
        return match.group(1).strip()
    return None


def _metal_archives_album_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> AlbumDraftData:
    title = _extract_anchor_text(html, "album_name") or request.album_title or ""
    artist_name = _extract_anchor_text(html, "band_name") or request.artist_name
    details = _extract_definition_list(html)
    release_date = details.get("Release date", "")
    year_match = re.search(r"(19|20)\d{2}", release_date)
    release_year = int(year_match.group(0)) if year_match else None
    tracks, total_seconds = _extract_metal_archives_tracks(html)
    cover_url = _extract_metal_archives_cover(html) or metadata.get("image")
    album_type = details.get("Type") or None
    notes_parts = [
        f"{label}: {details[label]}"
        for label in ["Label", "Format", "Version desc.", "Catalog ID"]
        if details.get(label)
    ]
    return AlbumDraftData(
        artist_name=artist_name,
        artist_description=None,
        artist_description_source_url=request.source_url,
        artist_description_source_label=metadata.get("source_label"),
        album_external_url=request.source_url,
        album_title=title,
        release_year=release_year,
        album_type=album_type,
        duration_seconds=total_seconds,
        cover_source_url=cover_url,
        notes=" | ".join(notes_parts) or metadata.get("title") or None,
        tracks=tracks,
    )


def _parse_iso_duration(s: str) -> int | None:
    """Convert ISO 8601 duration (e.g. PT3M33S) to seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?$", s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = int(float(m.group(3) or 0))
    return h * 3600 + mins * 60 + secs


def _extract_bandcamp_ld_json(html: str) -> dict[str, Any] | None:
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("@type") in ("MusicAlbum", "Album"):
            return data
    return None


def _bandcamp_album_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> AlbumDraftData:
    ld = _extract_bandcamp_ld_json(html) or {}
    # Tracks from ld+json ItemList
    tracks: list[dict[str, Any]] = []
    track_list = ld.get("track") or {}
    items = track_list.get("itemListElement", []) if isinstance(track_list, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        inner = item.get("item") or {}
        name = str(inner.get("name") or "").strip()
        position = item.get("position") or (len(tracks) + 1)
        duration_raw = str(inner.get("duration") or "")
        duration_sec = _parse_iso_duration(duration_raw) if duration_raw else None
        if name:
            tracks.append({"track_number": int(position), "title": name, "duration_seconds": duration_sec})
    # Album title and artist from ld+json or page title
    album_title = str(ld.get("name") or request.album_title or "").strip()
    artist_name = request.artist_name
    by_artist = ld.get("byArtist") or {}
    if isinstance(by_artist, dict) and not artist_name:
        artist_name = str(by_artist.get("name") or "").strip()
    if not album_title:
        page_title = str(metadata.get("title") or "")
        for sep in (" | ", " by ", " - "):
            if sep in page_title:
                album_title = page_title.split(sep, 1)[0].strip()
                if not artist_name:
                    artist_name = page_title.split(sep, 1)[1].strip()
                break
    # Release year from datePublished or credits text
    release_year: int | None = None
    date_str = str(ld.get("datePublished") or "")
    year_m = re.search(r"\b(19|20)\d{2}\b", date_str)
    if year_m:
        release_year = int(year_m.group(0))
    if not release_year:
        credits_m = re.search(r"released\s+\w+\s+\d+,\s+(\d{4})", _strip_html(html), re.IGNORECASE)
        if credits_m:
            release_year = int(credits_m.group(1))
    # Cover image
    album_image = ld.get("image")
    if isinstance(album_image, list) and album_image:
        album_image = album_image[0]
    cover_url = (album_image if isinstance(album_image, str) else None) or metadata.get("image")
    return AlbumDraftData(
        artist_name=artist_name or request.artist_name,
        artist_description=metadata.get("description"),
        artist_description_source_url=request.source_url,
        artist_description_source_label=metadata.get("source_label"),
        album_external_url=request.source_url,
        album_title=album_title,
        release_year=release_year,
        cover_source_url=cover_url,
        tracks=tracks,
    )


def _extract_wikipedia_infobox(html: str) -> dict[str, Any]:
    infobox_m = re.search(r'(?is)<table[^>]*\bclass="[^"]*\binfobox\b[^"]*"[^>]*>(.*?)</table>', html)
    if not infobox_m:
        return {}
    infobox = infobox_m.group(1)
    values: dict[str, Any] = {}
    # Parse row-by-row so the th+td regex never spans across rows
    for row_m in re.finditer(r'(?is)<tr[^>]*>(.*?)</tr>', infobox):
        row = row_m.group(1)
        ths = re.findall(r'(?is)<th[^>]*>(.*?)</th>', row)
        tds = re.findall(r'(?is)<td[^>]*>(.*?)</td>', row)
        if len(ths) == 1 and len(tds) == 1:
            key = _html_unescape(_strip_html(ths[0])).strip().rstrip(":")
            val = _html_unescape(_strip_html(tds[0])).strip()
            if key and val:
                values[key] = val
        for th_content in ths:
            text = _html_unescape(_strip_html(th_content)).strip()
            artist_m = re.search(r'(?i)(?:studio|live|compilation)\s+album\s+by\s+(.+)$', text)
            if artist_m:
                values["_artist"] = artist_m.group(1).strip()
    # Cover image from infobox-image cell
    img_m = re.search(r'(?is)class="[^"]*infobox-image[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"', infobox)
    if img_m:
        src = img_m.group(1)
        if src.startswith("//"):
            src = "https:" + src
        values["_cover"] = src
    return values


def _extract_wikipedia_tracks(html: str) -> list[dict[str, Any]]:
    tracklist_m = re.search(r'(?is)<table[^>]*\btracklist\b[^>]*>(.*?)</table>', html)
    if not tracklist_m:
        return []
    rows = re.findall(r'(?is)<tr[^>]*>(.*?)</tr>', tracklist_m.group(1))
    tracks: list[dict[str, Any]] = []
    for row in rows:
        # Wikipedia uses <th scope="row"> for track numbers in tracklist tables
        th_m = re.search(r'(?is)<th[^>]*scope=["\']row["\'][^>]*>(.*?)</th>', row)
        if not th_m:
            continue
        num_raw = _strip_html(th_m.group(1)).strip().rstrip(".")
        if not num_raw.isdigit():
            continue
        cells = re.findall(r'(?is)<td[^>]*>(.*?)</td>', row)
        if not cells:
            continue
        # Strip footnote <sup> refs from title, then decode entities
        title_html = re.sub(r'(?is)<sup[^>]*>.*?</sup>', '', cells[0])
        title = _html_unescape(_strip_html(title_html)).strip()
        # Strip Wikipedia-style enclosing quotes: "Title" → Title, "Title" (with X) → Title (with X)
        quote_m = re.match(r'^[\u201c"](.*?)[\u201d"]\s*(.*?)\s*$', title)
        if quote_m:
            inner = quote_m.group(1).strip()
            suffix = quote_m.group(2).strip()
            title = (inner + " " + suffix).strip() if suffix else inner
        # Normalize spaces inside parentheses left by stripped anchor tags
        title = re.sub(r'\(\s+', '(', re.sub(r'\s+\)', ')', title))
        duration_text = _strip_html(cells[-1]).strip()
        duration_sec = display_to_seconds(duration_text) if re.match(r'^\d+:\d+$', duration_text) else None
        if title:
            tracks.append({"track_number": int(num_raw), "title": title, "duration_seconds": duration_sec})
    return tracks


def _wikipedia_album_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> AlbumDraftData:
    infobox = _extract_wikipedia_infobox(html)
    tracks = _extract_wikipedia_tracks(html)
    # Album title: strip " - Wikipedia" suffix and "(album)" disambiguation
    page_title = str(metadata.get("title") or "")
    album_title = request.album_title or ""
    if not album_title:
        raw = re.split(r'\s[\-\u2013\u2014|]\s', page_title, maxsplit=1)[0].strip()
        album_title = re.sub(r'\s*\([^)]*\balbum\b[^)]*\)\s*', '', raw).strip()
    # Artist
    artist_name = request.artist_name or infobox.get("_artist", "")
    # Release year
    released = infobox.get("Released") or infobox.get("Release date") or ""
    year_m = re.search(r'\b(19|20)\d{2}\b', released)
    release_year = int(year_m.group(0)) if year_m else None
    # Genre: first value only
    genre_raw = infobox.get("Genre") or infobox.get("Genres")
    genre = re.split(r'[,/\n]', genre_raw)[0].strip() if genre_raw else None
    # Total duration — strip spaces from span-wrapped digits like "49 : 47"
    length_str = (infobox.get("Length") or "").strip().replace(" ", "")
    total_seconds = display_to_seconds(length_str) if re.match(r'^\d+:\d+$', length_str) else None
    return AlbumDraftData(
        artist_name=artist_name,
        artist_description=metadata.get("description"),
        artist_description_source_url=request.source_url,
        artist_description_source_label=metadata.get("source_label"),
        album_external_url=request.source_url,
        album_title=album_title,
        release_year=release_year,
        genre=genre,
        duration_seconds=total_seconds,
        cover_source_url=infobox.get("_cover") or metadata.get("image"),
        tracks=tracks,
    )


def _parse_yt_duration(s: str) -> int | None:
    """Parse YouTube duration strings.

    YouTube playlist pages use a dot separator (e.g. ``4.10`` for 4m10s)
    instead of the colon used elsewhere.  Colon-separated values (``4:10``,
    ``1:04:10``) are handled by the normal ``display_to_seconds`` helper.
    """
    s = s.strip()
    if not s:
        return None
    # M.SS dot format: digits, dot, exactly two digits
    dot_m = re.match(r"^(\d+)\.(\d{2})$", s)
    if dot_m:
        secs = int(dot_m.group(2))
        if secs >= 60:
            return None
        return int(dot_m.group(1)) * 60 + secs
    # Fall back to standard M:SS or H:MM:SS
    try:
        return display_to_seconds(s)
    except (ValueError, AttributeError):
        return None


def _find_all_by_key(obj: Any, key: str) -> list[Any]:
    """Recursively collect every value in *obj* whose dict key equals *key*."""
    results: list[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                results.append(v)
            else:
                results.extend(_find_all_by_key(v, key))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_find_all_by_key(item, key))
    return results


def _fetch_ytm_full_page(url: str) -> str:
    """Return the full HTML of a music.youtube.com page without size truncation.

    Uses ``Accept-Language: en-US`` so that text fields (subtitle, title) come
    back in English rather than the browser's locale.
    """
    try:
        result = subprocess.run(
            [
                "curl", "-L", "-sS",
                "-A", DEFAULT_HEADERS["User-Agent"],
                "-H", "Accept-Language: en-US,en;q=0.9",
                "--max-time", "30",
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except Exception:
        return ""


def _decode_ytm_initial_data_objects(raw: str) -> list[dict[str, Any]]:
    """Decode hex-escaped ``data: '...'`` payloads from a YTM page.

    YouTube Music stores page data in ``initialData.push({..., data: '\\x7b...'})``
    blocks.  The ``params`` argument of the push call can contain commas, so
    matching the full push expression reliably is fragile.  Instead we match
    only the ``data: '...'`` portion which is stable.
    """
    objects: list[dict[str, Any]] = []
    for m in re.finditer(r"data:\s*'((?:[^'\\]|\\.)*)'", raw):
        encoded = m.group(1)
        try:
            decoded = re.sub(r"\\x([0-9a-fA-F]{2})", lambda x: chr(int(x.group(1), 16)), encoded)
            decoded = decoded.replace("\\/", "/")
            objects.append(json.loads(decoded))
        except (ValueError, json.JSONDecodeError):
            pass
    return objects


def _runs_text(runs_obj: Any) -> str:
    """Join ``runs[*].text`` from a YTM text object into a single string."""
    if isinstance(runs_obj, dict):
        parts = runs_obj.get("runs") or []
        if parts:
            return "".join(str(r.get("text") or "") for r in parts if isinstance(r, dict))
        return str(runs_obj.get("simpleText") or "")
    return ""


def _extract_ytm_year(raw: str) -> int | None:
    """Extract the release year from the ``subtitle`` field of a YTM album page.

    The subtitle renderer produces ``["Album", " • ", "2026"]`` (three runs).
    This is inside one of the hex-escaped ``initialData.push()`` blocks.
    """
    for obj in _decode_ytm_initial_data_objects(raw):
        for subtitle in _find_all_by_key(obj, "subtitle"):
            if not isinstance(subtitle, dict):
                continue
            runs = subtitle.get("runs") or []
            # We want exactly 3 runs: ["Album", " • ", "<year>"]
            if len(runs) == 3:
                year_text = str(runs[2].get("text") or "").strip()
                if re.match(r"^(19|20)\d{2}$", year_text):
                    return int(year_text)
    return None


def _fetch_yt_playlist_raw(playlist_id: str) -> str:
    """Return the full HTML of a YouTube playlist page without size truncation."""
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        result = subprocess.run(
            ["curl", "-L", "-sS", "-A", DEFAULT_HEADERS["User-Agent"], "--max-time", "30", url],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except Exception:
        return ""


def _extract_yt_playlist_tracks(playlist_id: str) -> list[dict[str, Any]]:
    """Fetch www.youtube.com/playlist and parse tracks from ytInitialData."""
    raw = _fetch_yt_playlist_raw(playlist_id)
    if not raw:
        return []
    # Extract the ytInitialData JSON blob (page is ~800KB; data starts well past 600KB)
    m = re.search(r"ytInitialData\s*=\s*(\{.+?\});\s*(?:var |</script>|window\.)", raw, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []
    renderers = _find_all_by_key(data, "playlistVideoRenderer")
    tracks: list[dict[str, Any]] = []
    for renderer in renderers:
        if not isinstance(renderer, dict):
            continue
        # Title from runs list
        title_runs = _find_all_by_key(renderer.get("title") or {}, "text")
        title = "".join(str(r) for r in title_runs).strip()
        if not title:
            continue
        # Duration from lengthText.simpleText (format "M.SS")
        length_text = renderer.get("lengthText") or {}
        duration_raw = str(length_text.get("simpleText") or "").strip()
        duration_sec = _parse_yt_duration(duration_raw) if duration_raw else None
        # Index / position — YouTube uses 1-based index in this field
        idx = renderer.get("index") or {}
        position_raw = str(idx.get("simpleText") or "").strip()
        position = int(position_raw) if position_raw.isdigit() else len(tracks) + 1
        tracks.append({"track_number": position, "title": title, "duration_seconds": duration_sec})
    return tracks


def _youtube_music_album_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> AlbumDraftData:
    """Build an AlbumDraftData from a YouTube Music playlist URL."""
    # Extract playlist ID from the original source URL
    pid_m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", request.source_url)
    playlist_id = pid_m.group(1) if pid_m else ""

    # Fetch the full YTM page (Accept-Language: en-US) to get year from initialData.
    # _page_metadata() truncates to 40KB which misses the initialData blocks.
    ytm_raw = _fetch_ytm_full_page(request.source_url)

    # og:title from music.youtube.com is English and follows "X - Album by Y"
    og_title = str(metadata.get("title") or "")
    album_title = request.album_title or ""
    artist_name = request.artist_name or ""

    if og_title:
        # e.g. "Burn The Ships - Album by American Adrenalin"
        by_m = re.search(r"(.+?)\s*-\s*(?:Album\s+by|EP\s+by|Single\s+by)\s+(.+)", og_title, re.IGNORECASE)
        if by_m:
            if not album_title:
                album_title = by_m.group(1).strip()
            if not artist_name:
                artist_name = by_m.group(2).strip()
        else:
            # Fallback: everything before " – " or " - " is the album title
            for sep in (" \u2013 ", " - "):
                if sep in og_title:
                    parts = og_title.split(sep, 1)
                    if not album_title:
                        album_title = parts[-1].strip()
                    break
            if not album_title:
                album_title = og_title.strip()

    # Cover: og:image from the music.youtube.com fetch is reliable
    cover_url = metadata.get("image")

    # Release year from the subtitle initialData field ("Album • 2026")
    release_year = _extract_ytm_year(ytm_raw) if ytm_raw else None

    # Tracks from the regular YouTube playlist page
    tracks: list[dict[str, Any]] = []
    if playlist_id:
        tracks = _extract_yt_playlist_tracks(playlist_id)

    # Total duration: sum known track durations
    known_secs = [t["duration_seconds"] for t in tracks if t.get("duration_seconds") is not None]
    total_seconds = sum(known_secs) if known_secs else None

    return AlbumDraftData(
        artist_name=artist_name or request.artist_name,
        artist_description=None,
        artist_description_source_url=request.source_url,
        artist_description_source_label=metadata.get("source_label"),
        album_external_url=request.source_url,
        album_stream_url=request.source_url,
        album_title=album_title,
        release_year=release_year,
        duration_seconds=total_seconds,
        cover_source_url=cover_url,
        tracks=tracks,
    )


def _best_effort_artist_draft(request: ImportRequest) -> ArtistDraftData:
    metadata = _page_metadata(request.source_url)
    artist_name = request.artist_name.strip()
    if not artist_name:
        title = str(metadata.get("title") or "").strip()
        if title:
            artist_name = title.split(" - ")[0].strip()
    if not artist_name:
        artist_name = _host_label(request.source_url) or "Unknown Artist"
    return ArtistDraftData(
        artist_name=artist_name,
        description=metadata.get("description"),
        description_source_url=request.source_url,
        description_source_label=metadata.get("source_label"),
        external_url=request.source_url,
        origin=None,
    )


_STREAMING_HOSTS = {"music.youtube.com", "open.spotify.com", "spotify.com"}

_ALBUM_TYPE_MAP: dict[str, str] = {
    "album": "Full-length",
    "full length": "Full-length",
    "full-length": "Full-length",
    "full length album": "Full-length",
    "lp": "Full-length",
    "ep": "EP",
    "e.p.": "EP",
    "single": "Single",
    "demo": "Demo",
    "live": "Live album",
    "live album": "Live album",
    "compilation": "Compilation",
    "split": "Split",
    "video": "Video",
}


def _normalize_album_type(value: str | None) -> str | None:
    if not value:
        return value
    return _ALBUM_TYPE_MAP.get(value.strip().lower(), value)


def _infer_album_type(duration_seconds: int | None, track_count: int | None) -> str | None:
    """Infer album type from duration and track count when no explicit type is available.

    Thresholds (industry-standard):
      Single  : ≤3 tracks  OR  duration ≤ 10 min
      EP      : ≤6 tracks  OR  duration ≤ 30 min
      Full-length: otherwise
    Track count takes precedence when available; duration is used as a
    tie-breaker or sole indicator when track count is unknown.
    """
    dur = duration_seconds or 0
    tc = track_count or 0
    if tc and tc <= 3:
        return "Single"
    if tc and tc <= 6:
        return "EP"
    if tc and tc >= 7:
        return "Full-length"
    # Track count unknown — fall back to duration only
    if dur and dur <= 600:   # ≤ 10 min
        return "Single"
    if dur and dur <= 1800:  # ≤ 30 min
        return "EP"
    if dur and dur > 1800:
        return "Full-length"
    return None


def _is_streaming_url(url: str | None) -> bool:
    if not url:
        return False
    host = _host_label(url) or ""
    return any(h in host for h in _STREAMING_HOSTS)


def _best_effort_album_draft(request: ImportRequest, metadata: dict[str, Any] | None = None) -> AlbumDraftData:
    if metadata is None:
        metadata = _page_metadata(request.source_url)
    html = str(metadata.get("html") or "")
    source_label = str(metadata.get("source_label") or _host_label(request.source_url) or "")
    if "music.youtube.com" in source_label:
        draft = _youtube_music_album_draft(request, html, metadata)
    elif "metal-archives.com" in source_label and html:
        draft = _metal_archives_album_draft(request, html, metadata)
    elif "bandcamp.com" in source_label and html:
        draft = _bandcamp_album_draft(request, html, metadata)
    elif "wikipedia.org" in source_label and html:
        draft = _wikipedia_album_draft(request, html, metadata)
    else:
        page_title = str(metadata.get("title") or "")
        album_title = request.album_title or ""
        if not album_title and page_title:
            album_title = page_title.split(" - ")[0].strip()
        stream_url = request.source_url if _is_streaming_url(request.source_url) else None
        draft = AlbumDraftData(
            artist_name=request.artist_name,
            artist_description=metadata.get("description"),
            artist_description_source_url=request.source_url,
            artist_description_source_label=metadata.get("source_label"),
            album_external_url=request.source_url,
            album_stream_url=stream_url,
            album_title=album_title,
            cover_source_url=metadata.get("image"),
            notes=page_title or None,
        )
    if not draft.album_type:
        inferred = _infer_album_type(draft.duration_seconds, len(draft.tracks) or None)
        if inferred:
            draft = draft.model_copy(update={"album_type": inferred})
    return draft


def infer_cover_source_url_from_album_url(album_url: str | None) -> str | None:
    if not album_url:
        return None
    request = ImportRequest(artist_name="", album_title="", source_url=album_url)
    draft = _best_effort_album_draft(request)
    return _normalize_cover_source_url(draft.cover_source_url, album_url)


_IMAGE_CDN_HOSTS = {
    "lh3.googleusercontent.com",
    "yt3.googleusercontent.com",
    "i.ytimg.com",
    "i9.ytimg.com",
    "img.youtube.com",
}


def _looks_like_image_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    # Known image CDN hosts serve images even without a file extension
    if parsed.netloc in _IMAGE_CDN_HOSTS:
        return True
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"])


def _normalize_cover_source_url(candidate_url: str | None, source_url: str | None) -> str | None:
    if not candidate_url:
        return None
    cleaned = candidate_url.strip()
    if not cleaned:
        return None
    if source_url and cleaned.rstrip("/") == source_url.rstrip("/"):
        return None
    if cleaned.startswith("data:"):
        return None
    return cleaned if _looks_like_image_url(cleaned) else None


def _merge_album_drafts(ai_data: dict[str, Any], fallback: AlbumDraftData, request: ImportRequest) -> AlbumDraftData:
    merged = dict(ai_data)
    merged["artist_name"] = merged.get("artist_name") or fallback.artist_name or request.artist_name
    merged["album_title"] = merged.get("album_title") or fallback.album_title or request.album_title or ""
    merged["artist_description"] = merged.get("artist_description") or fallback.artist_description
    merged["artist_description_source_url"] = (
        merged.get("artist_description_source_url")
        or fallback.artist_description_source_url
        or request.source_url
    )
    merged["artist_description_source_label"] = (
        merged.get("artist_description_source_label")
        or fallback.artist_description_source_label
        or _host_label(request.source_url)
    )
    merged["album_external_url"] = merged.get("album_external_url") or fallback.album_external_url or request.source_url
    merged["album_stream_url"] = fallback.album_stream_url or merged.get("album_stream_url")
    merged["release_year"] = merged.get("release_year") or fallback.release_year
    merged["genre"] = merged.get("genre") or fallback.genre
    merged["duration_seconds"] = merged.get("duration_seconds") or fallback.duration_seconds
    album_type = _normalize_album_type(fallback.album_type or merged.get("album_type"))
    if not album_type:
        track_count = len(merged.get("tracks") or fallback.tracks or [])
        album_type = _infer_album_type(merged.get("duration_seconds") or fallback.duration_seconds, track_count or None)
    merged["album_type"] = album_type
    merged["notes"] = fallback.notes or merged.get("notes")
    merged["tracks"] = merged.get("tracks") or [track.model_dump(mode="json") for track in fallback.tracks]
    merged["cover_source_url"] = (
        _normalize_cover_source_url(merged.get("cover_source_url"), request.source_url)
        or _normalize_cover_source_url(fallback.cover_source_url, request.source_url)
    )
    return AlbumDraftData.model_validate(merged)


class MetadataImporter:
    def __init__(self, client: OpenAIClient | None) -> None:
        self.client = client
        self.last_request_failed = False
        self.last_error: str | None = None
        self.last_diagnostics: dict[str, Any] = {}

    def _set_diagnostics(self, diagnostics: dict[str, Any]) -> None:
        self.last_diagnostics = diagnostics

    def _mark_success(self) -> None:
        self.last_request_failed = False
        self.last_error = None

    def _mark_failure(self, detail: str) -> None:
        self.last_request_failed = True
        self.last_error = detail

    def create_artist_draft(self, request: ImportRequest, *, model: str) -> ArtistDraftData:
        source_metadata = _page_metadata(request.source_url)
        context = self._build_context(request.source_url, metadata=source_metadata)
        if self.client is None:
            draft = _best_effort_artist_draft(request)
            self._set_diagnostics(
                {
                    "target": "artist",
                    "mode": "fallback_only",
                    "reason": "OPENAI_API_KEY missing or AI client unavailable",
                    "request": request.model_dump(mode="json"),
                    "source_context": {
                        "url": request.source_url,
                        "metadata": self._diagnostic_metadata(source_metadata),
                        "context_excerpt": context,
                    },
                    "result": draft.model_dump(mode="json"),
                }
            )
            return draft
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "artist_name": {"type": "string"},
                "description": {"type": ["string", "null"]},
                "description_source_url": {"type": ["string", "null"]},
                "description_source_label": {"type": ["string", "null"]},
                "external_url": {"type": ["string", "null"]},
                "origin": {"type": ["string", "null"]},
            },
            "required": [
                "artist_name",
                "description",
                "description_source_url",
                "description_source_label",
                "external_url",
                "origin",
            ],
        }
        prompt = (
            f"Create a concise artist metadata draft for '{request.artist_name or 'the artist on the source page'}'. "
            "Prefer factual content. If data is uncertain, return null rather than inventing it. "
            "For 'origin', provide the country first, then city or region if known, e.g. 'UK, London' or 'USA, Nashville'. "
            f"Preferred source URL: {request.source_url or 'none provided'}.\n\n"
            f"Reference context:\n{context}"
        )
        try:
            data = self.client.generate_json(
                model=model,
                system_prompt="You extract clean artist metadata for a local music catalog.",
                user_prompt=prompt,
                schema_name="artist_draft",
                schema=schema,
            )
        except OpenAIClientError as exc:
            self._mark_failure("AI request failed; using page metadata fallback.")
            draft = _best_effort_artist_draft(request)
            self._set_diagnostics(
                {
                    "target": "artist",
                    "mode": "ai_failed_fallback",
                    "reason": str(exc),
                    "request": request.model_dump(mode="json"),
                    "source_context": {
                        "url": request.source_url,
                        "metadata": self._diagnostic_metadata(source_metadata),
                        "context_excerpt": context,
                    },
                    "result": draft.model_dump(mode="json"),
                }
            )
            return draft
        self._mark_success()
        if not data.get("artist_name"):
            data["artist_name"] = _best_effort_artist_draft(request).artist_name
        data.setdefault("description_source_url", request.source_url)
        data.setdefault("description_source_label", _host_label(request.source_url))
        draft = ArtistDraftData.model_validate(data)
        self._set_diagnostics(
            {
                "target": "artist",
                "mode": "ai_success",
                "request": request.model_dump(mode="json"),
                "source_context": {
                    "url": request.source_url,
                    "metadata": self._diagnostic_metadata(source_metadata),
                    "context_excerpt": context,
                },
                "ai_result": data,
                "result": draft.model_dump(mode="json"),
            }
        )
        return draft

    def create_album_draft(self, request: ImportRequest, *, model: str) -> AlbumDraftData:
        source_metadata = _page_metadata(request.source_url)
        context = self._build_context(request.source_url, metadata=source_metadata)
        fallback_draft = _best_effort_album_draft(request, metadata=source_metadata)
        if self.client is None:
            draft = fallback_draft
            self._set_diagnostics(
                {
                    "target": "album",
                    "mode": "fallback_only",
                    "reason": "OPENAI_API_KEY missing or AI client unavailable",
                    "request": request.model_dump(mode="json"),
                    "source_context": {
                        "url": request.source_url,
                        "metadata": self._diagnostic_metadata(source_metadata),
                        "context_excerpt": context,
                    },
                    "result": draft.model_dump(mode="json"),
                }
            )
            return draft
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "artist_name": {"type": "string"},
                "artist_description": {"type": ["string", "null"]},
                "artist_description_source_url": {"type": ["string", "null"]},
                "artist_description_source_label": {"type": ["string", "null"]},
                "album_external_url": {"type": ["string", "null"]},
                "album_title": {"type": "string"},
                "release_year": {"type": ["integer", "null"]},
                "genre": {"type": ["string", "null"]},
                "duration_seconds": {"type": ["integer", "null"]},
                "cover_source_url": {"type": ["string", "null"]},
                "album_type": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
                "tracks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "track_number": {"type": "integer"},
                            "title": {"type": "string"},
                            "duration_seconds": {"type": ["integer", "null"]},
                        },
                        "required": ["track_number", "title", "duration_seconds"],
                    },
                },
            },
            "required": [
                "artist_name",
                "artist_description",
                "artist_description_source_url",
                "artist_description_source_label",
                "album_external_url",
                "album_title",
                "release_year",
                "genre",
                "duration_seconds",
                "cover_source_url",
                "album_type",
                "notes",
                "tracks",
            ],
        }
        prompt = (
            f"Create an album metadata draft for artist '{request.artist_name}' and album '{request.album_title or ''}'. "
            "Return only confident factual data. Use null for unknown fields. "
            f"Preferred source URL: {request.source_url or 'none provided'}.\n"
            "For album_type use Metal Archives naming: 'Full-length', 'EP', 'Single', 'Demo', 'Live album', 'Compilation', 'Split', 'Video'.\n\n"
            f"Reference context:\n{context}"
        )
        try:
            data = self.client.generate_json(
                model=model,
                system_prompt="You extract album metadata for a local music catalog and ranking app.",
                user_prompt=prompt,
                schema_name="album_draft",
                schema=schema,
            )
        except OpenAIClientError as exc:
            self._mark_failure("AI request failed; using page metadata fallback.")
            draft = fallback_draft
            self._set_diagnostics(
                {
                    "target": "album",
                    "mode": "ai_failed_fallback",
                    "reason": str(exc),
                    "request": request.model_dump(mode="json"),
                    "source_context": {
                        "url": request.source_url,
                        "metadata": self._diagnostic_metadata(source_metadata),
                        "context_excerpt": context,
                    },
                    "result": draft.model_dump(mode="json"),
                }
            )
            return draft
        self._mark_success()
        draft = _merge_album_drafts(data, fallback_draft, request)
        self._set_diagnostics(
            {
                "target": "album",
                "mode": "ai_success",
                "request": request.model_dump(mode="json"),
                "source_context": {
                    "url": request.source_url,
                    "metadata": self._diagnostic_metadata(source_metadata),
                    "context_excerpt": context,
                },
                "ai_result": data,
                "fallback_result": fallback_draft.model_dump(mode="json"),
                "result": draft.model_dump(mode="json"),
            }
        )
        return draft

    def _build_context(self, source_url: str | None, metadata: dict[str, Any] | None = None) -> str:
        if not source_url:
            return "No explicit source URL supplied. Use best-effort world knowledge only."
        if metadata is None:
            try:
                metadata = _page_metadata(source_url)
            except Exception:
                metadata = {}
        host = _host_label(source_url) or source_url
        parts = [f"Source host: {host}", f"Source URL: {source_url}"]
        if metadata.get("title"):
            parts.append(f"Page title: {metadata['title']}")
        if metadata.get("description"):
            parts.append(f"Page description: {metadata['description']}")
        excerpt = metadata.get("excerpt") or ""
        if excerpt:
            parts.append(f"Page text excerpt:\n{excerpt}")
        return "\n".join(parts)

    def _diagnostic_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        if not metadata:
            return {}
        return {
            "title": metadata.get("title"),
            "description": metadata.get("description"),
            "image": metadata.get("image"),
            "source_label": metadata.get("source_label"),
            "excerpt": metadata.get("excerpt"),
            "fetch_method": metadata.get("fetch_method"),
            "fetch_error": metadata.get("fetch_error"),
        }


class CoverDownloader:
    def __init__(self, cover_dir: Path) -> None:
        self.cover_dir = cover_dir

    def download(self, url: str | None, *, stem: str) -> str | None:
        if not url:
            return None
        self.cover_dir.mkdir(parents=True, exist_ok=True)
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix or ".jpg"
        safe_stem = re.sub(r"[^a-zA-Z0-9_.-]", "-", stem)
        target = self.cover_dir / f"{safe_stem}{suffix[:8]}"
        request = Request(url, headers=DEFAULT_HEADERS)
        with urlopen(request, timeout=30) as response:
            target.write_bytes(response.read())
        return str(target)


def draft_to_json(data: ArtistDraftData | AlbumDraftData) -> dict[str, object]:
    return json.loads(data.model_dump_json())
