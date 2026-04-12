from __future__ import annotations

import html
import json
from pathlib import Path

from album_ranker.schemas import (
    AlbumCardRecord,
    AlbumDetailRecord,
    GenreRecord,
    AlbumListRecord,
    ArtistWithAlbumsRecord,
    ImportDraftRecord,
    SettingsRecord,
    seconds_to_display,
)


def _escape(value: str | None) -> str:
    return html.escape(value or "")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True)


def _cover_src(path: str | None) -> str:
    if not path:
        return "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='600'%3E%3Crect width='100%25' height='100%25' fill='%23111a24'/%3E%3Ctext x='50%25' y='50%25' font-size='44' fill='%236e8397' dominant-baseline='middle' text-anchor='middle' font-family='Helvetica Neue'%3ENo Cover%3C/text%3E%3C/svg%3E"
    name = Path(path).name
    return f"/library-data/covers/{html.escape(name)}"


def _display_multiline_text(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = text.replace("; ", ";\n")
    text = text.replace(". ", ".\n")
    return html.escape(text)


def _rating_markup(rating: int | None) -> str:
    if not rating:
        return ""
    filled = "&#9733;" * int(rating)
    empty = "&#9734;" * (10 - int(rating))
    return (
        f'<div class="rating-line" aria-label="Rating: {rating} out of 10">'
        f'<span class="stars">{filled}{empty}</span>'
        f'<span class="rating-value">{rating}/10</span>'
        f"</div>"
    )


def _shell(title: str, active: str, body: str, *, page_state: dict[str, object]) -> str:
    navigation = [
        ("Artists", "/artists", "artists"),
        ("Albums", "/albums", "albums"),
        ("Genres", "/genres", "genres"),
        ("Lists", "/lists", "lists"),
        ("Settings", "/settings", "settings"),
    ]
    nav_markup = "".join(
        f'<a class="nav-link" data-active="{str(item_active == active).lower()}" href="{href}">{label}</a>'
        for label, href, item_active in navigation
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{_escape(title)}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#127925;</text></svg>">
    <style>
      :root {{
        --bg: #071018;
        --bg-elevated: #0d1823;
        --panel: #101f2c;
        --panel-strong: #15283a;
        --panel-soft: rgba(16, 31, 44, 0.82);
        --ink: #f3f7fb;
        --muted: #93a7b9;
        --line: rgba(163, 187, 209, 0.14);
        --accent: #ff7a3d;
        --accent-strong: #ff9a57;
        --success: #2ea87c;
        --danger: #db5a63;
        --shadow: 0 28px 80px rgba(0, 0, 0, 0.34);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        color: var(--ink);
        font-family: "Avenir Next", "Helvetica Neue", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(255, 122, 61, 0.12), transparent 24%),
          radial-gradient(circle at right, rgba(74, 115, 171, 0.2), transparent 24%),
          linear-gradient(180deg, #061018, #0a1520 42%, #08111a);
      }}
      a {{ color: inherit; }}
      .app {{
        display: grid;
        grid-template-columns: 240px minmax(0, 1fr);
        min-height: 100vh;
      }}
      .sidebar {{
        padding: 28px 20px;
        border-right: 1px solid var(--line);
        background: rgba(5, 11, 18, 0.72);
        backdrop-filter: blur(16px);
        position: sticky;
        top: 0;
        height: 100vh;
      }}
      .brand {{
        margin: 0 0 24px;
        font-family: "Iowan Old Style", "Palatino", serif;
        font-size: 34px;
        line-height: 0.95;
      }}
      .brand small {{
        display: block;
        margin-top: 8px;
        color: var(--muted);
        font-size: 13px;
        font-family: "Avenir Next", "Helvetica Neue", sans-serif;
        text-transform: uppercase;
        letter-spacing: 0.18em;
      }}
      .nav {{
        display: grid;
        gap: 10px;
      }}
      .nav-link {{
        display: block;
        padding: 12px 14px;
        border-radius: 14px;
        text-decoration: none;
        color: var(--muted);
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid transparent;
      }}
      .nav-link[data-active="true"] {{
        color: var(--ink);
        background: linear-gradient(135deg, rgba(255, 122, 61, 0.2), rgba(255, 154, 87, 0.12));
        border-color: rgba(255, 122, 61, 0.32);
      }}
      .sidebar-foot {{
        margin-top: 28px;
        color: var(--muted);
        font-size: 12px;
        line-height: 1.6;
      }}
      .sidebar-status {{
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid var(--line);
      }}
      .sidebar-status strong {{
        color: var(--ink);
      }}
      .content {{
        padding: 24px;
      }}
      .hero {{
        padding: 28px;
        border-radius: 28px;
        background:
          linear-gradient(145deg, rgba(255, 122, 61, 0.14), rgba(14, 28, 40, 0.94)),
          linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0));
        border: 1px solid var(--line);
        box-shadow: var(--shadow);
      }}
      .eyebrow {{
        margin: 0 0 10px;
        color: var(--accent-strong);
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 12px;
      }}
      h1, h2, h3 {{
        margin: 0;
      }}
      h1 {{
        font-family: "Iowan Old Style", "Palatino", serif;
        font-size: clamp(34px, 4.2vw, 58px);
        line-height: 0.96;
      }}
      .hero p {{
        margin: 12px 0 0;
        max-width: 760px;
        color: var(--muted);
        line-height: 1.7;
      }}
      .grid {{
        display: grid;
        gap: 18px;
        margin-top: 20px;
      }}
      .grid.two {{
        grid-template-columns: minmax(0, 1fr) minmax(340px, 0.95fr);
      }}
      .grid.three {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .panel {{
        padding: 20px;
        border-radius: 24px;
        background: var(--panel-soft);
        border: 1px solid var(--line);
        box-shadow: var(--shadow);
      }}
      .panel-title {{
        margin-bottom: 14px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-size: 12px;
      }}
      .muted {{
        color: var(--muted);
      }}
      form {{
        display: grid;
        gap: 10px;
      }}
      .form-field {{
        display: grid;
        gap: 6px;
      }}
      .form-label {{
        color: var(--muted);
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .row {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        align-items: center;
      }}
      .row > * {{
        flex: 1;
        min-width: 0;
      }}
      input, textarea, select {{
        width: 100%;
        border: 1px solid rgba(163, 187, 209, 0.16);
        background: rgba(4, 10, 17, 0.46);
        color: var(--ink);
        padding: 12px 14px;
        border-radius: 14px;
        font: inherit;
      }}
      textarea {{ min-height: 110px; resize: vertical; }}
      button {{
        appearance: none;
        border: 0;
        border-radius: 999px;
        padding: 11px 16px;
        background: linear-gradient(135deg, var(--accent), var(--accent-strong));
        color: #091019;
        font-weight: 700;
        cursor: pointer;
      }}
      button.secondary {{
        background: rgba(255, 255, 255, 0.08);
        color: var(--ink);
      }}
      button.danger {{
        background: rgba(219, 90, 99, 0.14);
        color: #ffd8dc;
      }}
      .status {{
        min-height: 22px;
        color: var(--muted);
        font-size: 13px;
      }}
      .album-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
        gap: 18px;
      }}
      .album-card {{
        text-decoration: none;
        color: inherit;
      }}
      .cover {{
        aspect-ratio: 1 / 1;
        width: 100%;
        border-radius: 22px;
        overflow: hidden;
        background: #101a24;
        box-shadow: 0 18px 42px rgba(0, 0, 0, 0.32);
        position: relative;
        cursor: pointer;
      }}
      .cover img {{
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }}
      .cover-upload-overlay {{
        position: absolute;
        inset: 0;
        background: rgba(0,0,0,0.55);
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0;
        transition: opacity 0.15s;
        border-radius: 22px;
        font-size: 13px;
        color: #fff;
        pointer-events: none;
      }}
      .cover:hover .cover-upload-overlay {{
        opacity: 1;
      }}
      .album-title {{
        margin-top: 12px;
        font-weight: 600;
      }}
      .album-subtitle {{
        margin-top: 4px;
        color: var(--muted);
        font-size: 14px;
      }}
      .rating-line {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 8px;
        color: var(--accent-strong);
        font-size: 13px;
      }}
      .stars {{
        letter-spacing: 0.08em;
      }}
      .rating-value {{
        color: var(--muted);
        font-size: 12px;
      }}
      .star-widget {{
        margin-top: 14px;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
      }}
      .star-widget-row {{
        display: flex;
        gap: 1px;
      }}
      .star-btn {{
        background: none;
        border: none;
        padding: 1px 2px;
        font-size: 26px;
        line-height: 1;
        color: #3a4f61;
        cursor: pointer;
        transition: color 0.1s, transform 0.12s;
        user-select: none;
      }}
      .star-btn.on {{
        color: var(--accent);
      }}
      .star-btn:hover {{
        transform: scale(1.2);
      }}
      .star-widget-label {{
        font-size: 13px;
        font-weight: 600;
        color: var(--muted);
        min-height: 18px;
        letter-spacing: 0.02em;
      }}
      .star-widget-status {{
        font-size: 11px;
        color: var(--accent-strong);
        min-height: 14px;
      }}
      .filters {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }}
      .filters select {{
        max-width: 240px;
      }}
      .artist-card {{
        padding: 18px;
        border-radius: 22px;
        border: 1px solid var(--line);
        background: rgba(255, 255, 255, 0.03);
      }}
      .artist-card + .artist-card {{
        margin-top: 14px;
      }}
      .artist-albums {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 14px;
      }}
      .tag {{
        display: inline-flex;
        align-items: center;
        padding: 7px 11px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.07);
        color: var(--muted);
        font-size: 13px;
        text-decoration: none;
      }}
      .clamp {{
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        white-space: pre-line;
      }}
      .clamp.expanded {{
        display: block;
      }}
      .toggle-link {{
        margin-top: 8px;
        color: var(--accent-strong);
        font-size: 13px;
        cursor: pointer;
        background: transparent;
        border: 0;
        padding: 0;
      }}
      .detail-layout {{
        display: grid;
        grid-template-columns: minmax(280px, 380px) minmax(0, 480px);
        gap: 96px;
        margin-top: 20px;
        align-items: start;
      }}
      .meta-stack {{
        display: grid;
        gap: 10px;
        margin-top: 14px;
      }}
      .detail-head {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 14px;
      }}
      .icon-button {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 42px;
        height: 42px;
        border-radius: 999px;
        padding: 0;
        font-size: 18px;
      }}
      .meta-item {{
        padding: 12px 14px;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.04);
      }}
      .meta-item-label {{
        display: block;
        margin-bottom: 6px;
        color: var(--muted);
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .tracklist {{
        display: grid;
        gap: 8px;
      }}
      .track-row {{
        display: grid;
        grid-template-columns: 42px minmax(0, 1fr) 60px;
        gap: 12px;
        padding: 10px 12px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.03);
        font-size: 15px;
      }}
      .track-row .muted {{
        text-align: right;
      }}
      .track-num {{
        display: flex;
        justify-content: flex-end;
        align-items: center;
        font-size: 14px;
        color: var(--muted);
      }}
      .list-block {{
        border-radius: 22px;
        border: 1px solid var(--line);
        overflow: hidden;
      }}
      .list-head {{
        padding: 18px;
        background: rgba(255, 255, 255, 0.04);
        display: flex;
        justify-content: space-between;
        align-items: center;
        cursor: pointer;
        user-select: none;
      }}
      .rank-list {{
        display: grid;
      }}
      .rank-item {{
        display: grid;
        grid-template-columns: 42px 64px minmax(0, 1fr) auto;
        gap: 14px;
        align-items: center;
        padding: 14px 18px;
        border-top: 1px solid var(--line);
        background: rgba(10, 19, 28, 0.92);
      }}
      .rank-cover {{
        width: 64px;
        height: 64px;
        border-radius: 14px;
        overflow: hidden;
      }}
      .rank-cover img {{
        width: 100%;
        height: 100%;
        object-fit: cover;
      }}
      .mini-actions {{
        display: flex;
        gap: 6px;
      }}
      .mini-actions button {{
        padding: 8px 11px;
        font-size: 12px;
      }}
      .draft {{
        padding: 14px;
        border-radius: 18px;
        background: rgba(255, 122, 61, 0.08);
        border: 1px solid rgba(255, 122, 61, 0.18);
      }}
      .hidden {{ display: none !important; }}
      code, pre {{
        font-family: "SFMono-Regular", "Menlo", monospace;
      }}
      pre {{
        margin: 0;
        padding: 12px;
        border-radius: 16px;
        background: rgba(0,0,0,0.24);
        overflow: auto;
      }}
      @media (max-width: 980px) {{
        .app {{ grid-template-columns: 1fr; }}
        .sidebar {{
          height: auto;
          position: static;
          border-right: 0;
          border-bottom: 1px solid var(--line);
        }}
        .detail-layout,
        .grid.two,
        .grid.three {{
          grid-template-columns: 1fr;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="app">
      <aside class="sidebar">
        <a class="brand" href="/albums" style="display:block; text-decoration:none;">Album<br>Ranker<small>Local Library</small></a>
        <nav class="nav">{nav_markup}</nav>
        <div class="sidebar-foot">
          Active model: <strong>{_escape(str(page_state["settings"]["active_model"]))}</strong><br>
          Host: {_escape(str(page_state["settings"]["host"]))}:{_escape(str(page_state["settings"]["port"]))}
          <div class="sidebar-status">
            AI: <strong>{_escape(str(page_state["settings"]["ai_status"]).replace("_", " "))}</strong>
            {f"<br>{_escape(str(page_state['settings'].get('ai_status_detail') or ''))}" if page_state["settings"].get("ai_status_detail") else ""}
          </div>
        </div>
      </aside>
      <main class="content">
        {body}
      </main>
    </div>
    <script>
      const pageState = {_json(page_state)};
      function escapeHtml(value) {{
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      }}
      function formatDuration(seconds) {{
        if (seconds === null || seconds === undefined || seconds === "") return "";
        const total = Number(seconds);
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;
        if (hours > 0) return `${{hours}}:${{String(minutes).padStart(2, "0")}}:${{String(secs).padStart(2, "0")}}`;
        return `${{minutes}}:${{String(secs).padStart(2, "0")}}`;
      }}
      function parseDuration(raw) {{
        const value = String(raw ?? "").trim();
        if (!value) return null;
        const parts = value.split(":").map((part) => part.trim());
        if (!parts.every((part) => /^\\d+$/.test(part))) throw new Error("Duration must use m:ss or h:mm:ss");
        if (parts.length === 2) {{
          const minutes = Number(parts[0]);
          const seconds = Number(parts[1]);
          if (seconds >= 60) throw new Error("Seconds must be below 60");
          return minutes * 60 + seconds;
        }}
        if (parts.length === 3) {{
          const hours = Number(parts[0]);
          const minutes = Number(parts[1]);
          const seconds = Number(parts[2]);
          if (minutes >= 60 || seconds >= 60) throw new Error("Minutes and seconds must be below 60");
          return hours * 3600 + minutes * 60 + seconds;
        }}
        throw new Error("Duration must use m:ss or h:mm:ss");
      }}
      function parseTracklist(text) {{
        return String(text ?? "")
          .split("\\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .map((line, index) => {{
            const parts = line.split("|").map((part) => part.trim());
            if (parts.length < 2) throw new Error("Track lines must use number|title|duration");
            const trackNumber = Number(parts[0].replace(".", ""));
            if (!trackNumber) throw new Error("Each track needs a numeric position");
            return {{
              track_number: trackNumber,
              title: parts[1],
              duration_seconds: parts[2] ? parseDuration(parts[2]) : null,
              position: index + 1,
            }};
          }});
      }}
      async function fetchJson(url, options = {{}}) {{
        const response = await fetch(url, {{
          headers: {{
            "Content-Type": "application/json",
            ...(options.headers || {{}})
          }},
          ...options
        }});
        if (!response.ok) {{
          const payload = await response.text();
          throw new Error(payload || `Request failed: ${{response.status}}`);
        }}
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) return null;
        return response.json();
      }}
      document.querySelectorAll("[data-toggle-clamp]").forEach((button) => {{
        const target = document.getElementById(button.dataset.toggleClamp);
        if (!target) return;
        const isOverflowing = target.scrollHeight > target.clientHeight + 2;
        if (!isOverflowing) {{
          button.classList.add("hidden");
          return;
        }}
        button.addEventListener("click", () => {{
          target.classList.toggle("expanded");
          button.textContent = target.classList.contains("expanded") ? "LESS" : "MORE";
        }});
      }});
    </script>
  </body>
</html>"""


def _artist_markup(artist: ArtistWithAlbumsRecord) -> str:
    return f"""
      <article class="artist-card">
        <div class="row">
          <div>
            <h3><a href="/artists/{artist.id}" style="text-decoration:none;">{_escape(artist.name)}</a></h3>
          </div>
          <div class="row" style="justify-content:flex-end; flex:0 0 auto;">
            <button type="button" class="secondary edit-artist" data-artist='{_json(artist.model_dump())}'>Edit</button>
            <button type="button" class="danger delete-artist" data-artist-id="{artist.id}" data-artist-name="{_escape(artist.name)}">Delete</button>
          </div>
        </div>
      </article>
    """


def _album_card_markup(album: AlbumCardRecord) -> str:
    artist_line = " • ".join(part for part in [album.artist_name, str(album.release_year or "")] if part).strip()
    genre_line = album.genre or ""
    rating_markup = _rating_markup(album.rating)
    return f"""
      <a class="album-card" href="/albums/{album.id}" data-genre="{_escape(album.genre)}" data-year="{_escape(str(album.release_year or ''))}" data-artist="{_escape(album.artist_name)}">
        <div class="cover"><img src="{_cover_src(album.cover_image_path)}" alt="{_escape(album.title)} cover"></div>
        <div class="album-title">{_escape(album.title)}</div>
        <div class="album-subtitle">{_escape(artist_line)}</div>
        <div class="album-subtitle">{_escape(genre_line)}</div>
        {rating_markup}
      </a>
    """


def _list_markup(record: AlbumListRecord) -> str:
    items = "".join(
        f"""
        <div class="rank-item" data-item-id="{item.id}">
          <div><strong>{item.rank_position}.</strong></div>
          <a class="rank-cover" href="/albums/{item.album.id}"><img src="{_cover_src(item.album.cover_image_path)}" alt="{_escape(item.album.title)} cover"></a>
          <div>
            <a href="/albums/{item.album.id}" style="text-decoration:none;"><strong>{_escape(item.album.title)}</strong></a>
            <div class="muted">{_escape(item.album.artist_name)} { _escape(str(item.album.release_year or '')) }</div>
          </div>
          <div class="mini-actions">
            <button type="button" class="secondary move-up">Up</button>
            <button type="button" class="secondary move-down">Down</button>
            <button type="button" class="danger remove-item">-</button>
          </div>
        </div>
        """
        for item in record.items
    ) or '<div class="rank-item"><div></div><div></div><div class="muted">No albums in this list yet.</div><div></div></div>'
    return f"""
      <section class="list-block" data-list-id="{record.id}">
        <div class="list-head" data-toggle="list-body-{record.id}">
          <div>
            <h3 style="margin:0;"><a href="/lists/{record.id}" style="text-decoration:none;" onclick="event.stopPropagation();">{_escape(record.name)}</a></h3>
            <div class="muted" style="font-size:12px; margin-top:2px;">{_escape(record.description)} {_escape(record.genre_filter_hint)} {_escape(str(record.year or ''))}</div>
          </div>
          <button type="button" class="secondary list-toggle-btn" style="flex:0 0 auto;">&#9660;</button>
        </div>
        <div id="list-body-{record.id}" class="hidden">
          <div class="rank-list">{items}</div>
          <div style="padding:14px 18px; border-top:1px solid var(--line);">
            <button type="button" class="save-order">Save</button>
            <button type="button" class="danger delete-list" style="margin-left:8px;">Delete List</button>
          </div>
        </div>
      </section>
    """


def render_artists_page(
    settings: SettingsRecord,
    artists: list[ArtistWithAlbumsRecord],
    imports: list[ImportDraftRecord],
) -> str:
    artists_markup = "".join(_artist_markup(artist) for artist in artists) or '<p class="muted">No artists yet.</p>'
    has_artists = bool(artists)
    body = f"""
      <section class="hero">
        <div class="eyebrow">Artists</div>
        <h1>Build a library around artists, not just files.</h1>
        <p>Keep the band description, source link, and album catalog together. Import when it helps, edit everything when it does not.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Artist Tools</div>
          {('<button type="button" id="artistToolsToggle" class="secondary" title="Toggle artist tools">Show Tools</button>' if has_artists else '')}
        </div>
      </section>
      <div id="artistToolsPanel" class="grid two {('hidden' if has_artists else '')}">
        <section class="panel">
          <div class="panel-title">Artist Import</div>
          <form id="artistImportForm">
            <div class="form-field">
              <label class="form-label" for="artistImportSourceUrl">Source URL</label>
              <input id="artistImportSourceUrl" name="source_url" placeholder="Source URL" required>
            </div>
            <div class="row">
              <button type="submit">Populate With AI</button>
              <span class="status" id="artistImportStatus"></span>
            </div>
          </form>
          <div id="artistImportReview" class="draft hidden" style="margin-top:14px;">
            <form id="artistConfirmForm">
              <input type="hidden" name="draft_id">
              <div class="form-field">
                <label class="form-label" for="artistConfirmName">Artist Name</label>
                <input id="artistConfirmName" name="name" placeholder="Artist name" required>
              </div>
              <div class="form-field">
                <label class="form-label" for="artistConfirmDescription">Description</label>
                <textarea id="artistConfirmDescription" name="description" placeholder="Description"></textarea>
              </div>
              <div class="form-field">
                <label class="form-label" for="artistConfirmDescriptionSourceUrl">Description Source URL</label>
                <input id="artistConfirmDescriptionSourceUrl" name="description_source_url" placeholder="Description source URL">
              </div>
              <div class="form-field">
                <label class="form-label" for="artistConfirmDescriptionSourceLabel">Description Source Label</label>
                <input id="artistConfirmDescriptionSourceLabel" name="description_source_label" placeholder="Description source label">
              </div>
              <div class="form-field">
                <label class="form-label" for="artistConfirmPageUrl">Artist Page URL</label>
                <input id="artistConfirmPageUrl" name="external_url" placeholder="Official site, Wikipedia, or main reference page">
              </div>
              <div class="row">
                <button type="submit">Confirm Import</button>
                <button type="button" class="secondary" id="artistImportReset">Clear</button>
              </div>
            </form>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">Manual Artist</div>
          <form id="artistForm">
            <input type="hidden" name="artist_id">
            <input type="hidden" name="description_source_url">
            <input type="hidden" name="description_source_label">
            <div class="form-field">
              <label class="form-label" for="artistFormName">Artist Name</label>
              <input id="artistFormName" name="name" placeholder="Artist name" required>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistFormDescription">Description</label>
              <textarea id="artistFormDescription" name="description" placeholder="Description"></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistFormPageUrl">Artist Page URL</label>
              <input id="artistFormPageUrl" name="external_url" placeholder="Official site, Wikipedia, or main reference page">
            </div>
            <div class="row">
              <button type="submit">Save Artist</button>
              <button type="button" class="secondary" id="artistFormReset">New</button>
              <span class="status" id="artistFormStatus"></span>
            </div>
          </form>
        </section>
      </div>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Library Artists</div>
        <div>{artists_markup}</div>
      </section>
      <script>
        const artistForm = document.getElementById("artistForm");
        const artistToolsPanel = document.getElementById("artistToolsPanel");
        const artistImportForm = document.getElementById("artistImportForm");
        const artistImportReview = document.getElementById("artistImportReview");
        const artistConfirmForm = document.getElementById("artistConfirmForm");
        const artistFormStatus = document.getElementById("artistFormStatus");
        const artistImportStatus = document.getElementById("artistImportStatus");
        const artistToolsToggle = document.getElementById("artistToolsToggle");
        function syncArtistToolsToggle() {{
          if (!artistToolsToggle) return;
          artistToolsToggle.textContent = artistToolsPanel.classList.contains("hidden") ? "Show Tools" : "Hide Tools";
        }}
        artistToolsToggle?.addEventListener("click", () => {{
          artistToolsPanel.classList.toggle("hidden");
          syncArtistToolsToggle();
        }});
        function fillArtistForm(data) {{
          artistToolsPanel.classList.remove("hidden");
          syncArtistToolsToggle();
          artistForm.artist_id.value = data.id || "";
          artistForm.name.value = data.name || data.artist_name || "";
          artistForm.description.value = data.description || "";
          artistForm.description_source_url.value = data.description_source_url || "";
          artistForm.description_source_label.value = data.description_source_label || "";
          artistForm.external_url.value = data.external_url || "";
        }}
        function fillArtistImportDraft(draft) {{
          artistToolsPanel.classList.remove("hidden");
          syncArtistToolsToggle();
          artistImportReview.classList.remove("hidden");
          artistConfirmForm.draft_id.value = draft.id;
          artistConfirmForm.name.value = draft.draft_payload.artist_name || "";
          artistConfirmForm.description.value = draft.draft_payload.description || "";
          artistConfirmForm.description_source_url.value = draft.draft_payload.description_source_url || draft.chosen_source_url || "";
          artistConfirmForm.description_source_label.value = draft.draft_payload.description_source_label || "";
          artistConfirmForm.external_url.value = draft.draft_payload.external_url || "";
        }}
        document.querySelectorAll(".edit-artist").forEach((button) => {{
          button.addEventListener("click", () => fillArtistForm(JSON.parse(button.dataset.artist)));
        }});
        document.querySelectorAll(".delete-artist").forEach((button) => {{
          button.addEventListener("click", async () => {{
            const artistName = button.dataset.artistName || "this artist";
            if (!window.confirm(`Delete ${{artistName}}? Albums by this artist will also be removed.`)) return;
            try {{
              await fetchJson(`/api/artists/${{button.dataset.artistId}}`, {{ method: "DELETE" }});
              window.location.reload();
            }} catch (error) {{
              artistFormStatus.textContent = error.message;
            }}
          }});
        }});
        document.getElementById("artistFormReset").addEventListener("click", () => {{
          artistForm.reset();
          artistForm.artist_id.value = "";
          artistFormStatus.textContent = "";
        }});
        document.getElementById("artistImportReset").addEventListener("click", () => {{
          artistImportReview.classList.add("hidden");
          artistConfirmForm.reset();
          artistImportStatus.textContent = "";
        }});
        artistForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          artistFormStatus.textContent = "Saving...";
          const payload = {{
            name: artistForm.name.value.trim(),
            description: artistForm.description.value.trim() || null,
            description_source_url: artistForm.description_source_url.value.trim() || null,
            description_source_label: artistForm.description_source_label.value.trim() || null,
            external_url: artistForm.external_url.value.trim() || null,
          }};
          const artistId = artistForm.artist_id.value.trim();
          await fetchJson(artistId ? `/api/artists/${{artistId}}` : "/api/artists", {{
            method: artistId ? "PUT" : "POST",
            body: JSON.stringify(payload),
          }});
          window.location.reload();
        }});
        artistImportForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          artistImportStatus.textContent = "Creating draft...";
          const response = await fetchJson("/api/import/artist", {{
            method: "POST",
            body: JSON.stringify({{
              artist_name: "",
              source_url: artistImportForm.source_url.value.trim() || null,
            }}),
          }});
          fillArtistImportDraft(response.draft);
          artistImportStatus.textContent = "Draft ready for review.";
        }});
        artistConfirmForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          artistImportStatus.textContent = "Saving import...";
          await fetchJson(`/api/import/${{artistConfirmForm.draft_id.value}}/confirm`, {{
            method: "POST",
            body: JSON.stringify({{
              target_type: "artist",
              chosen_source_url: artistConfirmForm.description_source_url.value.trim() || null,
              payload: {{
                name: artistConfirmForm.name.value.trim(),
                description: artistConfirmForm.description.value.trim() || null,
                description_source_url: artistConfirmForm.description_source_url.value.trim() || null,
                description_source_label: artistConfirmForm.description_source_label.value.trim() || null,
                external_url: artistConfirmForm.external_url.value.trim() || null,
              }},
            }}),
          }});
          window.location.reload();
        }});
        syncArtistToolsToggle();
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Artists | Album Ranker", "artists", body, page_state=state)


def render_artist_detail_page(
    settings: SettingsRecord,
    artist: ArtistWithAlbumsRecord,
    imports: list[ImportDraftRecord],
) -> str:
    albums_markup = "".join(
        _album_card_markup(album) for album in artist.albums
    ) or '<p class="muted">No albums added yet.</p>'
    source_link = (
        f'<a class="tag" href="{_escape(artist.description_source_url)}" target="_blank" rel="noreferrer">Open Source</a>'
        if artist.description_source_url
        else ""
    )
    clamp_id = f"artist-detail-description-{artist.id}"
    body = f"""
      <section class="hero">
        <div class="eyebrow">Artist</div>
        <h1>{_escape(artist.name)}</h1>
        <p>Open the artist library view, import albums in artist context, and keep the catalog grouped under the right record.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Artist Overview</div>
          <div class="row" style="justify-content:flex-end; flex:0 0 auto;">
            {source_link}
            <a class="secondary" href="/artists" style="display:inline-flex; align-items:center; text-decoration:none; border-radius:999px; padding:11px 16px; background:rgba(255,255,255,0.08); color:var(--ink);">Back To Artists</a>
          </div>
        </div>
        <div id="{clamp_id}" class="clamp muted">{_escape(artist.description or 'No description yet.')}</div>
        <button type="button" class="toggle-link" data-toggle-clamp="{clamp_id}">MORE</button>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Album Import</div>
          <button type="button" id="artistAlbumToolsToggle" class="secondary" title="Toggle album import">Show Import</button>
        </div>
        <div id="artistAlbumToolsPanel" class="hidden">
        <form id="artistAlbumImportForm">
          <input type="hidden" name="artist_name" value="{_escape(artist.name)}">
          <div class="form-field">
            <label class="form-label" for="artistAlbumImportSourceUrl">Source URL</label>
            <input id="artistAlbumImportSourceUrl" name="source_url" placeholder="Source URL" required>
          </div>
          <div class="row">
            <button type="submit">Populate With AI</button>
            <span class="status" id="artistAlbumImportStatus"></span>
          </div>
        </form>
          <div id="artistAlbumImportReview" class="draft hidden" style="margin-top:14px;">
          <form id="artistAlbumConfirmForm">
            <input type="hidden" name="draft_id">
            <input type="hidden" name="artist_name" value="{_escape(artist.name)}">
            <input type="hidden" name="artist_description" value="{_escape(artist.description)}">
            <input type="hidden" name="artist_description_source_url" value="{_escape(artist.description_source_url)}">
            <input type="hidden" name="artist_description_source_label" value="{_escape(artist.description_source_label)}">
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmArtistName">Artist</label>
              <input id="artistAlbumConfirmArtistName" value="{_escape(artist.name)}" disabled>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmTitle">Album</label>
              <input id="artistAlbumConfirmTitle" name="title" placeholder="Album" required>
            </div>
            <div class="row">
              <div class="form-field">
                <label class="form-label" for="artistAlbumConfirmYear">Year</label>
                <input id="artistAlbumConfirmYear" name="release_year" placeholder="Year">
              </div>
              <div class="form-field">
                <label class="form-label" for="artistAlbumConfirmGenre">Genre</label>
                <input id="artistAlbumConfirmGenre" name="genre" placeholder="Genre">
              </div>
              <div class="form-field">
                <label class="form-label" for="artistAlbumConfirmDuration">Length</label>
                <input id="artistAlbumConfirmDuration" name="duration" placeholder="Length e.g. 42:18">
              </div>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmCoverUrl">Cover Source URL</label>
              <input id="artistAlbumConfirmCoverUrl" name="cover_source_url" placeholder="Cover source URL">
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmExternalUrl">Album External URL</label>
              <input id="artistAlbumConfirmExternalUrl" name="album_external_url" placeholder="Album external URL">
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmNotes">Album Description</label>
              <textarea id="artistAlbumConfirmNotes" name="notes" placeholder="Album description"></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmTracklist">Tracklist</label>
              <textarea id="artistAlbumConfirmTracklist" name="tracklist_text" placeholder="Track lines: 1|Track Name|2:46"></textarea>
            </div>
            <div class="row">
              <button type="submit">Confirm Import</button>
              <button type="button" class="secondary" id="artistAlbumImportReset">Clear</button>
            </div>
          </form>
        </div>
        </div>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Albums</div>
        <div class="album-grid">{albums_markup}</div>
      </section>
      <script>
        const artistAlbumToolsPanel = document.getElementById("artistAlbumToolsPanel");
        const artistAlbumToolsToggle = document.getElementById("artistAlbumToolsToggle");
        const artistAlbumImportForm = document.getElementById("artistAlbumImportForm");
        const artistAlbumImportReview = document.getElementById("artistAlbumImportReview");
        const artistAlbumConfirmForm = document.getElementById("artistAlbumConfirmForm");
        const artistAlbumImportStatus = document.getElementById("artistAlbumImportStatus");
        function syncArtistAlbumToolsToggle() {{
          artistAlbumToolsToggle.textContent = artistAlbumToolsPanel.classList.contains("hidden") ? "Show Import" : "Hide Import";
        }}
        artistAlbumToolsToggle.addEventListener("click", () => {{
          artistAlbumToolsPanel.classList.toggle("hidden");
          syncArtistAlbumToolsToggle();
        }});
        function artistAlbumPayload(form) {{
          return {{
            artist_name: form.artist_name.value.trim(),
            artist_description: form.artist_description.value.trim() || null,
            artist_description_source_url: form.artist_description_source_url.value.trim() || null,
            artist_description_source_label: form.artist_description_source_label.value.trim() || null,
            album_external_url: form.album_external_url.value.trim() || null,
            title: form.title.value.trim(),
            release_year: form.release_year.value.trim() ? Number(form.release_year.value.trim()) : null,
            genre: form.genre.value.trim() || null,
            rating: null,
            duration_seconds: parseDuration(form.duration.value),
            cover_source_url: form.cover_source_url.value.trim() || null,
            cover_image_path: null,
            notes: form.notes.value.trim() || null,
            tracks: parseTracklist(form.tracklist_text.value),
          }};
        }}
        function fillArtistAlbumDraft(draft) {{
          artistAlbumToolsPanel.classList.remove("hidden");
          syncArtistAlbumToolsToggle();
          artistAlbumImportReview.classList.remove("hidden");
          artistAlbumConfirmForm.draft_id.value = draft.id;
          const payload = draft.draft_payload;
          artistAlbumConfirmForm.title.value = payload.album_title || "";
          artistAlbumConfirmForm.release_year.value = payload.release_year || "";
          artistAlbumConfirmForm.genre.value = payload.genre || "";
          artistAlbumConfirmForm.duration.value = formatDuration(payload.duration_seconds);
          artistAlbumConfirmForm.cover_source_url.value = payload.cover_source_url || "";
          artistAlbumConfirmForm.album_external_url.value = payload.album_external_url || "";
          artistAlbumConfirmForm.notes.value = payload.notes || "";
          artistAlbumConfirmForm.tracklist_text.value = (payload.tracks || []).map((track) => `${{track.track_number}}|${{track.title}}|${{formatDuration(track.duration_seconds)}}`).join("\\n");
        }}
        artistAlbumImportForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          artistAlbumImportStatus.textContent = "Creating draft...";
          const form = event.currentTarget;
          const response = await fetchJson("/api/import/album", {{
            method: "POST",
            body: JSON.stringify({{
              artist_name: form.artist_name.value.trim(),
              album_title: null,
              source_url: form.source_url.value.trim() || null,
            }}),
          }});
          fillArtistAlbumDraft(response.draft);
          artistAlbumImportStatus.textContent = "Draft ready for review.";
        }});
        document.getElementById("artistAlbumImportReset").addEventListener("click", () => {{
          artistAlbumImportReview.classList.add("hidden");
          artistAlbumConfirmForm.reset();
          artistAlbumConfirmForm.artist_name.value = "{_escape(artist.name)}";
          artistAlbumConfirmForm.artist_description.value = "{_escape(artist.description)}";
          artistAlbumConfirmForm.artist_description_source_url.value = "{_escape(artist.description_source_url)}";
          artistAlbumConfirmForm.artist_description_source_label.value = "{_escape(artist.description_source_label)}";
          artistAlbumImportStatus.textContent = "";
        }});
        artistAlbumConfirmForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          artistAlbumImportStatus.textContent = "Saving import...";
          await fetchJson(`/api/import/${{artistAlbumConfirmForm.draft_id.value}}/confirm`, {{
            method: "POST",
            body: JSON.stringify({{
              target_type: "album",
              chosen_source_url: artistAlbumConfirmForm.album_external_url.value.trim() || null,
              payload: artistAlbumPayload(artistAlbumConfirmForm),
            }}),
          }});
          window.location.reload();
        }});
        syncArtistAlbumToolsToggle();
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell(f"{artist.name} | Album Ranker", "artists", body, page_state=state)


def render_albums_page(
    settings: SettingsRecord,
    albums: list[AlbumCardRecord],
    artists: list[ArtistWithAlbumsRecord],
    genres: list[GenreRecord],
    imports: list[ImportDraftRecord],
) -> str:
    albums_markup = "".join(_album_card_markup(album) for album in albums) or '<p class="muted">No albums yet.</p>'
    has_albums = bool(albums)
    genre_options = "".join(
        f'<option value="{_escape(genre.name)}">{_escape(genre.name)}</option>'
        for genre in genres
    )
    year_options = "".join(
        f'<option value="{year}">{year}</option>'
        for year in sorted({album.release_year for album in albums if album.release_year}, reverse=True)
    )
    artist_options = "".join(
        f'<option value="{_escape(artist.name)}">{_escape(artist.name)}</option>'
        for artist in artists
    )
    body = f"""
      <section class="hero">
        <div class="eyebrow">Albums</div>
        <h1>See the library as a wall of records.</h1>
        <p>Filter by genre, year, or artist, open any cover into the full album detail view, and add manual entries from here. AI album import now lives on the Artists page so the import stays tied to the artist you picked.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Album Tools</div>
          {('<button type="button" id="albumToolsToggle" class="secondary" title="Toggle album tools">Show Tools</button>' if has_albums else '')}
        </div>
      </section>
      <div id="albumToolsPanel" class="grid {('hidden' if has_albums else '')}">
        <section class="panel">
          <div class="panel-title">Manual Album</div>
          <form id="albumForm">
            <input name="artist_name" list="artistNames" placeholder="Artist name" required>
            <datalist id="artistNames">{artist_options}</datalist>
            <input name="title" placeholder="Album name" required>
            <div class="row">
              <input name="release_year" placeholder="Year">
              <input name="genre" placeholder="Genre">
              <input name="rating" type="number" min="1" max="10" placeholder="Rating 1-10">
              <input name="duration" placeholder="Length e.g. 42:18">
            </div>
            <input name="album_external_url" placeholder="Album external URL">
            <input name="cover_source_url" placeholder="Optional cover URL">
            <textarea name="artist_description" placeholder="Artist description"></textarea>
            <textarea name="notes" placeholder="Notes"></textarea>
            <textarea name="tracklist_text" placeholder="Track lines: 1|Track Name|2:46"></textarea>
            <div class="row">
              <button type="submit">Save Album</button>
              <span class="status" id="albumFormStatus"></span>
            </div>
          </form>
        </section>
      </div>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Filters</div>
        <div class="filters">
          <select id="genreFilter"><option value="">Genre</option>{genre_options}</select>
          <select id="yearFilter"><option value="">Year</option>{year_options}</select>
          <select id="artistFilter"><option value="">Artist</option>{artist_options}</select>
        </div>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Album Library</div>
        <div id="albumGrid" class="album-grid">{albums_markup}</div>
      </section>
      <script>
        const albumToolsPanel = document.getElementById("albumToolsPanel");
        const albumToolsToggle = document.getElementById("albumToolsToggle");
        function syncAlbumToolsToggle() {{
          if (!albumToolsToggle) return;
          albumToolsToggle.textContent = albumToolsPanel.classList.contains("hidden") ? "Show Tools" : "Hide Tools";
        }}
        albumToolsToggle?.addEventListener("click", () => {{
          albumToolsPanel.classList.toggle("hidden");
          if (!albumToolsPanel.classList.contains("hidden")) {{
            albumToolsPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
          }}
          syncAlbumToolsToggle();
        }});
        function albumPayloadFromForm(form) {{
          return {{
            artist_name: form.artist_name.value.trim(),
            artist_description: form.artist_description.value.trim() || null,
            artist_description_source_url: (form.artist_description_source_url?.value || "").trim() || null,
            artist_description_source_label: (form.artist_description_source_label?.value || "").trim() || null,
            album_external_url: (form.album_external_url?.value || "").trim() || null,
            title: form.title.value.trim(),
            release_year: form.release_year.value.trim() ? Number(form.release_year.value.trim()) : null,
            genre: form.genre.value.trim() || null,
            rating: form.rating.value.trim() ? Number(form.rating.value.trim()) : null,
            duration_seconds: parseDuration(form.duration.value),
            cover_source_url: form.cover_source_url.value.trim() || null,
            cover_image_path: null,
            notes: form.notes.value.trim() || null,
            tracks: parseTracklist(form.tracklist_text.value),
          }};
        }}
        document.getElementById("albumForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const status = document.getElementById("albumFormStatus");
          try {{
            status.textContent = "Saving...";
            await fetchJson("/api/albums", {{
              method: "POST",
              body: JSON.stringify(albumPayloadFromForm(event.currentTarget)),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message;
          }}
        }});
        document.querySelectorAll("#albumGrid .album-card").forEach((card) => {{
          const applyFilters = () => {{
            const genre = document.getElementById("genreFilter").value;
            const year = document.getElementById("yearFilter").value;
            const artist = document.getElementById("artistFilter").value;
            card.classList.toggle("hidden",
              (genre && !card.dataset.genre.toLowerCase().includes(genre.toLowerCase())) ||
              (year && card.dataset.year !== year) ||
              (artist && card.dataset.artist !== artist)
            );
          }};
          document.getElementById("genreFilter").addEventListener("change", applyFilters);
          document.getElementById("yearFilter").addEventListener("change", applyFilters);
          document.getElementById("artistFilter").addEventListener("change", applyFilters);
        }});
        syncAlbumToolsToggle();
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Albums | Album Ranker", "albums", body, page_state=state)


def render_album_detail_page(settings: SettingsRecord, album: AlbumDetailRecord) -> str:
    track_rows = "".join(
        f'<div class="track-row"><div class="track-num" style="display:flex;justify-content:flex-end;align-items:center;">{track.track_number}.</div><div>{_escape(track.title)}</div><div class="muted">{_escape(seconds_to_display(track.duration_seconds))}</div></div>'
        for track in album.tracks
    ) or '<p class="muted">No tracklist yet.</p>'
    description_title = "Album Description" if album.notes else "Artist Description"
    raw_description_text = album.notes or album.artist_description or "No description yet."
    description_text = _display_multiline_text(raw_description_text)
    description_source_url = album.album_external_url or album.artist_description_source_url
    description_source_label = "Open Source" if description_source_url else ""
    star_buttons = "".join(
        f'<button type="button" class="star-btn{" on" if (album.rating or 0) >= i else ""}" data-value="{i}" aria-label="Rate {i} out of 10">&#9733;</button>'
        for i in range(1, 11)
    )
    star_initial_label = f"{album.rating}/10" if album.rating else "Rate this album"
    body = f"""
      <section class="hero">
        <div class="eyebrow">Album Details</div>
        <h1><a href="/artists/{album.artist_id}" style="text-decoration:none;">{_escape(album.artist_name)}</a></h1>
        <p>{_escape(album.title)} {_escape(str(album.release_year or ''))}</p>
      </section>
      <section class="detail-layout">
        <div>
          <label class="cover" for="coverFileInput" title="Click to upload a cover image">
            <img id="coverImg" src="{_cover_src(album.cover_image_path)}" alt="{_escape(album.title)} cover">
            <div class="cover-upload-overlay">&#128247; Upload cover</div>
          </label>
          <input type="file" id="coverFileInput" accept="image/jpeg,image/png,image/webp" style="display:none;">
          <div class="star-widget">
            <div class="star-widget-row" id="starRatingRow" data-album-id="{album.id}" data-current="{album.rating or 0}">{star_buttons}</div>
            <div class="star-widget-label" id="starWidgetLabel">{_escape(star_initial_label)}</div>
            <div class="star-widget-status" id="starWidgetStatus"></div>
          </div>
          {('<div class="row" style="margin-top:10px;gap:8px;justify-content:center;">' + (f'<a class="tag" href="{_escape(album.album_external_url)}" target="_blank" rel="noopener noreferrer">Source</a>' if album.album_external_url else '') + (f'<a class="tag" href="{_escape(album.album_stream_url)}" target="_blank" rel="noopener noreferrer">&#9654; Play</a>' if album.album_stream_url else '') + '</div>') if album.album_external_url or album.album_stream_url else ''}
          <div class="meta-stack">
            <div class="detail-head">
              <div class="meta-item" style="flex:1;">
                <span class="meta-item-label">Edit</span>
                <strong>Album metadata</strong>
              </div>
              <button type="button" id="albumEditToggle" class="secondary icon-button" title="Show album editor">✎</button>
            </div>
            <div class="meta-item">
              <span class="meta-item-label">Length</span>
              {_escape(seconds_to_display(album.duration_seconds) or 'Unknown length')}
            </div>
            <div class="meta-item">
              <span class="meta-item-label">Genre</span>
              {_escape(album.genre or 'Unknown genre')}
            </div>
          </div>
        </div>
        <div class="grid" style="align-self:start; margin-top:0;">
          <section class="panel">
            <div class="panel-title">Tracklist</div>
            <div class="tracklist">{track_rows}</div>
          </section>
          <section class="panel hidden" id="albumEditPanel">
            <div class="detail-head">
              <div class="panel-title" style="margin-bottom:0;">Edit Album</div>
              <button type="button" id="albumDeleteButton" class="danger">Delete Album</button>
            </div>
            <form id="albumDetailForm">
              <input type="hidden" name="cover_image_path" id="coverImagePathField" value="{_escape(album.cover_image_path or '')}">
              <input type="hidden" name="cover_source_url" value="{_escape(album.cover_source_url)}">
              <input type="hidden" name="artist_description_source_url" value="{_escape(album.artist_description_source_url)}">
              <input type="hidden" name="artist_description_source_label" value="{_escape(album.artist_description_source_label)}">
              <input type="hidden" name="album_external_url" value="{_escape(album.album_external_url)}">
              <div class="form-field">
                <label class="form-label" for="albumEditArtistName">Artist</label>
                <input id="albumEditArtistName" name="artist_name" value="{_escape(album.artist_name)}" required>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditTitle">Album Name</label>
                <input id="albumEditTitle" name="title" value="{_escape(album.title)}" required>
              </div>
              <div class="row">
                <div class="form-field">
                  <label class="form-label" for="albumEditYear">Year</label>
                  <input id="albumEditYear" name="release_year" value="{_escape(str(album.release_year or ''))}" placeholder="Year">
                </div>
                <div class="form-field">
                  <label class="form-label" for="albumEditGenre">Genre</label>
                  <input id="albumEditGenre" name="genre" value="{_escape(album.genre)}" placeholder="Genre">
                </div>
                <div class="form-field">
                  <label class="form-label" for="albumEditDuration">Length</label>
                  <input id="albumEditDuration" name="duration" value="{_escape(seconds_to_display(album.duration_seconds))}" placeholder="Length">
                </div>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditStreamUrl">Stream URL</label>
                <input id="albumEditStreamUrl" name="album_stream_url" value="{_escape(album.album_stream_url)}" placeholder="https://...">
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditDescription">Artist Description</label>
                <textarea id="albumEditDescription" name="artist_description" placeholder="Artist description">{_escape(album.artist_description)}</textarea>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditNotes">Notes</label>
                <textarea id="albumEditNotes" name="notes" placeholder="Notes">{_escape(album.notes)}</textarea>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditTracklist">Tracklist</label>
                <textarea id="albumEditTracklist" name="tracklist_text" placeholder="Track lines: 1|Track Name|2:46">{_escape(chr(10).join(f"{track.track_number}|{track.title}|{seconds_to_display(track.duration_seconds)}" for track in album.tracks))}</textarea>
              </div>
              <div class="row">
                <button type="submit">Save Changes</button>
                <span class="status" id="albumDetailStatus"></span>
              </div>
            </form>
          </section>
        </div>
      </section>
      <section class="panel" style="margin-top:16px; max-width:884px;">
        <div class="panel-title">{_escape(description_title)}</div>
        <div id="albumArtistDescription" class="clamp">{description_text}</div>
        <div class="row" style="margin-top:8px;">
          <button type="button" class="toggle-link" data-toggle-clamp="albumArtistDescription" style="flex:0 0 auto;">MORE</button>
          {f'<a class="tag" href="{_escape(description_source_url)}" target="_blank" rel="noreferrer" style="flex:0 0 auto;">{_escape(description_source_label)}</a>' if description_source_url else ''}
        </div>
      </section>
      <script>
        (function() {{
          const row = document.getElementById('starRatingRow');
          const stars = row.querySelectorAll('.star-btn');
          const label = document.getElementById('starWidgetLabel');
          const status = document.getElementById('starWidgetStatus');
          let current = Number(row.dataset.current) || 0;
          function highlight(n) {{
            stars.forEach((s, i) => s.classList.toggle('on', i < n));
            label.textContent = n ? n + '/10' : 'Rate this album';
          }}
          highlight(current);
          stars.forEach((star, idx) => {{
            star.addEventListener('mouseenter', () => highlight(idx + 1));
            star.addEventListener('mouseleave', () => highlight(current));
            star.addEventListener('click', async () => {{
              const newVal = (idx + 1 === current) ? null : idx + 1;
              try {{
                status.textContent = 'Saving\u2026';
                await fetchJson('/api/albums/{album.id}/rating', {{
                  method: 'PATCH',
                  body: JSON.stringify({{ rating: newVal }}),
                }});
                current = newVal || 0;
                row.dataset.current = current;
                highlight(current);
                status.textContent = '\u2713 Saved';
                setTimeout(() => {{ status.textContent = ''; }}, 1500);
              }} catch (err) {{
                status.textContent = err.message;
              }}
            }});
          }});
        }})();
        (function() {{
          const coverFileInput = document.getElementById("coverFileInput");
          const coverImg = document.getElementById("coverImg");
          coverFileInput.addEventListener("change", async () => {{
            const file = coverFileInput.files[0];
            if (!file) return;
            const fd = new FormData();
            fd.append("file", file);
            try {{
              const resp = await fetch("/api/albums/{album.id}/cover", {{ method: "POST", body: fd }});
              if (!resp.ok) {{ const t = await resp.text(); console.error("Cover upload failed:", t); return; }}
              const data = await resp.json();
              if (data.cover_image_path) {{
                const name = data.cover_image_path.split("/").pop();
                coverImg.src = "/library-data/covers/" + name + "?t=" + Date.now();
                const pathField = document.getElementById("coverImagePathField");
                if (pathField) pathField.value = data.cover_image_path;
              }}
            }} catch (e) {{ console.error("Cover upload error:", e); }}
          }});
        }})();
        const albumEditToggle = document.getElementById("albumEditToggle");
        const albumEditPanel = document.getElementById("albumEditPanel");
        const albumDeleteButton = document.getElementById("albumDeleteButton");
        function syncAlbumEditToggle() {{
          const isOpen = !albumEditPanel.classList.contains("hidden");
          albumEditToggle.textContent = isOpen ? "×" : "✎";
          albumEditToggle.title = isOpen ? "Hide album editor" : "Show album editor";
        }}
        albumEditToggle.addEventListener("click", () => {{
          const willOpen = albumEditPanel.classList.contains("hidden");
          albumEditPanel.classList.toggle("hidden");
          syncAlbumEditToggle();
          if (willOpen) {{
            albumEditPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
          }}
        }});
        syncAlbumEditToggle();
        albumDeleteButton.addEventListener("click", async () => {{
          if (!window.confirm(`Delete {_escape(album.artist_name)} - {_escape(album.title)}?`)) return;
          const status = document.getElementById("albumDetailStatus");
          try {{
            status.textContent = "Deleting...";
            await fetchJson("/api/albums/{album.id}", {{ method: "DELETE" }});
            window.location.href = "/albums";
          }} catch (error) {{
            status.textContent = error.message;
          }}
        }});
        document.getElementById("albumDetailForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("albumDetailStatus");
          try {{
            status.textContent = "Saving...";
            await fetchJson("/api/albums/{album.id}", {{
              method: "PUT",
              body: JSON.stringify({{
                artist_name: form.artist_name.value.trim(),
                artist_description: form.artist_description.value.trim() || null,
                artist_description_source_url: form.artist_description_source_url.value.trim() || null,
                artist_description_source_label: form.artist_description_source_label.value.trim() || null,
                album_external_url: form.album_external_url.value.trim() || null,
                album_stream_url: form.album_stream_url.value.trim() || null,
                title: form.title.value.trim(),
                release_year: form.release_year.value.trim() ? Number(form.release_year.value.trim()) : null,
                genre: form.genre.value.trim() || null,
                rating: (function() {{ const v = Number(document.getElementById('starRatingRow').dataset.current); return v || null; }})(),
                duration_seconds: parseDuration(form.duration.value),
                cover_image_path: form.cover_image_path.value.trim() || null,
                cover_source_url: form.cover_source_url.value.trim() || null,
                notes: form.notes.value.trim() || null,
                tracks: parseTracklist(form.tracklist_text.value),
              }}),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message;
          }}
        }});
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": f"/albums/{album.id}"}
    return _shell(f"{album.title} | Album Ranker", "details", body, page_state=state)


def render_lists_page(settings: SettingsRecord, lists: list[AlbumListRecord], albums: list[AlbumCardRecord], genres: list[GenreRecord]) -> str:
    list_markup = "".join(_list_markup(record) for record in lists) or '<p class="muted">No ranking lists yet.</p>'
    has_lists = bool(lists)
    existing_list_names = _json([lst.name for lst in lists])
    unique_years = sorted({a.release_year for a in albums if a.release_year}, reverse=True)
    year_options = "<option value=''>All time</option>" + "".join(
        f"<option value='{y}'>{y}</option>" for y in unique_years
    )
    genre_options = "<option value=''>All genres</option>" + "".join(
        f"<option value='{_escape(g.name)}'>{_escape(g.name)}</option>" for g in sorted(genres, key=lambda g: g.name)
    )
    body = f"""
      <section class="hero">
        <div class="eyebrow">Lists</div>
        <h1>Rank albums into actual tops.</h1>
        <p>Create focused lists, add albums from your library, then drag or button them into the order that actually reflects preference.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Create List</div>
          {('<button type="button" id="listToolsToggle" class="secondary" title="Toggle create list">Show</button>' if has_lists else '')}
        </div>
        <div id="listToolsPanel" class="{('hidden' if has_lists else '')}" style="margin-top:14px;">
          <form id="listForm">
            <input name="name" placeholder="List name" required>
            <textarea name="description" placeholder="Description"></textarea>
            <div class="row">
              <input name="year" placeholder="Year">
              <input name="genre_filter_hint" placeholder="Genre hint">
            </div>
            <div class="row">
              <button type="submit">Create List</button>
              <span class="status" id="listFormStatus"></span>
            </div>
          </form>
        </div>
      </section>
      <section class="panel" style="margin-top:16px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Automatic Lists</div>
          <button type="button" id="autoListToggle" class="secondary">Show</button>
        </div>
        <div id="autoListPanel" class="hidden" style="margin-top:14px;">
          <div style="margin-bottom:12px; color:var(--muted); font-size:13px;">Choose a wizard, configure it, and generate a list automatically.</div>
          <div class="row" style="margin-bottom:16px; align-items:flex-start;">
            <button type="button" class="auto-wizard-tab secondary" data-wizard="best-rated" style="flex:0 0 auto;">&#9733; Best Rated</button>
          </div>
          <div id="wizard-best-rated" class="auto-wizard hidden">
            <div class="panel" style="background:rgba(255,255,255,0.03); border:1px solid var(--line);">
              <div class="panel-title" style="font-size:13px; margin-bottom:12px;">Best Rated Albums</div>
              <div class="row">
                <div class="form-field" style="flex:1;">
                  <label class="form-label">Time period</label>
                  <select id="brYear">{year_options}</select>
                </div>
                <div class="form-field" style="flex:1;">
                  <label class="form-label">Genre</label>
                  <select id="brGenre">{genre_options}</select>
                </div>
                <div class="form-field" style="flex:0 0 100px;">
                  <label class="form-label">How many</label>
                  <input id="brLimit" type="number" min="1" max="500" value="10" style="width:100%;">
                </div>
              </div>
              <div class="form-field" style="margin-top:8px;">
                <label class="form-label">List name</label>
                <input id="brName" type="text" style="width:100%;">
              </div>
              <div class="row" style="margin-top:12px;">
                <button type="button" id="brGenerate" style="flex:0 0 auto;">Generate</button>
                <span class="status" id="brStatus"></span>
              </div>
              <div id="brConflictBox" class="hidden" style="margin-top:12px; padding:12px; border-radius:12px; background:rgba(255,122,61,0.08); border:1px solid rgba(255,122,61,0.3);">
                <div style="font-size:13px; margin-bottom:10px;">A list named <strong id="brConflictName"></strong> already exists. What would you like to do?</div>
                <div class="row">
                  <button type="button" id="brUpdateExisting" style="flex:0 0 auto;">Update existing</button>
                  <button type="button" id="brCreateNew" class="secondary" style="flex:0 0 auto;">Create with new name</button>
                </div>
                <div class="form-field hidden" id="brNewNameField" style="margin-top:10px;">
                  <label class="form-label">New name</label>
                  <input id="brNewName" type="text" style="width:100%;">
                  <button type="button" id="brCreateNewConfirm" style="margin-top:8px; flex:0 0 auto;">Create</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section class="grid" style="margin-top:20px;">{list_markup}</section>
      <script>
        const existingListNames = {existing_list_names};
        const listToolsPanel = document.getElementById("listToolsPanel");
        const listToolsToggle = document.getElementById("listToolsToggle");
        function syncListToolsToggle() {{
          if (!listToolsToggle) return;
          listToolsToggle.textContent = listToolsPanel.classList.contains("hidden") ? "Show" : "Hide";
        }}
        listToolsToggle?.addEventListener("click", () => {{
          listToolsPanel.classList.toggle("hidden");
          syncListToolsToggle();
        }});

        // ── Automatic Lists ──────────────────────────────────────────────────
        const autoListToggle = document.getElementById("autoListToggle");
        const autoListPanel = document.getElementById("autoListPanel");
        autoListToggle.addEventListener("click", () => {{
          autoListPanel.classList.toggle("hidden");
          autoListToggle.textContent = autoListPanel.classList.contains("hidden") ? "Show" : "Hide";
        }});
        document.querySelectorAll(".auto-wizard-tab").forEach((btn) => {{
          btn.addEventListener("click", () => {{
            document.querySelectorAll(".auto-wizard").forEach((w) => w.classList.add("hidden"));
            document.querySelectorAll(".auto-wizard-tab").forEach((b) => b.classList.remove("active"));
            document.getElementById("wizard-" + btn.dataset.wizard).classList.remove("hidden");
            btn.classList.add("active");
          }});
        }});

        // Best Rated wizard ───────────────────────────────────────────────────
        function buildBestRatedName() {{
          const year = document.getElementById("brYear").value;
          const genre = document.getElementById("brGenre").value;
          const limit = document.getElementById("brLimit").value || "10";
          let name = "Best Rated";
          if (genre) name += " " + genre;
          if (year) name += " " + year;
          name += " (Top " + limit + ")";
          return name;
        }}
        function syncBestRatedName() {{
          const nameInput = document.getElementById("brName");
          nameInput.value = buildBestRatedName();
        }}
        ["brYear", "brGenre", "brLimit"].forEach((id) => {{
          document.getElementById(id).addEventListener("change", syncBestRatedName);
          document.getElementById(id).addEventListener("input", syncBestRatedName);
        }});
        syncBestRatedName();

        async function submitBestRated(name, updateExisting) {{
          const status = document.getElementById("brStatus");
          const year = document.getElementById("brYear").value;
          const genre = document.getElementById("brGenre").value;
          const limit = Number(document.getElementById("brLimit").value) || 10;
          try {{
            status.textContent = "Generating\u2026";
            await fetchJson("/api/auto-lists/best-rated", {{
              method: "POST",
              body: JSON.stringify({{
                name,
                limit,
                year: year ? Number(year) : null,
                genre: genre || null,
                update_existing: updateExisting,
              }}),
            }});
            window.location.reload();
          }} catch (err) {{
            if (err.message && err.message.includes("already exists")) {{
              status.textContent = "";
              const conflictBox = document.getElementById("brConflictBox");
              document.getElementById("brConflictName").textContent = name;
              conflictBox.classList.remove("hidden");
            }} else {{
              status.textContent = err.message;
            }}
          }}
        }}

        document.getElementById("brGenerate").addEventListener("click", () => {{
          document.getElementById("brConflictBox").classList.add("hidden");
          document.getElementById("brNewNameField").classList.add("hidden");
          submitBestRated(document.getElementById("brName").value.trim(), false);
        }});
        document.getElementById("brUpdateExisting").addEventListener("click", () => {{
          document.getElementById("brConflictBox").classList.add("hidden");
          submitBestRated(document.getElementById("brName").value.trim(), true);
        }});
        document.getElementById("brCreateNew").addEventListener("click", () => {{
          const newNameField = document.getElementById("brNewNameField");
          document.getElementById("brNewName").value = document.getElementById("brName").value.trim() + " (2)";
          newNameField.classList.remove("hidden");
        }});
        document.getElementById("brCreateNewConfirm").addEventListener("click", () => {{
          const newName = document.getElementById("brNewName").value.trim();
          if (!newName) return;
          document.getElementById("brConflictBox").classList.add("hidden");
          submitBestRated(newName, false);
        }});
        // ─────────────────────────────────────────────────────────────────────

        document.getElementById("listForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          document.getElementById("listFormStatus").textContent = "Saving...";
          await fetchJson("/api/lists", {{
            method: "POST",
            body: JSON.stringify({{
              name: form.name.value.trim(),
              description: form.description.value.trim() || null,
              year: form.year.value.trim() ? Number(form.year.value.trim()) : null,
              genre_filter_hint: form.genre_filter_hint.value.trim() || null,
            }}),
          }});
          window.location.reload();
        }});
        document.querySelectorAll(".list-head[data-toggle]").forEach((head) => {{
          head.addEventListener("click", () => {{
            const body = document.getElementById(head.dataset.toggle);
            if (!body) return;
            body.classList.toggle("hidden");
            const btn = head.querySelector(".list-toggle-btn");
            if (btn) btn.innerHTML = body.classList.contains("hidden") ? "&#9660;" : "&#9650;";
          }});
        }});
        document.querySelectorAll(".list-block").forEach((block) => {{
          const listId = block.dataset.listId;
          const move = (item, direction) => {{
            const sibling = direction === "up" ? item.previousElementSibling : item.nextElementSibling;
            if (!sibling) return;
            if (direction === "up") item.parentNode.insertBefore(item, sibling);
            else item.parentNode.insertBefore(sibling, item);
            [...block.querySelectorAll(".rank-item")].forEach((row, index) => {{
              const counter = row.querySelector("strong");
              if (counter) counter.textContent = `${{index + 1}}.`;
            }});
          }};
          block.querySelectorAll(".move-up").forEach((button) => button.addEventListener("click", () => move(button.closest(".rank-item"), "up")));
          block.querySelectorAll(".move-down").forEach((button) => button.addEventListener("click", () => move(button.closest(".rank-item"), "down")));
          block.querySelector(".save-order")?.addEventListener("click", async () => {{
            const itemIds = [...block.querySelectorAll(".rank-item[data-item-id]")].map((item) => Number(item.dataset.itemId));
            await fetchJson(`/api/lists/${{listId}}/items/reorder`, {{
              method: "POST",
              body: JSON.stringify({{ item_ids: itemIds }}),
            }});
            window.location.reload();
          }});
          block.querySelectorAll(".remove-item").forEach((button) => button.addEventListener("click", async () => {{
            const item = button.closest(".rank-item");
            if (!window.confirm("Remove this album from the list?")) return;
            await fetchJson(`/api/lists/${{listId}}/items/${{item.dataset.itemId}}`, {{
              method: "DELETE",
            }});
            window.location.reload();
          }}));
          block.querySelector(".delete-list")?.addEventListener("click", async () => {{
            if (!window.confirm("Delete this list?")) return;
            try {{
              await fetchJson(`/api/lists/${{listId}}`, {{ method: "DELETE" }});
              window.location.reload();
            }} catch (error) {{
              document.getElementById("listFormStatus").textContent = error.message;
            }}
          }});
        }});
        syncListToolsToggle();
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Lists | Album Ranker", "lists", body, page_state=state)


def render_settings_page(settings: SettingsRecord) -> str:
    options = "".join(
        f'<option value="{_escape(model)}"{" selected" if model == settings.active_model else ""}>{_escape(model)}</option>'
        for model in settings.available_models
    )
    body = f"""
      <section class="hero">
        <div class="eyebrow">Settings</div>
        <h1>Keep AI optional and visible.</h1>
        <p>Choose the active OpenAI model used for draft generation. More settings can be added later without redesigning the page.</p>
      </section>
      <section class="grid two">
        <section class="panel">
          <div class="panel-title">Model</div>
          <form id="settingsForm">
            <select name="active_model">{options}</select>
            <div class="row">
              <button type="submit">Save Settings</button>
              <span class="status" id="settingsStatus"></span>
            </div>
          </form>
        </section>
        <section class="panel">
          <div class="panel-title">Runtime</div>
          <p class="muted">OpenAI key configured: <strong>{'yes' if settings.openai_api_key_configured else 'no'}</strong></p>
          <p class="muted">AI status: <strong>{_escape(settings.ai_status.replace("_", " "))}</strong></p>
          {f'<p class="muted">{_escape(settings.ai_status_detail)}</p>' if settings.ai_status_detail else ''}
          <p class="muted">Server: {_escape(settings.host)}:{settings.port}</p>
          <p class="muted">Default model: {_escape(settings.model)}</p>
        </section>
      </section>
      <script>
        document.getElementById("settingsForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          document.getElementById("settingsStatus").textContent = "Saving...";
          await fetchJson("/api/settings", {{
            method: "PUT",
            body: JSON.stringify({{ active_model: form.active_model.value }}),
          }});
          window.location.reload();
        }});
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Settings | Album Ranker", "settings", body, page_state=state)


def render_genres_page(settings: SettingsRecord, genres: list[GenreRecord]) -> str:
    genres_markup = "".join(
        f"""
        <div class="artist-card">
          <div class="row">
            <div><strong>{_escape(genre.name)}</strong></div>
            <div class="row" style="justify-content:flex-end; flex:0 0 auto;">
              <button type="button" class="secondary edit-genre" data-genre-id="{genre.id}" data-genre-name="{_escape(genre.name)}">Rename</button>
              <button type="button" class="danger delete-genre" data-genre-id="{genre.id}">Delete</button>
            </div>
          </div>
        </div>
        """
        for genre in genres
    ) or '<p class="muted">No genres yet.</p>'
    body = f"""
      <section class="hero">
        <div class="eyebrow">Genres</div>
        <h1>Manage the filter list manually.</h1>
        <p>Add only the genres you want to see in the album filter. Album matching uses substring checks, so a filter like Gothic Metal will still match Industrial / Gothic Metal.</p>
      </section>
      <section class="grid two">
        <section class="panel">
          <div class="panel-title">Add Genre</div>
          <form id="genreForm">
            <input type="hidden" name="genre_id">
            <div class="form-field">
              <label class="form-label" for="genreName">Genre Name</label>
              <input id="genreName" name="name" placeholder="Genre name" required>
            </div>
            <div class="row">
              <button type="submit">Save Genre</button>
              <button type="button" class="secondary" id="genreReset">New</button>
              <span class="status" id="genreStatus"></span>
            </div>
          </form>
        </section>
        <section class="panel">
          <div class="panel-title">Managed Genres</div>
          <div>{genres_markup}</div>
        </section>
      </section>
      <script>
        document.getElementById("genreForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("genreStatus");
          try {{
            status.textContent = "Saving...";
            const genreId = form.genre_id.value.trim();
            await fetchJson(genreId ? `/api/genres/${{genreId}}` : "/api/genres", {{
              method: genreId ? "PUT" : "POST",
              body: JSON.stringify({{ name: form.name.value.trim() }}),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message;
          }}
        }});
        document.getElementById("genreReset").addEventListener("click", () => {{
          const form = document.getElementById("genreForm");
          form.reset();
          form.genre_id.value = "";
          document.getElementById("genreStatus").textContent = "";
        }});
        document.querySelectorAll(".edit-genre").forEach((button) => {{
          button.addEventListener("click", () => {{
            const form = document.getElementById("genreForm");
            form.genre_id.value = button.dataset.genreId;
            form.name.value = button.dataset.genreName || "";
            document.getElementById("genreStatus").textContent = "";
            form.scrollIntoView({{ behavior: "smooth", block: "start" }});
          }});
        }});
        document.querySelectorAll(".delete-genre").forEach((button) => {{
          button.addEventListener("click", async () => {{
            if (!window.confirm("Delete this genre?")) return;
            const status = document.getElementById("genreStatus");
            try {{
              await fetchJson(`/api/genres/${{button.dataset.genreId}}`, {{ method: "DELETE" }});
              window.location.reload();
            }} catch (error) {{
              status.textContent = error.message;
            }}
          }});
        }});
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Genres | Album Ranker", "genres", body, page_state=state)


def render_list_detail_page(settings: SettingsRecord, record: AlbumListRecord, albums: list[AlbumCardRecord]) -> str:
    items_markup = _list_markup(record)
    existing_album_ids = {item.album.id for item in record.items}
    available_albums = [album for album in albums if album.id not in existing_album_ids]
    album_options = "".join(
        f'<option value="{_escape(f"{album.artist_name} - {album.title}")}" data-album-id="{album.id}"></option>'
        for album in available_albums
    )
    body = f"""
      <section class="hero">
        <div class="eyebrow">List</div>
        <h1>{_escape(record.name)}</h1>
        <p>{_escape(record.description or 'Rank albums inside this list and add more entries when needed.')}</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">List Details</div>
        <form id="listDetailForm">
          <div class="form-field">
            <label class="form-label" for="listDetailName">List Name</label>
            <input id="listDetailName" name="name" value="{_escape(record.name)}" required>
          </div>
          <div class="form-field">
            <label class="form-label" for="listDetailDescription">Description</label>
            <textarea id="listDetailDescription" name="description" placeholder="Description">{_escape(record.description)}</textarea>
          </div>
          <div class="row">
            <div class="form-field">
              <label class="form-label" for="listDetailYear">Year</label>
              <input id="listDetailYear" name="year" value="{_escape(str(record.year or ''))}" placeholder="Year">
            </div>
            <div class="form-field">
              <label class="form-label" for="listDetailGenreHint">Genre Hint</label>
              <input id="listDetailGenreHint" name="genre_filter_hint" value="{_escape(record.genre_filter_hint)}" placeholder="Genre hint">
            </div>
          </div>
          <div class="row">
            <button type="submit">Save Details</button>
            <span class="status" id="listDetailStatus"></span>
          </div>
        </form>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Add Album To List</div>
          <a class="secondary" href="/lists" style="display:inline-flex; align-items:center; text-decoration:none; border-radius:999px; padding:11px 16px; background:rgba(255,255,255,0.08); color:var(--ink);">Back To Lists</a>
        </div>
        <form id="listItemForm">
          <div class="form-field">
            <label class="form-label" for="listAlbumPicker">Album</label>
            <input id="listAlbumPicker" name="album_label" list="listAlbumOptions" placeholder="Search and choose album" required>
            <datalist id="listAlbumOptions">{album_options}</datalist>
          </div>
          <input type="hidden" name="album_id">
          <div class="row">
            <button type="submit">Add Album</button>
            <span class="status" id="listItemStatus"></span>
          </div>
        </form>
      </section>
      <section class="grid" style="margin-top:20px;">{items_markup}</section>
      <script>
        document.getElementById("listDetailForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("listDetailStatus");
          try {{
            status.textContent = "Saving...";
            await fetchJson("/api/lists/{record.id}", {{
              method: "PUT",
              body: JSON.stringify({{
                name: form.name.value.trim(),
                description: form.description.value.trim() || null,
                year: form.year.value.trim() ? Number(form.year.value.trim()) : null,
                genre_filter_hint: form.genre_filter_hint.value.trim() || null,
              }}),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message;
          }}
        }});
        const listAlbumPicker = document.getElementById("listAlbumPicker");
        const listAlbumOptions = [...document.querySelectorAll("#listAlbumOptions option")];
        function syncListAlbumId() {{
          const match = listAlbumOptions.find((option) => option.value === listAlbumPicker.value);
          document.querySelector('#listItemForm input[name="album_id"]').value = match?.dataset.albumId || "";
        }}
        listAlbumPicker.addEventListener("input", syncListAlbumId);
        document.getElementById("listItemForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          syncListAlbumId();
          if (!form.album_id.value) {{
            document.getElementById("listItemStatus").textContent = "Choose an album from the list.";
            return;
          }}
          document.getElementById("listItemStatus").textContent = "Adding...";
          await fetchJson("/api/lists/{record.id}/items", {{
            method: "POST",
            body: JSON.stringify({{ album_id: Number(form.album_id.value) }}),
          }});
          window.location.reload();
        }});
        document.querySelectorAll(".list-block").forEach((block) => {{
          const listId = block.dataset.listId;
          const move = (item, direction) => {{
            const sibling = direction === "up" ? item.previousElementSibling : item.nextElementSibling;
            if (!sibling) return;
            if (direction === "up") item.parentNode.insertBefore(item, sibling);
            else item.parentNode.insertBefore(sibling, item);
            [...block.querySelectorAll(".rank-item")].forEach((row, index) => {{
              const counter = row.querySelector("strong");
              if (counter) counter.textContent = `${{index + 1}}.`;
            }});
          }};
          block.querySelectorAll(".move-up").forEach((button) => button.addEventListener("click", () => move(button.closest(".rank-item"), "up")));
          block.querySelectorAll(".move-down").forEach((button) => button.addEventListener("click", () => move(button.closest(".rank-item"), "down")));
          block.querySelector(".save-order")?.addEventListener("click", async () => {{
            const itemIds = [...block.querySelectorAll(".rank-item[data-item-id]")].map((item) => Number(item.dataset.itemId));
            await fetchJson(`/api/lists/${{listId}}/items/reorder`, {{
              method: "POST",
              body: JSON.stringify({{ item_ids: itemIds }}),
            }});
            window.location.reload();
          }});
          block.querySelectorAll(".remove-item").forEach((button) => button.addEventListener("click", async () => {{
            const item = button.closest(".rank-item");
            if (!window.confirm("Remove this album from the list?")) return;
            await fetchJson(`/api/lists/${{listId}}/items/${{item.dataset.itemId}}`, {{
              method: "DELETE",
            }});
            window.location.reload();
          }}));
          block.querySelector(".delete-list")?.addEventListener("click", async () => {{
            if (!window.confirm("Delete this list?")) return;
            try {{
              await fetchJson(`/api/lists/${{listId}}`, {{ method: "DELETE" }});
              window.location.href = "/lists";
            }} catch (error) {{
              document.getElementById("listItemStatus").textContent = error.message;
            }}
          }});
        }});
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell(f"{record.name} | Album Ranker", "lists", body, page_state=state)
