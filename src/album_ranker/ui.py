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
    return json.dumps(value, ensure_ascii=True).replace("</", "<\\/")


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


def _render_overview(text: str | None) -> str:
    """Escape overview text but convert [label](url) markdown links to clickable <a> tags."""
    import re
    if not text:
        return ""
    parts: list[str] = []
    last = 0
    for m in re.finditer(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', text):
        parts.append(html.escape(text[last:m.start()]))
        label = html.escape(m.group(1))
        url = html.escape(m.group(2))
        parts.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
        last = m.end()
    parts.append(html.escape(text[last:]))
    return ''.join(parts)


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
        ("Imports", "/imports", "imports"),
        ("Bookmarks", "/bookmarks", "bookmarks"),
        ("Genres", "/genres", "genres"),
        ("Lists", "/lists", "lists"),
        ("Settings", "/settings", "settings"),
    ]
    nav_markup = "".join(
        f'<a class="nav-link" data-active="{str(item_active == active).lower()}" href="{href}">{label}</a>'
        for label, href, item_active in navigation
    )
    _theme = (page_state.get("settings") or {}).get("theme", "dark") or "dark"
    return f"""<!doctype html>
<html lang="en" data-theme="{_escape(_theme)}">
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
        --body-bg:
          radial-gradient(circle at top left, rgba(255, 122, 61, 0.12), transparent 24%),
          radial-gradient(circle at right, rgba(74, 115, 171, 0.2), transparent 24%),
          linear-gradient(180deg, #061018, #0a1520 42%, #08111a);
      }}
      [data-theme="dark-brown"] {{
        --bg: #130e08;
        --bg-elevated: #1c1510;
        --panel: #231a10;
        --panel-strong: #2e2114;
        --panel-soft: rgba(35, 26, 16, 0.82);
        --ink: #f7f3ee;
        --muted: #b09878;
        --line: rgba(200, 170, 130, 0.14);
        --accent: #e8854d;
        --accent-strong: #f0a070;
        --success: #5a9e6a;
        --danger: #c85a44;
        --shadow: 0 28px 80px rgba(0, 0, 0, 0.38);
        --body-bg:
          radial-gradient(circle at top left, rgba(232, 133, 77, 0.13), transparent 24%),
          radial-gradient(circle at right, rgba(130, 90, 50, 0.18), transparent 24%),
          linear-gradient(180deg, #100c06, #1a1108 42%, #130e07);
      }}
      [data-theme="dark-green"] {{
        --bg: #060e09;
        --bg-elevated: #0b1610;
        --panel: #0e1d13;
        --panel-strong: #132619;
        --panel-soft: rgba(14, 29, 19, 0.82);
        --ink: #eef5ef;
        --muted: #7aaa88;
        --line: rgba(120, 180, 140, 0.14);
        --accent: #4ecb7a;
        --accent-strong: #72e096;
        --success: #3ab86a;
        --danger: #c85a55;
        --shadow: 0 28px 80px rgba(0, 0, 0, 0.38);
        --body-bg:
          radial-gradient(circle at top left, rgba(78, 203, 122, 0.10), transparent 24%),
          radial-gradient(circle at right, rgba(30, 90, 55, 0.18), transparent 24%),
          linear-gradient(180deg, #050d08, #091409 42%, #060e08);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        color: var(--ink);
        font-family: "Avenir Next", "Helvetica Neue", sans-serif;
        background: var(--body-bg);
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
      a:focus-visible,
      button:focus-visible,
      input:focus-visible,
      select:focus-visible,
      textarea:focus-visible,
      [tabindex]:focus-visible {{
        outline: 3px solid var(--accent-strong);
        outline-offset: 3px;
        box-shadow: 0 0 0 6px color-mix(in srgb, var(--accent) 22%, transparent);
      }}
      input:focus-visible,
      select:focus-visible,
      textarea:focus-visible {{
        border-color: color-mix(in srgb, var(--accent-strong) 72%, rgba(163, 187, 209, 0.16));
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
      .hero.compact {{
        padding: 18px 20px;
        border-radius: 20px;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.26);
      }}
      .hero.compact h1 {{
        font-size: clamp(28px, 3vw, 40px);
        line-height: 1.02;
      }}
      .hero.compact p {{
        margin-top: 8px;
        line-height: 1.5;
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
        width: auto;
      }}
      .row > button {{
        flex: 0 0 auto;
      }}
      button.secondary {{
        background: rgba(255, 255, 255, 0.08);
        color: var(--ink);
      }}
      .button-link {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-decoration: none;
        border-radius: 999px;
        padding: 11px 16px;
        color: var(--ink);
        white-space: nowrap;
      }}
      .button-link.secondary {{
        background: rgba(255, 255, 255, 0.08);
      }}
      .icon-action {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 34px;
        height: 34px;
        border-radius: 50%;
        padding: 0;
        color: var(--ink);
        text-decoration: none;
        font-size: 15px;
        background: rgba(255, 255, 255, 0.07);
      }}
      button.danger {{
        background: rgba(219, 90, 99, 0.14);
        color: #ffd8dc;
      }}
      .danger-zone {{
        margin-top: 16px;
        padding: 14px;
        border: 1px solid rgba(219, 90, 99, 0.28);
        border-radius: 16px;
        background: rgba(219, 90, 99, 0.08);
      }}
      .danger-zone .panel-title {{
        color: #ffd8dc;
      }}
      .danger-zone p {{
        margin: 0 0 12px;
        color: var(--muted);
        font-size: 13px;
        line-height: 1.5;
      }}
      .aa-tab.active {{
        background: linear-gradient(135deg, rgba(255, 122, 61, 0.92), rgba(255, 154, 87, 0.86));
        color: #091019;
        border: 1px solid rgba(255, 191, 145, 0.78);
        box-shadow: 0 0 0 2px rgba(255, 122, 61, 0.18);
      }}
      .status {{
        min-height: 22px;
        color: var(--muted);
        font-size: 13px;
      }}
      .status.compact {{
        text-align: center;
        font-size: 0.85em;
        margin-bottom: 4px;
      }}
      .status[data-state="loading"] {{
        color: var(--accent-strong);
      }}
      .status[data-state="success"] {{
        color: #89d88f;
      }}
      .status[data-state="error"] {{
        color: #ffd8dc;
      }}
      button:disabled {{
        opacity: 0.55;
        cursor: wait;
      }}
      #globalToast {{
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%) translateY(12px);
        background: #2a1a1a;
        color: #ffd8dc;
        border: 1px solid rgba(219, 90, 99, 0.45);
        padding: 11px 20px;
        border-radius: 999px;
        font-size: 14px;
        box-shadow: 0 8px 28px rgba(0,0,0,0.45);
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.2s, transform 0.2s;
        z-index: 9999;
        white-space: nowrap;
        max-width: 90vw;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      #globalToast.visible {{
        opacity: 1;
        transform: translateX(-50%) translateY(0);
      }}
      .form-note {{
        margin-top: 6px;
        font-size: 0.85em;
      }}
      .warning-box {{
        margin-top: 10px;
        padding: 10px 12px;
        border-radius: 6px;
        background: rgba(255, 200, 0, 0.1);
        border: 1px solid rgba(255, 200, 0, 0.3);
        color: var(--ink);
        font-size: 0.88em;
      }}
      .compact-url-input {{
        font-size: 0.82em;
        padding: 5px 8px;
      }}
      .album-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
        gap: 18px;
      }}
      .album-card {{
        color: inherit;
      }}
      .album-card-link {{
        color: inherit;
        text-decoration: none;
      }}
      .cover-frame {{
        position: relative;
      }}
      .cover {{
        aspect-ratio: 1 / 1;
        width: 100%;
        border-radius: 22px;
        overflow: hidden;
        background: #101a24;
        box-shadow: 0 18px 42px rgba(0, 0, 0, 0.32);
        cursor: pointer;
        display: block;
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
      .cover-bookmark-btn,
      .cover-listened-btn {{
        position: absolute;
        top: 8px;
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: rgba(0,0,0,0.55);
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0;
        transition: opacity 0.18s, background 0.18s, color 0.18s;
        z-index: 2;
        padding: 0;
        color: rgba(255,255,255,0.9);
      }}
      .cover-bookmark-btn {{
        right: 8px;
      }}
      .cover-listened-btn {{
        left: 8px;
      }}
      .cover-frame:hover .cover-bookmark-btn,
      .cover-frame:hover .cover-listened-btn,
      .cover-frame:focus-within .cover-bookmark-btn,
      .cover-frame:focus-within .cover-listened-btn,
      .cover-bookmark-btn[data-bookmarked="true"] {{
        opacity: 1;
      }}
      .cover-bookmark-btn[data-bookmarked="true"] {{
        color: var(--accent);
      }}
      .cover-listened-btn[data-listened="true"] {{
        opacity: 1;
        color: #89d88f;
      }}
      .cover-bookmark-btn:hover,
      .cover-listened-btn:hover {{
        background: rgba(0,0,0,0.8);
      }}
      .album-title {{
        display: block;
        margin-top: 12px;
        font-weight: 600;
      }}
      .album-subtitle {{
        margin-top: 4px;
        color: var(--muted);
        font-size: 14px;
      }}
      .album-type {{
        margin-top: 3px;
        font-size: 12px;
        line-height: 1.35;
      }}
      .album-genre {{
        margin-top: 4px;
        color: var(--accent);
        font-size: 13px;
      }}
      .letter-btn {{
        padding: 3px 8px;
        font-size: 13px;
        min-width: 30px;
        background: var(--surface);
        color: var(--muted);
        border: 1px solid var(--border);
        border-radius: 4px;
        cursor: pointer;
        line-height: 1.4;
      }}
      .letter-btn:hover {{
        color: var(--fg);
        border-color: var(--muted);
      }}
      .letter-btn.active {{
        background: var(--accent);
        color: #fff;
        border-color: var(--accent);
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
      .card-star-widget .star-btn {{
        font-size: 13px;
        padding: 0 1px;
        transform: none !important;
      }}
      .album-card-actions {{
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
        margin-top: 10px;
      }}
      .album-card-actions button {{
        padding: 7px 10px;
        font-size: 12px;
        flex: 1 1 auto;
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
        align-items: center;
      }}
      .filters select, .filters input {{
        max-width: 240px;
      }}
      .filters .wide-search {{
        max-width: 360px;
        min-width: 240px;
        flex: 1 1 260px;
      }}
      .filter-meta {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        margin: 0 0 12px;
      }}
      .filter-meta .muted {{
        margin: 0;
      }}
      .filter-count {{
        color: var(--muted);
        font-size: 13px;
        font-weight: 600;
      }}
      .empty-filter-state {{
        margin: 0 0 14px;
        padding: 14px 16px;
        border: 1px dashed var(--line);
        border-radius: 8px;
        color: var(--muted);
        background: rgba(255, 255, 255, 0.025);
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
      .input-clear-wrap {{
        position: relative;
        display: flex;
        align-items: center;
      }}
      .input-clear-wrap input {{
        flex: 1;
        padding-right: 30px;
      }}
      .input-clear-btn {{
        position: absolute;
        right: 8px;
        background: transparent;
        border: 0;
        padding: 0;
        cursor: pointer;
        color: var(--muted);
        font-size: 16px;
        line-height: 1;
        display: none;
      }}
      .input-clear-btn:hover {{
        color: var(--text);
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
        justify-items: start;
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
      .genre-tag-picker {{
        display: flex;
        flex-direction: column;
        gap: 8px;
      }}
      .genre-tag-picker select {{
        max-width: 280px;
      }}
      .genre-tag-chips {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        min-height: 10px;
      }}
      .genre-chip {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 4px 10px 4px 12px;
        border-radius: 999px;
        background: color-mix(in srgb, var(--accent) 15%, transparent);
        border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
        font-size: 13px;
        font-weight: 500;
        color: var(--ink);
        white-space: nowrap;
      }}
      .genre-chip-remove {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: rgba(255,255,255,0.12);
        border: none;
        color: var(--ink);
        font-size: 11px;
        line-height: 1;
        cursor: pointer;
        padding: 0;
        flex-shrink: 0;
      }}
      .genre-chip-remove:hover {{
        background: rgba(255,255,255,0.24);
      }}
      @keyframes indeterminate-slide {{
        0%   {{ left: -50%; width: 40%; }}
        50%  {{ left: 60%; width: 40%; }}
        100% {{ left: 110%; width: 40%; }}
      }}
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
      @media (hover: none), (pointer: coarse) {{
        .cover-frame .cover-bookmark-btn,
        .cover-frame .cover-listened-btn {{
          width: 38px;
          height: 38px;
          opacity: 1;
        }}
        .cover-upload-overlay {{
          opacity: 1;
        }}
      }}
      @media (max-width: 640px) {{
        .content {{
          padding: 14px;
        }}
        .sidebar {{
          padding: 18px 14px;
        }}
        .brand {{
          font-size: 28px;
          margin-bottom: 18px;
        }}
        .nav {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
        }}
        .nav-link {{
          padding: 10px 11px;
          border-radius: 12px;
          text-align: center;
        }}
        .hero {{
          padding: 20px;
          border-radius: 20px;
        }}
        h1 {{
          font-size: 34px;
          line-height: 1;
        }}
        .panel {{
          padding: 16px;
          border-radius: 18px;
        }}
        .detail-head {{
          align-items: stretch;
          flex-direction: column;
        }}
        .detail-head > .row,
        .filters,
        .mini-actions {{
          width: 100%;
        }}
        .filters select,
        .filters input,
        .genre-tag-picker select {{
          max-width: none;
        }}
        .album-grid {{
          grid-template-columns: repeat(auto-fill, minmax(135px, 1fr));
          gap: 14px;
        }}
        .row {{
          align-items: stretch;
        }}
        .row > button,
        .row > a.secondary,
        .album-card-actions button {{
          flex: 1 1 140px;
        }}
        .letter-btn {{
          min-width: 28px;
          padding: 5px 7px;
        }}
        .track-row {{
          grid-template-columns: 34px minmax(0, 1fr) auto;
          gap: 8px;
          padding: 9px 10px;
          font-size: 14px;
        }}
        .rank-item {{
          grid-template-columns: 34px 52px minmax(0, 1fr);
          gap: 10px;
          padding: 12px;
        }}
        .rank-cover {{
          width: 52px;
          height: 52px;
          border-radius: 12px;
        }}
        .rank-item .mini-actions {{
          grid-column: 1 / -1;
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
        <script>
          function initGenrePicker(container, allGenres, initialSelected, onChange) {{
            const select = container.querySelector(".genre-pick-select");
            const chips = container.querySelector(".genre-tag-chips");
            if (!select || !chips) return;
            let selected = [...initialSelected];
            function escHtml(v) {{ return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;"); }}
            function refreshSelect() {{
              const remaining = allGenres.filter((g) => !selected.includes(g));
              select.innerHTML = remaining.length
                ? '<option value="">Add a genre\u2026</option>' + remaining.map((g) => `<option value="${{escHtml(g)}}">${{escHtml(g)}}</option>`).join("")
                : '<option value="">All genres added</option>';
              select.disabled = remaining.length === 0;
            }}
            function removeGenre(name) {{
              selected = selected.filter((g) => g !== name);
              refreshSelect(); renderChips();
              if (onChange) onChange(selected);
            }}
            function renderChips() {{
              chips.innerHTML = selected.map((name) =>
                `<span class="genre-chip">${{escHtml(name)}}<button type="button" class="genre-chip-remove" aria-label="Remove ${{escHtml(name)}}" data-genre="${{escHtml(name)}}">&times;</button></span>`
              ).join("");
              chips.querySelectorAll(".genre-chip-remove").forEach((btn) => {{
                btn.addEventListener("click", () => removeGenre(btn.dataset.genre));
              }});
            }}
            select.addEventListener("change", () => {{
              const val = select.value;
              if (!val) return;
              if (!selected.includes(val)) selected.push(val);
              refreshSelect(); renderChips();
              if (onChange) onChange(selected);
            }});
            refreshSelect(); renderChips();
            container._getGenres = () => [...selected];
          }}
        </script>
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
      function statusState(text) {{
        const value = String(text || "").trim().toLowerCase();
        if (!value) return "";
        if (/\\b(saving|creating|fetching|generating|deleting|adding|regenerating|uploading)\\b/.test(value)) return "loading";
        if (/\\b(saved|ready|added|updated|uploaded|complete|success)\\b/.test(value)) return "success";
        if (/\\b(failed|error|invalid|required|choose|missing|not found|not configured|must|cannot|no source)\\b/.test(value)) return "error";
        return "";
      }}
      function syncStatusElement(el) {{
        if (!el) return;
        if (!el.hasAttribute("role")) el.setAttribute("role", "status");
        if (!el.hasAttribute("aria-live")) el.setAttribute("aria-live", "polite");
        if (!el.hasAttribute("aria-atomic")) el.setAttribute("aria-atomic", "true");
        const state = statusState(el.textContent);
        if (state) {{
          el.dataset.state = state;
        }} else {{
          delete el.dataset.state;
        }}
      }}
      function initStatusRegions(root = document) {{
        root.querySelectorAll(".status").forEach((el) => {{
          syncStatusElement(el);
          if (el._statusObserver) return;
          const observer = new MutationObserver(() => syncStatusElement(el));
          observer.observe(el, {{ childList: true, characterData: true, subtree: true }});
          el._statusObserver = observer;
        }});
      }}
      initStatusRegions();
      let _toastTimer = null;
      function showToast(message) {{
        const toast = document.getElementById("globalToast");
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add("visible");
        if (_toastTimer) clearTimeout(_toastTimer);
        _toastTimer = setTimeout(() => {{
          toast.classList.remove("visible");
          _toastTimer = null;
        }}, 4000);
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
            // Legacy pipe format: "1|Title|3:45"
            if (line.includes("|")) {{
              const parts = line.split("|").map((p) => p.trim());
              if (parts.length < 2) throw new Error("Track lines must use: 1. Title  3:45");
              const trackNumber = Number(parts[0].replace(".", ""));
              if (!trackNumber) throw new Error("Each track needs a numeric position");
              if (!parts[1]) throw new Error(`Track ${{trackNumber}} needs a title.`);
              return {{
                track_number: trackNumber,
                title: parts[1],
                duration_seconds: parts[2] ? parseDuration(parts[2]) : null,
                position: index + 1,
              }};
            }}
            // Human-friendly format: "1. Title  3:45" or "1. Title"
            const numMatch = line.match(/^(\\d+)[.):]?\\s+/);
            if (!numMatch) throw new Error(`Could not parse track number from: "${{line}}".`);
            const trackNumber = Number(numMatch[1]);
            const rest = line.slice(numMatch[0].length).trim();
            const durMatch = rest.match(/\\s+(\\d+:\\d{{2}}(?::\\d{{2}})?)$/);
            const duration = durMatch ? durMatch[1] : null;
            const title = durMatch ? rest.slice(0, rest.length - durMatch[0].length).trim() : rest;
            if (!title) throw new Error(`Track ${{trackNumber}} needs a title.`);
            return {{
              track_number: trackNumber,
              title,
              duration_seconds: duration ? parseDuration(duration) : null,
              position: index + 1,
            }};
          }});
      }}
      function validateRequired(value, label) {{
        if (!String(value || "").trim()) throw new Error(`${{label}} is required.`);
      }}
      function validateYear(value, label = "Year") {{
        const raw = String(value || "").trim();
        if (!raw) return null;
        if (!/^\\d{{4}}$/.test(raw)) throw new Error(`${{label}} must be a four-digit year.`);
        return Number(raw);
      }}
      function validateRating(value) {{
        if (value === null || value === undefined || value === "") return null;
        const rating = Number(value);
        if (Number(value) === 0) return null;
        if (!Number.isInteger(rating) || rating < 1 || rating > 10) throw new Error("Rating must be between 1 and 10.");
        return rating;
      }}
      function validateUrl(value, label = "URL") {{
        const raw = String(value || "").trim();
        if (!raw) return null;
        try {{
          return new URL(raw).toString();
        }} catch (err) {{
          throw new Error(`${{label}} must be a full URL, for example https://example.com/page.`);
        }}
      }}
      function validateMetalArchivesAlbumUrl(value) {{
        const raw = String(value || "").trim();
        if (!raw) throw new Error("Please provide a proper Metal Archives album URL from /albums/..., not an artist page URL.");
        let parsed;
        try {{
          parsed = new URL(raw);
        }} catch (err) {{
          throw new Error("Please provide a proper Metal Archives album URL from /albums/..., not an artist page URL. Use the full URL, for example https://www.metal-archives.com/albums/...");
        }}
        if (parsed.hostname.includes("metal-archives.com") && !parsed.pathname.startsWith("/albums/")) {{
          throw new Error("Please provide a proper Metal Archives album URL from /albums/..., not an artist page URL. This looks like an artist page.");
        }}
        return raw;
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
          let message = payload || `Request failed: ${{response.status}}`;
          try {{
            const parsed = JSON.parse(payload);
            message = parsed.detail || message;
          }} catch (err) {{}}
          throw new Error(message);
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
        button.setAttribute("aria-controls", target.id);
        button.setAttribute("aria-expanded", target.classList.contains("expanded") ? "true" : "false");
        button.addEventListener("click", () => {{
          target.classList.toggle("expanded");
          const isExpanded = target.classList.contains("expanded");
          button.textContent = isExpanded ? "LESS" : "MORE";
          button.setAttribute("aria-expanded", isExpanded ? "true" : "false");
        }});
      }});
      function updateAlbumListenState(albumId, payload) {{
        const bookmarked = Boolean(payload.bookmarked_at);
        const listened = Boolean(payload.listened_at);
        document.querySelectorAll(`.album-bookmark-toggle[data-album-id="${{albumId}}"]`).forEach((button) => {{
          button.dataset.bookmarked = bookmarked ? "true" : "false";
          if (button.classList.contains('cover-bookmark-btn')) {{
            button.innerHTML = bookmarked
              ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" height="17" fill="currentColor" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'
              : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>';
            button.title = bookmarked ? 'Remove from Later' : 'Save for Later';
            button.setAttribute('aria-label', bookmarked ? 'Remove from Later' : 'Save for Later');
          }} else {{
            button.textContent = bookmarked ? "Remove from Later" : "Save for Later";
          }}
        }});
        document.querySelectorAll(`.album-listened-toggle[data-album-id="${{albumId}}"]`).forEach((button) => {{
          button.dataset.listened = listened ? "true" : "false";
          if (button.classList.contains('cover-listened-btn')) {{
            button.innerHTML = listened
              ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.6 7.7-5.3 5.3a1 1 0 0 1-1.4 0l-2.5-2.5 1.4-1.4 1.8 1.8 4.6-4.6 1.4 1.4z"/></svg>'
              : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9 12l2 2 4-4"/></svg>';
            button.title = listened ? 'Mark Unlistened' : 'Mark Listened';
            button.setAttribute('aria-label', listened ? 'Mark Unlistened' : 'Mark Listened');
          }} else {{
            button.textContent = listened ? "Mark Unlistened" : "Mark Listened";
          }}
        }});
        document.querySelectorAll(`.album-listened-state[data-album-id="${{albumId}}"]`).forEach((node) => {{
          node.textContent = listened ? "Listened" : "Not Listened";
        }});
      }}
      document.querySelectorAll(".album-bookmark-toggle").forEach((button) => {{
        button.addEventListener("click", async (event) => {{
          event.preventDefault();
          event.stopPropagation();
          const albumId = button.dataset.albumId;
          const prevBookmarked = button.dataset.bookmarked === "true";
          const nextBookmarked = !prevBookmarked;
          button.disabled = true;
          try {{
            const payload = await fetchJson(`/api/albums/${{albumId}}/bookmark`, {{
              method: "PATCH",
              body: JSON.stringify({{ bookmarked: nextBookmarked }}),
            }});
            updateAlbumListenState(albumId, payload);
            if (!payload.bookmarked_at) {{
              const card = button.closest(".album-card");
              const grid = card?.parentElement;
              if (card && grid?.id === "bookmarkGrid") {{
                card.remove();
                const empty = document.getElementById("bookmarkEmpty");
                if (empty && !grid.querySelector(".album-card")) empty.classList.remove("hidden");
              }}
            }}
          }} catch (error) {{
            button.dataset.bookmarked = prevBookmarked ? "true" : "false";
            showToast(error.message || "Bookmark update failed.");
          }} finally {{
            button.disabled = false;
          }}
        }});
      }});
      document.querySelectorAll(".album-listened-toggle").forEach((button) => {{
        button.addEventListener("click", async (event) => {{
          event.preventDefault();
          event.stopPropagation();
          const albumId = button.dataset.albumId;
          const prevListened = button.dataset.listened === "true";
          const nextListened = !prevListened;
          button.disabled = true;
          try {{
            const payload = await fetchJson(`/api/albums/${{albumId}}/listened`, {{
              method: "PATCH",
              body: JSON.stringify({{ listened: nextListened }}),
            }});
            updateAlbumListenState(albumId, payload);
          }} catch (error) {{
            button.dataset.listened = prevListened ? "true" : "false";
            showToast(error.message || "Listened update failed.");
          }} finally {{
            button.disabled = false;
          }}
        }});
      }});
    </script>
    <div id="globalToast" role="alert" aria-live="assertive" aria-atomic="true"></div>
  </body>
</html>"""


def _artist_markup(
    artist: ArtistWithAlbumsRecord,
    *,
    hidden_initially: bool = False,
    extra_attrs: str = "",
) -> str:
    genres_data = "|".join(sorted({a.genre for a in artist.albums if a.genre}))
    classes = "artist-card hidden" if hidden_initially else "artist-card"
    return f"""
      <article class="{classes}" data-name="{_escape(artist.name.lower())}" data-genres="{_escape(genres_data)}"{(' ' + extra_attrs) if extra_attrs else ''}>
        <div class="row">
          <div>
            <h3><a href="/artists/{artist.id}" style="text-decoration:none;">{_escape(artist.name)}</a></h3>
          </div>
        </div>
      </article>
    """


def _album_card_markup(
    album: AlbumCardRecord,
    *,
    show_artist: bool = True,
    interactive_rating: bool = False,
    include_bookmark_action: bool = True,
    include_listened_action: bool = False,
    include_listened_cover_action: bool = True,
    extra_class: str = "",
    extra_attrs: str = "",
) -> str:
    year_str = str(album.release_year or "")
    if show_artist:
        artist_line = " • ".join(part for part in [album.artist_name, year_str] if part).strip()
    else:
        artist_line = year_str
    genre_line = album.genre or ""
    if interactive_rating:
        current = album.rating or 0
        star_btns = "".join(
            f'<button type="button" class="star-btn{" on" if current >= i else ""}" data-value="{i}" aria-label="Rate {i}">&#9733;</button>'
            for i in range(1, 11)
        )
        rating_widget = (
            f'<div class="card-star-widget" data-album-id="{album.id}" data-current="{current}" '
            f'style="display:flex; gap:1px; flex-wrap:nowrap; margin-top:6px;" onclick="event.preventDefault(); event.stopPropagation();">'
            f'{star_btns}</div>'
        )
    else:
        rating_widget = _rating_markup(album.rating)
    cover_bookmark_btn = _album_cover_bookmark_btn(album) if include_bookmark_action else ""
    cover_listened_btn = _album_cover_listened_btn(album) if include_listened_cover_action else ""
    listened_button = (
        _album_listened_button(album)
        if include_listened_action
        else ""
    )
    actions = f'<div class="album-card-actions">{listened_button}</div>' if listened_button else ""
    return f"""
      <article class="album-card{(' ' + extra_class) if extra_class else ''}" data-genre="{_escape(album.genre)}" data-year="{_escape(str(album.release_year or ''))}" data-artist="{_escape(album.artist_name)}" data-title="{_escape(album.title)}"{(' ' + extra_attrs) if extra_attrs else ''}>
        <div class="cover-frame">
          <a class="cover album-card-link" href="/albums/{album.id}" aria-label="Open {_escape(album.title)}">
            <img src="{_cover_src(album.cover_image_path)}" alt="{_escape(album.title)} cover">
          </a>
          {cover_listened_btn}{cover_bookmark_btn}
        </div>
        <a class="album-title album-card-link" href="/albums/{album.id}">{_escape(album.title)}</a>
        {f'<div class="album-type muted">{_escape(album.album_type)}</div>' if album.album_type else ''}
        <div class="album-subtitle">{_escape(artist_line)}</div>
        <div class="album-genre">{_escape(genre_line)}</div>
        {rating_widget}
        {actions}
      </article>
    """


def _album_bookmark_button(album: AlbumCardRecord) -> str:
    bookmarked = bool(album.bookmarked_at)
    return (
        f'<button type="button" class="secondary album-bookmark-toggle" data-album-id="{album.id}" '
        f'data-bookmarked="{str(bookmarked).lower()}">'
        f'{"Remove from Later" if bookmarked else "Save for Later"}</button>'
    )


_BOOKMARK_SVG_FILLED = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" height="17" fill="currentColor" aria-hidden="true">'
    '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'
)
_BOOKMARK_SVG_EMPTY = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="14" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">'
    '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'
)
_LISTENED_SVG_FILLED = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">'
    '<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.6 7.7-5.3 5.3a1 1 0 0 1-1.4 0l-2.5-2.5 1.4-1.4 1.8 1.8 4.6-4.6 1.4 1.4z"/></svg>'
)
_LISTENED_SVG_EMPTY = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/><path d="M9 12l2 2 4-4"/></svg>'
)


def _album_cover_bookmark_btn(album: AlbumCardRecord) -> str:
    bookmarked = bool(album.bookmarked_at)
    label = "Remove from Later" if bookmarked else "Save for Later"
    icon = _BOOKMARK_SVG_FILLED if bookmarked else _BOOKMARK_SVG_EMPTY
    return (
        f'<button type="button" class="album-bookmark-toggle cover-bookmark-btn" '
        f'data-album-id="{album.id}" data-bookmarked="{str(bookmarked).lower()}" '
        f'title="{label}" aria-label="{label}" '
        f'onclick="event.preventDefault(); event.stopPropagation();">{icon}</button>'
    )


def _album_cover_listened_btn(album: AlbumCardRecord) -> str:
    listened = bool(album.listened_at)
    label = "Mark Unlistened" if listened else "Mark Listened"
    icon = _LISTENED_SVG_FILLED if listened else _LISTENED_SVG_EMPTY
    return (
        f'<button type="button" class="album-listened-toggle cover-listened-btn" '
        f'data-album-id="{album.id}" data-listened="{str(listened).lower()}" '
        f'title="{label}" aria-label="{label}" '
        f'onclick="event.preventDefault(); event.stopPropagation();">{icon}</button>'
    )


def _album_listened_button(album: AlbumCardRecord) -> str:
    listened = bool(album.listened_at)
    return (
        f'<button type="button" class="secondary album-listened-toggle" data-album-id="{album.id}" '
        f'data-listened="{str(listened).lower()}">'
        f'{"Mark Unlistened" if listened else "Mark Listened"}</button>'
    )


def _album_detail_listen_action(album: AlbumCardRecord) -> str:
    return _album_bookmark_button(album) + _album_listened_button(album)


def _list_markup(record: AlbumListRecord, all_albums: "list[AlbumCardRecord] | None" = None) -> str:
    items = "".join(
        f"""
        <div class="rank-item" data-item-id="{item.id}">
          <div><strong>{item.rank_position}.</strong></div>
          <a class="rank-cover" href="/albums/{item.album.id}"><img src="{_cover_src(item.album.cover_image_path)}" alt="{_escape(item.album.title)} cover"></a>
          <div>
            <a href="/albums/{item.album.id}" style="text-decoration:none;"><strong>{_escape(item.album.title)}</strong></a>
            <div class="muted">{_escape(item.album.artist_name)} { _escape(str(item.album.release_year or '')) }</div>
            {_rating_markup(item.album.rating)}
          </div>
          <div class="mini-actions">
            {_album_bookmark_button(item.album)}
            <button type="button" class="secondary move-up">Up</button>
            <button type="button" class="secondary move-down">Down</button>
            <button type="button" class="danger remove-item">-</button>
          </div>
        </div>
        """
        for item in record.items
    ) or '<div class="rank-item"><div></div><div></div><div class="muted">No albums in this list yet.</div><div></div></div>'
    add_btn = ""
    add_panel = ""
    if not record.is_auto and all_albums is not None:
        existing_ids = {item.album.id for item in record.items}
        available = [a for a in all_albums if a.id not in existing_ids]
        albums_json = _escape(_json([{"id": a.id, "label": f"{a.artist_name} - {a.title}"} for a in available]))
        add_btn = f"<button type='button' class='list-add-toggle secondary' aria-controls='list-add-panel-{record.id}' aria-expanded='false'>+ Add album</button>"
        add_panel = f"""
          <div id="list-add-panel-{record.id}" class="list-add-panel hidden" style="padding:12px 18px; border-top:1px solid var(--line);" data-albums="{albums_json}">
            <form class="list-add-form">
              <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <input class="list-add-picker" placeholder="Search albums\u2026" autocomplete="off" style="flex:1; min-width:180px;">
                <input type="hidden" class="list-add-album-id">
                <button type="submit" style="flex:0 0 auto;">Add</button>
                <span class="status list-add-status" style="font-size:13px;"></span>
              </div>
              <ul class="list-add-suggestions" style="display:none; margin:6px 0 0; padding:0; list-style:none; border:1px solid var(--line); border-radius:8px; max-height:220px; overflow-y:auto;"></ul>
            </form>
          </div>"""
    return f"""
      <section class="list-block" data-list-id="{record.id}" data-name="{_escape(record.name.lower())}" data-list-name="{_escape(record.name)}" data-list-year="{_escape(str(record.year or ''))}" data-list-genres="{_escape(json.dumps(record.genres))}" data-list-limit="{record.auto_limit or max(len(record.items), 10)}">
        <div class="list-head" data-toggle="list-body-{record.id}">
          <div>
            <h3 style="margin:0;">{_escape(record.name)}{"&nbsp;<span style='font-size:11px; font-weight:600; letter-spacing:.04em; color:var(--accent); background:color-mix(in srgb, var(--accent) 12%, transparent); padding:2px 7px; border-radius:10px; vertical-align:middle;'>AUTO</span>" if record.is_auto else ""}</h3>
            <div class="muted" style="font-size:12px; margin-top:2px;">{_escape(record.description)} {_escape(", ".join(record.genres))} {_escape(str(record.year or ''))}</div>
          </div>
          <div style="display:flex; gap:6px; align-items:center; flex:0 0 auto;">
            <a href="/lists/{record.id}" class="icon-action" onclick="event.stopPropagation();" title="Edit list details" aria-label="Edit {_escape(record.name)} list details">&#9998;</a>
            <button type="button" class="secondary icon-action list-toggle-btn" aria-controls="list-body-{record.id}" aria-expanded="false" aria-label="Show list items">&#9660;</button>
          </div>
        </div>
        <div id="list-body-{record.id}" class="hidden" role="region" aria-label="{_escape(record.name)} items">
          <div class="rank-list">{items}</div>
          <div style="padding:14px 18px; border-top:1px solid var(--line); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <button type="button" class="save-order">Save</button>
            {"<button type='button' class='regenerate-list secondary' title='Re-run the Best Rated wizard and update this list'>&#8635; Regenerate</button>" if record.is_auto else ""}
            {add_btn}
            <button type="button" class="danger delete-list" style="margin-left:auto;">Delete List</button>
            {"<span class='status regenerate-status' style='font-size:13px;'></span>" if record.is_auto else ""}
          </div>
          {add_panel}
        </div>
      </section>
    """


def render_artists_page(
    settings: SettingsRecord,
    artists: list[ArtistWithAlbumsRecord],
    genres: list[GenreRecord],
    imports: list[ImportDraftRecord],
) -> str:
    recent_artists = sorted(artists, key=lambda artist: (artist.created_at, artist.id), reverse=True)
    artists_markup = "".join(
        _artist_markup(
            artist,
            hidden_initially=index >= 20,
            extra_attrs=f'data-recent-index="{index}"',
        )
        for index, artist in enumerate(recent_artists)
    ) or '<p class="muted">No artists yet. Use Artist Tools above to add your first artist or import one from Metal Archives.</p>'
    has_artists = bool(artists)
    genre_options = "".join(
        f'<option value="{_escape(genre.name)}">{_escape(genre.name)}</option>'
        for genre in genres
    )
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Artists</div>
        <h1>Build a library around artists</h1>
        <p>Keep the band description, source link, and album catalog together. Import when it helps, edit everything when it does not.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Artist Tools</div>
          {('<button type="button" id="artistToolsToggle" class="secondary" title="Toggle artist tools" aria-controls="artistToolsPanel" aria-expanded="false">Show Tools</button>' if has_artists else '')}
        </div>
      </section>
      <div id="artistToolsPanel" class="grid two {('hidden' if has_artists else '')}">
        <section class="panel">
          <div class="panel-title">Artist Import</div>
          <form id="artistImportForm">
            <div class="form-field">
              <label class="form-label" for="artistImportSourceUrl">Source URL</label>
              <div class="input-clear-wrap">
                <input id="artistImportSourceUrl" name="source_url" placeholder="Source URL" required>
                <button type="button" class="input-clear-btn" aria-label="Clear">&#x2715;</button>
              </div>
            </div>
            <div class="row">
              <button type="submit" id="artistImportSubmitBtn">Fetch Metadata</button>
              <button type="button" id="artistImportCancelBtn" class="secondary hidden">Cancel</button>
              <span class="status" id="artistImportStatus"></span>
            </div>
          </form>
          <div id="artistImportReview" class="draft hidden" style="margin-top:14px;">
            <form id="artistConfirmForm">
              <input type="hidden" name="draft_id">
              <div class="row" style="align-items:end;">
                <div class="form-field" style="flex:3;">
                  <label class="form-label" for="artistConfirmName">Artist Name</label>
                  <input id="artistConfirmName" name="name" placeholder="Artist name" required>
                </div>
                <div class="form-field" style="flex:1;">
                  <label class="form-label" for="artistConfirmOrigin">Origin</label>
                  <input id="artistConfirmOrigin" name="origin" placeholder="e.g. UK">
                </div>
              </div>
              <div class="form-field">
                <label class="form-label" for="artistConfirmDescription">Description</label>
                <textarea id="artistConfirmDescription" name="description" placeholder="Description"></textarea>
              </div>
              <div class="form-field">
                <label class="form-label" for="artistConfirmPageUrl">Artist Page URL</label>
                <input id="artistConfirmPageUrl" name="external_url" placeholder="Official site, Wikipedia, or main reference page" style="font-size:0.9em;">
              </div>
              <div class="row">
                <button type="submit">Confirm Import</button>
                <button type="button" class="secondary" id="artistImportReset">Clear</button>
              </div>
              <div id="artistDuplicateWarning" class="warning-box hidden">
                An artist named <strong id="artistDuplicateName"></strong> already exists in your library. <a id="artistDuplicateLink" href="#" target="_blank">Review existing artist</a>. You can still confirm to add another artist with the same name.
              </div>
            </form>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">Manual Artist</div>
          <form id="artistForm">
            <input type="hidden" name="artist_id">
            <div class="row" style="align-items:end;">
              <div class="form-field" style="flex:3;">
                <label class="form-label" for="artistFormName">Artist Name</label>
                <input id="artistFormName" name="name" placeholder="Artist name" required>
              </div>
              <div class="form-field" style="flex:1;">
                <label class="form-label" for="artistFormOrigin">Origin</label>
                <input id="artistFormOrigin" name="origin" placeholder="e.g. UK">
              </div>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistFormDescription">Description</label>
              <textarea id="artistFormDescription" name="description" placeholder="Description"></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistFormPageUrl">Artist Page URL</label>
              <input id="artistFormPageUrl" name="external_url" placeholder="Official site, Wikipedia, or main reference page" style="font-size:0.9em;">
            </div>
            <div class="row">
              <button type="submit">Save Artist</button>
              <button type="button" class="secondary" id="artistFormReset">Clear</button>
              <span class="status" id="artistFormStatus"></span>
            </div>
          </form>
        </section>
      </div>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head" style="margin-bottom:12px;">
          <div class="panel-title" style="margin-bottom:0;">Library Artists</div>
          <div class="filters">
            <input id="artistSearch" class="wide-search" type="search" placeholder="Search artists…">
            <select id="artistGenreFilter"><option value="">Genre</option>{genre_options}</select>
            <button type="button" class="secondary" id="artistFilterClear">Clear Filters</button>
          </div>
        </div>
        <div id="artistLetterBar" style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:14px;">
          <button type="button" class="letter-btn active" data-letter="">All</button>
          {''.join(f'<button type="button" class="letter-btn" data-letter="{c}">{c}</button>' for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')}
          <button type="button" class="letter-btn" data-letter="#">#</button>
        </div>
        <div class="filter-meta">
          {('<p id="artistFilterHint" class="muted">Showing the 20 most recently added artists. Use filters to search the full library.</p>' if len(artists) > 20 else '<span></span>')}
          <div id="artistFilterCount" class="filter-count"></div>
        </div>
        <p id="artistFilterEmpty" class="empty-filter-state hidden">No artists match the current filters.</p>
        <div id="artistList">{artists_markup}</div>
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
          const isOpen = !artistToolsPanel.classList.contains("hidden");
          artistToolsToggle.textContent = isOpen ? "Hide Tools" : "Show Tools";
          artistToolsToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }}
        artistToolsToggle?.addEventListener("click", () => {{
          artistToolsPanel.classList.toggle("hidden");
          syncArtistToolsToggle();
        }});
        // ── Input clear buttons ──────────────────────────────────────────────
        document.querySelectorAll(".input-clear-wrap").forEach((wrap) => {{
          const input = wrap.querySelector("input");
          const btn = wrap.querySelector(".input-clear-btn");
          const sync = () => {{ btn.style.display = input.value ? "block" : "none"; }};
          input.addEventListener("input", sync);
          btn.addEventListener("click", () => {{ input.value = ""; input.dispatchEvent(new Event("input")); input.focus(); }});
          sync();
        }});
        function fillArtistForm(data) {{
          artistToolsPanel.classList.remove("hidden");
          syncArtistToolsToggle();
          artistToolsPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
          artistForm.artist_id.value = data.id || "";
          artistForm.name.value = data.name || data.artist_name || "";
          artistForm.description.value = data.description || "";
          artistForm.external_url.value = data.external_url || "";
          artistForm.origin.value = data.origin || "";
        }}
        function fillArtistImportDraft(draft) {{
          artistToolsPanel.classList.remove("hidden");
          syncArtistToolsToggle();
          artistImportReview.classList.remove("hidden");
          artistConfirmForm.draft_id.value = draft.id;
          artistConfirmForm.name.value = draft.draft_payload.artist_name || "";
          artistConfirmForm.description.value = draft.draft_payload.description || "";
          artistConfirmForm.external_url.value = draft.draft_payload.external_url || "";
          artistConfirmForm.origin.value = draft.draft_payload.origin || "";
          // duplicate detection
          const importedName = (draft.draft_payload.artist_name || "").trim().toLowerCase();
          const warning = document.getElementById("artistDuplicateWarning");
          const existingCard = importedName
            ? Array.from(document.querySelectorAll("#artistList .artist-card")).find(
                card => (card.dataset.name || "") === importedName
              )
            : null;
          if (existingCard) {{
            const link = existingCard.querySelector("a[href^='/artists/']");
            document.getElementById("artistDuplicateLink").href = link ? link.getAttribute("href") : "/artists";
            document.getElementById("artistDuplicateName").textContent = draft.draft_payload.artist_name || "";
            warning.classList.remove("hidden");
          }} else {{
            warning.classList.add("hidden");
          }}
        }}
        document.querySelectorAll(".edit-artist").forEach((button) => {{
          button.addEventListener("click", () => fillArtistForm(JSON.parse(button.dataset.artist)));
        }});
        document.querySelectorAll(".delete-artist").forEach((button) => {{
          button.addEventListener("click", async () => {{
            const artistName = button.dataset.artistName || "this artist";
            if (!window.confirm(`Delete ${{artistName}}?`)) return;
            try {{
              await fetchJson(`/api/artists/${{button.dataset.artistId}}`, {{ method: "DELETE" }});
              window.location.reload();
            }} catch (error) {{
              artistFormStatus.textContent = error.message || "Delete failed.";
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
          document.getElementById("artistDuplicateWarning").classList.add("hidden");
        }});
        artistForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          try {{
            artistFormStatus.textContent = "Saving...";
            validateRequired(artistForm.name.value, "Artist name");
            const payload = {{
              name: artistForm.name.value.trim(),
              description: artistForm.description.value.trim() || null,
              external_url: validateUrl(artistForm.external_url.value, "Artist page URL"),
              origin: artistForm.origin.value.trim() || null,
            }};
            const artistId = artistForm.artist_id.value.trim();
            const result = await fetchJson(artistId ? `/api/artists/${{artistId}}` : "/api/artists", {{
              method: artistId ? "PUT" : "POST",
              body: JSON.stringify(payload),
            }});
            if (!artistId && result?.id) {{
              window.location.href = `/artists/${{result.id}}`;
            }} else {{
              window.location.reload();
            }}
          }} catch (error) {{
            artistFormStatus.textContent = error.message || "Save failed.";
          }}
        }});
        let artistImportAbortCtrl = null;
        document.getElementById("artistImportCancelBtn").addEventListener("click", () => {{
          if (artistImportAbortCtrl) {{
            artistImportAbortCtrl.abort();
            artistImportAbortCtrl = null;
          }}
        }});
        artistImportForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const submitBtn = document.getElementById("artistImportSubmitBtn");
          const cancelBtn = document.getElementById("artistImportCancelBtn");
          try {{
            validateUrl(artistImportForm.source_url.value, "Source URL");
          }} catch (err) {{
            artistImportStatus.textContent = err.message;
            return;
          }}
          artistImportAbortCtrl = new AbortController();
          submitBtn.disabled = true;
          cancelBtn.classList.remove("hidden");
          artistImportStatus.textContent = "Creating draft...";
          try {{
            const response = await fetchJson("/api/import/artist", {{
              method: "POST",
              signal: artistImportAbortCtrl.signal,
              body: JSON.stringify({{
                artist_name: "",
                source_url: artistImportForm.source_url.value.trim() || null,
              }}),
            }});
            fillArtistImportDraft(response.draft);
            artistImportStatus.textContent = "Draft ready for review.";
          }} catch (err) {{
            if (err.name === "AbortError") {{
              artistImportStatus.textContent = "Cancelled.";
            }} else {{
              artistImportStatus.textContent = err.message || "Import failed.";
            }}
          }} finally {{
            artistImportAbortCtrl = null;
            submitBtn.disabled = false;
            cancelBtn.classList.add("hidden");
          }}
        }});
        artistConfirmForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          try {{
            artistImportStatus.textContent = "Saving import...";
            validateRequired(artistConfirmForm.name.value, "Artist name");
            const confirmResult = await fetchJson(`/api/import/${{artistConfirmForm.draft_id.value}}/confirm`, {{
              method: "POST",
              body: JSON.stringify({{
                target_type: "artist",
                chosen_source_url: validateUrl(artistConfirmForm.external_url.value, "Artist page URL"),
                payload: {{
                  name: artistConfirmForm.name.value.trim(),
                  description: artistConfirmForm.description.value.trim() || null,
                  external_url: validateUrl(artistConfirmForm.external_url.value, "Artist page URL"),
                  origin: artistConfirmForm.origin.value.trim() || null,
                }},
              }}),
            }});
            if (confirmResult?.artist?.id) {{
              window.location.href = `/artists/${{confirmResult.artist.id}}`;
            }} else {{
              window.location.reload();
            }}
          }} catch (error) {{
            artistImportStatus.textContent = error.message || "Save failed.";
          }}
        }});
        syncArtistToolsToggle();

        // Artist letter + text + genre filter
        let activeLetter = "";
        function applyArtistFilters() {{
          const q = (document.getElementById("artistSearch")?.value || "").trim().toLowerCase();
          const genre = (document.getElementById("artistGenreFilter")?.value || "").toLowerCase();
          const hasFilter = q !== "" || genre !== "" || activeLetter !== "";
          const artistList = document.getElementById("artistList");
          const cards = Array.from(artistList.querySelectorAll(".artist-card"));
          let visibleCount = 0;
          cards.forEach(card => {{
            const recentIndex = Number(card.dataset.recentIndex || 0);
            const name = card.dataset.name || "";
            const firstChar = name.charAt(0);
            const letterMatch = activeLetter === ""
              || (activeLetter === "#" && !/[a-z]/.test(firstChar))
              || firstChar === activeLetter.toLowerCase();
            const textMatch = q === "" || name.includes(q);
            const genres = (card.dataset.genres || "").toLowerCase();
            const genreMatch = genre === "" || genres.split("|").some(g => g.includes(genre));
            const isHidden = !(letterMatch && textMatch && genreMatch) || (!hasFilter && recentIndex >= 20);
            card.classList.toggle("hidden", isHidden);
            if (!isHidden) {{
              visibleCount += 1;
            }}
          }});
          if (hasFilter) {{
            cards.sort((a, b) => (a.dataset.name || "").localeCompare(b.dataset.name || ""));
          }} else {{
            cards.sort((a, b) => Number(a.dataset.recentIndex || 0) - Number(b.dataset.recentIndex || 0));
          }}
          cards.forEach(card => artistList.appendChild(card));
          const hint = document.getElementById("artistFilterHint");
          if (hint) {{
            hint.classList.toggle("hidden", hasFilter);
          }}
          const count = document.getElementById("artistFilterCount");
          if (count) {{
            count.textContent = `Showing ${{visibleCount}} of ${{cards.length}} artists`;
          }}
          const empty = document.getElementById("artistFilterEmpty");
          if (empty) {{
            empty.classList.toggle("hidden", visibleCount > 0);
          }}
        }}
        document.querySelectorAll("#artistLetterBar .letter-btn").forEach(btn => {{
          btn.addEventListener("click", () => {{
            activeLetter = btn.dataset.letter;
            document.querySelectorAll("#artistLetterBar .letter-btn").forEach(b => b.classList.toggle("active", b === btn));
            applyArtistFilters();
          }});
        }});
        const artistSearch = document.getElementById("artistSearch");
        if (artistSearch) {{
          artistSearch.addEventListener("input", applyArtistFilters);
        }}
        const artistGenreFilter = document.getElementById("artistGenreFilter");
        if (artistGenreFilter) {{
          artistGenreFilter.addEventListener("change", applyArtistFilters);
        }}
        const artistFilterClear = document.getElementById("artistFilterClear");
        if (artistFilterClear) {{
          artistFilterClear.addEventListener("click", () => {{
            activeLetter = "";
            if (artistSearch) {{
              artistSearch.value = "";
            }}
            if (artistGenreFilter) {{
              artistGenreFilter.value = "";
            }}
            document.querySelectorAll("#artistLetterBar .letter-btn").forEach(b => b.classList.toggle("active", b.dataset.letter === ""));
            applyArtistFilters();
            artistSearch?.focus();
          }});
        }}
        applyArtistFilters();
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
        _album_card_markup(album, show_artist=False, interactive_rating=True) for album in artist.albums
    ) or '<p class="muted">No albums added yet.</p>'
    source_link = (
        f'<a class="tag" href="{_escape(artist.external_url)}" target="_blank" rel="noreferrer">Open Source</a>'
        if artist.external_url
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
          <div class="row" style="justify-content:flex-end; flex:0 0 auto; align-items:center;">
            {source_link}
            <a class="button-link secondary" href="/artists">Back to Artists</a>
          </div>
        </div>
        <div id="{clamp_id}" class="clamp muted">{_escape(artist.description or 'No description yet.')}</div>
        <button type="button" class="toggle-link" data-toggle-clamp="{clamp_id}" aria-controls="{clamp_id}" aria-expanded="false">MORE</button>
        {f'<div class="meta-item" style="margin-top:10px; display:inline-block;"><span class="meta-item-label">Origin</span>{_escape(artist.origin)}</div>' if artist.origin else ''}
        <div class="meta-stack" style="margin-top:14px; width:100%;">
          <button type="button" id="artistEditToggle" class="secondary" style="margin-bottom:8px;" aria-controls="artistEditPanel" aria-expanded="false">Edit Artist Metadata</button>
          <div style="display:flex; gap:4px; align-items:center; margin-bottom:4px; width:100%; max-width:none; justify-self:stretch;">
            <input id="artistRefreshUrlInput" class="compact-url-input" placeholder="Source URL (optional)" value="{_escape(artist.external_url)}" style="flex:1 1 auto; min-width:0; max-width:none;">
            <button type="button" id="artistRefreshBtn" class="secondary" style="white-space:nowrap; flex:0 0 auto;" title="Re-fetch metadata from source URL using AI">&#8635; Refresh</button>
            <button type="button" id="artistRefreshCancelBtn" class="secondary hidden" style="white-space:nowrap; flex:0 0 auto;">Cancel</button>
          </div>
          <div id="artistRefreshProgress" style="display:none; margin-bottom:4px; height:4px; border-radius:2px; background:var(--line); overflow:hidden; position:relative;">
            <div id="artistRefreshBar" style="position:absolute; height:100%; width:40%; background:var(--accent); border-radius:2px; animation:indeterminate-slide 1.4s ease-in-out infinite;"></div>
          </div>
          <div class="status compact" id="artistRefreshStatus" style="justify-self:stretch;"></div>
        </div>
        <div class="danger-zone">
          <div class="panel-title">Danger Zone</div>
          <p>Delete this artist and all albums attached to it.</p>
          <button type="button" id="artistDeleteButton" class="danger">Delete Artist</button>
        </div>
      </section>
      <section class="panel hidden" id="artistRefreshReview" style="margin-top:16px;">
        <div class="panel-title">Review Refreshed Artist Metadata</div>
        <form id="artistRefreshForm">
          <input type="hidden" name="draft_id" id="artistRefreshDraftId">
          <div class="row" style="align-items:end;">
            <div class="form-field" style="flex:3;">
              <label class="form-label">Name</label>
              <input name="name" id="artistRefreshName">
            </div>
            <div class="form-field" style="flex:1;">
              <label class="form-label">Origin</label>
              <input name="origin" id="artistRefreshOrigin" placeholder="Country or city">
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">Description</label>
            <textarea name="description" id="artistRefreshDescription" rows="5" placeholder="Artist description"></textarea>
          </div>
          <div class="form-field">
            <label class="form-label">External URL</label>
            <input name="external_url" id="artistRefreshExternalUrl" placeholder="https://..." style="font-size:0.9em;">
          </div>
          <div class="row">
            <button type="submit">Apply Changes</button>
            <button type="button" class="secondary" id="artistRefreshReject">Reject</button>
            <span class="status" id="artistRefreshApplyStatus"></span>
          </div>
        </form>
      </section>
      <section class="panel hidden" id="artistEditPanel" style="margin-top:16px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Edit Artist</div>
        </div>
        <form id="artistDetailForm">
          <div class="row" style="align-items:end;">
            <div class="form-field" style="flex:3;">
              <label class="form-label" for="artistEditName">Name</label>
              <input id="artistEditName" name="name" value="{_escape(artist.name)}" required>
            </div>
            <div class="form-field" style="flex:1;">
              <label class="form-label" for="artistEditOrigin">Origin</label>
              <input id="artistEditOrigin" name="origin" value="{_escape(artist.origin or '')}" placeholder="e.g. UK">
            </div>
          </div>
          <div class="form-field">
            <label class="form-label" for="artistEditExternalUrl">External URL</label>
            <input id="artistEditExternalUrl" name="external_url" value="{_escape(artist.external_url or '')}" placeholder="https://www.metal-archives.com/bands/..." style="font-size:0.9em;">
          </div>
          <div class="form-field">
            <label class="form-label" for="artistEditDescription">Description</label>
            <textarea id="artistEditDescription" name="description" placeholder="Artist description">{_escape(artist.description or '')}</textarea>
          </div>
          <div class="row">
            <button type="submit">Save Changes</button>
            <button type="button" class="secondary" id="artistEditCancel">Cancel</button>
            <span class="status" id="artistDetailStatus"></span>
          </div>
        </form>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Album Import</div>
          <button type="button" id="artistAlbumToolsToggle" class="secondary" title="Toggle album import" aria-controls="artistAlbumToolsPanel" aria-expanded="false">Show Import</button>
        </div>
        <div id="artistAlbumToolsPanel" class="hidden">
        <div class="row" role="tablist" aria-label="Album import mode" style="margin-bottom:16px; gap:8px;">
          <button type="button" id="aa-tab-button-import" class="aa-tab secondary active" data-tab="import" role="tab" aria-selected="true" aria-controls="aa-tab-import">Import from URL</button>
          <button type="button" id="aa-tab-button-manual" class="aa-tab secondary" data-tab="manual" role="tab" aria-selected="false" aria-controls="aa-tab-manual">Manual</button>
        </div>
        <div id="aa-tab-import" role="tabpanel" aria-labelledby="aa-tab-button-import">
        <form id="artistAlbumImportForm">
          <input type="hidden" name="artist_name" value="{_escape(artist.name)}">
          <div class="form-field">
            <label class="form-label" for="artistAlbumImportSourceUrl">Source URL</label>
            <div class="input-clear-wrap">
              <input id="artistAlbumImportSourceUrl" name="source_url" placeholder="Source URL" required>
              <button type="button" class="input-clear-btn" aria-label="Clear">&#x2715;</button>
            </div>
            <div class="form-note muted">
              Use a Metal Archives album page URL from /albums/..., not the artist page URL.
            </div>
          </div>
          <div class="row">
            <button type="submit" id="artistAlbumImportSubmitBtn">Fetch Metadata</button>
            <button type="button" id="artistAlbumImportCancelBtn" class="secondary hidden">Cancel</button>
            <span class="status" id="artistAlbumImportStatus"></span>
          </div>
        </form>
          <div id="artistAlbumImportReview" class="draft hidden" style="margin-top:14px;">
          <form id="artistAlbumConfirmForm">
            <input type="hidden" name="draft_id">
            <input type="hidden" name="artist_name" value="{_escape(artist.name)}">
            <input type="hidden" name="artist_description" value="{_escape(artist.description)}">
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
              <label class="form-label" for="artistAlbumConfirmStreamUrl">Stream URL</label>
              <input id="artistAlbumConfirmStreamUrl" name="album_stream_url" placeholder="https://...">
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmType">Type</label>
              <input id="artistAlbumConfirmType" name="album_type" placeholder="e.g. Full-length, EP, Single">
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmNotes">Album Description</label>
              <textarea id="artistAlbumConfirmNotes" name="notes" placeholder="Album description"></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="artistAlbumConfirmTracklist">Tracklist</label>
              <textarea id="artistAlbumConfirmTracklist" name="tracklist_text" placeholder="1. Track Name  3:45&#10;2. Another Track  4:20"></textarea>
            </div>
            <div class="row">
              <button type="submit">Confirm Import</button>
              <button type="button" class="secondary" id="artistAlbumImportReset">Clear</button>
            </div>
            <div id="albumDuplicateWarning" class="warning-box hidden">
              An album titled <strong id="albumDuplicateName"></strong> already exists for this artist. <a id="albumDuplicateLink" href="#" target="_blank">Review existing album</a>. You can still confirm to add another album with the same title.
            </div>
          </form>
        </div>
        </div>
        </div>
        <div id="aa-tab-manual" class="hidden" role="tabpanel" aria-labelledby="aa-tab-button-manual" hidden>
          <form id="artistAlbumManualForm">
            <input type="hidden" name="artist_name" value="{_escape(artist.name)}">
            <div class="form-field">
              <label class="form-label" for="aaManualTitle">Album Name</label>
              <input id="aaManualTitle" name="title" placeholder="Album name" required>
            </div>
            <div class="row">
              <div class="form-field">
                <label class="form-label" for="aaManualYear">Year</label>
                <input id="aaManualYear" name="release_year" placeholder="Year">
              </div>
              <div class="form-field">
                <label class="form-label" for="aaManualGenre">Genre</label>
                <input id="aaManualGenre" name="genre" placeholder="Genre">
              </div>
              <div class="form-field">
                <label class="form-label" for="aaManualDuration">Length</label>
                <input id="aaManualDuration" name="duration" placeholder="e.g. 42:18">
              </div>
            </div>
            <div class="row">
              <div class="form-field" style="flex:1;">
                <label class="form-label" for="aaManualType">Type</label>
                <input id="aaManualType" name="album_type" placeholder="e.g. Full-length, EP, Single">
              </div>
            </div>
            <div class="form-field">
              <label class="form-label" for="aaManualCoverUrl">Cover Source URL</label>
              <input id="aaManualCoverUrl" name="cover_source_url" placeholder="https://...">
            </div>
            <div class="form-field">
              <label class="form-label" for="aaManualExternalUrl">Album External URL</label>
              <input id="aaManualExternalUrl" name="album_external_url" placeholder="https://...">
            </div>
            <div class="form-field">
              <label class="form-label" for="aaManualNotes">Album Description</label>
              <textarea id="aaManualNotes" name="notes" placeholder="Album description"></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="aaManualTracklist">Tracklist</label>
              <textarea id="aaManualTracklist" name="tracklist_text" placeholder="1. Track Name  3:45&#10;2. Another Track  4:20"></textarea>
            </div>
            <div class="row">
              <button type="submit">Add Album</button>
              <span class="status" id="aaManualStatus"></span>
            </div>
          </form>
        </div>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Albums</div>
        <div class="album-grid">{albums_markup}</div>
      </section>
      <script>
        // ── Album card inline star ratings ────────────────────────────────────
        (function() {{
          document.querySelectorAll(".card-star-widget").forEach(function(widget) {{
            const albumId = widget.dataset.albumId;
            let current = Number(widget.dataset.current) || 0;
            const btns = widget.querySelectorAll(".star-btn");
            function highlight(n) {{
              btns.forEach((b, i) => b.classList.toggle("on", i < n));
            }}
            highlight(current);
            btns.forEach(function(btn, idx) {{
              btn.addEventListener("mouseenter", () => highlight(idx + 1));
              btn.addEventListener("mouseleave", () => highlight(current));
              btn.addEventListener("click", async function(e) {{
                e.preventDefault(); e.stopPropagation();
                const newVal = (idx + 1 === current) ? null : idx + 1;
                try {{
                  const payload = await fetchJson(`/api/albums/${{albumId}}/rating`, {{
                    method: "PATCH",
                    body: JSON.stringify({{ rating: newVal }}),
                  }});
                  current = newVal || 0;
                  widget.dataset.current = current;
                  highlight(current);
                  updateAlbumListenState(albumId, payload);
                }} catch (err) {{
                  console.error("Rating error:", err);
                }}
              }});
            }});
          }});
        }})();
        // ── Artist edit panel ─────────────────────────────────────────────────
        (function() {{
          const artistEditToggle = document.getElementById("artistEditToggle");
          const artistEditPanel = document.getElementById("artistEditPanel");
          function syncArtistEditToggle() {{
            const isOpen = !artistEditPanel.classList.contains("hidden");
            artistEditToggle.textContent = isOpen ? "Close Editor" : "Edit Artist Metadata";
            artistEditToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
          }}
          artistEditToggle.addEventListener("click", () => {{
            const willOpen = artistEditPanel.classList.contains("hidden");
            artistEditPanel.classList.toggle("hidden");
            syncArtistEditToggle();
            if (willOpen) {{
              artistEditPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
            }}
          }});
          syncArtistEditToggle();
          document.getElementById("artistEditCancel").addEventListener("click", () => {{
            artistEditPanel.classList.add("hidden");
            syncArtistEditToggle();
          }});
          document.getElementById("artistDetailForm").addEventListener("submit", async (event) => {{
            event.preventDefault();
            const form = event.currentTarget;
            const status = document.getElementById("artistDetailStatus");
            status.textContent = "Saving\u2026";
            try {{
              await fetchJson("/api/artists/{artist.id}", {{
                method: "PUT",
                body: JSON.stringify({{
                  name: form.name.value.trim(),
                  description: form.description.value.trim() || null,
                  external_url: form.external_url.value.trim() || null,
                  origin: form.origin.value.trim() || null,
                }}),
              }});
              status.textContent = "\u2713 Saved \u2014 reloading\u2026";
              window.location.reload();
            }} catch (err) {{
              status.textContent = err.message || "Save failed.";
            }}
          }});
          document.getElementById("artistDeleteButton").addEventListener("click", async () => {{
            if (!window.confirm("Delete this artist and all their albums? This cannot be undone.")) return;
            try {{
              await fetchJson("/api/artists/{artist.id}", {{ method: "DELETE" }});
              window.location.href = "/artists";
            }} catch (err) {{
              document.getElementById("artistDetailStatus").textContent = err.message || "Delete failed.";
            }}
          }});
        }})();
        // ── Artist refresh ────────────────────────────────────────────────────
        (function() {{
          const btn = document.getElementById("artistRefreshBtn");
          const cancelBtn = document.getElementById("artistRefreshCancelBtn");
          const status = document.getElementById("artistRefreshStatus");
          const progress = document.getElementById("artistRefreshProgress");
          const urlInput = document.getElementById("artistRefreshUrlInput");
          let abortCtrl = null;
          function resetRefreshUI() {{
            progress.style.display = "none";
            btn.disabled = false;
            btn.classList.remove("hidden");
            urlInput.disabled = false;
            btn.textContent = "\u21BB Refresh";
            cancelBtn.classList.add("hidden");
            abortCtrl = null;
          }}
          cancelBtn.addEventListener("click", () => {{
            if (abortCtrl) abortCtrl.abort();
          }});
          btn.addEventListener("click", async () => {{
            const sourceUrl = urlInput ? urlInput.value.trim() : null;
            abortCtrl = new AbortController();
            btn.classList.add("hidden");
            urlInput.disabled = true;
            cancelBtn.classList.remove("hidden");
            status.textContent = "Fetching source and generating metadata\u2026";
            progress.style.display = "block";
            const reviewPanel = document.getElementById("artistRefreshReview");
            if (reviewPanel) reviewPanel.classList.add("hidden");
            try {{
              const resp = await fetchJson("/api/import/artist", {{
                method: "POST",
                signal: abortCtrl.signal,
                body: JSON.stringify({{ artist_name: {_json(artist.name)}, source_url: sourceUrl || {_json(artist.external_url)} }}),
              }});
              const draft = resp.draft;
              const p = draft.draft_payload;
              document.getElementById("artistRefreshDraftId").value = draft.id;
              document.getElementById("artistRefreshName").value = p.artist_name || '';
              document.getElementById("artistRefreshOrigin").value = p.origin || '';
              document.getElementById("artistRefreshDescription").value = p.description || '';
              document.getElementById("artistRefreshExternalUrl").value = p.external_url || '';
              resetRefreshUI();
              status.textContent = "Draft ready \u2014 review below.";
              if (reviewPanel) {{
                reviewPanel.classList.remove("hidden");
                reviewPanel.scrollIntoView({{ behavior: "smooth", block: "start" }});
              }}
            }} catch (err) {{
              resetRefreshUI();
              status.textContent = err.name === "AbortError" ? "Cancelled." : (err.message || "Refresh failed.");
            }}
          }});
          const artistRefreshForm = document.getElementById("artistRefreshForm");
          if (artistRefreshForm) {{
            document.getElementById("artistRefreshReject").addEventListener("click", () => {{
              document.getElementById("artistRefreshReview").classList.add("hidden");
              status.textContent = '';
            }});
            artistRefreshForm.addEventListener("submit", async (e) => {{
              e.preventDefault();
              const applyStatus = document.getElementById("artistRefreshApplyStatus");
              applyStatus.textContent = "Saving\u2026";
              try {{
                await fetchJson("/api/artists/{artist.id}", {{
                  method: "PUT",
                  body: JSON.stringify({{
                    name: document.getElementById("artistRefreshName").value.trim(),
                    description: document.getElementById("artistRefreshDescription").value.trim() || null,
                    external_url: document.getElementById("artistRefreshExternalUrl").value.trim() || null,
                    origin: document.getElementById("artistRefreshOrigin").value.trim() || null,
                  }}),
                }});
                applyStatus.textContent = "\u2713 Saved \u2014 reloading\u2026";
                window.location.reload();
              }} catch (err) {{
                applyStatus.textContent = err.message || "Save failed.";
              }}
            }});
          }}
        }})();
        const artistAlbumToolsPanel = document.getElementById("artistAlbumToolsPanel");
        const artistAlbumToolsToggle = document.getElementById("artistAlbumToolsToggle");
        const artistAlbumImportForm = document.getElementById("artistAlbumImportForm");
        const artistAlbumImportReview = document.getElementById("artistAlbumImportReview");
        const artistAlbumConfirmForm = document.getElementById("artistAlbumConfirmForm");
        const artistAlbumImportStatus = document.getElementById("artistAlbumImportStatus");
        function syncArtistAlbumToolsToggle() {{
          const isOpen = !artistAlbumToolsPanel.classList.contains("hidden");
          artistAlbumToolsToggle.textContent = isOpen ? "Hide Import" : "Show Import";
          artistAlbumToolsToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }}
        artistAlbumToolsToggle.addEventListener("click", () => {{
          artistAlbumToolsPanel.classList.toggle("hidden");
          syncArtistAlbumToolsToggle();
        }});
        // ── Input clear buttons ──────────────────────────────────────────────
        document.querySelectorAll(".input-clear-wrap").forEach((wrap) => {{
          const input = wrap.querySelector("input");
          const btn = wrap.querySelector(".input-clear-btn");
          const sync = () => {{ btn.style.display = input.value ? "block" : "none"; }};
          input.addEventListener("input", sync);
          btn.addEventListener("click", () => {{ input.value = ""; input.dispatchEvent(new Event("input")); input.focus(); }});
          sync();
        }});
        function artistAlbumPayload(form) {{
          validateRequired(form.artist_name.value, "Artist name");
          validateRequired(form.title.value, "Album title");
          return {{
            artist_name: form.artist_name.value.trim(),
            artist_description: form.artist_description.value.trim() || null,
            album_external_url: validateUrl(form.album_external_url.value, "Album source URL"),
            album_stream_url: validateUrl(form.album_stream_url.value, "Stream URL"),
            album_type: form.album_type.value.trim() || null,
            title: form.title.value.trim(),
            release_year: validateYear(form.release_year.value, "Release year"),
            genre: form.genre.value.trim() || null,
            rating: null,
            duration_seconds: parseDuration(form.duration.value),
            cover_source_url: validateUrl(form.cover_source_url.value, "Cover source URL"),
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
          artistAlbumConfirmForm.album_stream_url.value = payload.album_stream_url || "";
          artistAlbumConfirmForm.album_type.value = payload.album_type || "";
          artistAlbumConfirmForm.notes.value = payload.notes || "";
          artistAlbumConfirmForm.tracklist_text.value = (payload.tracks || []).map((track) => `${{track.track_number}}. ${{track.title}}${{track.duration_seconds ? "  " + formatDuration(track.duration_seconds) : ""}}`).join("\\n");
          // duplicate detection
          const importedTitle = (payload.album_title || "").trim().toLowerCase();
          const albumWarning = document.getElementById("albumDuplicateWarning");
          const existingAlbumCard = importedTitle
            ? Array.from(document.querySelectorAll(".album-grid .album-card")).find(
                card => (card.dataset.title || "").trim().toLowerCase() === importedTitle
              )
            : null;
          if (existingAlbumCard) {{
            const existingAlbumLink = existingAlbumCard.querySelector("a[href^='/albums/']");
            document.getElementById("albumDuplicateLink").href = existingAlbumLink ? existingAlbumLink.getAttribute("href") : "/albums";
            document.getElementById("albumDuplicateName").textContent = payload.album_title || "";
            albumWarning.classList.remove("hidden");
          }} else {{
            albumWarning.classList.add("hidden");
          }}
        }}
        let artistAlbumImportAbortCtrl = null;
        document.getElementById("artistAlbumImportCancelBtn").addEventListener("click", () => {{
          if (artistAlbumImportAbortCtrl) {{
            artistAlbumImportAbortCtrl.abort();
            artistAlbumImportAbortCtrl = null;
          }}
        }});
        artistAlbumImportForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          const submitBtn = document.getElementById("artistAlbumImportSubmitBtn");
          const cancelBtn = document.getElementById("artistAlbumImportCancelBtn");
          let sourceUrl = "";
          try {{
            sourceUrl = validateMetalArchivesAlbumUrl(document.getElementById("artistAlbumImportSourceUrl").value);
          }} catch (err) {{
            artistAlbumImportStatus.textContent = err.message;
            return;
          }}
          artistAlbumImportAbortCtrl = new AbortController();
          submitBtn.disabled = true;
          cancelBtn.classList.remove("hidden");
          artistAlbumImportStatus.textContent = "Creating draft...";
          const form = event.currentTarget;
          try {{
            const response = await fetchJson("/api/import/album", {{
              method: "POST",
              signal: artistAlbumImportAbortCtrl.signal,
              body: JSON.stringify({{
                artist_name: form.artist_name.value.trim(),
                album_title: null,
                source_url: sourceUrl,
              }}),
            }});
            fillArtistAlbumDraft(response.draft);
            artistAlbumImportStatus.textContent = "Draft ready for review.";
          }} catch (err) {{
            if (err.name === "AbortError") {{
              artistAlbumImportStatus.textContent = "Cancelled.";
            }} else {{
              artistAlbumImportStatus.textContent = err.message || "Import failed.";
            }}
          }} finally {{
            artistAlbumImportAbortCtrl = null;
            submitBtn.disabled = false;
            cancelBtn.classList.add("hidden");
          }}
        }});
        document.getElementById("artistAlbumImportReset").addEventListener("click", () => {{
          artistAlbumImportReview.classList.add("hidden");
          artistAlbumConfirmForm.reset();
          artistAlbumConfirmForm.artist_name.value = {_json(artist.name)};
          artistAlbumConfirmForm.artist_description.value = {_json(artist.description)};
          artistAlbumConfirmForm.artist_origin.value = {_json(artist.origin)};
          artistAlbumConfirmForm.artist_origin.value = {_json(artist.origin)};
          artistAlbumImportStatus.textContent = "";
          document.getElementById("albumDuplicateWarning").classList.add("hidden");
        }});
        artistAlbumConfirmForm.addEventListener("submit", async (event) => {{
          event.preventDefault();
          try {{
            artistAlbumImportStatus.textContent = "Saving import...";
            await fetchJson(`/api/import/${{artistAlbumConfirmForm.draft_id.value}}/confirm`, {{
              method: "POST",
              body: JSON.stringify({{
                target_type: "album",
                chosen_source_url: validateUrl(artistAlbumConfirmForm.album_external_url.value, "Album source URL"),
                payload: artistAlbumPayload(artistAlbumConfirmForm),
              }}),
            }});
            window.location.reload();
          }} catch (error) {{
            artistAlbumImportStatus.textContent = error.message || "Save failed.";
          }}
        }});
        syncArtistAlbumToolsToggle();
        // ── Album panel tabs ──────────────────────────────────────────────────
        document.querySelectorAll(".aa-tab").forEach((btn) => {{
          btn.addEventListener("click", () => {{
            document.querySelectorAll(".aa-tab").forEach((b) => {{
              b.classList.remove("active");
              b.setAttribute("aria-selected", "false");
            }});
            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
            const importPanel = document.getElementById("aa-tab-import");
            const manualPanel = document.getElementById("aa-tab-manual");
            importPanel.classList.toggle("hidden", btn.dataset.tab !== "import");
            manualPanel.classList.toggle("hidden", btn.dataset.tab !== "manual");
            importPanel.toggleAttribute("hidden", btn.dataset.tab !== "import");
            manualPanel.toggleAttribute("hidden", btn.dataset.tab !== "manual");
          }});
        }});
        // ── Manual album form ─────────────────────────────────────────────────
        document.getElementById("artistAlbumManualForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("aaManualStatus");
          try {{
            status.textContent = "Saving...";
            validateRequired(form.artist_name.value, "Artist name");
            validateRequired(form.title.value, "Album title");
            await fetchJson("/api/albums", {{
              method: "POST",
              body: JSON.stringify({{
                artist_name: form.artist_name.value.trim(),
                title: form.title.value.trim(),
                release_year: validateYear(form.release_year.value, "Release year"),
                genre: form.genre.value.trim() || null,
                duration_seconds: parseDuration(form.duration.value),
                album_type: form.album_type.value.trim() || null,
                cover_source_url: validateUrl(form.cover_source_url.value, "Cover source URL"),
                album_external_url: validateUrl(form.album_external_url.value, "Album source URL"),
                notes: form.notes.value.trim() || null,
                tracks: parseTracklist(form.tracklist_text.value),
              }}),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message || "Save failed.";
          }}
        }});
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell(f"{artist.name} | Album Ranker", "artists", body, page_state=state)


def render_imports_page(settings: SettingsRecord) -> str:
    body = """
      <section class="hero compact">
        <div class="eyebrow">Imports</div>
        <h1>Import an album from a source URL</h1>
        <p>Paste a Metal Archives album page, review the artist draft when the artist is missing, then save the album in one pass.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Album URL Import</div>
        <form id="albumWithArtistImportForm">
          <div class="form-field">
            <label class="form-label" for="albumWithArtistSourceUrl">Source URL</label>
            <div class="input-clear-wrap">
              <input id="albumWithArtistSourceUrl" name="source_url" placeholder="https://www.metal-archives.com/albums/..." required>
              <button type="button" class="input-clear-btn" aria-label="Clear">&#x2715;</button>
            </div>
            <div class="form-note muted">
              Use the album page URL, for example https://www.metal-archives.com/albums/For_My_Pain.../Buried_Blue/1391127
            </div>
          </div>
          <div class="row">
            <button type="submit" id="albumWithArtistSubmitBtn">Create Drafts</button>
            <button type="button" id="albumWithArtistCancelBtn" class="secondary hidden">Cancel</button>
            <span class="status" id="albumWithArtistStatus"></span>
          </div>
        </form>
      </section>
      <section class="panel hidden" id="albumWithArtistReview" style="margin-top:20px;">
        <div class="panel-title">Review Import Drafts</div>
        <form id="albumWithArtistConfirmForm">
          <input type="hidden" id="bundleAlbumDraftId" name="album_draft_id">
          <input type="hidden" id="bundleArtistDraftId" name="artist_draft_id">
          <input type="hidden" id="bundleAlbumArtistName" name="album_artist_name">
          <div id="albumWithArtistExistingNotice" class="hidden" style="margin-bottom:14px; padding:10px 12px; background:rgba(46,168,124,0.12); border:1px solid rgba(46,168,124,0.32); border-radius:6px;">
            Artist already exists. This import will attach the album to the existing artist.
          </div>
          <div id="albumWithArtistArtistDraft" class="draft hidden" style="margin-bottom:16px;">
            <div class="panel-title">Artist Draft</div>
            <div class="form-field">
              <label class="form-label" for="bundleArtistName">Artist Name</label>
              <input id="bundleArtistName" name="artist_name" required disabled>
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleArtistOrigin">Origin</label>
              <input id="bundleArtistOrigin" name="artist_origin" placeholder="Country, city or region" disabled>
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleArtistDescription">Description</label>
              <textarea id="bundleArtistDescription" name="artist_description" placeholder="Description" disabled></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleArtistExternalUrl">Artist Page URL</label>
              <input id="bundleArtistExternalUrl" name="artist_external_url" placeholder="https://www.metal-archives.com/bands/..." disabled>
            </div>
          </div>
          <div class="draft">
            <div class="panel-title">Album Draft</div>
            <div class="form-field">
              <label class="form-label" for="bundleAlbumTitle">Album Name</label>
              <input id="bundleAlbumTitle" name="album_title" required>
            </div>
            <div class="grid two">
              <div class="form-field">
                <label class="form-label" for="bundleAlbumYear">Year</label>
                <input id="bundleAlbumYear" name="release_year" placeholder="Year">
              </div>
              <div class="form-field">
                <label class="form-label" for="bundleAlbumDuration">Length</label>
                <input id="bundleAlbumDuration" name="duration" placeholder="42:18">
              </div>
            </div>
            <div class="grid two">
              <div class="form-field">
                <label class="form-label" for="bundleAlbumGenre">Genre</label>
                <input id="bundleAlbumGenre" name="genre" placeholder="Genre">
              </div>
              <div class="form-field">
                <label class="form-label" for="bundleAlbumType">Type</label>
                <input id="bundleAlbumType" name="album_type" placeholder="Full-length, EP, Single">
              </div>
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleAlbumExternalUrl">Album Source URL</label>
              <input id="bundleAlbumExternalUrl" name="album_external_url" placeholder="https://...">
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleAlbumStreamUrl">Stream URL</label>
              <input id="bundleAlbumStreamUrl" name="album_stream_url" placeholder="https://...">
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleAlbumCoverUrl">Cover Source URL</label>
              <input id="bundleAlbumCoverUrl" name="cover_source_url" placeholder="https://...">
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleAlbumNotes">Notes</label>
              <textarea id="bundleAlbumNotes" name="notes" placeholder="Notes"></textarea>
            </div>
            <div class="form-field">
              <label class="form-label" for="bundleAlbumTracklist">Tracklist</label>
              <textarea id="bundleAlbumTracklist" name="tracklist_text" rows="8" placeholder="1. Track Name  3:45"></textarea>
            </div>
          </div>
          <div class="row" style="margin-top:14px;">
            <button type="submit">Confirm Import</button>
            <button type="button" class="secondary" id="albumWithArtistReset">Clear</button>
            <span class="status" id="albumWithArtistConfirmStatus"></span>
          </div>
        </form>
      </section>
      <script>
        const importForm = document.getElementById("albumWithArtistImportForm");
        const confirmForm = document.getElementById("albumWithArtistConfirmForm");
        const reviewPanel = document.getElementById("albumWithArtistReview");
        const artistDraftPanel = document.getElementById("albumWithArtistArtistDraft");
        const existingNotice = document.getElementById("albumWithArtistExistingNotice");
        const status = document.getElementById("albumWithArtistStatus");
        const confirmStatus = document.getElementById("albumWithArtistConfirmStatus");
        const bundleArtistFieldIds = [
          "bundleArtistName",
          "bundleArtistOrigin",
          "bundleArtistDescription",
          "bundleArtistExternalUrl",
        ];
        let importAbortCtrl = null;
        const setValue = (id, value) => {
          const el = document.getElementById(id);
          if (el) el.value = value ?? "";
        };
        const value = (id) => (document.getElementById(id)?.value || "").trim();
        function setArtistDraftEnabled(enabled) {
          bundleArtistFieldIds.forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.disabled = !enabled;
            if (!enabled) el.value = "";
          });
          document.getElementById("bundleArtistName").required = enabled;
        }
        document.querySelectorAll(".input-clear-wrap").forEach((wrap) => {
          const input = wrap.querySelector("input");
          const btn = wrap.querySelector(".input-clear-btn");
          const sync = () => { btn.style.display = input.value ? "block" : "none"; };
          input.addEventListener("input", sync);
          btn.addEventListener("click", () => { input.value = ""; input.dispatchEvent(new Event("input")); input.focus(); });
          sync();
        });
        function fillBundleDrafts(response) {
          const albumDraft = response.album_draft;
          const album = albumDraft.draft_payload || {};
          const artistDraft = response.artist_draft;
          setValue("bundleAlbumDraftId", albumDraft.id);
          setValue("bundleArtistDraftId", artistDraft ? artistDraft.id : "");
          existingNotice.classList.toggle("hidden", !response.artist_exists);
          artistDraftPanel.classList.toggle("hidden", !artistDraft);
          setArtistDraftEnabled(Boolean(artistDraft));
          let artistGenre = "";
          if (artistDraft) {
            const artist = artistDraft.draft_payload || {};
            artistGenre = artist.genre || "";
            setValue("bundleArtistName", artist.artist_name || album.artist_name || "");
            setValue("bundleArtistOrigin", artist.origin || "");
            setValue("bundleArtistDescription", artist.description || "");
            setValue("bundleArtistExternalUrl", artist.external_url || response.artist_source_url || "");
          }
          setValue("bundleAlbumArtistName", album.artist_name || "");
          setValue("bundleAlbumTitle", album.album_title || "");
          setValue("bundleAlbumYear", album.release_year || "");
          setValue("bundleAlbumDuration", formatDuration(album.duration_seconds));
          setValue("bundleAlbumGenre", album.genre || artistGenre || "");
          setValue("bundleAlbumType", album.album_type || "");
          setValue("bundleAlbumExternalUrl", album.album_external_url || "");
          setValue("bundleAlbumStreamUrl", album.album_stream_url || "");
          setValue("bundleAlbumCoverUrl", album.cover_source_url || "");
          setValue("bundleAlbumNotes", album.notes || "");
          setValue("bundleAlbumTracklist", (album.tracks || []).map((track) => `${track.track_number}. ${track.title}${track.duration_seconds ? "  " + formatDuration(track.duration_seconds) : ""}`).join("\\n"));
          reviewPanel.classList.remove("hidden");
          reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        function artistPayload() {
          if (!value("bundleArtistDraftId")) return null;
          return {
            name: value("bundleArtistName"),
            description: value("bundleArtistDescription") || null,
            external_url: value("bundleArtistExternalUrl") || null,
            origin: value("bundleArtistOrigin") || null,
          };
        }
        function albumPayload() {
          const artistName = value("bundleArtistDraftId")
            ? value("bundleArtistName")
            : value("bundleAlbumArtistName");
          validateRequired(artistName, "Artist name");
          validateRequired(value("bundleAlbumTitle"), "Album title");
          return {
            artist_name: artistName,
            artist_description: value("bundleArtistDescription") || null,
            album_external_url: validateUrl(value("bundleAlbumExternalUrl"), "Album source URL"),
            album_stream_url: validateUrl(value("bundleAlbumStreamUrl"), "Stream URL"),
            album_type: value("bundleAlbumType") || null,
            title: value("bundleAlbumTitle"),
            release_year: validateYear(value("bundleAlbumYear"), "Release year"),
            genre: value("bundleAlbumGenre") || null,
            rating: null,
            duration_seconds: parseDuration(value("bundleAlbumDuration")),
            cover_image_path: null,
            cover_source_url: validateUrl(value("bundleAlbumCoverUrl"), "Cover source URL"),
            notes: value("bundleAlbumNotes") || null,
            tracks: parseTracklist(document.getElementById("bundleAlbumTracklist")?.value || ""),
          };
        }
        document.getElementById("albumWithArtistCancelBtn").addEventListener("click", () => {
          if (importAbortCtrl) {
            importAbortCtrl.abort();
            importAbortCtrl = null;
          }
        });
        document.getElementById("albumWithArtistReset").addEventListener("click", () => {
          confirmForm.reset();
          reviewPanel.classList.add("hidden");
          artistDraftPanel.classList.add("hidden");
          setArtistDraftEnabled(false);
          existingNotice.classList.add("hidden");
          status.textContent = "";
          confirmStatus.textContent = "";
        });
        importForm.addEventListener("submit", async (event) => {
          event.preventDefault();
          const submitBtn = document.getElementById("albumWithArtistSubmitBtn");
          const cancelBtn = document.getElementById("albumWithArtistCancelBtn");
          let sourceUrl = "";
          try {
            sourceUrl = validateMetalArchivesAlbumUrl(document.getElementById("albumWithArtistSourceUrl").value);
          } catch (err) {
            status.textContent = err.message;
            return;
          }
          importAbortCtrl = new AbortController();
          submitBtn.disabled = true;
          cancelBtn.classList.remove("hidden");
          status.textContent = "Creating drafts...";
          try {
            const response = await fetchJson("/api/import/album-with-artist", {
              method: "POST",
              signal: importAbortCtrl.signal,
              body: JSON.stringify({
                artist_name: "",
                album_title: null,
                source_url: sourceUrl,
              }),
            });
            fillBundleDrafts(response);
            status.textContent = response.artist_draft ? "Album and artist drafts ready." : "Album draft ready.";
          } catch (err) {
            status.textContent = err.name === "AbortError" ? "Cancelled." : (err.message || "Import failed.");
          } finally {
            importAbortCtrl = null;
            submitBtn.disabled = false;
            cancelBtn.classList.add("hidden");
          }
        });
        confirmForm.addEventListener("submit", async (event) => {
          event.preventDefault();
          confirmStatus.textContent = "Saving import...";
          try {
            const result = await fetchJson("/api/import/album-with-artist/confirm", {
              method: "POST",
              body: JSON.stringify({
                album_draft_id: Number(value("bundleAlbumDraftId")),
                album_payload: albumPayload(),
                album_chosen_source_url: value("bundleAlbumExternalUrl") || null,
                artist_draft_id: value("bundleArtistDraftId") ? Number(value("bundleArtistDraftId")) : null,
                artist_payload: artistPayload(),
                artist_chosen_source_url: value("bundleArtistExternalUrl") || null,
              }),
            });
            if (result?.album?.id) {
              window.location.href = `/albums/${result.album.id}`;
            } else {
              window.location.href = "/albums";
            }
          } catch (err) {
            confirmStatus.textContent = err.message || "Save failed.";
          }
        });
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Imports | Album Ranker", "imports", body, page_state=state)


def render_albums_page(
    settings: SettingsRecord,
    albums: list[AlbumCardRecord],
    artists: list[ArtistWithAlbumsRecord],
    genres: list[GenreRecord],
    imports: list[ImportDraftRecord],
) -> str:
    recent_albums = sorted(albums, key=lambda album: (album.created_at, album.id), reverse=True)
    albums_markup = "".join(
        _album_card_markup(
            album,
            extra_class="hidden" if index >= 20 else "",
            extra_attrs=f'data-recent-index="{index}"',
        )
        for index, album in enumerate(recent_albums)
    ) or '<p class="muted">No albums yet. Head to an <a href="/artists">artist page</a> to import or create albums.</p>'
    genre_options = "".join(
        f'<option value="{_escape(genre.name)}">{_escape(genre.name)}</option>'
        for genre in genres
    )
    year_options = "".join(
        f'<option value="{year}">{year}</option>'
        for year in sorted({album.release_year for album in albums if album.release_year}, reverse=True)
    )
    artist_options = "".join(
        f'<option value="{_escape(artist.name)}">'
        for artist in artists
    )
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Albums</div>
        <h1>See the library as a wall of records</h1>
        <p>Filter by genre, year, or artist, open any cover into the full album detail view, and add manual entries from here. AI album import now lives on the Artists page so the import stays tied to the artist you picked.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Filters</div>
        <div class="filters">
          <select id="genreFilter"><option value="">Genre</option>{genre_options}</select>
          <select id="yearFilter"><option value="">Year</option>{year_options}</select>
          <input id="artistFilter" class="wide-search" type="search" list="artistDatalist" placeholder="Artist…" autocomplete="off">
          <button type="button" class="secondary" id="albumFilterClear">Clear Filters</button>
          <datalist id="artistDatalist">{artist_options}</datalist>
        </div>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Album Library</div>
        <div class="filter-meta">
          {('<p id="albumRecentHint" class="muted">Showing the 20 most recently added albums. Use filters to search the full library.</p>' if len(albums) > 20 else '<span></span>')}
          <div id="albumFilterCount" class="filter-count"></div>
        </div>
        <p id="albumFilterEmpty" class="empty-filter-state hidden">No albums match the current filters.</p>
        <div id="albumGrid" class="album-grid">{albums_markup}</div>
      </section>
      <script>
        (function () {{
          const cards = Array.from(document.querySelectorAll("#albumGrid .album-card"));
          const genreEl   = document.getElementById("genreFilter");
          const yearEl    = document.getElementById("yearFilter");
          const artistEl  = document.getElementById("artistFilter");
          const clearEl   = document.getElementById("albumFilterClear");
          function applyFilters() {{
            const genre  = genreEl.value;
            const year   = yearEl.value;
            const artist = artistEl.value.trim().toLowerCase();
            const hasFilter = Boolean(genre || year || artist);
            let visibleCount = 0;
            cards.forEach(card => {{
              const recentIndex = Number(card.dataset.recentIndex || 0);
              const isHidden =
                (genre  && !card.dataset.genre.toLowerCase().includes(genre.toLowerCase())) ||
                (year   && card.dataset.year !== year) ||
                (artist && !card.dataset.artist.toLowerCase().includes(artist)) ||
                (!hasFilter && recentIndex >= 20);
              card.classList.toggle("hidden", isHidden);
              if (!isHidden) {{
                visibleCount += 1;
              }}
            }});
            const hint = document.getElementById("albumRecentHint");
            if (hint) {{
              hint.classList.toggle("hidden", hasFilter);
            }}
            const count = document.getElementById("albumFilterCount");
            if (count) {{
              count.textContent = `Showing ${{visibleCount}} of ${{cards.length}} albums`;
            }}
            const empty = document.getElementById("albumFilterEmpty");
            if (empty) {{
              empty.classList.toggle("hidden", visibleCount > 0);
            }}
          }}
          [genreEl, yearEl, artistEl].forEach(el => {{
            el.addEventListener(el.tagName === "INPUT" ? "input" : "change", applyFilters);
          }});
          clearEl?.addEventListener("click", () => {{
            genreEl.value = "";
            yearEl.value = "";
            artistEl.value = "";
            applyFilters();
            artistEl.focus();
          }});
          applyFilters();
        }})();
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Albums | Album Ranker", "albums", body, page_state=state)


def render_bookmarks_page(settings: SettingsRecord, albums: list[AlbumCardRecord]) -> str:
    albums_markup = "".join(
        _album_card_markup(
            album,
            include_bookmark_action=True,
            include_listened_action=True,
        )
        for album in albums
    )
    empty_class = "" if not albums else "hidden"
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Bookmarks</div>
        <h1>Albums saved for later listening</h1>
        <p>Keep a focused queue of records to hear later or revisit, whether they are new to you or already listened.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="panel-title">Listen Later</div>
        <p id="bookmarkEmpty" class="muted {empty_class}">No bookmarked albums yet. <a href="/albums">Browse albums</a> to build a listening queue.</p>
        <div id="bookmarkGrid" class="album-grid">{albums_markup}</div>
      </section>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": "/albums"}
    return _shell("Bookmarks | Album Ranker", "bookmarks", body, page_state=state)


def render_album_detail_page(settings: SettingsRecord, album: AlbumDetailRecord) -> str:
    track_rows = "".join(
        f'<div class="track-row"><div class="track-num" style="display:flex;justify-content:flex-end;align-items:center;">{track.track_number}.</div><div>{_escape(track.title)}</div><div class="muted">{_escape(seconds_to_display(track.duration_seconds))}</div></div>'
        for track in album.tracks
    ) or '<p class="muted">No tracklist yet.</p>'
    description_title = "Album Description"
    raw_description_text = album.notes or "No description yet."
    description_text = _display_multiline_text(raw_description_text)
    description_source_url = album.album_external_url
    description_source_label = "Open Source" if description_source_url else ""
    star_buttons = "".join(
        f'<button type="button" class="star-btn{" on" if (album.rating or 0) >= i else ""}" data-value="{i}" aria-label="Rate {i} out of 10">&#9733;</button>'
        for i in range(1, 11)
    )
    star_initial_label = f"{album.rating}/10" if album.rating else "Rate this album"
    cover_action_label = "Change cover" if album.cover_image_path else "Upload cover"
    cover_action_title = "Click to change the cover image" if album.cover_image_path else "Click to upload a cover image"
    album_title_line = album.title + (f" - {album.release_year}" if album.release_year else "")
    body = f"""
      <section class="hero">
        <div class="eyebrow">Album Details</div>
        <h1><a href="/artists/{album.artist_id}" style="text-decoration:none;">{_escape(album.artist_name)}</a></h1>
        <p>{_escape(album_title_line)}</p>
      </section>
      <section class="detail-layout">
        <div>
          <label class="cover" for="coverFileInput" title="{cover_action_title}">
            <img id="coverImg" src="{_cover_src(album.cover_image_path)}" alt="{_escape(album.title)} cover">
            <div class="cover-upload-overlay" id="coverUploadOverlay">&#128247; {cover_action_label}</div>
          </label>
          <input type="file" id="coverFileInput" accept="image/jpeg,image/png,image/webp" style="display:none;">
          <div class="star-widget">
            <div class="star-widget-row" id="starRatingRow" data-album-id="{album.id}" data-current="{album.rating or 0}">{star_buttons}</div>
            <div class="star-widget-label" id="starWidgetLabel">{_escape(star_initial_label)}</div>
            <div class="star-widget-status" id="starWidgetStatus"></div>
          </div>
          {('<div class="row" style="margin-top:10px;gap:8px;justify-content:center;">' + (f'<a class="tag" href="{_escape(album.album_external_url)}" target="_blank" rel="noopener noreferrer">Source</a>' if album.album_external_url else '') + (f'<a class="tag" href="{_escape(album.album_stream_url)}" target="_blank" rel="noopener noreferrer">&#9654; Play</a>' if album.album_stream_url else '') + '</div>') if album.album_external_url or album.album_stream_url else ''}
          <div class="meta-stack">
            <div class="row" style="gap:8px; margin-bottom:8px;">
              {_album_detail_listen_action(album)}
            </div>
            <div class="status album-listened-state" data-album-id="{album.id}" style="text-align:center;">{"Listened" if album.listened_at else "Not Listened"}</div>
            <button type="button" id="albumEditToggle" class="secondary" style="margin-bottom:8px;" aria-controls="albumEditPanel" aria-expanded="false">Edit Album Metadata</button>
            <div style="display:flex; gap:4px; align-items:center; margin-bottom:4px;">
              <button type="button" id="albumRefreshBtn" class="secondary" title="Re-fetch metadata from source URL using AI" aria-controls="albumRefreshSourcePanel" aria-expanded="false">&#8635; Refresh Metadata</button>
            </div>
            <div id="albumRefreshSourcePanel" class="hidden" style="margin-bottom:4px;">
              <input id="albumRefreshUrlInput" class="compact-url-input" placeholder="https://..." value="{_escape(album.album_external_url)}" style="margin-bottom:4px;">
              <div style="display:flex; gap:4px; align-items:center;">
                <button type="button" id="albumRefreshGenerateBtn" style="white-space:nowrap; flex:1 1 auto;">Generate Draft</button>
                <button type="button" id="albumRefreshCancelBtn" class="secondary" style="white-space:nowrap; flex:0 0 auto;">Cancel</button>
              </div>
            </div>
            <div id="albumRefreshProgress" style="display:none; margin-bottom:4px; height:4px; border-radius:2px; background:var(--line); overflow:hidden; position:relative;">
              <div id="albumRefreshBar" style="position:absolute; height:100%; width:40%; background:var(--accent); border-radius:2px; animation:indeterminate-slide 1.4s ease-in-out infinite;"></div>
            </div>
            <div class="status compact" id="albumRefreshStatus"></div>
            <div class="danger-zone">
              <div class="panel-title">Danger Zone</div>
              <p>Delete this album from the library.</p>
              <button type="button" id="albumDeleteButton" class="danger">Delete Album</button>
            </div>
          </div>
        </div>
        <div class="grid" style="align-self:start; margin-top:0;">
          <section class="panel">
            <div class="panel-title">Tracklist</div>
            <div class="tracklist">{track_rows}</div>
            <div style="margin-top:12px; display:flex; flex-direction:column; gap:4px;">
              <div class="meta-item">
                <span class="meta-item-label">Length</span>
                {_escape(seconds_to_display(album.duration_seconds) or 'Unknown length')}
              </div>
              <div class="meta-item">
                <span class="meta-item-label">Genre</span>
                {_escape(album.genre or 'Unknown genre')}
              </div>
              <div class="meta-item">
                <span class="meta-item-label">Type</span>
                {_escape(album.album_type or 'Unknown type')}
              </div>
            </div>
          </section>
          <section class="panel hidden" id="albumEditPanel">
            <div class="detail-head">
              <div class="panel-title" style="margin-bottom:0;">Edit Album</div>
            </div>
            <form id="albumDetailForm">
              <input type="hidden" name="cover_image_path" id="coverImagePathField" value="{_escape(album.cover_image_path or '')}">
              <input type="hidden" name="cover_source_url" value="{_escape(album.cover_source_url)}">
              <div class="form-field">
                <label class="form-label" for="albumEditExternalUrl">Source URL</label>
                <input id="albumEditExternalUrl" name="album_external_url" value="{_escape(album.album_external_url)}" placeholder="https://www.metal-archives.com/albums/...">
              </div>
              <input type="hidden" name="artist_name" value="{_escape(album.artist_name)}">
              <input type="hidden" name="artist_origin" value="{_escape(album.artist_origin or '')}">
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
                  <label class="form-label" for="albumEditDuration">Length</label>
                  <input id="albumEditDuration" name="duration" value="{_escape(seconds_to_display(album.duration_seconds))}" placeholder="Length">
                </div>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditGenre">Genre</label>
                <input id="albumEditGenre" name="genre" value="{_escape(album.genre)}" placeholder="Genre">
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditStreamUrl">Stream URL</label>
                <input id="albumEditStreamUrl" name="album_stream_url" value="{_escape(album.album_stream_url)}" placeholder="https://...">
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditType">Type</label>
                <input id="albumEditType" name="album_type" value="{_escape(album.album_type or '')}" placeholder="e.g. Full-length, EP, Single">
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditDescription">Album Description</label>
                <textarea id="albumEditDescription" name="artist_description" placeholder="Album description">{_escape(album.artist_description)}</textarea>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditNotes">Notes</label>
                <textarea id="albumEditNotes" name="notes" placeholder="Notes">{_escape(album.notes)}</textarea>
              </div>
              <div class="form-field">
                <label class="form-label" for="albumEditTracklist">Tracklist</label>
                <textarea id="albumEditTracklist" name="tracklist_text" placeholder="1. Track Name  3:45&#10;2. Another Track  4:20">{_escape(chr(10).join((f"{track.track_number}. {track.title}  {seconds_to_display(track.duration_seconds)}" if track.duration_seconds else f"{track.track_number}. {track.title}") for track in album.tracks))}</textarea>
              </div>
              <div class="row">
                <button type="submit">Save Changes</button>
                <button type="button" class="secondary" id="albumEditCancel">Cancel</button>
                <span class="status" id="albumDetailStatus"></span>
              </div>
            </form>
          </section>
        </div>
      </section>
      <section class="panel hidden" id="albumRefreshReview" style="margin-top:16px; max-width:884px;">
        <div class="panel-title">Review Refreshed Metadata</div>
        <form id="albumRefreshForm">
          <input type="hidden" name="draft_id" id="albumRefreshDraftId">
          <div class="form-field">
            <label class="form-label">Title</label>
            <input name="title" id="albumRefreshTitle">
          </div>
          <div class="row">
            <div class="form-field">
              <label class="form-label">Year</label>
              <input name="release_year" id="albumRefreshYear" placeholder="Year">
            </div>
            <div class="form-field">
              <label class="form-label">Length</label>
              <input name="duration" id="albumRefreshDuration" placeholder="e.g. 42:18">
            </div>
          </div>
          <div class="form-field">
            <label class="form-label">Genre</label>
            <input name="genre" id="albumRefreshGenre" placeholder="Genre">
          </div>
          <div class="form-field">
            <label class="form-label">Type</label>
            <input name="album_type" id="albumRefreshType" placeholder="e.g. Full-length, EP">
          </div>
          <div class="form-field">
            <label class="form-label">Cover Source URL</label>
            <input name="cover_source_url" id="albumRefreshCoverUrl" placeholder="https://...">
          </div>
          <div class="form-field">
            <label class="form-label">Notes</label>
            <textarea name="notes" id="albumRefreshNotes" placeholder="Notes"></textarea>
          </div>
          <div class="form-field">
            <label class="form-label">Tracklist</label>
            <textarea name="tracklist_text" id="albumRefreshTracklist" rows="6" placeholder="1. Track Name  3:45"></textarea>
          </div>
          <div class="row">
            <button type="submit">Apply Changes</button>
            <button type="button" class="secondary" id="albumRefreshReject">Reject</button>
            <span class="status" id="albumRefreshApplyStatus"></span>
          </div>
        </form>
      </section>
      <section class="panel" style="margin-top:16px; max-width:884px;">
        <div class="panel-title">{_escape(description_title)}</div>
        {f'<a class="tag" href="{_escape(description_source_url)}" target="_blank" rel="noreferrer" style="flex:0 0 auto;">{_escape(description_source_label)}</a>' if description_source_url else ''}
        <div id="albumArtistDescription" class="clamp">{description_text}</div>
        <div class="row" style="margin-top:8px;">
          <button type="button" class="toggle-link" data-toggle-clamp="albumArtistDescription" style="flex:0 0 auto;" aria-controls="albumArtistDescription" aria-expanded="false">MORE</button>
        </div>
      </section>
      <section class="panel" style="margin-top:16px; max-width:884px;">
        <div class="detail-head" style="margin-bottom:0;">
          <div class="panel-title" style="margin-bottom:0;">Overview</div>
          <div class="row" style="gap:8px; align-items:center;">
            <label style="font-size:0.85em; color:var(--muted); display:flex; align-items:center; gap:4px; cursor:pointer;">
              <input type="radio" name="overviewLang" value="en" {"checked" if True else ""}> English
            </label>
            <label style="font-size:0.85em; color:var(--muted); display:flex; align-items:center; gap:4px; cursor:pointer;">
              <input type="radio" name="overviewLang" value="ru"> Russian
            </label>
            <button type="button" id="overviewGenerateBtn" class="secondary" style="flex:0 0 auto; font-size:0.85em;">{"✦ Regenerate" if album.overview else "✦ Generate Overview"}</button>
            <button type="button" id="overviewCancelBtn" class="secondary hidden" style="flex:0 0 auto; font-size:0.85em;">Cancel</button>
          </div>
        </div>
        <div id="overviewProgress" style="display:none; margin:8px 0 4px; height:4px; border-radius:2px; background:var(--line); overflow:hidden; position:relative;">
          <div style="position:absolute; height:100%; width:40%; background:var(--accent); border-radius:2px; animation:indeterminate-slide 1.4s ease-in-out infinite;"></div>
        </div>
        <div class="status" id="overviewStatus" style="font-size:0.85em; margin-top:6px;"></div>
        {(f'<div id="overviewDisplay" style="white-space:pre-wrap; font-size:0.95em; line-height:1.6; margin-top:12px;">{_render_overview(album.overview)}</div>') if album.overview else '<div id="overviewDisplay" style="display:none; white-space:pre-wrap; font-size:0.95em; line-height:1.6; margin-top:12px;"></div>'}
      </section>
      <section class="panel hidden" id="overviewDraftPanel" style="margin-top:16px; max-width:884px;">
        <div class="panel-title">Review Generated Overview</div>
        <div class="form-field">
          <textarea id="overviewDraftText" rows="14" style="font-family:inherit; font-size:0.92em; line-height:1.6;"></textarea>
        </div>
        <div class="row">
          <button type="button" id="overviewSaveBtn">Save Overview</button>
          <button type="button" class="secondary" id="overviewRejectBtn">Reject</button>
          <span class="status" id="overviewSaveStatus"></span>
        </div>
      </section>
      <script>
        (function() {{
          const row = document.getElementById('starRatingRow');
          const stars = Array.from(row.querySelectorAll('.star-btn'));
          const label = document.getElementById('starWidgetLabel');
          const status = document.getElementById('starWidgetStatus');
          let current = Number(row.dataset.current) || 0;
          row.setAttribute('role', 'group');
          row.setAttribute('aria-label', 'Star rating');
          function syncTabIndex() {{
            const focusIdx = current > 0 ? current - 1 : 0;
            stars.forEach((s, i) => s.setAttribute('tabindex', i === focusIdx ? '0' : '-1'));
          }}
          function highlight(n) {{
            stars.forEach((s, i) => s.classList.toggle('on', i < n));
            label.textContent = n ? n + '/10' : 'Rate this album';
          }}
          highlight(current);
          syncTabIndex();
          async function commitRating(newVal) {{
            try {{
              status.textContent = 'Saving\u2026';
              const payload = await fetchJson('/api/albums/{album.id}/rating', {{
                method: 'PATCH',
                body: JSON.stringify({{ rating: newVal }}),
              }});
              current = newVal || 0;
              row.dataset.current = current;
              highlight(current);
              syncTabIndex();
              updateAlbumListenState('{album.id}', payload);
              status.textContent = '\u2713 Saved';
              setTimeout(() => {{ status.textContent = ''; }}, 1500);
            }} catch (err) {{
              status.textContent = err.message;
            }}
          }}
          stars.forEach((star, idx) => {{
            star.addEventListener('mouseenter', () => highlight(idx + 1));
            star.addEventListener('mouseleave', () => highlight(current));
            star.addEventListener('click', () => commitRating(idx + 1 === current ? null : idx + 1));
            star.addEventListener('keydown', (e) => {{
              if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {{
                e.preventDefault();
                const next = Math.min(idx + 1, stars.length - 1);
                stars[next].setAttribute('tabindex', '0');
                stars[idx].setAttribute('tabindex', '-1');
                stars[next].focus();
                highlight(next + 1);
              }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {{
                e.preventDefault();
                const prev = Math.max(idx - 1, 0);
                stars[prev].setAttribute('tabindex', '0');
                stars[idx].setAttribute('tabindex', '-1');
                stars[prev].focus();
                highlight(prev + 1);
              }} else if (e.key === 'Enter' || e.key === ' ') {{
                e.preventDefault();
                commitRating(idx + 1 === current ? null : idx + 1);
              }}
            }});
          }});
        }})();
        (function() {{
          const coverFileInput = document.getElementById("coverFileInput");
          const coverImg = document.getElementById("coverImg");
          const coverUploadOverlay = document.getElementById("coverUploadOverlay");
          const coverStatus = document.getElementById("albumDetailStatus");
          coverFileInput.addEventListener("change", async () => {{
            const file = coverFileInput.files[0];
            if (!file) return;
            if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {{
              if (coverStatus) coverStatus.textContent = "Cover upload failed. Use JPG, PNG, or WebP.";
              coverFileInput.value = "";
              return;
            }}
            const fd = new FormData();
            fd.append("file", file);
            try {{
              const resp = await fetch("/api/albums/{album.id}/cover", {{ method: "POST", body: fd }});
              if (!resp.ok) {{
                const t = await resp.text();
                let message = "Cover upload failed. Use JPG, PNG, or WebP.";
                try {{ message = JSON.parse(t).detail || message; }} catch (err) {{}}
                if (coverStatus) coverStatus.textContent = message;
                return;
              }}
              const data = await resp.json();
              if (data.cover_image_path) {{
                const name = data.cover_image_path.split("/").pop();
                coverImg.src = "/library-data/covers/" + name + "?t=" + Date.now();
                if (coverUploadOverlay) coverUploadOverlay.textContent = "Change cover";
                const pathField = document.getElementById("coverImagePathField");
                if (pathField) pathField.value = data.cover_image_path;
                if (coverStatus) coverStatus.textContent = "Cover updated.";
              }}
            }} catch (e) {{
              if (coverStatus) coverStatus.textContent = "Cover upload failed. Check that the file is accessible and try again.";
            }}
          }});
        }})();
        const albumEditToggle = document.getElementById("albumEditToggle");
        const albumEditPanel = document.getElementById("albumEditPanel");
        const albumDeleteButton = document.getElementById("albumDeleteButton");
        function syncAlbumEditToggle() {{
          const isOpen = !albumEditPanel.classList.contains("hidden");
          albumEditToggle.textContent = isOpen ? "Close Editor" : "Edit Album Metadata";
          albumEditToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
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
        document.getElementById("albumEditCancel").addEventListener("click", () => {{
          albumEditPanel.classList.add("hidden");
          syncAlbumEditToggle();
        }});
        (function() {{
          const btn = document.getElementById('albumRefreshBtn');
          const generateBtn = document.getElementById('albumRefreshGenerateBtn');
          const cancelBtn = document.getElementById('albumRefreshCancelBtn');
          const status = document.getElementById('albumRefreshStatus');
          const progress = document.getElementById('albumRefreshProgress');
          const urlInput = document.getElementById('albumRefreshUrlInput');
          const sourcePanel = document.getElementById('albumRefreshSourcePanel');
          const reviewPanel = document.getElementById('albumRefreshReview');
          const refreshForm = document.getElementById('albumRefreshForm');
          let abortCtrl = null;
          function setSourcePanelOpen(isOpen) {{
            sourcePanel.classList.toggle('hidden', !isOpen);
            btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            if (isOpen) urlInput.focus();
          }}
          function resetRefreshUI() {{
            progress.style.display = 'none';
            btn.disabled = false;
            generateBtn.disabled = false;
            urlInput.disabled = false;
            generateBtn.textContent = 'Generate Draft';
            cancelBtn.textContent = 'Cancel';
            abortCtrl = null;
          }}
          cancelBtn.addEventListener('click', () => {{
            if (abortCtrl) {{
              abortCtrl.abort();
              setSourcePanelOpen(false);
              return;
            }}
            setSourcePanelOpen(false);
            status.textContent = '';
          }});
          document.getElementById('albumRefreshReject').addEventListener('click', () => {{
            reviewPanel.classList.add('hidden');
            status.textContent = '';
            setSourcePanelOpen(false);
          }});
          btn.addEventListener('click', () => {{
            setSourcePanelOpen(true);
          }});
          generateBtn.addEventListener('click', async () => {{
            let sourceUrl = urlInput ? urlInput.value.trim() : null;
            try {{
              if (sourceUrl) sourceUrl = validateMetalArchivesAlbumUrl(sourceUrl);
              else if (!{_json(album.album_external_url)}) throw new Error("No source URL available. Add an external URL to the album first.");
            }} catch (err) {{
              status.textContent = err.message;
              return;
            }}
            abortCtrl = new AbortController();
            btn.disabled = true;
            generateBtn.disabled = true;
            urlInput.disabled = true;
            generateBtn.textContent = 'Generating\u2026';
            cancelBtn.textContent = 'Cancel';
            status.textContent = 'Fetching source and generating metadata\u2026';
            progress.style.display = 'block';
            reviewPanel.classList.add('hidden');
            try {{
              const resp = await fetchJson('/api/import/album', {{
                method: 'POST',
                signal: abortCtrl.signal,
                body: JSON.stringify({{ artist_name: {_json(album.artist_name)}, album_title: {_json(album.title)}, source_url: sourceUrl || {_json(album.album_external_url)} }}),
              }});
              const draft = resp.draft;
              const p = draft.draft_payload;
              document.getElementById('albumRefreshDraftId').value = draft.id;
              document.getElementById('albumRefreshTitle').value = p.album_title || '';
              document.getElementById('albumRefreshYear').value = p.release_year || '';
              document.getElementById('albumRefreshDuration').value = p.duration_seconds ? formatDuration(p.duration_seconds) : '';
              document.getElementById('albumRefreshGenre').value = p.genre || '';
              document.getElementById('albumRefreshType').value = p.album_type || '';
              document.getElementById('albumRefreshCoverUrl').value = p.cover_source_url || '';
              document.getElementById('albumRefreshNotes').value = p.notes || '';
              document.getElementById('albumRefreshTracklist').value = (p.tracks || []).map(t => `${{t.track_number}}. ${{t.title}}${{t.duration_seconds ? '  ' + formatDuration(t.duration_seconds) : ''}}`).join('\\n');
              resetRefreshUI();
              setSourcePanelOpen(false);
              status.textContent = 'Draft ready \u2014 review below.';
              reviewPanel.classList.remove('hidden');
              reviewPanel.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }} catch (err) {{
              resetRefreshUI();
              status.textContent = err.name === 'AbortError' ? 'Cancelled.' : (err.message || 'Refresh failed.');
            }}
          }});
          refreshForm.addEventListener('submit', async (e) => {{
            e.preventDefault();
            const applyStatus = document.getElementById('albumRefreshApplyStatus');
            applyStatus.textContent = 'Saving\u2026';
            try {{
              validateRequired(document.getElementById('albumRefreshTitle').value, 'Album title');
              await fetchJson('/api/albums/{album.id}', {{
                method: 'PUT',
                body: JSON.stringify({{
                  artist_name: {_json(album.artist_name)},
                  artist_description: {_json(album.artist_description)},
                  artist_origin: {_json(album.artist_origin)},
                  title: document.getElementById('albumRefreshTitle').value.trim(),
                  release_year: validateYear(document.getElementById('albumRefreshYear').value, 'Release year'),
                  duration_seconds: parseDuration(document.getElementById('albumRefreshDuration').value),
                  genre: document.getElementById('albumRefreshGenre').value.trim() || null,
                  album_type: document.getElementById('albumRefreshType').value.trim() || null,
                  cover_source_url: validateUrl(document.getElementById('albumRefreshCoverUrl').value, 'Cover source URL'),
                  cover_image_path: {_json(album.cover_image_path)},
                  album_external_url: {_json(album.album_external_url)},
                  album_stream_url: {_json(album.album_stream_url)},
                  rating: {_json(album.rating)},
                  notes: document.getElementById('albumRefreshNotes').value.trim() || null,
                  tracks: parseTracklist(document.getElementById('albumRefreshTracklist').value),
                }}),
              }});
              applyStatus.textContent = '\u2713 Saved \u2014 reloading\u2026';
              setSourcePanelOpen(false);
              window.location.reload();
            }} catch (err) {{
              applyStatus.textContent = err.message || 'Save failed.';
            }}
          }});
        }})();
        albumDeleteButton.addEventListener("click", async () => {{
          if (!window.confirm(`Delete ${{{_json(album.artist_name)}}} - ${{{_json(album.title)}}}?`)) return;
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
            validateRequired(form.artist_name.value, "Artist name");
            validateRequired(form.title.value, "Album title");
            await fetchJson("/api/albums/{album.id}", {{
              method: "PUT",
              body: JSON.stringify({{
                artist_name: form.artist_name.value.trim(),
                artist_origin: form.artist_origin.value.trim() || null,
                artist_description: form.artist_description.value.trim() || null,
                album_external_url: validateUrl(form.album_external_url.value, "Album source URL"),
                album_stream_url: validateUrl(form.album_stream_url.value, "Stream URL"),
                album_type: form.album_type.value.trim() || null,
                title: form.title.value.trim(),
                release_year: validateYear(form.release_year.value, "Release year"),
                genre: form.genre.value.trim() || null,
                rating: validateRating(document.getElementById('starRatingRow').dataset.current),
                duration_seconds: parseDuration(form.duration.value),
                cover_image_path: form.cover_image_path.value.trim() || null,
                cover_source_url: validateUrl(form.cover_source_url.value, "Cover source URL"),
                notes: form.notes.value.trim() || null,
                tracks: parseTracklist(form.tracklist_text.value),
              }}),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message;
          }}
        }});
        (function() {{
          const generateBtn = document.getElementById('overviewGenerateBtn');
          const cancelBtn = document.getElementById('overviewCancelBtn');
          const progress = document.getElementById('overviewProgress');
          const statusEl = document.getElementById('overviewStatus');
          const draftPanel = document.getElementById('overviewDraftPanel');
          const draftText = document.getElementById('overviewDraftText');
          const saveBtn = document.getElementById('overviewSaveBtn');
          const rejectBtn = document.getElementById('overviewRejectBtn');
          const saveStatus = document.getElementById('overviewSaveStatus');
          const display = document.getElementById('overviewDisplay');
          let abortCtrl = null;

          function resetGenerateUI() {{
            progress.style.display = 'none';
            generateBtn.disabled = false;
            generateBtn.classList.remove('hidden');
            cancelBtn.classList.add('hidden');
            abortCtrl = null;
          }}

          cancelBtn.addEventListener('click', () => {{
            if (abortCtrl) abortCtrl.abort();
          }});

          generateBtn.addEventListener('click', async () => {{
            const lang = document.querySelector('input[name="overviewLang"]:checked')?.value || 'en';
            abortCtrl = new AbortController();
            generateBtn.classList.add('hidden');
            cancelBtn.classList.remove('hidden');
            statusEl.textContent = 'Generating overview\u2026';
            progress.style.display = 'block';
            draftPanel.classList.add('hidden');
            try {{
              const resp = await fetchJson('/api/albums/{album.id}/overview/draft', {{
                method: 'POST',
                signal: abortCtrl.signal,
                body: JSON.stringify({{ language: lang }}),
              }});
              draftText.value = resp.overview || '';
              resetGenerateUI();
              statusEl.textContent = 'Draft ready \u2014 review below.';
              draftPanel.classList.remove('hidden');
              draftPanel.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }} catch (err) {{
              resetGenerateUI();
              statusEl.textContent = err.name === 'AbortError' ? 'Cancelled.' : (err.message || 'Generation failed.');
            }}
          }});

          rejectBtn.addEventListener('click', () => {{
            draftPanel.classList.add('hidden');
            statusEl.textContent = '';
          }});

          saveBtn.addEventListener('click', async () => {{
            saveStatus.textContent = 'Saving\u2026';
            const text = draftText.value.trim() || null;
            try {{
              await fetchJson('/api/albums/{album.id}/overview', {{
                method: 'PATCH',
                body: JSON.stringify({{ overview: text }}),
              }});
              saveStatus.textContent = '\u2713 Saved \u2014 reloading\u2026';
              window.location.reload();
            }} catch (err) {{
              saveStatus.textContent = err.message || 'Save failed.';
            }}
          }});
        }})();
      </script>
    """
    state = {"settings": settings.model_dump(), "album_detail_link": f"/albums/{album.id}"}
    return _shell(f"{album.title} | Album Ranker", "details", body, page_state=state)


def render_lists_page(settings: SettingsRecord, lists: list[AlbumListRecord], albums: list[AlbumCardRecord], genres: list[GenreRecord]) -> str:
    list_markup = "".join(_list_markup(record, all_albums=albums) for record in lists) or '<p class="muted">No ranking lists yet.</p>'
    has_lists = bool(lists)
    existing_list_names = _json([lst.name for lst in lists])
    unique_years = sorted({a.release_year for a in albums if a.release_year}, reverse=True)
    year_options = "<option value=''>All time</option>" + "".join(
        f"<option value='{y}'>{y}</option>" for y in unique_years
    )
    sorted_genres = sorted(genres, key=lambda g: g.name)
    all_genres_json = _json([g.name for g in sorted_genres])
    no_genres_msg = '<p class="muted" style="font-size:13px;">No genres configured. Add some on the Genres page.</p>'
    def _genre_picker_html(picker_id: str) -> str:
        if not sorted_genres:
            return no_genres_msg
        return (
            f'<div class="genre-tag-picker" data-genre-picker id="{picker_id}">'
            f'<select class="genre-pick-select"></select>'
            f'<div class="genre-tag-chips"></div>'
            f'</div>'
        )
    genre_picker_create = _genre_picker_html("createGenrePicker")
    genre_picker_br = _genre_picker_html("brGenrePicker")
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Lists</div>
        <h1>Rank albums into actual tops</h1>
        <p>Create focused lists, add albums from your library, then drag or button them into the order that actually reflects preference.</p>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head">
          <div class="panel-title" style="margin-bottom:0;">Create List</div>
          {('<button type="button" id="listToolsToggle" class="secondary" title="Toggle create list" aria-controls="listToolsPanel" aria-expanded="false">Show</button>' if has_lists else '')}
        </div>
        <div id="listToolsPanel" class="{('hidden' if has_lists else '')}" style="margin-top:14px;">
          <div class="row" role="tablist" aria-label="Create list mode" style="margin-bottom:16px; gap:8px;">
            <button type="button" id="create-tab-button-manual" class="create-tab secondary active" data-tab="manual" role="tab" aria-selected="true" aria-controls="create-tab-manual">Manual</button>
            <button type="button" id="create-tab-button-best-rated" class="create-tab secondary" data-tab="best-rated" role="tab" aria-selected="false" aria-controls="create-tab-best-rated">&#9733; Best Rated</button>
          </div>
          <div id="create-tab-manual" role="tabpanel" aria-labelledby="create-tab-button-manual">
            <form id="listForm">
              <input name="name" placeholder="List name" required>
              <textarea name="description" placeholder="Description"></textarea>
              <div class="form-field">
                <label class="form-label">Year</label>
                <input name="year" placeholder="Year" style="max-width:120px;">
              </div>
              <div class="form-field">
                <label class="form-label">Genres</label>
                {genre_picker_create}
              </div>
              <div class="row">
                <button type="submit">Create List</button>
                <span class="status" id="listFormStatus"></span>
              </div>
            </form>
          </div>
          <div id="create-tab-best-rated" class="hidden" role="tabpanel" aria-labelledby="create-tab-button-best-rated" hidden>
            <div class="row">
              <div class="form-field" style="flex:1;">
                <label class="form-label">Time period</label>
                <select id="brYear">{year_options}</select>
              </div>
              <div class="form-field" style="flex:0 0 100px;">
                <label class="form-label">How many</label>
                <input id="brLimit" type="number" min="1" max="500" value="10" style="width:100%;">
              </div>
            </div>
            <div class="form-field" style="margin-top:8px;">
              <label class="form-label">Genres (leave empty for all)</label>
              {genre_picker_br}
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
      </section>
      <div style="margin:16px 0 8px;">
        <input id="listSearch" type="search" placeholder="Search lists…" style="width:100%; max-width:400px;">
      </div>
      <section class="grid" style="margin-top:8px;">{list_markup}</section>
      <script>
        const existingListNames = {existing_list_names};
        const allGenres = {all_genres_json};
        const listToolsPanel = document.getElementById("listToolsPanel");
        const listToolsToggle = document.getElementById("listToolsToggle");
        function syncListToolsToggle() {{
          if (!listToolsToggle) return;
          const isOpen = !listToolsPanel.classList.contains("hidden");
          listToolsToggle.textContent = isOpen ? "Hide" : "Show";
          listToolsToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }}
        listToolsToggle?.addEventListener("click", () => {{
          listToolsPanel.classList.toggle("hidden");
          syncListToolsToggle();
        }});

        // ── Create List tabs ─────────────────────────────────────────────────
        document.querySelectorAll(".create-tab").forEach((btn) => {{
          btn.addEventListener("click", () => {{
            document.querySelectorAll(".create-tab").forEach((b) => {{
              b.classList.remove("active");
              b.setAttribute("aria-selected", "false");
            }});
            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
            const manualPanel = document.getElementById("create-tab-manual");
            const bestRatedPanel = document.getElementById("create-tab-best-rated");
            manualPanel.classList.toggle("hidden", btn.dataset.tab !== "manual");
            bestRatedPanel.classList.toggle("hidden", btn.dataset.tab !== "best-rated");
            manualPanel.toggleAttribute("hidden", btn.dataset.tab !== "manual");
            bestRatedPanel.toggleAttribute("hidden", btn.dataset.tab !== "best-rated");
          }});
        }});

        // ── Genre pickers ────────────────────────────────────────────────────
        const createPicker = document.getElementById("createGenrePicker");
        const brPicker = document.getElementById("brGenrePicker");

        // Best Rated wizard ───────────────────────────────────────────────────
        function getBrGenres() {{
          return brPicker ? brPicker._getGenres() : [];
        }}
        function buildBestRatedName() {{
          const year = document.getElementById("brYear").value;
          const genres = getBrGenres();
          const limit = document.getElementById("brLimit").value || "10";
          let name = "Best Rated";
          if (genres.length) name += " " + genres.join(", ");
          if (year) name += " " + year;
          name += " (Top " + limit + ")";
          return name;
        }}
        function syncBestRatedName() {{
          const nameInput = document.getElementById("brName");
          nameInput.value = buildBestRatedName();
        }}
        document.getElementById("brYear").addEventListener("change", syncBestRatedName);
        document.getElementById("brYear").addEventListener("input", syncBestRatedName);
        document.getElementById("brLimit").addEventListener("change", syncBestRatedName);
        document.getElementById("brLimit").addEventListener("input", syncBestRatedName);
        if (createPicker) initGenrePicker(createPicker, allGenres, []);
        if (brPicker) initGenrePicker(brPicker, allGenres, [], syncBestRatedName);
        syncBestRatedName();

        async function submitBestRated(name, updateExisting) {{
          const status = document.getElementById("brStatus");
          const year = document.getElementById("brYear").value;
          const genres = getBrGenres();
          const limit = Number(document.getElementById("brLimit").value) || 10;
          try {{
            validateRequired(name, "List name");
            if (!Number.isInteger(limit) || limit < 1 || limit > 500) throw new Error("List size must be between 1 and 500.");
            status.textContent = "Generating\u2026";
            await fetchJson("/api/auto-lists/best-rated", {{
              method: "POST",
              body: JSON.stringify({{
                name,
                limit,
                year: year ? Number(year) : null,
                genres,
                update_existing: updateExisting,
              }}),
            }});
            sessionStorage.setItem("expandListName", name);
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

        document.querySelectorAll(".regenerate-list").forEach((btn) => {{
          btn.addEventListener("click", async (e) => {{
            e.stopPropagation();
            const block = btn.closest(".list-block");
            const status = block.querySelector(".regenerate-status");
            const name = block.dataset.listName;
            const year = block.dataset.listYear ? Number(block.dataset.listYear) : null;
            let genres = [];
            try {{ genres = JSON.parse(block.dataset.listGenres || "[]"); }} catch(err) {{ genres = []; }}
            const limit = Number(block.dataset.listLimit) || 10;
            status.textContent = "Regenerating\u2026";
            btn.disabled = true;
            try {{
              await fetchJson("/api/auto-lists/best-rated", {{
                method: "POST",
                body: JSON.stringify({{ name, limit, year, genres, update_existing: true }}),
              }});
              window.location.hash = "list-body-" + block.dataset.listId;
              window.location.reload();
            }} catch (err) {{
              status.textContent = err.message;
              btn.disabled = false;
            }}
          }});
        }});
        document.getElementById("listForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("listFormStatus");
          try {{
            status.textContent = "Saving...";
            validateRequired(form.name.value, "List name");
            const genres = createPicker ? createPicker._getGenres() : [];
            await fetchJson("/api/lists", {{
              method: "POST",
              body: JSON.stringify({{
                name: form.name.value.trim(),
                description: form.description.value.trim() || null,
                year: validateYear(form.year.value, "Year"),
                genres,
              }}),
            }});
            sessionStorage.setItem("expandListName", form.name.value.trim());
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message || "Save failed.";
          }}
        }});
        document.querySelectorAll(".list-head[data-toggle]").forEach((head) => {{
          function syncListToggle(body) {{
            const btn = head.querySelector(".list-toggle-btn");
            if (!btn) return;
            const isOpen = !body.classList.contains("hidden");
            btn.innerHTML = isOpen ? "&#9650;" : "&#9660;";
            btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
            btn.setAttribute("aria-label", isOpen ? "Hide list items" : "Show list items");
          }}
          function doToggle() {{
            const body = document.getElementById(head.dataset.toggle);
            if (!body) return;
            body.classList.toggle("hidden");
            syncListToggle(body);
          }}
          head.addEventListener("click", (e) => {{
            if (!e.target.closest(".list-toggle-btn")) doToggle();
          }});
          const toggleBtn = head.querySelector(".list-toggle-btn");
          if (toggleBtn) {{
            toggleBtn.addEventListener("click", (e) => {{
              e.stopPropagation();
              doToggle();
            }});
          }}
        }});
        document.getElementById("listSearch").addEventListener("input", (e) => {{
          const q = e.target.value.toLowerCase().trim();
          document.querySelectorAll(".list-block").forEach((block) => {{
            block.style.display = (!q || block.dataset.name.includes(q)) ? "" : "none";
          }});
        }});
        // Auto-expand a list after regenerate (hash = "list-body-<id>")
        const expandId = location.hash.replace("#", "");
        if (expandId.startsWith("list-body-")) {{
          const target = document.getElementById(expandId);
          if (target) {{
            target.classList.remove("hidden");
            const head = target.closest(".list-block")?.querySelector(".list-head");
            const btn = head?.querySelector(".list-toggle-btn");
            if (btn) {{
              btn.innerHTML = "&#9650;";
              btn.setAttribute("aria-expanded", "true");
              btn.setAttribute("aria-label", "Hide list items");
            }}
            target.scrollIntoView({{ behavior: "smooth", block: "start" }});
            history.replaceState(null, "", location.pathname + location.search);
          }}
        }}
        // Auto-expand a list after create/generate (sessionStorage key)
        const expandName = sessionStorage.getItem("expandListName");
        if (expandName) {{
          sessionStorage.removeItem("expandListName");
          const block = [...document.querySelectorAll(".list-block")].find(
            (b) => b.dataset.listName === expandName
          );
          if (block) {{
            const body = document.getElementById("list-body-" + block.dataset.listId);
            if (body) {{
              body.classList.remove("hidden");
              const btn = block.querySelector(".list-toggle-btn");
              if (btn) {{
                btn.innerHTML = "&#9650;";
                btn.setAttribute("aria-expanded", "true");
                btn.setAttribute("aria-label", "Hide list items");
              }}
              block.scrollIntoView({{ behavior: "smooth", block: "start" }});
            }}
          }}
        }}
        // Restore open lists after bookmark/listened reload
        const openListIds = JSON.parse(sessionStorage.getItem("openListIds") || "null");
        if (openListIds) {{
          sessionStorage.removeItem("openListIds");
          openListIds.forEach((id) => {{
            const body = document.getElementById("list-body-" + id);
            if (body) {{
              body.classList.remove("hidden");
              const btn = body.closest(".list-block")?.querySelector(".list-toggle-btn");
              if (btn) {{
                btn.innerHTML = "&#9650;";
                btn.setAttribute("aria-expanded", "true");
                btn.setAttribute("aria-label", "Hide list items");
              }}
            }}
          }});
        }}
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
          const addToggle = block.querySelector(".list-add-toggle");
          const addPanel = block.querySelector(".list-add-panel");
          if (addToggle && addPanel) {{
            addToggle.addEventListener("click", (e) => {{
              e.stopPropagation();
              addPanel.classList.toggle("hidden");
              const isOpen = !addPanel.classList.contains("hidden");
              addToggle.textContent = isOpen ? "\u2715 Cancel" : "+ Add album";
              addToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
            }});
            const picker = addPanel.querySelector(".list-add-picker");
            const hiddenId = addPanel.querySelector(".list-add-album-id");
            const suggestions = addPanel.querySelector(".list-add-suggestions");
            let albums = []; try {{ albums = JSON.parse(addPanel.getAttribute("data-albums") || "[]"); }} catch(err) {{ console.error("list-add: bad albums JSON", err); }}
            function renderSuggestions(q) {{
              const ql = q.toLowerCase();
              if (!ql) {{ suggestions.style.display = "none"; return; }}
              const scored = albums
                .filter((a) => a.label.toLowerCase().includes(ql))
                .map((a) => {{
                  const l = a.label.toLowerCase();
                  const idx = l.indexOf(ql);
                  const score = idx === 0 ? 0 : (idx > 0 && !/[a-z0-9]/.test(l[idx - 1])) ? 1 : 2;
                  return {{ ...a, score }};
                }})
                .sort((a, b) => a.score - b.score)
                .slice(0, 50);
              const matches = scored;
              suggestions.innerHTML = matches.map((a) =>
                `<li data-id="${{a.id}}" style="padding:8px 12px; cursor:pointer; font-size:14px;">${{a.label}}</li>`
              ).join("");
              suggestions.style.display = matches.length ? "block" : "none";
              suggestions.querySelectorAll("li").forEach((li) => {{
                li.addEventListener("mousedown", (e) => {{
                  e.preventDefault();
                  picker.value = li.textContent;
                  hiddenId.value = li.dataset.id;
                  suggestions.style.display = "none";
                }});
                li.addEventListener("mouseover", () => li.style.background = "rgba(255,255,255,0.08)");
                li.addEventListener("mouseout", () => li.style.background = "");
              }});
            }}
            picker.addEventListener("input", () => {{
              hiddenId.value = "";
              renderSuggestions(picker.value);
            }});
            picker.addEventListener("blur", () => setTimeout(() => {{ suggestions.style.display = "none"; }}, 150));
            picker.addEventListener("focus", () => {{ if (picker.value) renderSuggestions(picker.value); }});
            addPanel.querySelector(".list-add-form").addEventListener("submit", async (e) => {{
              e.preventDefault();
              const status = addPanel.querySelector(".list-add-status");
              if (!hiddenId.value) {{ status.textContent = "Choose an album."; return; }}
              status.textContent = "Adding\u2026";
              try {{
                await fetchJson(`/api/lists/${{listId}}/items`, {{
                  method: "POST",
                  body: JSON.stringify({{ album_id: Number(hiddenId.value) }}),
                }});
                window.location.reload();
              }} catch (err) {{
                status.textContent = err.message;
              }}
            }});
          }}
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
    _themes = [
        ("dark", "Dark", "Deep blue-black — the default dark theme."),
        ("dark-brown", "Dark Brown", "Warm dark brown with amber accents."),
        ("dark-green", "Dark Green", "Deep forest green — dark theme with a green tint."),
    ]
    theme_options = "".join(
        f"""<label class="theme-option{' theme-option--active' if t_val == settings.theme else ''}" data-theme-value="{_escape(t_val)}">
              <input type="radio" name="theme" value="{_escape(t_val)}"{' checked' if t_val == settings.theme else ''}>
              <span class="theme-option-name">{_escape(t_label)}</span>
              <span class="theme-option-desc">{_escape(t_desc)}</span>
            </label>"""
        for t_val, t_label, t_desc in _themes
    )
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Settings</div>
        <h1>Keep AI optional and visible</h1>
        <p>Choose the active OpenAI model used for draft generation, and pick a colour theme for the interface.</p>
      </section>
      <section class="grid two">
        <section class="panel">
          <div class="panel-title">Model</div>
          <form id="settingsForm">
            <select name="active_model">{options}</select>
            <div class="panel-title" style="margin-top:20px;">Theme</div>
            <div class="theme-picker">{theme_options}</div>
            <div class="row" style="margin-top:16px;">
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
      <style>
        .theme-picker {{
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 8px;
        }}
        .theme-option {{
          display: flex;
          flex-direction: column;
          gap: 2px;
          padding: 10px 14px;
          border: 1px solid var(--line);
          border-radius: 8px;
          cursor: pointer;
          transition: border-color 0.15s;
        }}
        .theme-option input[type="radio"] {{
          display: none;
        }}
        .theme-option:hover {{
          border-color: var(--accent);
        }}
        .theme-option--active {{
          border-color: var(--accent);
          background: rgba(255, 122, 61, 0.06);
        }}
        .theme-option-name {{
          font-weight: 600;
          font-size: 0.92em;
          color: var(--ink);
        }}
        .theme-option-desc {{
          font-size: 0.82em;
          color: var(--muted);
        }}
      </style>
      <script>
        document.querySelectorAll(".theme-option").forEach((el) => {{
          el.addEventListener("click", () => {{
            document.querySelectorAll(".theme-option").forEach((o) => o.classList.remove("theme-option--active"));
            el.classList.add("theme-option--active");
            el.querySelector("input[type=radio]").checked = true;
            // Live-preview the theme without saving
            document.documentElement.setAttribute("data-theme", el.dataset.themeValue);
          }});
        }});
        document.getElementById("settingsForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("settingsStatus");
          try {{
            status.textContent = "Saving...";
            validateRequired(form.active_model.value, "Model");
            const selectedTheme = form.querySelector("input[name=theme]:checked")?.value || "dark";
            await fetchJson("/api/settings", {{
              method: "PUT",
              body: JSON.stringify({{ active_model: form.active_model.value, theme: selectedTheme }}),
            }});
            status.textContent = "Settings saved.";
            setTimeout(() => window.location.reload(), 600);
          }} catch (error) {{
            status.textContent = error.message || "Save failed.";
          }}
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
      <section class="hero compact">
        <div class="eyebrow">Genres</div>
        <h1>Manage the filter list manually</h1>
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
            <div id="genreDuplicateWarning" class="warning-box hidden">
              A genre named <strong id="genreDuplicateName"></strong> already exists. Saving will keep the existing genre.
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
            validateRequired(form.name.value, "Genre name");
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
          document.getElementById("genreDuplicateWarning").classList.add("hidden");
        }});
        // ── Genre duplicate detection ─────────────────────────────────────────
        (function() {{
          const nameInput = document.getElementById("genreName");
          const warning = document.getElementById("genreDuplicateWarning");
          const dupName = document.getElementById("genreDuplicateName");
          const form = document.getElementById("genreForm");
          nameInput.addEventListener("input", () => {{
            const val = nameInput.value.trim().toLowerCase();
            const currentId = form.genre_id.value.trim();
            const match = val && Array.from(document.querySelectorAll(".edit-genre")).find(btn => {{
              return btn.dataset.genreName.trim().toLowerCase() === val && btn.dataset.genreId !== currentId;
            }});
            if (match) {{
              dupName.textContent = match.dataset.genreName;
              warning.classList.remove("hidden");
            }} else {{
              warning.classList.add("hidden");
            }}
          }});
        }})();
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


def render_list_detail_page(settings: SettingsRecord, record: AlbumListRecord, albums: list[AlbumCardRecord], genres: list[GenreRecord]) -> str:
    items_markup = _list_markup(record)
    sorted_genres = sorted(genres, key=lambda g: g.name)
    all_genres_json = _json([g.name for g in sorted_genres])
    initial_genres_json = _json(record.genres)
    genre_picker_detail = (
        '<div class="genre-tag-picker" data-genre-picker id="detailGenrePicker">'
        '<select class="genre-pick-select"></select>'
        '<div class="genre-tag-chips"></div>'
        '</div>'
        if sorted_genres
        else '<p class="muted" style="font-size:13px;">No genres configured. Add some on the Genres page.</p>'
    )
    body = f"""
      <section class="hero compact">
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
          <div class="form-field">
            <label class="form-label" for="listDetailYear">Year</label>
            <input id="listDetailYear" name="year" value="{_escape(str(record.year or ''))}" placeholder="Year" style="max-width:120px;">
          </div>
          <div class="form-field">
            <label class="form-label">Genres</label>
            {genre_picker_detail}
          </div>
          <div class="row">
            <button type="submit">Save Details</button>
            <span class="status" id="listDetailStatus"></span>
          </div>
        </form>
      </section>
      <section class="panel" style="margin-top:20px;">
        <div class="detail-head" style="justify-content:flex-end;">
          <a class="button-link secondary" href="/lists">Back to Lists</a>
        </div>
      </section>
      <section class="grid" style="margin-top:20px;">{items_markup}</section>
      <script>
        const allGenresDetail = {all_genres_json};
        const initialGenresDetail = {initial_genres_json};
        const detailPicker = document.getElementById("detailGenrePicker");
        if (detailPicker) initGenrePicker(detailPicker, allGenresDetail, initialGenresDetail);

        document.getElementById("listDetailForm").addEventListener("submit", async (event) => {{
          event.preventDefault();
          const form = event.currentTarget;
          const status = document.getElementById("listDetailStatus");
          try {{
            status.textContent = "Saving...";
            validateRequired(form.name.value, "List name");
            const genres = detailPicker ? detailPicker._getGenres() : [];
            await fetchJson("/api/lists/{record.id}", {{
              method: "PUT",
              body: JSON.stringify({{
                name: form.name.value.trim(),
                description: form.description.value.trim() || null,
                year: validateYear(form.year.value, "Year"),
                genres,
              }}),
            }});
            window.location.reload();
          }} catch (error) {{
            status.textContent = error.message;
          }}
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
