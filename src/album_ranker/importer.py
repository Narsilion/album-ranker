from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import socket
import subprocess
from html import unescape as _html_unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from album_ranker.openai_client import AIClientError, AlbumWriteupAIClient, OpenAIClientError
from album_ranker.schemas import AlbumDetailRecord, AlbumDraftData, ArtistDraftData, ImportRequest, display_to_seconds

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SOURCE_FETCH_TIMEOUT_SECONDS = 15
MAX_SOURCE_BYTES = 2_000_000
PAGE_METADATA_CHARS = 40_000
ALLOWED_SOURCE_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
    "text/plain",
)


def _validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https source URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("Source URL must include a host.")

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ValueError(f"Could not resolve source URL host: {parsed.hostname}") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ValueError("Source URL resolves to a private or local network address.")


def _is_allowed_source_content_type(content_type: str) -> bool:
    if not content_type:
        return True
    normalized = content_type.split(";", 1)[0].strip().lower()
    return any(normalized == allowed for allowed in ALLOWED_SOURCE_CONTENT_TYPES)


def _curl_source_args(url: str, *, user_agent: str | None = None) -> list[str]:
    return [
        "curl",
        "-L",
        "-sS",
        "--proto",
        "=http,https",
        "--max-time",
        str(SOURCE_FETCH_TIMEOUT_SECONDS),
        "--max-filesize",
        str(MAX_SOURCE_BYTES),
        "-A",
        user_agent or DEFAULT_HEADERS["User-Agent"],
        url,
    ]


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html_unescape(text)
    return re.sub(r"\s+", " ", text).strip()


_COMMON_IMPORTED_TEXT_REPLACEMENTS = {
    "england": "UK",
}


def _apply_common_import_replacements(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return _COMMON_IMPORTED_TEXT_REPLACEMENTS.get(stripped.lower(), stripped)


def _normalize_imported_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    cleaned = re.sub(r"\s+,", ",", origin)
    cleaned = re.sub(r",\s*", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    if not cleaned:
        return None
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if not parts:
        return None
    parts = [_apply_common_import_replacements(part) or part for part in parts]
    if parts[0] == "UK":
        return ", ".join(parts)
    if parts[-1] == "UK":
        return ", ".join(["UK", *parts[:-1]])
    return ", ".join(parts)


def _normalize_imported_genre(genre: str | None) -> str | None:
    if not genre:
        return None
    normalized = re.sub(r"\s*/\s*", " / ", genre)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def _clean_wikipedia_text(text: str) -> str:
    text = re.sub(r"(?:\[\s*\d+(?:\s*,\s*\d+)*\s*\]\s*)+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_with_urllib(url: str) -> tuple[str, str]:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=SOURCE_FETCH_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        if not _is_allowed_source_content_type(content_type):
            raise ValueError(f"Unsupported content type: {content_type}")
        raw_bytes = response.read(MAX_SOURCE_BYTES + 1)
        if len(raw_bytes) > MAX_SOURCE_BYTES:
            raise ValueError(f"Source response exceeds {MAX_SOURCE_BYTES} bytes.")
        raw = raw_bytes.decode("utf-8", errors="ignore")
    return raw, content_type


def _fetch_with_curl(url: str) -> tuple[str, str]:
    result = subprocess.run(
        _curl_source_args(url),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout[:PAGE_METADATA_CHARS], "text/html"


def _fetch_with_curl_ua(url: str, user_agent: str) -> tuple[str, str]:
    result = subprocess.run(
        _curl_source_args(url, user_agent=user_agent),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout[:PAGE_METADATA_CHARS], "text/html"


def _fetch_url_document(url: str) -> tuple[str, str]:
    _validate_source_url(url)
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


def _wikipedia_artist_key(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", text)


def _wikipedia_url_for_title(title: str) -> str:
    page = re.sub(r"\s+", "_", title.strip())
    return f"https://en.wikipedia.org/wiki/{quote(page, safe='()_-')}"


def _wikipedia_title_from_metadata(metadata: dict[str, Any]) -> str | None:
    title = str(metadata.get("title") or "").strip()
    if not title:
        return None
    title = re.sub(r"\s+-\s+Wikipedia\s*$", "", title).strip()
    if not title or title.lower() in {"search results", "wikipedia"}:
        return None
    return title


def _wikipedia_artist_title_matches(artist_name: str, page_title: str | None) -> bool:
    artist_key = _wikipedia_artist_key(artist_name)
    page_key = _wikipedia_artist_key(page_title)
    if not artist_key or not page_key:
        return False
    return page_key == artist_key


_WIKIPEDIA_MUSIC_TITLE_HINTS = (
    "band",
    "musician",
    "singer",
    "rapper",
    "songwriter",
    "record producer",
    "dj",
    "composer",
)
_WIKIPEDIA_MUSIC_ARTIST_TEXT_RE = re.compile(
    r"\b("
    r"band|musical group|music group|rock group|metal group|"
    r"singer|musician|rapper|songwriter|record producer|disc jockey|dj|composer|"
    r"vocalist|guitarist|bassist|drummer|keyboardist|multi-instrumentalist"
    r")\b",
    re.IGNORECASE,
)
_WIKIPEDIA_NON_ARTIST_TEXT_RE = re.compile(
    r"\b(harbour|harbor|marina|quai|lake|river|building|street|road|station|village|town|city|commune)\b",
    re.IGNORECASE,
)


def _wikipedia_music_title_priority(title: str) -> int:
    lowered = title.lower()
    for index, hint in enumerate(_WIKIPEDIA_MUSIC_TITLE_HINTS):
        if f"({hint})" in lowered:
            return index
    return len(_WIKIPEDIA_MUSIC_TITLE_HINTS)


def _wikipedia_page_looks_like_music_artist(page_info: dict[str, Any]) -> bool:
    title = str(page_info.get("title") or "")
    if _wikipedia_music_title_priority(title) < len(_WIKIPEDIA_MUSIC_TITLE_HINTS):
        return True

    pageprops = page_info.get("pageprops")
    short_description = ""
    if isinstance(pageprops, dict):
        short_description = str(
            pageprops.get("wikibase-shortdesc")
            or pageprops.get("description")
            or pageprops.get("shortdesc")
            or ""
        )
    if short_description and _WIKIPEDIA_MUSIC_ARTIST_TEXT_RE.search(short_description):
        return True
    if short_description and _WIKIPEDIA_NON_ARTIST_TEXT_RE.search(short_description):
        return False

    categories = page_info.get("categories")
    if isinstance(categories, list):
        category_text = " ".join(
            str(category.get("title") or "") for category in categories if isinstance(category, dict)
        )
        if _WIKIPEDIA_MUSIC_ARTIST_TEXT_RE.search(category_text):
            return True
        if category_text and _WIKIPEDIA_NON_ARTIST_TEXT_RE.search(category_text):
            return False

    return False


def _verified_wikipedia_artist_url(artist_name: str, url: str) -> str | None:
    parsed = urlparse(url)
    title = unquote(parsed.path.rsplit("/", 1)[-1]).replace("_", " ") if parsed.path else ""
    page_info = _fetch_wikipedia_page_info(title)
    if not page_info:
        return None
    page_title = str(page_info.get("title") or "")
    if not _wikipedia_artist_title_matches(artist_name, page_title):
        return None
    if not _wikipedia_page_looks_like_music_artist(page_info):
        return None
    page_url = str(page_info.get("fullurl") or "").strip()
    return page_url or _wikipedia_url_for_title(page_title)


def _fetch_wikipedia_page_info(title: str) -> dict[str, Any] | None:
    title = title.strip()
    if not title:
        return None
    query = urlencode(
        {
            "action": "query",
            "titles": title,
            "prop": "info|pageprops|categories",
            "inprop": "url",
            "cllimit": "max",
            "redirects": "1",
            "format": "json",
        }
    )
    url = f"https://en.wikipedia.org/w/api.php?{query}"
    _validate_source_url(url)
    request = Request(url, headers={**DEFAULT_HEADERS, "Accept": "application/json"})
    with urlopen(request, timeout=SOURCE_FETCH_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.lower():
            return None
        raw_bytes = response.read(MAX_SOURCE_BYTES + 1)
        if len(raw_bytes) > MAX_SOURCE_BYTES:
            return None
    try:
        data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    pages = data.get("query", {}).get("pages", {}) if isinstance(data, dict) else {}
    if not isinstance(pages, dict):
        return None
    for page in pages.values():
        if isinstance(page, dict) and "missing" not in page:
            return page
    return None


def _fetch_wikipedia_search_titles(artist_name: str) -> list[str]:
    query = urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": artist_name,
            "srlimit": "5",
            "format": "json",
        }
    )
    url = f"https://en.wikipedia.org/w/api.php?{query}"
    _validate_source_url(url)
    request = Request(url, headers={**DEFAULT_HEADERS, "Accept": "application/json"})
    with urlopen(request, timeout=SOURCE_FETCH_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.lower():
            return []
        raw_bytes = response.read(MAX_SOURCE_BYTES + 1)
        if len(raw_bytes) > MAX_SOURCE_BYTES:
            return []
    try:
        data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    results = data.get("query", {}).get("search", []) if isinstance(data, dict) else []
    titles: list[str] = []
    for result in results:
        if isinstance(result, dict):
            title = str(result.get("title") or "").strip()
            if title:
                titles.append(title)
    return titles


def wikipedia_artist_url_from_name(artist_name: str | None) -> str | None:
    artist_name = (artist_name or "").strip()
    if not artist_name:
        return None
    direct_url = _wikipedia_url_for_title(artist_name)
    try:
        verified = _verified_wikipedia_artist_url(artist_name, direct_url)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        verified = None
    if verified:
        return verified
    try:
        titles = _fetch_wikipedia_search_titles(artist_name)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        titles = []
    for title in sorted(titles, key=_wikipedia_music_title_priority):
        if not _wikipedia_artist_title_matches(artist_name, title):
            continue
        try:
            verified = _verified_wikipedia_artist_url(artist_name, _wikipedia_url_for_title(title))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            verified = None
        if verified:
            return verified
    return None


def _is_youtube_music_album_source_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return "music.youtube.com" in parsed.netloc and (
        parsed.path.startswith("/playlist") or parsed.path.startswith("/watch") or "list=" in parsed.query
    )


def _is_youtube_music_watch_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return "music.youtube.com" in parsed.netloc and parsed.path.startswith("/watch")


def _extract_title(html: str) -> str | None:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return None
    return _strip_html(match.group(1)) or None


def _extract_meta_content(html: str, key: str, *, attr: str = "property") -> str | None:
    pattern = rf'(?is)<meta[^>]+{attr}\s*=\s*["\']{re.escape(key)}["\'][^>]+content\s*=\s*(["\'])(.*?)\1'
    match = re.search(pattern, html)
    if match:
        return _strip_html(match.group(2)) or None
    reverse_pattern = rf'(?is)<meta[^>]+content\s*=\s*(["\'])(.*?)\1[^>]+{attr}\s*=\s*["\']{re.escape(key)}["\']'
    match = re.search(reverse_pattern, html)
    if match:
        return _strip_html(match.group(2)) or None
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


def _extract_anchor_href(html: str, class_name: str) -> str | None:
    pattern = rf'(?is)<h[12][^>]*class=["\']{re.escape(class_name)}["\'][^>]*>.*?<a[^>]+href=["\'](.*?)["\']'
    match = re.search(pattern, html)
    if not match:
        return None
    return _html_unescape(match.group(1)).strip() or None


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


def _extract_metal_archives_band_comment(html: str) -> str | None:
    match = re.search(
        r'(?is)<div[^>]+class=["\'][^"\']*\bband_comment\b[^"\']*["\'][^>]*>(.*?)</div>',
        html,
    )
    if not match:
        return None
    return _strip_html(match.group(1)) or None


def _normalize_metal_archives_url(href: str | None, source_url: str | None = None) -> str | None:
    if not href:
        return None
    base = source_url or "https://www.metal-archives.com/"
    return urljoin(base, _html_unescape(href).strip())


def extract_metal_archives_artist_url_from_album_html(html: str, source_url: str | None = None) -> str | None:
    href = _extract_anchor_href(html, "band_name")
    return _normalize_metal_archives_url(href, source_url)


def metal_archives_artist_url_from_album_url(album_url: str | None) -> str | None:
    if not album_url:
        return None
    metadata = _page_metadata(album_url)
    html = str(metadata.get("html") or "")
    if "metal-archives.com" not in str(metadata.get("source_label") or _host_label(album_url) or ""):
        return None
    return extract_metal_archives_artist_url_from_album_html(html, album_url)


def metal_archives_album_draft_from_url(request: ImportRequest) -> AlbumDraftData | None:
    if not request.source_url:
        return None
    metadata = _page_metadata(request.source_url)
    html = str(metadata.get("html") or "")
    if "metal-archives.com" not in str(metadata.get("source_label") or _host_label(request.source_url) or ""):
        return None
    if not html:
        url_artist_name, url_album_title = _metal_archives_album_url_names(request.source_url)
        artist_name = request.artist_name or url_artist_name
        album_title = request.album_title or url_album_title
        if not artist_name and not album_title:
            return None
        return AlbumDraftData(
            artist_name=artist_name or "",
            album_external_url=request.source_url,
            album_title=album_title or "",
        )
    return _best_effort_album_draft(request, metadata=metadata)


def _metal_archives_album_url_names(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return None, None
    parsed = urlparse(url)
    parts = [unquote(part).replace("_", " ").strip() for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "albums":
        return parts[1] or None, parts[2] or None
    return None, None


def _metal_archives_album_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> AlbumDraftData:
    url_artist_name, url_album_title = _metal_archives_album_url_names(request.source_url)
    title = _extract_anchor_text(html, "album_name") or request.album_title or url_album_title or ""
    artist_name = _extract_anchor_text(html, "band_name") or request.artist_name or url_artist_name or ""
    details = _extract_definition_list(html)
    release_date = details.get("Release date", "")
    year_match = re.search(r"(19|20)\d{2}", release_date)
    release_year = int(year_match.group(0)) if year_match else None
    tracks, total_seconds = _extract_metal_archives_tracks(html)
    cover_url = _extract_metal_archives_cover(html) or metadata.get("image")
    album_type = details.get("Type") or None
    notes_parts = [
        f"{label}: {details[label]}"
        for label in ["Label", "Format", "Version desc."]
        if details.get(label)
    ]
    return AlbumDraftData(
        artist_name=artist_name,
        artist_description=None,
        album_external_url=request.source_url,
        album_title=title,
        release_year=release_year,
        album_type=album_type,
        duration_seconds=total_seconds,
        cover_source_url=cover_url,
        notes="\n".join(notes_parts) or None,
        tracks=tracks,
    )


def _metal_archives_artist_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> ArtistDraftData:
    artist_name = _extract_anchor_text(html, "band_name") or request.artist_name.strip()
    if not artist_name:
        title = str(metadata.get("title") or "").strip()
        artist_name = re.sub(r"\s*-\s*Encyclopaedia Metallum.*$", "", title).strip()
    details = _extract_definition_list(html)
    country = details.get("Country of origin")
    location = details.get("Location")
    origin_parts = [part for part in [country, location] if part]
    origin = _normalize_imported_origin(", ".join(origin_parts) or None)
    genre = _normalize_imported_genre(details.get("Genre") or details.get("Genre(s)"))
    description = _extract_metal_archives_band_comment(html) or metadata.get("description")
    if not description:
        formed = details.get("Formed in")
        status = details.get("Status")
        description_parts = [
            f"Formed in: {formed}" if formed else "",
            f"Status: {status}" if status else "",
        ]
        description = "\n".join(part for part in description_parts if part) or None
    return ArtistDraftData(
        artist_name=artist_name or _host_label(request.source_url) or "Unknown Artist",
        description=description,
        external_url=request.source_url,
        origin=origin,
        genre=genre,
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


def _extract_bandcamp_artist_location(html: str) -> str | None:
    location_match = re.search(
        r'(?is)<span[^>]+class=["\'][^"\']*\blocation\b[^"\']*["\'][^>]*>(.*?)</span>',
        html,
    )
    if location_match:
        return _normalize_imported_origin(_strip_html(location_match.group(1)))
    return None


def _extract_bandcamp_artist_bio(html: str) -> str | None:
    bio_match = re.search(
        r'(?is)<div[^>]+class=["\'][^"\']*\bsigned-out-artists-bio-text\b[^"\']*["\'][^>]*>(.*?)</div>',
        html,
    )
    if bio_match:
        return _strip_html(bio_match.group(1)) or None
    return None


def _bandcamp_description_without_name_origin(description: str | None, artist_name: str, origin: str | None) -> str | None:
    if not description:
        return None
    cleaned = re.sub(r"\s+", " ", description).strip()
    if not cleaned:
        return None
    fragments = [part.strip() for part in re.split(r"\s*\.\s*", cleaned) if part.strip()]
    removable = {artist_name.lower()}
    if origin:
        removable.add(origin.lower())
    remaining = [
        part
        for part in fragments
        if part.lower() not in removable and (_normalize_imported_origin(part) or "").lower() not in removable
    ]
    return ". ".join(remaining) or None


def _bandcamp_artist_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> ArtistDraftData:
    artist_name = request.artist_name.strip()
    if not artist_name:
        title = str(metadata.get("title") or "").strip()
        artist_name = re.sub(r"^\s*Music\s*\|\s*", "", title, flags=re.IGNORECASE).strip()
    if not artist_name:
        artist_name = _host_label(request.source_url) or "Unknown Artist"
    origin = _extract_bandcamp_artist_location(html)
    description = (
        _extract_bandcamp_artist_bio(html)
        or _bandcamp_description_without_name_origin(str(metadata.get("description") or ""), artist_name, origin)
    )
    return ArtistDraftData(
        artist_name=artist_name,
        description=description,
        external_url=request.source_url,
        origin=origin,
        genre=None,
    )


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
            if key in {"Genre", "Genres"}:
                val = _normalize_wikipedia_genres_from_html(tds[0]) or _html_unescape(_strip_html(tds[0])).strip()
            else:
                val = _html_unescape(_strip_html(tds[0])).strip()
            val = _clean_wikipedia_text(val)
            if key and val:
                values[key] = val
        for th_content in ths:
            text = _clean_wikipedia_text(_html_unescape(_strip_html(th_content)).strip())
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


def _titlecase_genre(value: str) -> str:
    words = []
    for word in value.split():
        pieces = [piece.capitalize() for piece in word.split("-")]
        words.append("-".join(pieces))
    return " ".join(words)


def _normalize_wikipedia_genres_from_html(html: str) -> str | None:
    clean = re.sub(r"(?is)<sup[^>]*>.*?</sup>", "", html)
    items = re.findall(r"(?is)<li[^>]*>(.*?)</li>", clean)
    if not items:
        clean = re.sub(r"(?is)<br\s*/?>", "\n", clean)
        clean = re.sub(r"(?is)</(?:div|span|p)>", "\n", clean)
        items = clean.splitlines()

    genres: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _html_unescape(_strip_html(item)).strip()
        text = re.sub(r"\[\s*\d+\s*\]", "", text)
        text = re.sub(r"\s+", " ", text).strip(" ,;/")
        if not text:
            continue
        for part in re.split(r"\s*(?:/|,|;)\s*", text):
            genre = _titlecase_genre(part.strip())
            key = genre.lower()
            if genre and key not in seen:
                genres.append(genre)
                seen.add(key)
    return " / ".join(genres) if genres else None


def _extract_wikipedia_lead_description(html: str, *, max_paragraphs: int = 2) -> str | None:
    content_start = re.search(r'(?is)<div[^>]+id=["\']mw-content-text["\'][^>]*>', html)
    if content_start:
        fragment = html[content_start.end():]
    else:
        body_start = re.search(r"(?is)<body[^>]*>", html)
        fragment = html[body_start.end():] if body_start else html

    first_heading = re.search(r"(?is)<h2\b", fragment)
    if first_heading:
        fragment = fragment[: first_heading.start()]

    paragraphs: list[str] = []
    for para_m in re.finditer(r"(?is)<p\b[^>]*>(.*?)</p>", fragment):
        para = para_m.group(1)
        para = re.sub(r"(?is)<sup\b[^>]*>.*?</sup>", " ", para)
        para = re.sub(r"(?is)<span[^>]+class=[\"'][^\"']*mw-editsection[^\"']*[\"'][^>]*>.*?</span>", " ", para)
        text = _html_unescape(_strip_html(para)).strip()
        text = _clean_wikipedia_text(text)
        if len(text) <= 40:
            continue
        paragraphs.append(text)
        if len(paragraphs) >= max_paragraphs:
            break
    return "\n\n".join(paragraphs) if paragraphs else None


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
    genre = _normalize_imported_genre(re.split(r'[,\n]', genre_raw)[0].strip()) if genre_raw else None
    # Total duration — strip spaces from span-wrapped digits like "49 : 47"
    length_str = (infobox.get("Length") or "").strip().replace(" ", "")
    total_seconds = display_to_seconds(length_str) if re.match(r'^\d+:\d+$', length_str) else None
    return AlbumDraftData(
        artist_name=artist_name,
        artist_description=metadata.get("description"),
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
    _validate_source_url(url)
    try:
        result = subprocess.run(
            [
                "curl", "-L", "-sS",
                "--proto", "=http,https",
                "-A", DEFAULT_HEADERS["User-Agent"],
                "-H", "Accept-Language: en-US,en;q=0.9",
                "--max-time", str(SOURCE_FETCH_TIMEOUT_SECONDS),
                "--max-filesize", str(MAX_SOURCE_BYTES),
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout[:MAX_SOURCE_BYTES]
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
            decoded = _decode_js_string_literal_contents(encoded)
            objects.append(json.loads(decoded))
        except (ValueError, json.JSONDecodeError):
            pass
    return objects


def _decode_js_string_literal_contents(encoded: str) -> str:
    chars: list[str] = []
    i = 0
    while i < len(encoded):
        char = encoded[i]
        if char != "\\" or i + 1 >= len(encoded):
            chars.append(char)
            i += 1
            continue

        esc = encoded[i + 1]
        if esc == "x" and i + 3 < len(encoded) and re.match(r"^[0-9a-fA-F]{2}$", encoded[i + 2 : i + 4]):
            chars.append(chr(int(encoded[i + 2 : i + 4], 16)))
            i += 4
            continue
        if esc == "u" and i + 5 < len(encoded) and re.match(r"^[0-9a-fA-F]{4}$", encoded[i + 2 : i + 6]):
            chars.append(chr(int(encoded[i + 2 : i + 6], 16)))
            i += 6
            continue
        if esc == "n":
            chars.append("\n")
        elif esc == "r":
            chars.append("\r")
        elif esc == "t":
            chars.append("\t")
        elif esc == "b":
            chars.append("\b")
        elif esc == "f":
            chars.append("\f")
        else:
            chars.append(esc)
        i += 2
    return "".join(chars)


def _runs_text(runs_obj: Any) -> str:
    """Join ``runs[*].text`` from a YTM text object into a single string."""
    if isinstance(runs_obj, dict):
        parts = runs_obj.get("runs") or []
        if parts:
            return "".join(str(r.get("text") or "") for r in parts if isinstance(r, dict))
        return str(runs_obj.get("simpleText") or "")
    return ""


def _ytm_text(obj: Any) -> str:
    if isinstance(obj, dict):
        return _runs_text(obj)
    return ""


def _extract_ytm_artist_name(
    metadata: dict[str, Any],
    objects: list[dict[str, Any]] | None = None,
) -> str:
    """Extract an artist across the old and current YouTube Music metadata shapes."""
    title = str(metadata.get("title") or "").strip()
    by_m = re.search(r"\s*-\s*(?:Album\s+by|EP\s+by|Single\s+by)\s+(.+)", title, re.IGNORECASE)
    if by_m:
        return by_m.group(1).strip()

    for obj in objects or []:
        for strapline in _find_all_by_key(obj, "straplineTextOne"):
            artist_name = _ytm_text(strapline).strip()
            if artist_name:
                return artist_name

    description = str(metadata.get("description") or "").strip()
    type_m = re.match(r"^(?:Album|EP|Single)\s*[\u2022\u00b7]\s*(.+)$", description, re.IGNORECASE)
    if type_m:
        return type_m.group(1).strip()
    listen_m = re.search(r"\bby\s+(.+?)\s+on\s+YouTube Music\b", description, re.IGNORECASE)
    if listen_m:
        return listen_m.group(1).strip()
    return ""


def _clean_ytm_album_notes(value: Any) -> str | None:
    """Keep real album descriptions while dropping YTM's type/artist label."""
    notes = str(value or "").strip()
    if not notes:
        return None
    if re.fullmatch(r"(?:Album|EP|Single)\s*[\u2022\u00b7]\s*.+", notes, re.IGNORECASE):
        return None
    return notes


def _ytm_thumbnail_url(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    thumbnails = obj.get("thumbnails")
    if isinstance(thumbnails, list) and thumbnails:
        candidates = [thumb for thumb in thumbnails if isinstance(thumb, dict) and thumb.get("url")]
        if candidates:
            best = max(candidates, key=lambda thumb: int(thumb.get("width") or 0) * int(thumb.get("height") or 0))
            return str(best.get("url") or "") or None
    for thumbnail in _find_all_by_key(obj, "thumbnail"):
        if isinstance(thumbnail, dict):
            url = _ytm_thumbnail_url(thumbnail)
            if url:
                return url
    return None


def _ytm_api_config(raw: str) -> tuple[str | None, str]:
    api_key_m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', raw)
    version_m = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', raw)
    return (
        api_key_m.group(1) if api_key_m else None,
        version_m.group(1) if version_m else "1.20260505.09.00",
    )


def _ytm_video_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    for part in parsed.query.split("&"):
        if part.startswith("v="):
            video_id = part.split("=", 1)[1].strip()
            return video_id or None
    return None


def _fetch_ytm_api(endpoint: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"https://music.youtube.com/youtubei/v1/{endpoint}?key={api_key}"
    _validate_source_url(url)
    try:
        result = subprocess.run(
            [
                "curl", "-L", "-sS",
                "--proto", "=http,https",
                "-A", DEFAULT_HEADERS["User-Agent"],
                "-H", "Accept-Language: en-US,en;q=0.9",
                "-H", "Content-Type: application/json",
                "-H", "Origin: https://music.youtube.com",
                "-H", "Referer: https://music.youtube.com/",
                "--max-time", str(SOURCE_FETCH_TIMEOUT_SECONDS),
                "--max-filesize", str(MAX_SOURCE_BYTES),
                "--data-raw", json.dumps(payload),
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
        return {}


def _ytm_api_payload(client_version: str, **payload: Any) -> dict[str, Any]:
    return {
        "context": {
            "client": {
                "clientName": "WEB_REMIX",
                "clientVersion": client_version,
                "hl": "en",
                "gl": "US",
            }
        },
        **payload,
    }


def _extract_ytm_album_browse_id(data: dict[str, Any]) -> str | None:
    for endpoint in _find_all_by_key(data, "browseEndpoint"):
        if not isinstance(endpoint, dict):
            continue
        config = endpoint.get("browseEndpointContextSupportedConfigs") or {}
        music_config = config.get("browseEndpointContextMusicConfig") or {}
        if music_config.get("pageType") == "MUSIC_PAGE_TYPE_ALBUM":
            browse_id = str(endpoint.get("browseId") or "").strip()
            if browse_id:
                return browse_id
    return None


def _extract_ytm_year_from_objects(objects: list[dict[str, Any]]) -> int | None:
    for obj in objects:
        for subtitle in _find_all_by_key(obj, "subtitle"):
            if not isinstance(subtitle, dict):
                continue
            runs = subtitle.get("runs") or []
            for run in runs:
                year_text = str(run.get("text") or "").strip() if isinstance(run, dict) else ""
                if re.match(r"^(19|20)\d{2}$", year_text):
                    return int(year_text)
    return None


def _extract_ytm_album_tracks_from_browse(data: dict[str, Any]) -> list[dict[str, Any]]:
    for shelf in _find_all_by_key(data, "musicShelfRenderer"):
        if not isinstance(shelf, dict):
            continue
        tracks: list[dict[str, Any]] = []
        for renderer in _find_all_by_key(shelf.get("contents") or [], "musicResponsiveListItemRenderer"):
            if not isinstance(renderer, dict):
                continue
            fixed_columns = renderer.get("fixedColumns") or []
            if not fixed_columns:
                continue
            title = ""
            flex_columns = renderer.get("flexColumns") or []
            if flex_columns:
                column = flex_columns[0].get("musicResponsiveListItemFlexColumnRenderer") or {}
                title = _ytm_text(column.get("text")).strip()
            duration_seconds: int | None = None
            fixed_column = fixed_columns[0].get("musicResponsiveListItemFixedColumnRenderer") or {}
            duration_raw = _ytm_text(fixed_column.get("text")).strip()
            if re.match(r"^\d+:\d+", duration_raw):
                try:
                    duration_seconds = display_to_seconds(duration_raw)
                except ValueError:
                    duration_seconds = None
            if title:
                tracks.append(
                    {
                        "track_number": len(tracks) + 1,
                        "title": title,
                        "duration_seconds": duration_seconds,
                    }
                )
        if len(tracks) > 1:
            return tracks
    return []


def _youtube_music_album_draft_from_browse(
    request: ImportRequest,
    browse_data: dict[str, Any],
    fallback_url: str,
) -> AlbumDraftData | None:
    if not browse_data:
        return None
    microformat = (browse_data.get("microformat") or {}).get("microformatDataRenderer") or {}
    title_text = str(microformat.get("title") or "").strip()
    album_title = request.album_title or ""
    artist_name = request.artist_name or ""
    if title_text:
        by_m = re.search(r"(.+?)\s*-\s*(?:Album\s+by|EP\s+by|Single\s+by)\s+(.+)", title_text, re.IGNORECASE)
        if by_m:
            album_title = album_title or by_m.group(1).strip()
            artist_name = artist_name or by_m.group(2).strip()
        else:
            album_title = album_title or title_text
    if not artist_name:
        strapline = _find_all_by_key(browse_data, "straplineTextOne")
        for item in strapline:
            text = _ytm_text(item).strip()
            if text:
                artist_name = text
                break
    if not album_title:
        for title in _find_all_by_key(browse_data, "title"):
            text = _ytm_text(title).strip()
            if text:
                album_title = text
                break

    tracks = _extract_ytm_album_tracks_from_browse(browse_data)
    release_year = _extract_ytm_year_from_objects([browse_data])
    known_secs = [t["duration_seconds"] for t in tracks if t.get("duration_seconds") is not None]
    total_seconds = sum(known_secs) if known_secs else None
    album_url = str(microformat.get("urlCanonical") or fallback_url)
    cover_url = _ytm_thumbnail_url(microformat.get("thumbnail")) or _ytm_thumbnail_url(browse_data)

    return AlbumDraftData(
        artist_name=artist_name or request.artist_name,
        artist_description=None,
        album_external_url=album_url,
        album_stream_url=album_url,
        album_title=album_title,
        release_year=release_year,
        duration_seconds=total_seconds,
        cover_source_url=cover_url,
        notes=_clean_ytm_album_notes(microformat.get("description")),
        tracks=tracks,
    )


def _youtube_music_album_draft_from_watch_url(
    request: ImportRequest,
    ytm_raw: str,
    metadata: dict[str, Any],
) -> AlbumDraftData | None:
    video_id = _ytm_video_id(request.source_url)
    api_key, client_version = _ytm_api_config(ytm_raw)
    if not video_id or not api_key:
        return None
    next_data = _fetch_ytm_api(
        "next",
        _ytm_api_payload(client_version, videoId=video_id, isAudioOnly=True),
        api_key,
    )
    browse_id = _extract_ytm_album_browse_id(next_data)
    if not browse_id:
        return None
    browse_data = _fetch_ytm_api("browse", _ytm_api_payload(client_version, browseId=browse_id), api_key)
    draft = _youtube_music_album_draft_from_browse(request, browse_data, request.source_url)
    if draft is None:
        return None
    if not draft.cover_source_url:
        draft = draft.model_copy(update={"cover_source_url": metadata.get("image")})
    return draft


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
    _validate_source_url(url)
    try:
        result = subprocess.run(
            _curl_source_args(url),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout[:MAX_SOURCE_BYTES]
    except Exception:
        return ""


def _extract_ytm_tracks_from_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract tracks from decoded YTM initialData push objects.

    Each track is represented as a ``musicResponsiveListItemRenderer``.  The
    title lives in ``flexColumns[0]`` and the duration (``M:SS`` format) lives
    in ``fixedColumns[0]``.  This data comes from the same page already fetched
    by ``_fetch_ytm_full_page``, so no extra HTTP request is needed.  Unlike
    ``www.youtube.com/playlist``, the YTM page embeds the *complete* tracklist
    rather than only the first few lazily-loaded items.
    """
    for obj in objects:
        renderers = _find_all_by_key(obj, "musicResponsiveListItemRenderer")
        if not renderers:
            continue
        tracks: list[dict[str, Any]] = []
        for pos, renderer in enumerate(renderers, start=1):
            if not isinstance(renderer, dict):
                continue
            fc = renderer.get("flexColumns") or []
            title = ""
            if fc:
                col0 = (fc[0].get("musicResponsiveListItemFlexColumnRenderer") or {})
                runs = (col0.get("text") or {}).get("runs") or []
                if runs:
                    title = str(runs[0].get("text") or "").strip()
            if not title:
                continue
            fixed = renderer.get("fixedColumns") or []
            duration_sec: int | None = None
            if fixed:
                col0 = (fixed[0].get("musicResponsiveListItemFixedColumnRenderer") or {})
                runs = (col0.get("text") or {}).get("runs") or []
                if runs:
                    dur_text = str(runs[0].get("text") or "").strip()
                    if re.match(r"^\d+:\d+", dur_text):
                        try:
                            duration_sec = display_to_seconds(dur_text)
                        except ValueError:
                            duration_sec = None
            tracks.append({"track_number": pos, "title": title, "duration_seconds": duration_sec})
        if tracks:
            return tracks
    return []


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
    is_watch_url = _is_youtube_music_watch_url(request.source_url)
    if is_watch_url:
        resolved_draft = _youtube_music_album_draft_from_watch_url(request, ytm_raw, metadata)
        if resolved_draft is not None and len(resolved_draft.tracks) > 1:
            return resolved_draft

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
            if is_watch_url and not artist_name:
                artist_name = str(metadata.get("description") or "").strip()

    # Cover: og:image from the music.youtube.com fetch is reliable
    cover_url = metadata.get("image")

    # Decode the YTM initialData objects once; reuse for both year and tracks.
    ytm_objects = _decode_ytm_initial_data_objects(ytm_raw) if ytm_raw else []
    if not artist_name:
        artist_name = _extract_ytm_artist_name(metadata, ytm_objects)

    # Release year from the subtitle initialData field ("Album • 2026").
    release_year = _extract_ytm_year_from_objects(ytm_objects)

    # Tracks: prefer the YTM page data (complete tracklist) over the regular
    # YouTube playlist page which only lazily inlines the first few items.
    tracks: list[dict[str, Any]] = _extract_ytm_tracks_from_objects(ytm_objects)
    if not tracks and playlist_id:
        tracks = _extract_yt_playlist_tracks(playlist_id)

    # Total duration: sum known track durations
    known_secs = [t["duration_seconds"] for t in tracks if t.get("duration_seconds") is not None]
    total_seconds = sum(known_secs) if known_secs else None

    return AlbumDraftData(
        artist_name=artist_name or request.artist_name,
        artist_description=None,
        album_external_url=request.source_url,
        album_stream_url=request.source_url,
        album_title=album_title,
        release_year=release_year,
        duration_seconds=total_seconds,
        cover_source_url=cover_url,
        tracks=tracks,
    )


def _extract_location_from_born(born_text: str) -> str | None:
    """Extract location from a Wikipedia 'Born' field.

    Solo-artist pages put name + dates + age in parentheses + location in one cell.
    Example: 'Benjamin George Cramer ( 1991-04-16 ) April 16, 1991 (age 35) Atlanta , Georgia, United States'
    We split on the last '(age N)' marker and return everything after it, stripped.
    """
    m = re.search(r'\(age\s+\d+\)\s*(.*)', born_text)
    if m:
        location = m.group(1).strip()
        return location or None
    return None


_WIKIPEDIA_COUNTRY_ALIASES = {
    "u.s.": "USA",
    "u.s": "USA",
    "us": "USA",
    "usa": "USA",
    "u.s.a.": "USA",
    "u.s.a": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "u.k": "United Kingdom",
}

_WIKIPEDIA_COUNTRY_NAMES = {
    "australia",
    "canada",
    "denmark",
    "england",
    "finland",
    "france",
    "germany",
    "ireland",
    "israel",
    "italy",
    "japan",
    "netherlands",
    "new zealand",
    "norway",
    "poland",
    "scotland",
    "serbia",
    "spain",
    "sweden",
    "united kingdom",
    "wales",
}

_WIKIPEDIA_US_STATE_NAMES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "west virginia",
    "wisconsin",
    "wyoming",
}


def _normalize_wikipedia_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    cleaned = re.sub(r"\s+,", ",", origin)
    cleaned = re.sub(r",\s*", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
    if not cleaned:
        return None

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(parts) < 2:
        if cleaned.lower() in _WIKIPEDIA_US_STATE_NAMES:
            return f"USA, {cleaned}"
        return cleaned

    country_raw = _clean_wikipedia_text(parts[-1]).rstrip(".")
    country_key = country_raw.lower()
    country = _WIKIPEDIA_COUNTRY_ALIASES.get(country_key)
    if country is None and country_key in _WIKIPEDIA_COUNTRY_NAMES:
        country = parts[-1]
    if country is None and country_key in _WIKIPEDIA_US_STATE_NAMES:
        return _normalize_imported_origin(", ".join(["USA", *parts]))
    if country is None:
        return _normalize_imported_origin(cleaned)
    return _normalize_imported_origin(", ".join([country, *parts[:-1]]))


def _best_effort_artist_draft(request: ImportRequest) -> ArtistDraftData:
    metadata = _page_metadata(request.source_url)
    html = str(metadata.get("html") or "")
    source_label = str(metadata.get("source_label") or _host_label(request.source_url) or "")
    if "music.youtube.com" in source_label:
        artist_name = request.artist_name.strip()
        if not artist_name:
            artist_name = _extract_ytm_artist_name(metadata)
        if not artist_name:
            title = str(metadata.get("title") or "").strip()
            by_m = re.search(r"\s*-\s*(?:Album\s+by|EP\s+by|Single\s+by)\s+(.+)", title, re.IGNORECASE)
            if by_m:
                artist_name = by_m.group(1).strip()
            elif _is_youtube_music_watch_url(request.source_url):
                artist_name = str(metadata.get("description") or "").strip()
            elif title:
                artist_name = re.sub(r"\s*-\s*YouTube Music\s*$", "", title, flags=re.IGNORECASE).strip()
        if not artist_name:
            artist_name = _host_label(request.source_url) or "Unknown Artist"
        description = None if _is_youtube_music_album_source_url(request.source_url) else metadata.get("description")
        return ArtistDraftData(
            artist_name=artist_name,
            description=description,
            external_url=request.source_url,
            origin=None,
            genre=None,
        )
    if "metal-archives.com" in source_label and html:
        return _metal_archives_artist_draft(request, html, metadata)
    if "bandcamp.com" in source_label and html:
        return _bandcamp_artist_draft(request, html, metadata)
    if "wikipedia.org" in source_label and html:
        infobox = _extract_wikipedia_infobox(html)
        artist_name = request.artist_name.strip()
        if not artist_name:
            title = str(metadata.get("title") or "").strip()
            artist_name = title.split(" - ")[0].strip() if title else ""
        if not artist_name:
            artist_name = _host_label(request.source_url) or "Unknown Artist"
        born = infobox.get("Born")
        born_location = _extract_location_from_born(born) if born else None
        origin = infobox.get("Birthplace") or born_location or infobox.get("Origin")
        origin = _normalize_wikipedia_origin(origin)
        genre_raw = infobox.get("Genre") or infobox.get("Genres")
        genre = _normalize_imported_genre(genre_raw)
        description = metadata.get("description") or _extract_wikipedia_lead_description(html)
        return ArtistDraftData(
            artist_name=artist_name,
            description=description,
            external_url=request.source_url,
            origin=origin,
            genre=genre,
        )
    artist_name = request.artist_name.strip()
    if not artist_name:
        title = str(metadata.get("title") or "").strip()
        if title:
            artist_name = title.split(" - ")[0].strip()
    if not artist_name:
        artist_name = _host_label(request.source_url) or "Unknown Artist"
    if "alterportal.net" in source_label and html:
        clean = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        if not artist_name:
            og_title = str(metadata.get("title") or "").strip()
            title_no_year = re.sub(r"\s*\(\d{4}\)\s*$", "", og_title).strip()
            if " - " in title_no_year:
                artist_name = title_no_year.split(" - ", 1)[0].strip()
        genre_raw = _alterportal_field(clean, "Стиль")
        genre = _normalize_imported_genre(re.split(r"\s*/\s*", genre_raw)[0].strip()) if genre_raw else None
        origin = _alterportal_origin(_alterportal_field(clean, "Страна"))
        return ArtistDraftData(
            artist_name=artist_name or _host_label(request.source_url) or "Unknown Artist",
            description=None,
            external_url=request.source_url,
            origin=origin,
            genre=genre,
        )
    return ArtistDraftData(
        artist_name=artist_name,
        description=metadata.get("description"),
        external_url=request.source_url,
        origin=None,
        genre=None,
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
    "live": "Live",
    "live album": "Live",
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


def _alterportal_field(clean_html: str, label: str) -> str | None:
    """Extract a labeled field value from an alterportal page body (HTML comments pre-stripped)."""
    for line in _alterportal_text_lines(clean_html):
        m = re.match(rf"^{re.escape(label)}\s*:?\s*(.+)$", line, re.IGNORECASE)
        if m:
            return m.group(1).strip() or None
    m = re.search(rf"{re.escape(label)}.*?</b>\s*:?\s*(.*?)<br", clean_html, re.IGNORECASE | re.DOTALL)
    return _strip_html(m.group(1)).strip() or None if m else None


def _alterportal_text_lines(clean_html: str) -> list[str]:
    text = re.sub(r"(?i)<br\s*/?>", "\n", clean_html)
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html_unescape(text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _alterportal_title_parts(og_title: str, request: ImportRequest) -> tuple[str, str, int | None]:
    artist_name = request.artist_name or ""
    album_title = request.album_title or ""
    release_year: int | None = None
    title_part = og_title.strip()
    if title_part:
        title_part = re.split(r"\s+»\s+", title_part, maxsplit=1)[0].strip()
        year_m = re.search(r"\((\d{4})\)\s*$", title_part)
        if year_m:
            release_year = int(year_m.group(1))
            title_part = title_part[: year_m.start()].strip()
        else:
            slug_year_m = re.search(r"[-_/]((?:19|20)\d{2})(?:\.html)?$", request.source_url or "")
            if slug_year_m:
                release_year = int(slug_year_m.group(1))
        if " - " in title_part:
            parts = title_part.split(" - ", 1)
            if not artist_name:
                artist_name = parts[0].strip()
            if not album_title:
                album_title = parts[1].strip()
        elif not album_title:
            album_title = title_part
    return artist_name, album_title, release_year


def _alterportal_tracks(clean_html: str) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    in_tracklist = False
    for line in _alterportal_text_lines(clean_html):
        if re.match(r"^Треклист\s*:?\s*$", line, re.IGNORECASE):
            in_tracklist = True
            continue
        if not in_tracklist:
            continue
        if re.match(r"^(Download|Скачать)\s*:?", line, re.IGNORECASE):
            break
        track_m = re.match(r"^0*(\d+)\.\s+(.+?)(?:\s*[\[(]\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[\])])?\s*$", line)
        if not track_m:
            if tracks:
                break
            continue
        title = track_m.group(2).strip()
        duration_seconds = None
        if track_m.group(3):
            try:
                duration_seconds = display_to_seconds(track_m.group(3))
            except ValueError:
                duration_seconds = None
        if title:
            tracks.append({"track_number": int(track_m.group(1)), "title": _html_unescape(title), "duration_seconds": duration_seconds})
    return tracks


def _alterportal_release_year(clean_html: str) -> int | None:
    release_raw = _alterportal_field(clean_html, "Дата релиза")
    if release_raw:
        date_m = re.search(r"\b((?:19|20)\d{2})\b", release_raw)
        if date_m:
            return int(date_m.group(1))
    return None


def _alterportal_origin(value: str | None) -> str | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) >= 2:
        return _normalize_imported_origin(", ".join([parts[-1], *parts[:-1]]))
    return _normalize_imported_origin(value.strip() or None)


def _alterportal_album_draft(request: ImportRequest, html: str, metadata: dict[str, Any]) -> AlbumDraftData:
    """Build an AlbumDraftData from an alterportal.net album page."""
    og_title = str(metadata.get("title") or "").strip()
    artist_name, album_title, release_year = _alterportal_title_parts(og_title, request)

    clean = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    release_year = release_year or _alterportal_release_year(clean)

    genre_raw = _alterportal_field(clean, "Стиль")
    genre = _normalize_imported_genre(re.split(r"\s*/\s*", genre_raw)[0].strip()) if genre_raw else None

    duration_raw = _alterportal_field(clean, "Время звучания")
    duration_seconds: int | None = None
    if duration_raw:
        dur_m = re.search(r"(\d+)\s*min(?:\s*(\d+)\s*sec)?", duration_raw)
        if dur_m:
            duration_seconds = int(dur_m.group(1)) * 60 + int(dur_m.group(2) or 0)

    tracks = _alterportal_tracks(clean)
    if duration_seconds is None:
        known_secs = [track["duration_seconds"] for track in tracks if track.get("duration_seconds") is not None]
        duration_seconds = sum(known_secs) if known_secs else None

    format_raw = _alterportal_field(clean, "Формат")
    notes = f"Format: {format_raw}" if format_raw else None

    return AlbumDraftData(
        artist_name=artist_name or request.artist_name,
        artist_description=None,
        album_external_url=request.source_url,
        album_title=album_title,
        release_year=release_year,
        genre=genre,
        duration_seconds=duration_seconds,
        cover_source_url=metadata.get("image"),
        notes=notes,
        tracks=tracks,
    )


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
    elif "alterportal.net" in source_label and html:
        draft = _alterportal_album_draft(request, html, metadata)
    else:
        page_title = str(metadata.get("title") or "")
        album_title = request.album_title or ""
        if not album_title and page_title:
            album_title = page_title.split(" - ")[0].strip()
        stream_url = request.source_url if _is_streaming_url(request.source_url) else None
        draft = AlbumDraftData(
            artist_name=request.artist_name,
            artist_description=metadata.get("description"),
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
    updates: dict[str, object] = {}
    if draft.album_title:
        updates["album_title"] = _fix_imported_title(draft.album_title)
    if draft.tracks:
        fixed_tracks = [t.model_copy(update={"title": _fix_imported_title(t.title)}) for t in draft.tracks]
        updates["tracks"] = fixed_tracks
    if updates:
        draft = draft.model_copy(update=updates)
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


def _fix_imported_title(text: str) -> str:
    """Normalize imported album and track titles that arrive in machine casing."""
    if not text:
        return text
    if text.isupper():
        return text.title()
    if any(ch.isalpha() for ch in text) and text == text.lower():
        first_alpha = next((idx for idx, ch in enumerate(text) if ch.isalpha()), None)
        if first_alpha is not None:
            fixed = text[:first_alpha] + text[first_alpha].upper() + text[first_alpha + 1 :]
            return re.sub(r"\bi(?=$|[^A-Za-z])", "I", fixed)

    def _fix_word(m: re.Match) -> str:
        w = m.group(0)
        if len(w) >= 3 and w.isupper():
            return w.title()
        return w

    return re.sub(r"[A-Za-z']+", _fix_word, text)


def _fix_allcaps(text: str) -> str:
    return _fix_imported_title(text)


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
    merged["album_title"] = _fix_imported_title(merged.get("album_title") or fallback.album_title or request.album_title or "")
    merged["artist_description"] = merged.get("artist_description") or fallback.artist_description
    merged["album_external_url"] = merged.get("album_external_url") or fallback.album_external_url or request.source_url
    merged["album_stream_url"] = fallback.album_stream_url or merged.get("album_stream_url")
    merged["release_year"] = merged.get("release_year") or fallback.release_year
    merged["genre"] = _normalize_imported_genre(merged.get("genre") or fallback.genre)
    merged["duration_seconds"] = merged.get("duration_seconds") or fallback.duration_seconds
    album_type = _normalize_album_type(fallback.album_type or merged.get("album_type"))
    if not album_type:
        track_count = len(merged.get("tracks") or fallback.tracks or [])
        album_type = _infer_album_type(merged.get("duration_seconds") or fallback.duration_seconds, track_count or None)
    merged["album_type"] = album_type
    merged["notes"] = fallback.notes or merged.get("notes")
    raw_tracks = merged.get("tracks") or [track.model_dump(mode="json") for track in fallback.tracks]
    for t in raw_tracks:
        if isinstance(t, dict) and t.get("title"):
            t["title"] = _fix_imported_title(t["title"])
    merged["tracks"] = raw_tracks
    merged["cover_source_url"] = (
        _normalize_cover_source_url(merged.get("cover_source_url"), request.source_url)
        or _normalize_cover_source_url(fallback.cover_source_url, request.source_url)
    )
    return AlbumDraftData.model_validate(merged)


class SourceMetadataImporter:
    def __init__(self) -> None:
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
        draft = _best_effort_artist_draft(request)
        self._mark_success()
        self._set_diagnostics(
            {
                "target": "artist",
                "mode": "source_parse_only",
                "reason": "AI is reserved for album write-up / Telegram post generation.",
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

    def create_album_draft(self, request: ImportRequest, *, model: str) -> AlbumDraftData:
        source_metadata = _page_metadata(request.source_url)
        context = self._build_context(request.source_url, metadata=source_metadata)
        draft = _best_effort_album_draft(request, metadata=source_metadata)
        self._mark_success()
        self._set_diagnostics(
            {
                "target": "album",
                "mode": "source_parse_only",
                "reason": "AI is reserved for album write-up / Telegram post generation.",
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


def _extract_spotify_album_url(search_html: str) -> str | None:
    for raw_href in re.findall(r'(?i)href=["\']([^"\']+)["\']', search_html):
        href = _html_unescape(raw_href)
        parsed = urlparse(href)
        if parsed.netloc.lower().endswith("duckduckgo.com"):
            href = parse_qs(parsed.query).get("uddg", [""])[0]
            parsed = urlparse(href)
        if parsed.netloc.lower() != "open.spotify.com":
            continue
        match = re.match(r"^/album/([A-Za-z0-9]+)", parsed.path)
        if match:
            return f"https://open.spotify.com/album/{match.group(1)}"
    return None


def _find_spotify_album_url(artist_name: str, album_title: str) -> str | None:
    spotify_url = _find_spotify_album_url_with_api(artist_name, album_title)
    if spotify_url:
        return spotify_url

    query = f'site:open.spotify.com/album "{artist_name}" "{album_title}"'
    search_url = f"https://html.duckduckgo.com/html/?{urlencode({'q': query})}"
    try:
        try:
            search_html, _ = _fetch_with_urllib(search_url)
        except (HTTPError, URLError, TimeoutError, ValueError):
            search_html, _ = _fetch_with_curl(search_url)
    except Exception:
        return None
    return _extract_spotify_album_url(search_html)


def _spotify_json_request(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
    }
    if headers:
        request_headers.update(headers)
    request = Request(url, data=data, headers=request_headers)
    with urlopen(request, timeout=SOURCE_FETCH_TIMEOUT_SECONDS) as response:
        raw_bytes = response.read(MAX_SOURCE_BYTES + 1)
    if len(raw_bytes) > MAX_SOURCE_BYTES:
        raise ValueError("Spotify response is too large.")
    data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
    if not isinstance(data, dict):
        raise ValueError("Spotify response is not a JSON object.")
    return data


def _find_spotify_album_url_with_api(artist_name: str, album_title: str) -> str | None:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    try:
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        token_data = _spotify_json_request(
            "https://accounts.spotify.com/api/token",
            data=urlencode({"grant_type": "client_credentials"}).encode("ascii"),
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        access_token = str(token_data.get("access_token") or "")
        if not access_token:
            return None
        query = f'album:"{album_title}" artist:"{artist_name}"'
        search_data = _spotify_json_request(
            f"https://api.spotify.com/v1/search?{urlencode({'type': 'album', 'limit': '5', 'q': query})}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except Exception:
        return None

    albums = search_data.get("albums")
    if not isinstance(albums, dict):
        return None
    items = albums.get("items")
    if not isinstance(items, list):
        return None

    expected_album = _normalize_lookup_text(album_title)
    expected_artist = _normalize_lookup_text(artist_name)
    for item in items:
        if not isinstance(item, dict):
            continue
        item_name = _normalize_lookup_text(str(item.get("name") or ""))
        artists = item.get("artists")
        if item_name != expected_album or not isinstance(artists, list):
            continue
        artist_names = {
            _normalize_lookup_text(str(artist.get("name") or ""))
            for artist in artists
            if isinstance(artist, dict)
        }
        if expected_artist not in artist_names:
            continue
        external_urls = item.get("external_urls")
        spotify_url = external_urls.get("spotify") if isinstance(external_urls, dict) else None
        if isinstance(spotify_url, str) and spotify_url.startswith("https://open.spotify.com/album/"):
            return spotify_url.split("?", 1)[0]
    return None


def _normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _spotify_album_search_url(artist_name: str, album_title: str) -> str:
    query = quote(f'album:"{album_title}" artist:"{artist_name}"', safe="")
    return f"https://open.spotify.com/search/{query}/albums"


def _ensure_spotify_writeup_link(writeup: str, spotify_url: str | None) -> str:
    if not spotify_url or f"]({spotify_url})" in writeup:
        return writeup
    listen_line = re.compile(
        r"(?im)^((?:🎧\s*)?(?:Listen|Слушать)\s*:\s*\n+)([^\n]+)$"
    )

    def add_link(match: re.Match[str]) -> str:
        services = match.group(2)
        linked_services = re.sub(r"(?<!\[)\bSpotify\b(?!\])", f"[Spotify]({spotify_url})", services)
        return match.group(1) + linked_services

    return listen_line.sub(add_link, writeup, count=1)


def _ensure_writeup_listen_links(
    writeup: str,
    *,
    youtube_music_url: str | None,
    spotify_url: str | None,
    language: str,
) -> str:
    """Deterministically add or replace the Listen block after AI generation."""
    if not youtube_music_url and not spotify_url:
        return writeup
    youtube = f"[YouTube Music]({youtube_music_url})" if youtube_music_url else "YouTube Music"
    spotify = f"[Spotify]({spotify_url})" if spotify_url else "Spotify"
    label = "Слушать" if language == "ru" else "Listen"
    block = f"🎧 {label}:\n{youtube} | {spotify}"
    listen_block = re.compile(
        r"(?im)^(?:🎧\s*)?(?:Listen|Слушать)\s*:\s*\n+[^\n]*"
    )
    if listen_block.search(writeup):
        return listen_block.sub(block, writeup, count=1)
    return f"{writeup.rstrip()}\n\n{block}"


def _strip_inline_web_citations(writeup: str) -> str:
    """Remove Responses API inline web citations; sources are shown separately in the UI."""
    return re.sub(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\)", "", writeup)


def _titlecase_known_genres(description: str, genre: str | None) -> str:
    """Title-case every word in known genre names in an artist biography."""
    genre_names = [part.strip() for part in re.split(r"\s*[/,;]\s*", genre or "") if part.strip()]
    for genre_name in sorted(genre_names, key=len, reverse=True):
        pattern = re.escape(genre_name).replace(r"\ ", r"[\s-]+")
        description = re.sub(
            rf"(?<!\w){pattern}(?!\w)",
            lambda match: _titlecase_genre(match.group(0)),
            description,
            flags=re.IGNORECASE,
        )
    return description


class AlbumWriteupGenerator:
    def __init__(self, client: AlbumWriteupAIClient | None) -> None:
        self.client = client
        self.last_request_failed = False
        self.last_error: str | None = None
        self.last_artist_description_sources: list[dict[str, str]] = []
        self.last_album_writeup_sources: list[dict[str, str]] = []

    def _mark_success(self) -> None:
        self.last_request_failed = False
        self.last_error = None

    def _mark_failure(self, detail: str) -> None:
        self.last_request_failed = True
        self.last_error = detail

    def generate_album_overview(self, album: AlbumDetailRecord, *, language: str, model: str) -> str:
        # Compatibility wrapper for callers that still use the old "overview" name.
        return self.generate_album_writeup(album, language=language, model=model)

    def generate_artist_description(
        self,
        artist_name: str,
        *,
        origin: str | None,
        album_title: str | None,
        genre: str | None,
        source_url: str | None,
        model: str,
    ) -> str:
        if self.client is None:
            raise AIClientError("No AI client is configured")
        self.last_artist_description_sources = []

        source_excerpt = ""
        if source_url:
            try:
                source_excerpt = _fetch_url_excerpt(source_url)
            except Exception:
                pass

        wikipedia_excerpt = ""
        try:
            wikipedia_excerpt = _fetch_url_excerpt(wikipedia_artist_url_from_name(artist_name))
        except Exception:
            pass

        context_parts = [
            f"Artist: {artist_name}",
            f"Origin: {origin or 'unknown'}",
            f"Imported album: {album_title or 'unknown'}",
            f"Imported genre: {genre or 'unknown'}",
        ]
        if source_url:
            context_parts.append(f"Reference URL: {source_url}")
        if source_excerpt:
            context_parts.append(f"Reference page excerpt:\n{source_excerpt[:6000]}")
        if wikipedia_excerpt and wikipedia_excerpt != source_excerpt:
            context_parts.append(f"Wikipedia excerpt:\n{wikipedia_excerpt[:4000]}")

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "description": {"type": "string"},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["title", "url"],
                    },
                },
            },
            "required": ["description", "sources"],
        }
        try:
            data, sources = self.client.generate_json_with_web_search(
                model=model,
                system_prompt=(
                    "You research and write concise, factual biographies of musical artists for a personal music library. "
                    "Use web search to identify the exact artist and verify concrete facts before writing."
                ),
                user_prompt=(
                    "Search the web for the exact band or musical artist below before answering. Use the album, genre, and URL "
                    "to disambiguate artists with similar names. Your search query should quote the artist name and include the "
                    "known album or release title when provided. Prefer the artist's official site or Bandcamp, label pages, "
                    "MusicBrainz, Discogs, AllMusic, and reputable music publications. Write one informative English paragraph "
                    "of 60 to 90 words containing concrete facts such as origin, members, genre, career history, and "
                    "notable releases when supported by sources. Do not infer style from a song or album title, and avoid vague "
                    "filler such as 'mysterious', 'intriguing', 'possibly', or 'limited information'. Do not include changing "
                    "statistics such as listener, follower, or play counts. Write every musical genre name in title case, "
                    "capitalizing every word and every hyphenated part; for example, Black Metal, Death Metal, Dream Pop, "
                    "or Heavy Psych-Rock. Do not write genre names in all caps. "
                    "Return clean prose in the description field without "
                    "headings, markdown, URLs, or inline citations. In the sources field, return 2 to 5 web pages actually used, "
                    "each with a concise title and canonical URL. Do not use Reddit, forums, or user-generated playlists as "
                    "primary biographical sources.\n\n"
                    + "\n\n".join(context_parts)
                ),
                schema_name="artist_description",
                schema=schema,
            )
            description = str(data["description"]).strip()
            if not description:
                raise AIClientError("AI returned an empty artist description")
            description = _titlecase_known_genres(description, genre)
            structured_source_list: list[dict[str, str]] = []
            structured_sources = data.get("sources")
            if isinstance(structured_sources, list):
                for source in structured_sources:
                    if not isinstance(source, dict):
                        continue
                    url = str(source.get("url") or "").strip()
                    title = str(source.get("title") or url).strip()
                    if url.startswith(("https://", "http://")):
                        structured_source_list.append({"title": title, "url": url})
            combined_sources = structured_source_list + list(sources)
            seen_urls: set[str] = set()
            self.last_artist_description_sources = []
            for source in combined_sources:
                if source["url"] in seen_urls:
                    continue
                seen_urls.add(source["url"])
                self.last_artist_description_sources.append(source)
                if len(self.last_artist_description_sources) >= 10:
                    break
            self._mark_success()
            return description
        except (OpenAIClientError, AIClientError) as exc:
            self._mark_failure(str(exc))
            raise
        except Exception as exc:
            self._mark_failure(str(exc))
            raise

    def generate_album_writeup(self, album: AlbumDetailRecord, *, language: str, model: str) -> str:
        if self.client is None:
            raise AIClientError("No AI client is configured")
        self.last_album_writeup_sources = []

        page_excerpt = ""
        if album.album_external_url:
            try:
                page_excerpt = _fetch_url_excerpt(album.album_external_url)
            except Exception:
                pass

        wiki_excerpt = ""
        try:
            from urllib.parse import quote as _url_quote
            wiki_title = f"{album.artist_name}_{album.title}".replace(" ", "_")
            wiki_url = f"https://en.wikipedia.org/wiki/{_url_quote(wiki_title)}"
            wiki_excerpt = _fetch_url_excerpt(wiki_url)
        except Exception:
            pass

        lang_instruction = (
            "Write the album write-up in English."
            if language == "en"
            else "Write the album write-up in Russian (Русский язык)."
        )

        tracklist_text = "\n".join(
            f"{t.track_number}. {t.title}" + (f"  {t.duration_seconds // 60}:{t.duration_seconds % 60:02d}" if t.duration_seconds else "")
            for t in album.tracks
        ) or "No tracklist available."

        stream_line = ""
        if album.album_stream_url:
            stream_line = f"\nStream URL: {album.album_stream_url}"
        stream_host = urlparse(album.album_stream_url or "").netloc.lower()
        has_spotify_stream = "spotify.com" in stream_host
        spotify_url_is_exact = has_spotify_stream
        if has_spotify_stream:
            spotify_url = album.album_stream_url
        else:
            spotify_url = _find_spotify_album_url(album.artist_name, album.title)
            spotify_url_is_exact = bool(spotify_url)
            if not spotify_url:
                spotify_url = _spotify_album_search_url(album.artist_name, album.title)
        youtube_music_url = album.album_stream_url if "music.youtube.com" in stream_host else None
        if youtube_music_url and spotify_url:
            listen_line_example = f"[YouTube Music]({youtube_music_url}) | [Spotify]({spotify_url})"
        elif spotify_url:
            listen_line_example = f"YouTube Music | [Spotify]({spotify_url})"
        else:
            listen_line_example = f"[YouTube Music]({youtube_music_url}) | Spotify" if youtube_music_url else ""
        listen_instruction = (
            "For the '🎧 Listen' / '🎧 Слушать' line, use every exact streaming URL supplied below as a Markdown link. "
            "When both URLs are known, write '[YouTube Music](url) | [Spotify](url)'. "
            "When only Spotify is known, write 'YouTube Music | [Spotify](url)'. "
            "When only YouTube Music is known, write '[YouTube Music](url) | Spotify'. "
            "Always mention both services when at least one supported stream URL is known. "
            "If no stream URL is known, omit the Listen line entirely.\n"
        )

        context_parts = [
            f"Artist: {album.artist_name}",
            f"Album: {album.title}",
            f"Year: {album.release_year or 'unknown'}",
            f"Genre: {album.genre or 'unknown'}",
            f"Type: {album.album_type or 'unknown'}",
            f"Country/Origin: {album.artist_origin or 'unknown'}",
            f"Duration: {album.duration_seconds // 60} min" if album.duration_seconds else "Duration: unknown",
            f"Tracklist:\n{tracklist_text}",
            stream_line,
        ]
        if spotify_url and not has_spotify_stream and spotify_url_is_exact:
            context_parts.append(f"Spotify URL found for album: {spotify_url}")
        elif spotify_url and not has_spotify_stream:
            context_parts.append(f"Spotify album search URL: {spotify_url}")
        if page_excerpt:
            context_parts.append(f"\nSource page excerpt (Metal Archives or similar):\n{page_excerpt[:6000]}")
        if wiki_excerpt:
            context_parts.append(f"\nWikipedia excerpt:\n{wiki_excerpt[:4000]}")

        context = "\n".join(p for p in context_parts if p)

        format_example_en = (
            "Format example (English):\n"
            "🎸 Album: Artist — Title\n\n"
            "📅 Release date: Month Day, Year\n\n"
            "🌍 Country: Country\n\n"
            "🎶 Genre: Genre (always in English)\n\n"
            "📌 Description:\n"
            "A few paragraphs about the album — history, sound, reception, notable facts.\n\n"
            "⭐ User ratings:\n"
            "Source: score/scale (rating count when available)\n"
            "Metal Archives reviews: average% (review count)\n\n"
            "🎧 Listen:\n"
            f"{listen_line_example}"
        )
        format_example_ru = (
            "Format example (Russian):\n"
            "🎸 Альбом: Исполнитель — Название\n\n"
            "📅 Дата выхода: ДД Месяц ГГГГ\n\n"
            "🌍 Страна: Страна\n\n"
            "🎶 Жанр: Genre (always in English, e.g. Progressive Metal)\n\n"
            "📌 Описание:\n"
            "Несколько абзацев об альбоме — история, звучание, reception, факты.\n\n"
            "⭐ Пользовательские оценки:\n"
            "Источник: оценка/шкала (количество оценок, если доступно)\n"
            "Metal Archives reviews: средняя оценка% (количество рецензий)\n\n"
            "🎧 Слушать:\n"
            f"{listen_line_example}"
        )
        format_example = format_example_ru if language == "ru" else format_example_en

        prompt = (
            f"Write a rich, factual Telegram-ready album post for the following album.\n"
            f"{lang_instruction}\n"
            f"IMPORTANT: The genre value (after the 🎶 label) must always be written in English, "
            f"even when the write-up language is Russian.\n"
            f"Search the web for the exact album before writing, using the artist, album title, and year together to disambiguate it. "
            f"Use the provided metadata and source excerpts as additional context. Prefer official artist or label pages, Bandcamp, "
            f"MusicBrainz, Discogs, AllMusic, and reputable music publications.\n"
            f"Research public user/community ratings on Rate Your Music, Album of the Year, and Metal Storm. Do not use Sputnikmusic. "
            f"For metal albums, explicitly check the exact album's reviews on Encyclopaedia Metallum (metal-archives.com). Report its "
            f"review average as 'Metal Archives reviews: NN% (N reviews)' when both values are available; this is a review average, not "
            f"a user-rating score, so label it clearly. When at least one verifiable rating or Metal Archives review average exists, "
            f"include the User ratings section with each source's "
            f"score, original scale, and rating/vote count when available. Do not convert scales, confuse critic scores with user scores, "
            f"or invent missing numbers. Omit the entire User ratings section when no verifiable user rating is found. The sources field "
            f"must include the exact page supporting every reported rating. Keep the overview text clean: do not put inline citations, "
            f"source URLs, or citation markdown inside it because sources are displayed separately.\n"
            f"{listen_instruction}"
            f"Keep the write-up informative but concise (3–6 sentences in the description paragraph).\n\n"
            f"{format_example}\n\n"
            f"Album data:\n{context}"
        )

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "overview": {"type": "string"},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["title", "url"],
                    },
                },
            },
            "required": ["overview", "sources"],
        }

        try:
            request_kwargs = dict(
                model=model,
                system_prompt=(
                    "You are a music writer creating concise, factual album write-ups "
                    "for Telegram posts and a personal music library app. Use web search and only verified facts."
                ),
                user_prompt=prompt,
                schema_name="album_overview",
                schema=schema,
            )
            generate_with_search = getattr(self.client, "generate_json_with_web_search", None)
            if callable(generate_with_search):
                data, sources = generate_with_search(**request_kwargs)
            else:
                # Compatibility for injected/legacy clients; the production OpenAI client always uses web search.
                data = self.client.generate_json(**request_kwargs)
                sources = []
            structured_source_list: list[dict[str, str]] = []
            structured_sources = data.get("sources")
            if isinstance(structured_sources, list):
                for source in structured_sources:
                    if not isinstance(source, dict):
                        continue
                    url = str(source.get("url") or "").strip()
                    title = str(source.get("title") or url).strip()
                    if url.startswith(("https://", "http://")):
                        structured_source_list.append({"title": title, "url": url})
            rating_domains = (
                "albumoftheyear.org",
                "rateyourmusic.com",
                "metalstorm.net",
                "metal-archives.com",
            )
            sources = [source for source in sources if "sputnikmusic.com" not in source["url"]]
            rating_sources = [source for source in sources if any(domain in source["url"] for domain in rating_domains)]
            other_sources = [source for source in sources if source not in rating_sources]
            combined_sources = structured_source_list + rating_sources + other_sources
            seen_urls: set[str] = set()
            for source in combined_sources:
                if source["url"] in seen_urls:
                    continue
                seen_urls.add(source["url"])
                self.last_album_writeup_sources.append(source)
                if len(self.last_album_writeup_sources) >= 10:
                    break
            self._mark_success()
            clean_writeup = _strip_inline_web_citations(str(data["overview"]))
            return _ensure_writeup_listen_links(
                clean_writeup,
                youtube_music_url=youtube_music_url,
                spotify_url=spotify_url,
                language=language,
            )
        except (OpenAIClientError, AIClientError) as exc:
            self._mark_failure(str(exc))
            raise
        except Exception as exc:
            self._mark_failure(str(exc))
            raise


class MetadataImporter:
    def __init__(
        self,
        client: AlbumWriteupAIClient | None,
        *,
        source_importer: SourceMetadataImporter | None = None,
        writeup_generator: AlbumWriteupGenerator | None = None,
    ) -> None:
        self.source_importer = source_importer or SourceMetadataImporter()
        self.writeup_generator = writeup_generator or AlbumWriteupGenerator(client)

    @property
    def client(self) -> AlbumWriteupAIClient | None:
        return self.writeup_generator.client

    @property
    def last_request_failed(self) -> bool:
        return self.writeup_generator.last_request_failed

    @property
    def last_error(self) -> str | None:
        return self.writeup_generator.last_error

    @property
    def last_artist_description_sources(self) -> list[dict[str, str]]:
        return self.writeup_generator.last_artist_description_sources

    @property
    def last_album_writeup_sources(self) -> list[dict[str, str]]:
        return self.writeup_generator.last_album_writeup_sources

    @property
    def last_diagnostics(self) -> dict[str, Any]:
        return self.source_importer.last_diagnostics

    def create_artist_draft(self, request: ImportRequest, *, model: str) -> ArtistDraftData:
        return self.source_importer.create_artist_draft(request, model=model)

    def create_album_draft(self, request: ImportRequest, *, model: str) -> AlbumDraftData:
        return self.source_importer.create_album_draft(request, model=model)

    def generate_album_overview(self, album: AlbumDetailRecord, *, language: str, model: str) -> str:
        return self.writeup_generator.generate_album_overview(album, language=language, model=model)

    def generate_artist_description(
        self,
        artist_name: str,
        *,
        origin: str | None,
        album_title: str | None,
        genre: str | None,
        source_url: str | None,
        model: str,
    ) -> str:
        return self.writeup_generator.generate_artist_description(
            artist_name,
            origin=origin,
            album_title=album_title,
            genre=genre,
            source_url=source_url,
            model=model,
        )

    def generate_album_writeup(self, album: AlbumDetailRecord, *, language: str, model: str) -> str:
        return self.writeup_generator.generate_album_writeup(album, language=language, model=model)


class CoverDownloader:
    _IMAGE_HEADERS = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
    }

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
        request = Request(url, headers=self._IMAGE_HEADERS)
        with urlopen(request, timeout=30) as response:
            data = response.read()
        if not data[:2] == b"\xff\xd8" and not data[:8] == b"\x89PNG\r\n\x1a\n" and not data[:4] in (b"RIFF", b"webp"):
            # Received HTML or unexpected content instead of an image; discard it
            return None
        target.write_bytes(data)
        return str(target)


def draft_to_json(data: ArtistDraftData | AlbumDraftData) -> dict[str, object]:
    return json.loads(data.model_dump_json())
