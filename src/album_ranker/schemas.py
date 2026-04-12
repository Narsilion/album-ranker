from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TrackUpsert(BaseModel):
    track_number: int = Field(ge=1)
    title: str
    duration_seconds: int | None = Field(default=None, ge=0)
    position: int = Field(default=0, ge=0)


class TrackRecord(TrackUpsert):
    id: int
    album_id: int
    model_config = ConfigDict(from_attributes=True)


class ArtistUpsert(BaseModel):
    name: str
    description: str | None = None
    description_source_url: str | None = None
    description_source_label: str | None = None
    external_url: str | None = None


class ArtistRecord(ArtistUpsert):
    id: int
    slug: str
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class AlbumUpsert(BaseModel):
    artist_name: str
    artist_description: str | None = None
    artist_description_source_url: str | None = None
    artist_description_source_label: str | None = None
    album_external_url: str | None = None
    title: str
    release_year: int | None = Field(default=None, ge=1000, le=9999)
    genre: str | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
    duration_seconds: int | None = Field(default=None, ge=0)
    cover_image_path: str | None = None
    cover_source_url: str | None = None
    notes: str | None = None
    tracks: list[TrackUpsert] = Field(default_factory=list)


class AlbumRatingPatch(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=10)


class AlbumCardRecord(BaseModel):
    id: int
    artist_id: int
    artist_name: str
    title: str
    release_year: int | None = None
    genre: str | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
    duration_seconds: int | None = None
    cover_image_path: str | None = None
    cover_source_url: str | None = None
    album_external_url: str | None = None
    notes: str | None = None
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class AlbumDetailRecord(AlbumCardRecord):
    artist_description: str | None = None
    artist_description_source_url: str | None = None
    artist_description_source_label: str | None = None
    tracks: list[TrackRecord] = Field(default_factory=list)


class ArtistWithAlbumsRecord(ArtistRecord):
    albums: list[AlbumCardRecord] = Field(default_factory=list)


class AlbumListUpsert(BaseModel):
    name: str
    description: str | None = None
    year: int | None = Field(default=None, ge=1000, le=9999)
    genre_filter_hint: str | None = None


class AlbumListRecord(AlbumListUpsert):
    id: int
    created_at: str
    updated_at: str
    items: list["AlbumListItemRecord"] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class AlbumListItemRecord(BaseModel):
    id: int
    list_id: int
    album_id: int
    rank_position: int
    album: AlbumCardRecord
    model_config = ConfigDict(from_attributes=True)


class AlbumListItemAddRequest(BaseModel):
    album_id: int


class ReorderListItemsRequest(BaseModel):
    item_ids: list[int] = Field(default_factory=list)


class AutoListBestRatedRequest(BaseModel):
    name: str
    limit: int = Field(default=10, ge=1, le=500)
    year: int | None = Field(default=None, ge=1000, le=9999)
    genre: str | None = None
    update_existing: bool = False


class GenreUpsert(BaseModel):
    name: str


class GenreRecord(GenreUpsert):
    id: int
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class SettingsRecord(BaseModel):
    model: str
    active_model: str
    available_models: list[str] = Field(default_factory=list)
    openai_api_key_configured: bool = False
    ai_status: str = "key_missing"
    ai_status_detail: str | None = None
    last_import_diagnostics: dict[str, Any] | None = None
    host: str
    port: int


class SettingsUpdateRequest(BaseModel):
    active_model: str


class ImportRequest(BaseModel):
    artist_name: str = ""
    album_title: str | None = None
    source_url: str | None = None


class ImportTrackDraft(BaseModel):
    track_number: int = Field(ge=1)
    title: str
    duration_seconds: int | None = Field(default=None, ge=0)


class ArtistDraftData(BaseModel):
    artist_name: str
    description: str | None = None
    description_source_url: str | None = None
    description_source_label: str | None = None
    external_url: str | None = None


class AlbumDraftData(BaseModel):
    artist_name: str
    artist_description: str | None = None
    artist_description_source_url: str | None = None
    artist_description_source_label: str | None = None
    album_external_url: str | None = None
    album_title: str
    release_year: int | None = None
    genre: str | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
    duration_seconds: int | None = None
    cover_source_url: str | None = None
    notes: str | None = None
    tracks: list[ImportTrackDraft] = Field(default_factory=list)


class ImportDraftRecord(BaseModel):
    id: int
    target_type: Literal["artist", "album"]
    requested_artist_name: str
    requested_album_title: str | None = None
    requested_source_url: str | None = None
    chosen_source_url: str | None = None
    status: str
    draft_payload: dict[str, Any]
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class ImportDraftResponse(BaseModel):
    draft: ImportDraftRecord


class ImportConfirmRequest(BaseModel):
    target_type: Literal["artist", "album"]
    payload: dict[str, Any]
    chosen_source_url: str | None = None


class ImportConfirmResponse(BaseModel):
    draft: ImportDraftRecord
    artist: ArtistRecord | None = None
    album: AlbumDetailRecord | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    now: datetime


class RunStatusResponse(BaseModel):
    status: str


class PageState(BaseModel):
    settings: SettingsRecord
    artists: list[ArtistWithAlbumsRecord] = Field(default_factory=list)
    albums: list[AlbumCardRecord] = Field(default_factory=list)
    album_detail: AlbumDetailRecord | None = None
    lists: list[AlbumListRecord] = Field(default_factory=list)
    selected_list_id: int | None = None
    imports: list[ImportDraftRecord] = Field(default_factory=list)


def seconds_to_display(seconds: int | None) -> str:
    if seconds is None:
        return ""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def display_to_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    parts = raw.split(":")
    if not all(part.isdigit() for part in parts):
        raise ValueError("Duration must use digits and ':' separators")
    if len(parts) == 2:
        minutes, seconds = (int(part) for part in parts)
        if seconds >= 60:
            raise ValueError("Seconds must be below 60")
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = (int(part) for part in parts)
        if minutes >= 60 or seconds >= 60:
            raise ValueError("Minutes and seconds must be below 60")
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError("Duration must use m:ss or h:mm:ss")


class AlbumFormPayload(BaseModel):
    artist_name: str
    artist_description: str | None = None
    artist_description_source_url: str | None = None
    artist_description_source_label: str | None = None
    album_external_url: str | None = None
    title: str
    release_year: int | None = Field(default=None, ge=1000, le=9999)
    genre: str | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
    duration: str | None = None
    cover_image_path: str | None = None
    cover_source_url: str | None = None
    notes: str | None = None
    tracklist_text: str | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def normalize_duration(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    def to_album_upsert(self) -> AlbumUpsert:
        tracks: list[TrackUpsert] = []
        lines = [line.strip() for line in (self.tracklist_text or "").splitlines() if line.strip()]
        for index, line in enumerate(lines, start=1):
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 2:
                raise ValueError("Track lines must use 'number|title|duration'")
            track_number = int(parts[0].rstrip("."))
            title = parts[1]
            duration_seconds = display_to_seconds(parts[2]) if len(parts) > 2 and parts[2] else None
            tracks.append(
                TrackUpsert(
                    track_number=track_number,
                    title=title,
                    duration_seconds=duration_seconds,
                    position=index,
                )
            )
        return AlbumUpsert(
            artist_name=self.artist_name,
            artist_description=self.artist_description,
            artist_description_source_url=self.artist_description_source_url,
            artist_description_source_label=self.artist_description_source_label,
            album_external_url=self.album_external_url,
            title=self.title,
            release_year=self.release_year,
            genre=self.genre,
            rating=self.rating,
            duration_seconds=display_to_seconds(self.duration),
            cover_image_path=self.cover_image_path,
            cover_source_url=self.cover_source_url,
            notes=self.notes,
            tracks=tracks,
        )


AlbumListRecord.model_rebuild()
