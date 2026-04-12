from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    project_root: Path
    db_path: Path
    data_dir: Path
    cover_dir: Path
    host: str
    port: int
    openai_api_key: str | None
    model: str


def resolve_project_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / "pyproject.toml").exists() and (cwd / "src" / "album_ranker").exists():
        return cwd
    return Path(__file__).resolve().parents[2]


def load_settings() -> Settings:
    project_root = resolve_project_root()
    db_path = Path(os.environ.get("ALBUM_RANKER_DB_PATH", "./.data/album-ranker.db")).expanduser()
    if not db_path.is_absolute():
        db_path = project_root / db_path
    data_dir = db_path.parent
    cover_dir = data_dir / "covers"
    return Settings(
        project_root=project_root,
        db_path=db_path,
        data_dir=data_dir,
        cover_dir=cover_dir,
        host=os.environ.get("ALBUM_RANKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("ALBUM_RANKER_PORT", "8780")),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        model=os.environ.get("ALBUM_RANKER_MODEL", "gpt-5"),
    )
