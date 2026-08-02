from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3


def rotate(log_path: Path) -> None:
    log_path.with_name(f"{log_path.name}.{LOG_BACKUPS}").unlink(missing_ok=True)
    for index in range(LOG_BACKUPS - 1, 0, -1):
        source = log_path.with_name(f"{log_path.name}.{index}")
        if source.exists():
            source.replace(log_path.with_name(f"{log_path.name}.{index + 1}"))
    if log_path.exists():
        log_path.replace(log_path.with_name(f"{log_path.name}.1"))


def main() -> int:
    home = Path.home()
    runtime_root = home / "Library" / "Application Support" / "Album Ranker"
    python = runtime_root / "venv" / "bin" / "python"
    log_path = home / "Library" / "Logs" / "Album Ranker" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(runtime_root / "app")
    env["ALBUM_RANKER_DB_PATH"] = str(runtime_root / "Data" / "album-ranker.db")
    command = [
        "/bin/zsh",
        "-lc",
        'source "$HOME/.zshrc" >/dev/null 2>&1 || true; exec "$@"',
        "album-ranker-service",
        str(python),
        "-m",
        "album_ranker.main",
    ]
    process = subprocess.Popen(
        command,
        cwd=runtime_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    def stop_child(signum: int, _frame: object) -> None:
        if process.poll() is None:
            os.killpg(process.pid, signum)

    signal.signal(signal.SIGTERM, stop_child)
    signal.signal(signal.SIGINT, stop_child)

    assert process.stdout is not None
    log = log_path.open("ab", buffering=0)
    try:
        while chunk := os.read(process.stdout.fileno(), 8192):
            if log.tell() + len(chunk) > MAX_LOG_BYTES:
                log.close()
                rotate(log_path)
                log = log_path.open("ab", buffering=0)
            log.write(chunk)
    finally:
        log.close()
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
