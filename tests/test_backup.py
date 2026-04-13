from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from album_ranker.backup import create_backup, prune_backups


def test_create_backup_copies_database(tmp_path: Path) -> None:
    db_path = tmp_path / "album-ranker.db"
    backup_dir = tmp_path / "backups"

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE demo (name TEXT)")
        connection.execute("INSERT INTO demo(name) VALUES ('vanir')")
        connection.commit()
    finally:
        connection.close()

    backup_path = create_backup(db_path, backup_dir, retention_days=30)

    assert backup_path.exists()
    backup_connection = sqlite3.connect(backup_path)
    try:
        row = backup_connection.execute("SELECT name FROM demo").fetchone()
    finally:
        backup_connection.close()
    assert row == ("vanir",)


def test_create_backup_creates_backup_dir_if_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "album-ranker.db"
    sqlite3.connect(db_path).close()
    backup_dir = tmp_path / "deep" / "nested" / "backups"

    backup_path = create_backup(db_path, backup_dir, retention_days=30)

    assert backup_dir.exists()
    assert backup_path.parent == backup_dir


def test_prune_backups_removes_oldest_over_limit(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    files = []
    for i in range(5):
        f = backup_dir / f"album-ranker-2026-01-0{i + 1}.db"
        f.write_bytes(b"x")
        # stagger mtime so ordering is deterministic
        f.touch()
        files.append(f)
        time.sleep(0.01)

    prune_backups(backup_dir, retention_days=3)

    remaining = sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime)
    assert len(remaining) == 3
    # the two oldest are gone
    assert files[0] not in remaining
    assert files[1] not in remaining


def test_prune_backups_noop_with_zero_retention(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for i in range(10):
        (backup_dir / f"album-ranker-2026-01-{i + 1:02d}.db").write_bytes(b"x")

    prune_backups(backup_dir, retention_days=0)

    assert len(list(backup_dir.glob("*.db"))) == 10
