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
    ai_provider: str = "openai"
    github_models_token: str | None = None
    github_models_token_source: str | None = None
    github_models: list[str] | None = None


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit("ALBUM_RANKER_PORT must be an integer between 1 and 65535.") from exc
    if port < 1 or port > 65535:
        raise SystemExit("ALBUM_RANKER_PORT must be between 1 and 65535.")
    return port


def _parse_model(raw: str) -> str:
    model = raw.strip()
    if not model:
        raise SystemExit("ALBUM_RANKER_MODEL must not be empty.")
    if len(model) > 200:
        raise SystemExit("ALBUM_RANKER_MODEL must be 200 characters or fewer.")
    if any(not char.isprintable() for char in model):
        raise SystemExit("ALBUM_RANKER_MODEL must contain only printable characters.")
    return model


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
    port = _parse_port(os.environ.get("ALBUM_RANKER_PORT", "8780"))
    model = _parse_model(os.environ.get("ALBUM_RANKER_MODEL", "gpt-4o"))
    github_models = [
        m.strip()
        for m in os.environ.get("ALBUM_RANKER_GITHUB_MODELS", "openai/gpt-4.1,openai/gpt-4o,openai/o4-mini").split(",")
        if m.strip()
    ]
    return Settings(
        project_root=project_root,
        db_path=db_path,
        data_dir=data_dir,
        cover_dir=cover_dir,
        host=os.environ.get("ALBUM_RANKER_HOST", "127.0.0.1"),
        port=port,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        model=model,
        ai_provider=os.environ.get("ALBUM_RANKER_AI_PROVIDER", "openai").strip().lower() or "openai",
        github_models_token=os.environ.get("GITHUB_MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        github_models_token_source=(
            "GITHUB_MODELS_TOKEN"
            if os.environ.get("GITHUB_MODELS_TOKEN")
            else ("GITHUB_TOKEN" if os.environ.get("GITHUB_TOKEN") else None)
        ),
        github_models=github_models or ["openai/gpt-4.1"],
    )
