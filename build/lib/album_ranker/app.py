from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from album_ranker.db import Database
from album_ranker.importer import (
    CoverDownloader,
    MetadataImporter,
    draft_to_json,
    infer_cover_source_url_from_album_url,
    metal_archives_album_draft_from_url,
    metal_archives_artist_url_from_album_url,
)
from album_ranker.openai_client import OpenAIClient
from album_ranker.schemas import (
    AlbumBookmarkPatch,
    AlbumDetailRecord,
    AlbumListenedPatch,
    AlbumRatingPatch,
    AlbumWithArtistConfirmRequest,
    AlbumWithArtistImportResponse,
    AlbumListItemAddRequest,
    AlbumListRecord,
    AlbumListUpsert,
    AlbumUpsert,
    AutoListBestRatedRequest,
    GenreRecord,
    GenreUpsert,
    ArtistRecord,
    ArtistUpsert,
    HealthResponse,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportDraftResponse,
    ImportRequest,
    OverviewDraftRequest,
    OverviewDraftResponse,
    OverviewSaveRequest,
    RefreshAlbumRequest,
    ReorderListItemsRequest,
    SettingsRecord,
    SettingsUpdateRequest,
    TrackUpsert,
)
from album_ranker.settings import Settings
from album_ranker.ui import (
    render_album_detail_page,
    render_albums_page,
    render_artist_detail_page,
    render_artists_page,
    render_bookmarks_page,
    render_genres_page,
    render_imports_page,
    render_list_detail_page,
    render_lists_page,
    render_settings_page,
)


def _resolve_album_cover(
    album_upsert: AlbumUpsert,
    payload: dict[str, object] | None,
    cover_downloader: CoverDownloader,
) -> AlbumUpsert:
    resolved_cover_source_url = album_upsert.cover_source_url or infer_cover_source_url_from_album_url(album_upsert.album_external_url)
    if resolved_cover_source_url and resolved_cover_source_url != album_upsert.cover_source_url:
        album_upsert = album_upsert.model_copy(update={"cover_source_url": resolved_cover_source_url})
        if payload is not None:
            payload["cover_source_url"] = resolved_cover_source_url
    if album_upsert.cover_source_url:
        stem = f"{album_upsert.artist_name}-{album_upsert.title}".lower().replace(" ", "-")
        try:
            local_path = cover_downloader.download(album_upsert.cover_source_url, stem=stem)
        except Exception:
            local_path = None
        if local_path:
            album_upsert = album_upsert.model_copy(update={"cover_image_path": local_path})
            if payload is not None:
                payload["cover_image_path"] = local_path
    return album_upsert


def _validate_album_source_url(source_url: str | None) -> None:
    if not source_url:
        return
    parsed_source = urlparse(source_url)
    if "metal-archives.com" in parsed_source.netloc.lower() and not parsed_source.path.startswith("/albums/"):
        raise HTTPException(
            status_code=400,
            detail="Paste a Metal Archives album URL from /albums/..., not an artist page URL.",
        )


def _validation_message(field: str, message: str) -> str:
    normalized = message.replace("Value error, ", "")
    field_labels = {
        "active_model": "Model",
        "artist_name": "Artist name",
        "album_title": "Album title",
        "title": "Album title",
        "name": "Name",
        "release_year": "Release year",
        "year": "Year",
        "rating": "Rating",
        "duration_seconds": "Duration",
        "duration": "Duration",
        "track_number": "Track number",
        "language": "Overview language",
        "limit": "List size",
    }
    label = field_labels.get(field, field.replace("_", " ").title())
    if normalized == "Field required":
        return f"{label} is required."
    if "greater than or equal to 1000" in normalized or "less than or equal to 9999" in normalized:
        return f"{label} must be a four-digit year."
    if "greater than or equal to 1" in normalized and ("rating" in field or "limit" in field):
        return f"{label} must be at least 1."
    if "less than or equal to 10" in normalized and "rating" in field:
        return "Rating must be between 1 and 10."
    if "less than or equal to 500" in normalized and "limit" in field:
        return "List size must be between 1 and 500."
    if "Input should be 'en' or 'ru'" in normalized:
        return "Overview language must be English or Russian."
    return f"{label}: {normalized}"


def _validation_detail(errors: list[dict[str, object]]) -> str:
    messages = []
    for error in errors:
        loc = [str(part) for part in error.get("loc", []) if part not in ("body", "query", "path")]
        field = loc[-1] if loc else "value"
        messages.append(_validation_message(field, str(error.get("msg", "Invalid value"))))
    return " ".join(dict.fromkeys(messages)) or "Check the highlighted fields and try again."


def _friendly_ai_error(exc: Exception, *, action: str) -> str:
    detail = str(exc)
    if "OPENAI_API_KEY is not configured" in detail:
        return "AI is not configured. Add OPENAI_API_KEY and restart the app."
    if "Unexpected OpenAI response shape" in detail or "not a JSON object" in detail:
        return f"AI returned {action} in an unexpected format. Try regenerating."
    if "OpenAI request failed" in detail:
        return "AI request failed. Check your connection, API key, or model setting, then try again."
    return detail or f"{action.capitalize()} failed. Try again."


def _error_page(title: str, message: str, back_href: str = "/albums", back_label: str = "Back To Albums") -> str:
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} | Album Ranker</title>
    <style>
      body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#101114; color:#f2f0ea; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      main {{ width:min(560px, calc(100vw - 32px)); }}
      h1 {{ margin:0 0 10px; font-size:32px; }}
      p {{ color:#b8b2a8; line-height:1.5; }}
      a {{ display:inline-flex; margin-top:14px; padding:11px 16px; border-radius:999px; background:#f0b35a; color:#15100a; text-decoration:none; font-weight:700; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      <p>{message}</p>
      <a href="{back_href}">{back_label}</a>
    </main>
  </body>
</html>"""


def create_app(
    settings: Settings,
    *,
    importer: MetadataImporter | None = None,
    cover_downloader: CoverDownloader | None = None,
) -> FastAPI:
    available_models = ["gpt-5-mini", "gpt-5.4-mini", "gpt-5", "gpt-5.4"]
    if settings.model not in available_models:
        available_models.insert(0, settings.model)
    db = Database(settings.db_path)
    db.initialize()
    db.set_app_setting("active_model", db.get_active_model(settings.model))
    importer = importer or MetadataImporter(OpenAIClient(settings.openai_api_key) if settings.openai_api_key else None)
    cover_downloader = cover_downloader or CoverDownloader(settings.cover_dir)
    ai_state = {
        "status": "ready" if settings.openai_api_key else "key_missing",
        "detail": None if settings.openai_api_key else "OPENAI_API_KEY is not configured.",
    }

    app = FastAPI(title="Album Ranker")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cover_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/library-data", StaticFiles(directory=settings.data_dir), name="library-data")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _validation_detail(exc.errors())})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if not request.url.path.startswith("/api/") and exc.status_code == 404:
            noun = "Page"
            if request.url.path.startswith("/albums/"):
                noun = "Album"
            elif request.url.path.startswith("/artists/"):
                noun = "Artist"
            elif request.url.path.startswith("/lists/"):
                noun = "List"
            return HTMLResponse(
                _error_page(f"{noun} Not Found", f"{noun} was not found. It may have been deleted."),
                status_code=404,
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    def build_settings() -> SettingsRecord:
        return db.build_settings_record(
            default_model=settings.model,
            available_models=available_models,
            host=settings.host,
            port=settings.port,
            openai_api_key_configured=bool(settings.openai_api_key),
            ai_status=ai_state["status"],
            ai_status_detail=ai_state["detail"],
            last_import_diagnostics=importer.last_diagnostics or None,
        )

    @app.get("/", response_class=HTMLResponse)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/albums", status_code=307)

    @app.get("/artists", response_class=HTMLResponse)
    async def artists_page() -> str:
        imports = [draft for draft in reversed(_all_drafts(db)) if draft.target_type == "artist" and draft.status == "draft"]
        return render_artists_page(build_settings(), db.list_artists(), db.list_genres(), imports)

    @app.get("/artists/{artist_id}", response_class=HTMLResponse)
    async def artist_detail_page(artist_id: int) -> str:
        try:
            artist = db.get_artist_with_albums(artist_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        imports = [draft for draft in reversed(_all_drafts(db)) if draft.target_type == "album" and draft.status == "draft"]
        return render_artist_detail_page(build_settings(), artist, imports)

    @app.get("/albums", response_class=HTMLResponse)
    async def albums_page() -> str:
        return render_albums_page(build_settings(), db.list_albums(), db.list_artists(), db.list_genres(), [])

    @app.get("/imports", response_class=HTMLResponse)
    async def imports_page() -> str:
        return render_imports_page(build_settings())

    @app.get("/bookmarks", response_class=HTMLResponse)
    async def bookmarks_page() -> str:
        return render_bookmarks_page(build_settings(), db.list_bookmarked_albums())

    @app.get("/genres", response_class=HTMLResponse)
    async def genres_page() -> str:
        return render_genres_page(build_settings(), db.list_genres())

    @app.get("/albums/{album_id}", response_class=HTMLResponse)
    async def album_detail_page(album_id: int) -> str:
        try:
            album = db.get_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return render_album_detail_page(build_settings(), album)

    @app.get("/lists", response_class=HTMLResponse)
    async def lists_page() -> str:
        return render_lists_page(build_settings(), db.list_lists(), db.list_albums(), db.list_genres())

    @app.get("/lists/{list_id}", response_class=HTMLResponse)
    async def list_detail_page(list_id: int) -> str:
        try:
            record = db.get_list(list_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return render_list_detail_page(build_settings(), record, db.list_albums(), db.list_genres())

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page() -> str:
        return render_settings_page(build_settings())

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(now=datetime.now(UTC))

    @app.get("/api/settings", response_model=SettingsRecord)
    async def get_settings() -> SettingsRecord:
        return build_settings()

    @app.put("/api/settings", response_model=SettingsRecord)
    async def update_settings(payload: SettingsUpdateRequest) -> SettingsRecord:
        if payload.active_model not in available_models:
            raise HTTPException(status_code=400, detail="That model is not in the available model list. Pick one from the menu.")
        try:
            db.update_settings(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return build_settings()

    @app.get("/api/artists", response_model=list[ArtistRecord | dict])
    async def list_artists() -> list[dict]:
        return [artist.model_dump(mode="json") for artist in db.list_artists()]

    @app.get("/api/genres", response_model=list[GenreRecord])
    async def list_genres() -> list[GenreRecord]:
        return db.list_genres()

    @app.post("/api/genres", response_model=GenreRecord)
    async def create_genre(payload: GenreUpsert) -> GenreRecord:
        return db.create_genre(payload)

    @app.put("/api/genres/{genre_id}", response_model=GenreRecord)
    async def update_genre(genre_id: int, payload: GenreUpsert) -> GenreRecord:
        try:
            return db.update_genre(genre_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/genres/{genre_id}")
    async def delete_genre(genre_id: int) -> dict[str, bool]:
        try:
            db.delete_genre(genre_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/artists", response_model=ArtistRecord)
    async def create_artist(payload: ArtistUpsert) -> ArtistRecord:
        return db.create_artist(payload)

    @app.put("/api/artists/{artist_id}", response_model=ArtistRecord)
    async def update_artist(artist_id: int, payload: ArtistUpsert) -> ArtistRecord:
        try:
            return db.update_artist(artist_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/artists/{artist_id}")
    async def delete_artist(artist_id: int) -> dict[str, bool]:
        try:
            db.delete_artist(artist_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/artists/{artist_id}/refresh", response_model=ArtistRecord)
    async def refresh_artist(artist_id: int, payload: RefreshAlbumRequest = RefreshAlbumRequest()) -> ArtistRecord:
        try:
            existing = db.get_artist(artist_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        source_url = payload.source_url or existing.external_url
        if not source_url:
            raise HTTPException(
                status_code=400,
                detail="No source URL available. Add an external URL to the artist first.",
            )
        request = ImportRequest(
            artist_name=existing.name,
            source_url=source_url,
        )
        try:
            draft_data = importer.create_artist_draft(request, model=db.get_active_model(settings.model))
        except Exception as exc:
            detail = _friendly_ai_error(exc, action="metadata")
            if settings.openai_api_key:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = detail
            raise HTTPException(status_code=502, detail=detail) from exc
        upsert = ArtistUpsert(
            name=draft_data.artist_name or existing.name,
            description=draft_data.description or existing.description,
            description_source_url=draft_data.description_source_url or existing.description_source_url,
            description_source_label=draft_data.description_source_label or existing.description_source_label,
            external_url=draft_data.external_url or existing.external_url,
            origin=draft_data.origin or existing.origin,
        )
        return db.update_artist(artist_id, upsert)

    @app.get("/api/albums", response_model=list[dict])
    async def list_albums() -> list[dict]:
        return [album.model_dump(mode="json") for album in db.list_albums()]

    @app.post("/api/albums", response_model=AlbumDetailRecord)
    async def create_album(payload: AlbumUpsert) -> AlbumDetailRecord:
        return db.create_album(_resolve_album_cover(payload, None, cover_downloader))

    @app.get("/api/albums/{album_id}", response_model=AlbumDetailRecord)
    async def get_album(album_id: int) -> AlbumDetailRecord:
        try:
            return db.get_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/albums/{album_id}", response_model=AlbumDetailRecord)
    async def update_album(album_id: int, payload: AlbumUpsert) -> AlbumDetailRecord:
        try:
            return db.update_album(album_id, _resolve_album_cover(payload, None, cover_downloader))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/api/albums/{album_id}/rating", response_model=AlbumDetailRecord)
    async def patch_album_rating(album_id: int, payload: AlbumRatingPatch) -> AlbumDetailRecord:
        try:
            return db.patch_album_rating(album_id, payload.rating)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/api/albums/{album_id}/bookmark", response_model=AlbumDetailRecord)
    async def patch_album_bookmark(album_id: int, payload: AlbumBookmarkPatch) -> AlbumDetailRecord:
        try:
            return db.set_album_bookmarked(album_id, payload.bookmarked)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.patch("/api/albums/{album_id}/listened", response_model=AlbumDetailRecord)
    async def patch_album_listened(album_id: int, payload: AlbumListenedPatch) -> AlbumDetailRecord:
        try:
            return db.mark_album_listened(album_id, payload.listened)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/albums/{album_id}/cover", response_model=AlbumDetailRecord)
    async def upload_album_cover(album_id: int, file: UploadFile) -> AlbumDetailRecord:
        try:
            db.get_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        suffix = Path(file.filename or "").suffix.lower() or ".jpg"
        if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
            raise HTTPException(status_code=400, detail="Cover upload failed. Use JPG, PNG, or WebP.")
        settings.cover_dir.mkdir(parents=True, exist_ok=True)
        target = settings.cover_dir / f"album-{album_id}-cover{suffix}"
        try:
            target.write_bytes(await file.read())
        except OSError as exc:
            raise HTTPException(status_code=500, detail="The selected file could not be saved. Check that the data directory is writable.") from exc
        return db.patch_album_cover(album_id, str(target))

    @app.post("/api/albums/{album_id}/refresh", response_model=AlbumDetailRecord)
    async def refresh_album(album_id: int, payload: RefreshAlbumRequest = RefreshAlbumRequest()) -> AlbumDetailRecord:
        try:
            existing = db.get_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        source_url = payload.source_url or existing.album_external_url
        if not source_url:
            raise HTTPException(
                status_code=400,
                detail="No source URL available. Add an external URL to the album first.",
            )
        _validate_album_source_url(source_url)
        request = ImportRequest(
            artist_name=existing.artist_name,
            album_title=existing.title,
            source_url=source_url,
        )
        try:
            draft_data = importer.create_album_draft(request, model=db.get_active_model(settings.model))
        except Exception as exc:
            detail = _friendly_ai_error(exc, action="metadata")
            if settings.openai_api_key:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = detail
            raise HTTPException(status_code=502, detail=detail) from exc
        tracks = [
            TrackUpsert(track_number=t.track_number, title=t.title, duration_seconds=t.duration_seconds)
            for t in draft_data.tracks
        ]
        # Preserve cover if already downloaded locally; only re-download if no local cover
        cover_source_url = existing.cover_source_url if existing.cover_image_path else (
            draft_data.cover_source_url or existing.cover_source_url
        )
        upsert = AlbumUpsert(
            artist_name=existing.artist_name,
            artist_description=draft_data.artist_description or existing.artist_description,
            artist_description_source_url=draft_data.artist_description_source_url or existing.artist_description_source_url,
            artist_description_source_label=draft_data.artist_description_source_label or existing.artist_description_source_label,
            album_external_url=draft_data.album_external_url or existing.album_external_url,
            album_stream_url=existing.album_stream_url,
            album_type=draft_data.album_type or existing.album_type,
            title=draft_data.album_title or existing.title,
            release_year=draft_data.release_year or existing.release_year,
            genre=draft_data.genre or existing.genre,
            rating=existing.rating,
            duration_seconds=draft_data.duration_seconds or existing.duration_seconds,
            cover_image_path=existing.cover_image_path,
            cover_source_url=cover_source_url,
            notes=draft_data.notes or existing.notes,
            tracks=tracks or list(existing.tracks),
        )
        upsert = _resolve_album_cover(upsert, None, cover_downloader)
        return db.update_album(album_id, upsert)

    @app.delete("/api/albums/{album_id}")
    async def delete_album(album_id: int) -> dict[str, bool]:
        try:
            db.delete_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/albums/{album_id}/overview/draft", response_model=OverviewDraftResponse)
    async def generate_album_overview(album_id: int, payload: OverviewDraftRequest) -> OverviewDraftResponse:
        try:
            album = db.get_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            overview = importer.generate_album_overview(
                album,
                language=payload.language,
                model=db.get_active_model(settings.model),
            )
        except Exception as exc:
            detail = _friendly_ai_error(exc, action="overview")
            if settings.openai_api_key:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = detail
            raise HTTPException(status_code=502, detail=detail) from exc
        if settings.openai_api_key:
            ai_state["status"] = "ready"
            ai_state["detail"] = None
        return OverviewDraftResponse(overview=overview)

    @app.patch("/api/albums/{album_id}/overview", response_model=AlbumDetailRecord)
    async def save_album_overview(album_id: int, payload: OverviewSaveRequest) -> AlbumDetailRecord:
        try:
            return db.update_album_overview(album_id, payload.overview)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/lists", response_model=list[AlbumListRecord])
    async def list_lists() -> list[AlbumListRecord]:
        return db.list_lists()

    @app.post("/api/lists", response_model=AlbumListRecord)
    async def create_list(payload: AlbumListUpsert) -> AlbumListRecord:
        return db.create_list(payload)

    @app.put("/api/lists/{list_id}", response_model=AlbumListRecord)
    async def update_list(list_id: int, payload: AlbumListUpsert) -> AlbumListRecord:
        try:
            return db.update_list(list_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/lists/{list_id}/items", response_model=AlbumListRecord)
    async def add_list_item(list_id: int, payload: AlbumListItemAddRequest) -> AlbumListRecord:
        try:
            return db.add_album_to_list(list_id, payload.album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/lists/{list_id}/items/reorder", response_model=AlbumListRecord)
    async def reorder_list(list_id: int, payload: ReorderListItemsRequest) -> AlbumListRecord:
        try:
            return db.reorder_list_items(list_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/lists/{list_id}/items/{item_id}", response_model=AlbumListRecord)
    async def delete_list_item(list_id: int, item_id: int) -> AlbumListRecord:
        try:
            return db.remove_list_item(list_id, item_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/api/lists/{list_id}")
    async def delete_list(list_id: int) -> dict[str, bool]:
        try:
            db.delete_list(list_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/auto-lists/best-rated", response_model=AlbumListRecord)
    async def auto_list_best_rated(payload: AutoListBestRatedRequest) -> AlbumListRecord:
        try:
            return db.auto_list_best_rated(payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/import/artist", response_model=ImportDraftResponse)
    async def import_artist(payload: ImportRequest) -> ImportDraftResponse:
        try:
            draft_data = importer.create_artist_draft(payload, model=db.get_active_model(settings.model))
        except Exception as exc:
            detail = _friendly_ai_error(exc, action="metadata")
            if settings.openai_api_key:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = detail
            raise HTTPException(status_code=502, detail=detail) from exc
        if settings.openai_api_key:
            if importer.last_request_failed:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = _friendly_ai_error(Exception(importer.last_error or ""), action="metadata")
            else:
                ai_state["status"] = "ready"
                ai_state["detail"] = None
        draft = db.create_import_job("artist", payload, draft_to_json(draft_data))
        return ImportDraftResponse(draft=draft)

    @app.post("/api/import/album", response_model=ImportDraftResponse)
    async def import_album(payload: ImportRequest) -> ImportDraftResponse:
        _validate_album_source_url(payload.source_url)
        try:
            draft_data = importer.create_album_draft(payload, model=db.get_active_model(settings.model))
        except Exception as exc:
            detail = _friendly_ai_error(exc, action="metadata")
            if settings.openai_api_key:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = detail
            raise HTTPException(status_code=502, detail=detail) from exc
        if settings.openai_api_key:
            if importer.last_request_failed:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = _friendly_ai_error(Exception(importer.last_error or ""), action="metadata")
            else:
                ai_state["status"] = "ready"
                ai_state["detail"] = None
        draft = db.create_import_job("album", payload, draft_to_json(draft_data))
        return ImportDraftResponse(draft=draft)

    @app.post("/api/import/album-with-artist", response_model=AlbumWithArtistImportResponse)
    async def import_album_with_artist(payload: ImportRequest) -> AlbumWithArtistImportResponse:
        if not payload.source_url:
            raise HTTPException(status_code=400, detail="Source URL is required")
        _validate_album_source_url(payload.source_url)
        try:
            album_data = importer.create_album_draft(payload, model=db.get_active_model(settings.model))
        except Exception as exc:
            detail = _friendly_ai_error(exc, action="metadata")
            if settings.openai_api_key:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = detail
            raise HTTPException(status_code=502, detail=detail) from exc
        deterministic_album_data = metal_archives_album_draft_from_url(
            ImportRequest(
                artist_name=album_data.artist_name or payload.artist_name,
                album_title=album_data.album_title or payload.album_title,
                source_url=payload.source_url,
            )
        )
        if deterministic_album_data is not None:
            album_data = album_data.model_copy(
                update={
                    "artist_name": deterministic_album_data.artist_name or album_data.artist_name,
                    "album_title": deterministic_album_data.album_title or album_data.album_title,
                    "album_external_url": deterministic_album_data.album_external_url or album_data.album_external_url,
                    "album_type": deterministic_album_data.album_type or album_data.album_type,
                    "release_year": deterministic_album_data.release_year or album_data.release_year,
                    "duration_seconds": deterministic_album_data.duration_seconds or album_data.duration_seconds,
                    "cover_source_url": deterministic_album_data.cover_source_url or album_data.cover_source_url,
                    "notes": deterministic_album_data.notes or album_data.notes,
                    "tracks": deterministic_album_data.tracks or album_data.tracks,
                }
            )
        if album_data.notes and "Encyclopaedia Metallum" in album_data.notes:
            album_data = album_data.model_copy(update={"notes": None})
        album_request = ImportRequest(
            artist_name=album_data.artist_name or payload.artist_name,
            album_title=album_data.album_title or payload.album_title,
            source_url=payload.source_url,
        )
        album_draft = db.create_import_job("album", album_request, draft_to_json(album_data))
        artist_source_url = metal_archives_artist_url_from_album_url(payload.source_url)
        artist_exists = bool(album_data.artist_name and db.get_artist_by_name(album_data.artist_name))
        artist_draft = None
        if not artist_exists and artist_source_url:
            artist_request = ImportRequest(artist_name=album_data.artist_name, source_url=artist_source_url)
            try:
                artist_data = importer.create_artist_draft(artist_request, model=db.get_active_model(settings.model))
            except Exception as exc:
                detail = _friendly_ai_error(exc, action="metadata")
                if settings.openai_api_key:
                    ai_state["status"] = "last_request_failed"
                    ai_state["detail"] = detail
                raise HTTPException(status_code=502, detail=detail) from exc
            artist_payload = draft_to_json(artist_data)
            if artist_data.genre and not album_data.genre:
                album_data = album_data.model_copy(update={"genre": artist_data.genre})
                album_draft = db.update_import_job(
                    album_draft.id,
                    payload=draft_to_json(album_data),
                    chosen_source_url=album_draft.chosen_source_url,
                    status=album_draft.status,
                )
            artist_draft = db.create_import_job("artist", artist_request, artist_payload)
        if settings.openai_api_key:
            if importer.last_request_failed:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = _friendly_ai_error(Exception(importer.last_error or ""), action="metadata")
            else:
                ai_state["status"] = "ready"
                ai_state["detail"] = None
        return AlbumWithArtistImportResponse(
            album_draft=album_draft,
            artist_draft=artist_draft,
            artist_exists=artist_exists,
            artist_source_url=artist_source_url,
        )

    @app.post("/api/import/album-with-artist/confirm", response_model=ImportConfirmResponse)
    async def confirm_album_with_artist(payload: AlbumWithArtistConfirmRequest) -> ImportConfirmResponse:
        try:
            album_draft = db.get_import_job(payload.album_draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if album_draft.target_type != "album":
            raise HTTPException(status_code=400, detail="Album draft target type does not match")
        artist_draft = None
        if payload.artist_draft_id is not None:
            try:
                artist_draft = db.get_import_job(payload.artist_draft_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if artist_draft.target_type != "artist":
                raise HTTPException(status_code=400, detail="Artist draft target type does not match")
        artist: ArtistRecord | None = None
        if payload.artist_draft_id is not None:
            if payload.artist_payload is None:
                raise HTTPException(status_code=400, detail="Artist payload is required when artist_draft_id is set")
            artist_payload = dict(payload.artist_payload)
            if "name" not in artist_payload and "artist_name" in artist_payload:
                artist_payload["name"] = artist_payload.pop("artist_name")
            try:
                artist = db.create_artist(ArtistUpsert.model_validate(artist_payload))
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=_validation_detail(exc.errors())) from exc
            db.update_import_job(
                payload.artist_draft_id,
                payload=payload.artist_payload,
                chosen_source_url=payload.artist_chosen_source_url,
                status="confirmed",
            )
        album_payload = dict(payload.album_payload)
        try:
            album_upsert = AlbumUpsert.model_validate(album_payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc.errors())) from exc
        album_upsert = _resolve_album_cover(album_upsert, album_payload, cover_downloader)
        existing: AlbumDetailRecord | None = None
        if album_upsert.album_external_url:
            existing = db.get_album_by_external_url(album_upsert.album_external_url)
        if existing is not None:
            album = db.update_album(existing.id, album_upsert)
        else:
            album = db.create_album(album_upsert)
        updated = db.update_import_job(
            payload.album_draft_id,
            payload=album_payload,
            chosen_source_url=payload.album_chosen_source_url,
            status="confirmed",
        )
        if artist is None:
            artist = db.get_artist_by_name(album.artist_name)
        return ImportConfirmResponse(draft=updated, artist=artist, album=album)

    @app.post("/api/import/{draft_id}/confirm", response_model=ImportConfirmResponse)
    async def confirm_import(draft_id: int, payload: ImportConfirmRequest) -> ImportConfirmResponse:
        try:
            draft = db.get_import_job(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if draft.target_type != payload.target_type:
            raise HTTPException(status_code=400, detail="Draft target type does not match confirm payload")
        artist: ArtistRecord | None = None
        album: AlbumDetailRecord | None = None
        if payload.target_type == "artist":
            artist_payload = dict(payload.payload)
            if "name" not in artist_payload and "artist_name" in artist_payload:
                artist_payload["name"] = artist_payload.pop("artist_name")
            try:
                artist = db.create_artist(ArtistUpsert.model_validate(artist_payload))
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=_validation_detail(exc.errors())) from exc
            updated = db.update_import_job(
                draft_id,
                payload=payload.payload,
                chosen_source_url=payload.chosen_source_url,
                status="confirmed",
            )
            return ImportConfirmResponse(draft=updated, artist=artist)
        try:
            album_upsert = AlbumUpsert.model_validate(payload.payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=_validation_detail(exc.errors())) from exc
        album_upsert = _resolve_album_cover(album_upsert, payload.payload, cover_downloader)
        existing: AlbumDetailRecord | None = None
        if album_upsert.album_external_url:
            existing = db.get_album_by_external_url(album_upsert.album_external_url)
        if existing is not None:
            album = db.update_album(existing.id, album_upsert)
        else:
            album = db.create_album(album_upsert)
        updated = db.update_import_job(
            draft_id,
            payload=payload.payload,
            chosen_source_url=payload.chosen_source_url,
            status="confirmed",
        )
        return ImportConfirmResponse(draft=updated, album=album)

    return app


def _all_drafts(db: Database) -> list:
    drafts = []
    draft_id = 1
    while True:
        try:
            drafts.append(db.get_import_job(draft_id))
            draft_id += 1
        except KeyError:
            break
    return drafts
