from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from album_ranker.settings import load_settings


def create_backup(db_path: Path, backup_dir: Path, *, retention_days: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    target = backup_dir / f"{db_path.stem}-{stamp}.db"

    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()

    prune_backups(backup_dir, retention_days=retention_days)
    return target


def prune_backups(backup_dir: Path, *, retention_days: int) -> None:
    if retention_days <= 0:
        return
    backups = sorted(backup_dir.glob("*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    for stale in backups[retention_days:]:
        stale.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a dated backup of the Album Ranker SQLite database.")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Directory where daily backups are stored.")
    parser.add_argument("--retention-days", type=int, default=30, help="How many daily backup files to keep.")
    args = parser.parse_args()

    settings = load_settings()
    backup_dir = args.backup_dir or (settings.data_dir / "backups")
    target = create_backup(settings.db_path, backup_dir, retention_days=args.retention_days)
    print(f"Backup created: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
