from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from album_ranker.db import Database
from album_ranker.importer import CoverDownloader, MetadataImporter, draft_to_json, infer_cover_source_url_from_album_url
from album_ranker.openai_client import OpenAIClient
from album_ranker.schemas import (
    AlbumDetailRecord,
    AlbumRatingPatch,
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
    ReorderListItemsRequest,
    SettingsRecord,
    SettingsUpdateRequest,
)
from album_ranker.settings import Settings
from album_ranker.ui import (
    render_album_detail_page,
    render_albums_page,
    render_artist_detail_page,
    render_artists_page,
    render_genres_page,
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
        return render_artists_page(build_settings(), db.list_artists(), imports)

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
        return render_list_detail_page(build_settings(), record, db.list_albums())

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
        db.update_settings(payload)
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
        return {"ok": True}

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

    @app.delete("/api/albums/{album_id}")
    async def delete_album(album_id: int) -> dict[str, bool]:
        try:
            db.delete_album(album_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True}

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
        draft_data = importer.create_artist_draft(payload, model=db.get_active_model(settings.model))
        if settings.openai_api_key:
            if importer.last_request_failed:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = importer.last_error
            else:
                ai_state["status"] = "ready"
                ai_state["detail"] = None
        draft = db.create_import_job("artist", payload, draft_to_json(draft_data))
        return ImportDraftResponse(draft=draft)

    @app.post("/api/import/album", response_model=ImportDraftResponse)
    async def import_album(payload: ImportRequest) -> ImportDraftResponse:
        draft_data = importer.create_album_draft(payload, model=db.get_active_model(settings.model))
        if settings.openai_api_key:
            if importer.last_request_failed:
                ai_state["status"] = "last_request_failed"
                ai_state["detail"] = importer.last_error
            else:
                ai_state["status"] = "ready"
                ai_state["detail"] = None
        draft = db.create_import_job("album", payload, draft_to_json(draft_data))
        return ImportDraftResponse(draft=draft)

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
            artist = db.create_artist(ArtistUpsert.model_validate(payload.payload))
            updated = db.update_import_job(
                draft_id,
                payload=payload.payload,
                chosen_source_url=payload.chosen_source_url,
                status="confirmed",
            )
            return ImportConfirmResponse(draft=updated, artist=artist)
        album_upsert = AlbumUpsert.model_validate(payload.payload)
        album_upsert = _resolve_album_cover(album_upsert, payload.payload, cover_downloader)
        existing_album = db.get_album_by_artist_and_title(album_upsert.artist_name, album_upsert.title)
        if existing_album is None:
            album = db.create_album(album_upsert)
        else:
            album = db.update_album(existing_album.id, album_upsert)
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
