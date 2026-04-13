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


def _fetch_url_document(url: str) -> tuple[str, str]:
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
    notes_parts = [
        f"{label}: {details[label]}"
        for label in ["Type", "Label", "Format", "Version desc.", "Catalog ID"]
        if details.get(label)
    ]
    return AlbumDraftData(
        artist_name=artist_name,
        artist_description=metadata.get("description"),
        artist_description_source_url=request.source_url,
        artist_description_source_label=metadata.get("source_label"),
        album_external_url=request.source_url,
        album_title=title,
        release_year=release_year,
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


def _best_effort_album_draft(request: ImportRequest) -> AlbumDraftData:
    metadata = _page_metadata(request.source_url)
    html = str(metadata.get("html") or "")
    source_label = str(metadata.get("source_label") or "")
    if "metal-archives.com" in source_label and html:
        return _metal_archives_album_draft(request, html, metadata)
    if "bandcamp.com" in source_label and html:
        return _bandcamp_album_draft(request, html, metadata)
    if "wikipedia.org" in source_label and html:
        return _wikipedia_album_draft(request, html, metadata)
    page_title = str(metadata.get("title") or "")
    album_title = request.album_title or ""
    if not album_title and page_title:
        album_title = page_title.split(" - ")[0].strip()
    return AlbumDraftData(
        artist_name=request.artist_name,
        artist_description=metadata.get("description"),
        artist_description_source_url=request.source_url,
        artist_description_source_label=metadata.get("source_label"),
        album_external_url=request.source_url,
        album_title=album_title,
        cover_source_url=metadata.get("image"),
        notes=page_title or None,
    )


def infer_cover_source_url_from_album_url(album_url: str | None) -> str | None:
    if not album_url:
        return None
    request = ImportRequest(artist_name="", album_title="", source_url=album_url)
    draft = _best_effort_album_draft(request)
    return _normalize_cover_source_url(draft.cover_source_url, album_url)


def _looks_like_image_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
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
    merged["release_year"] = merged.get("release_year") or fallback.release_year
    merged["genre"] = merged.get("genre") or fallback.genre
    merged["duration_seconds"] = merged.get("duration_seconds") or fallback.duration_seconds
    merged["notes"] = merged.get("notes") or fallback.notes
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
        context = self._build_context(request.source_url)
        source_metadata = _page_metadata(request.source_url)
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
            "For 'origin', provide the city and country (or just country) where the artist is from, e.g. 'London, UK' or 'Nashville, USA'. "
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
        context = self._build_context(request.source_url)
        source_metadata = _page_metadata(request.source_url)
        fallback_draft = _best_effort_album_draft(request)
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
                "notes",
                "tracks",
            ],
        }
        prompt = (
            f"Create an album metadata draft for artist '{request.artist_name}' and album '{request.album_title or ''}'. "
            "Return only confident factual data. Use null for unknown fields. "
            f"Preferred source URL: {request.source_url or 'none provided'}.\n\n"
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

    def _build_context(self, source_url: str | None) -> str:
        if not source_url:
            return "No explicit source URL supplied. Use best-effort world knowledge only."
        try:
            excerpt = _fetch_url_excerpt(source_url)
        except (HTTPError, URLError, TimeoutError, ValueError, subprocess.CalledProcessError):
            excerpt = ""
        host = _host_label(source_url) or source_url
        return f"Source host: {host}\nSource URL: {source_url}\nExcerpt: {excerpt}"

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
        target = self.cover_dir / f"{stem}{suffix[:8]}"
        request = Request(url, headers=DEFAULT_HEADERS)
        with urlopen(request, timeout=30) as response:
            target.write_bytes(response.read())
        return str(target)


def draft_to_json(data: ArtistDraftData | AlbumDraftData) -> dict[str, object]:
    return json.loads(data.model_dump_json())
