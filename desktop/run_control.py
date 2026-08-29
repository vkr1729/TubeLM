"""Cross-process execution, resume, and power-management helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


class PipelineAlreadyRunningError(RuntimeError):
    """Raised when another live pipeline owns the global run lock."""


class PipelineRunLock:
    """An OS-backed lock that is released automatically when a process exits."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._file = None

    def acquire(
        self,
        *,
        wait: bool = False,
        poll_interval: float = 30.0,
        on_wait=None,
    ) -> "PipelineRunLock":
        """Acquire the process lock, optionally waiting until its owner exits."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            lock_file = self.path.open("a+", encoding="utf-8")
            try:
                if os.name == "nt":
                    import msvcrt

                    lock_file.seek(0)
                    if lock_file.read(1) == "":
                        lock_file.write("\0")
                        lock_file.flush()
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                lock_file.close()
                if not wait:
                    raise PipelineAlreadyRunningError(
                        "Another TubeLM pipeline is already running."
                    ) from exc
                if on_wait is not None:
                    on_wait()
                time.sleep(max(0.01, poll_interval))
                continue
            break

        self._file = lock_file
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
        lock_file.flush()
        return self

    def release(self) -> None:
        if self._file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self) -> "PipelineRunLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def is_pipeline_running(path: Path) -> bool:
    """Return whether another process currently owns the pipeline lock."""
    probe = PipelineRunLock(path)
    try:
        probe.acquire()
    except PipelineAlreadyRunningError:
        return True
    else:
        probe.release()
        return False


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def save_resume_request(path: Path, request: dict) -> None:
    """Persist a credential-free description of an unfinished live run."""
    payload = dict(request)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(Path(path), payload)


def load_resume_request(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def clear_resume_request(path: Path) -> None:
    Path(path).unlink(missing_ok=True)


def save_compute_deferral(path: Path, not_before: datetime, reason: str) -> None:
    """Persist the next safe NotebookLM retry time without storing credentials."""
    if not_before.tzinfo is None:
        not_before = not_before.replace(tzinfo=timezone.utc)
    _atomic_write_json(
        Path(path),
        {
            "not_before": not_before.astimezone(timezone.utc).isoformat(),
            "reason": reason,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def load_compute_deferral(path: Path) -> dict | None:
    """Load a valid future compute deferral, deleting stale or invalid markers."""
    marker = load_resume_request(path)
    if not marker:
        return None
    try:
        not_before = datetime.fromisoformat(str(marker["not_before"]).replace("Z", "+00:00"))
        if not_before.tzinfo is None:
            not_before = not_before.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        clear_resume_request(path)
        return None
    if not_before <= datetime.now(timezone.utc):
        clear_resume_request(path)
        return None
    marker["not_before_dt"] = not_before
    return marker


def get_shutdown_command(platform: str | None = None) -> list[str]:
    """Return the native immediate power-off command for the platform."""
    platform = platform or sys.platform
    if platform == "win32":
        return ["shutdown", "/s", "/t", "0"]
    if platform == "darwin":
        return [
            "osascript",
            "-e",
            'tell application "System Events" to shut down',
        ]
    return ["systemctl", "poweroff"]


def request_system_shutdown() -> None:
    """Request an OS shutdown and raise if the request is rejected."""
    command = get_shutdown_command()
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"Shutdown request failed: {details}")
