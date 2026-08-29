"""Durable generation and weekly download rotation for Cinematic Videos."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from notebooklm.exceptions import RateLimitError

import paths

logger = logging.getLogger(__name__)

_COMPUTE_REFRESH_DELAY = timedelta(hours=5, minutes=15)
_VIDEO_POLL_DELAY = timedelta(minutes=15)
_GENERATION_COOLDOWN = 60


def current_week_start(today: date | None = None) -> str:
    """Return the Monday that identifies the local calendar week."""
    value = today or date.today()
    return (value - timedelta(days=value.weekday())).isoformat()


def _load_batches() -> list[dict]:
    try:
        payload = json.loads(
            paths.get_weekly_video_batches_file().read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []
    batches = payload.get("batches", []) if isinstance(payload, dict) else []
    return [batch for batch in batches if isinstance(batch, dict)]


def _save_batches(batches: list[dict]) -> None:
    path = paths.get_weekly_video_batches_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps({"batches": batches}, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def register_weekly_video(
    *,
    notebook_id: str,
    notebook_url: str = "",
    source_name: str,
    channel_order: int,
    source_ids: list[str],
    instructions: str,
    week_start: str | None = None,
) -> None:
    """Idempotently add one generated notebook to its weekly video batch."""
    week_key = week_start or current_week_start()
    batches = _load_batches()
    batch = next((item for item in batches if item.get("week_start") == week_key), None)
    if batch is None:
        batch = {
            "week_start": week_key,
            "sealed": False,
            "downloaded": False,
            "entries": [],
        }
        batches.append(batch)

    entries = batch.setdefault("entries", [])
    entry = next((item for item in entries if item.get("notebook_id") == notebook_id), None)
    if entry is None:
        entry = {"notebook_id": notebook_id, "state": "queued"}
        entries.append(entry)
    entry.update(
        {
            "source_name": source_name,
            "notebook_url": notebook_url,
            "channel_order": int(channel_order),
            "source_ids": list(source_ids),
            "instructions": instructions,
        }
    )
    batch["sealed"] = False
    batch["downloaded"] = False
    _save_batches(batches)


def seal_weekly_video_batch(week_start: str | None = None) -> None:
    """Declare that no more notebooks will be added to the current run."""
    week_key = week_start or current_week_start()
    batches = _load_batches()
    batch = next((item for item in batches if item.get("week_start") == week_key), None)
    if batch and batch.get("entries"):
        batch["sealed"] = True
        _save_batches(batches)


def pending_weekly_video_count() -> int:
    """Return entries belonging to batches that have not been downloaded."""
    return sum(
        len(batch.get("entries", []))
        for batch in _load_batches()
        if not batch.get("downloaded")
    )


def unnotified_completed_video_batches() -> list[dict]:
    return [
        batch
        for batch in _load_batches()
        if batch.get("downloaded") and not batch.get("completion_email_sent_at")
    ]


def mark_video_completion_email_sent(week_start: str) -> None:
    batches = _load_batches()
    batch = next((item for item in batches if item.get("week_start") == week_start), None)
    if batch:
        batch["completion_email_sent_at"] = datetime.now(timezone.utc).isoformat()
        _save_batches(batches)


def _artifact_for_entry(artifacts: list, entry: dict):
    artifact_id = entry.get("artifact_id")
    if artifact_id:
        matched = next((item for item in artifacts if item.id == artifact_id), None)
        if matched is not None and (
            matched.is_completed or matched.is_processing or matched.is_pending
        ):
            return matched
        if matched is not None:
            return None
    viable = [
        item
        for item in artifacts
        if item.is_completed or item.is_processing or item.is_pending
    ]
    return viable[-1] if viable else None


async def _start_or_poll_video(client, entry: dict) -> str:
    artifacts = await client.artifacts.list_video(entry["notebook_id"])
    artifact = _artifact_for_entry(artifacts, entry)
    if artifact is not None:
        entry["artifact_id"] = artifact.id
        entry["artifact_title"] = (artifact.title or "").strip()
        if artifact.is_completed:
            entry["state"] = "completed"
            return "completed"
        entry["state"] = "processing"
        return "processing"

    async def generate():
        return await client.artifacts.generate_cinematic_video(
            entry["notebook_id"],
            source_ids=entry.get("source_ids") or None,
            instructions=entry.get("instructions") or None,
        )

    # A quota rejection starts Gemini Notebook's absolute refresh window. Do
    # not hide it behind short retries that would move TubeLM's persisted anchor.
    status = await generate()
    if not status or status.is_failed or not status.task_id:
        entry["state"] = "queued"
        return "failed"
    entry["artifact_id"] = status.task_id
    entry["state"] = "processing"
    return "started"


def _safe_filename_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:100].rstrip(" .")


def _assign_filenames(entries: list[dict]) -> None:
    used: set[str] = set()
    for entry in sorted(entries, key=lambda item: (item.get("channel_order", 0), item.get("notebook_id", ""))):
        source_name = _safe_filename_part(entry.get("source_name", ""), "Source")
        artifact_title = _safe_filename_part(entry.get("artifact_title", ""), "")
        stem = f"TubeLM {int(entry.get('channel_order', 0)):02d} - {source_name}"
        if artifact_title:
            stem += f" - {artifact_title}"
        filename = f"{stem}.mp4"
        suffix = 2
        while filename.casefold() in used:
            filename = f"{stem} ({suffix}).mp4"
            suffix += 1
        used.add(filename.casefold())
        entry["filename"] = filename


def _clear_directory(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)


async def _download_and_rotate(client, batch: dict) -> None:
    entries = batch.get("entries", [])
    _assign_filenames(entries)
    current_dir = paths.get_video_download_dir()
    previous_dir = paths.get_previous_video_download_dir()
    staging_dir = current_dir.parent / f".TubeLM_{batch['week_start']}_staging"
    _clear_directory(staging_dir)

    try:
        for entry in entries:
            output_path = staging_dir / entry["filename"]
            await client.artifacts.download_video(
                entry["notebook_id"],
                str(output_path),
                artifact_id=entry["artifact_id"],
            )
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise RuntimeError(f"NotebookLM did not write {output_path.name}")

        _clear_directory(previous_dir)
        current_dir.mkdir(parents=True, exist_ok=True)
        for item in list(current_dir.iterdir()):
            if not item.is_file() or item.suffix.casefold() != ".mp4":
                continue
            shutil.move(str(item), str(previous_dir / item.name))
        for item in list(staging_dir.iterdir()):
            shutil.move(str(item), str(current_dir / item.name))
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


async def resume_weekly_video_batches(client) -> dict:
    """Kick off/poll videos and rotate downloads when an entire batch is ready."""
    batches = _load_batches()
    pending_batches = sorted(
        (batch for batch in batches if not batch.get("downloaded")),
        key=lambda batch: batch.get("week_start", ""),
    )
    if not pending_batches:
        return {"pending": 0, "deferred_until": None, "rate_limited": False}

    batch = pending_batches[0]
    now = datetime.now(timezone.utc)
    not_before_value = batch.get("not_before")
    if not_before_value:
        try:
            not_before = datetime.fromisoformat(not_before_value)
            if not_before.tzinfo is None:
                not_before = not_before.replace(tzinfo=timezone.utc)
            if not_before > now:
                return {
                    "pending": pending_weekly_video_count(),
                    "deferred_until": not_before,
                    "rate_limited": True,
                }
        except (TypeError, ValueError):
            batch.pop("not_before", None)

    for entry in sorted(
        batch.get("entries", []), key=lambda item: item.get("channel_order", 0)
    ):
        try:
            outcome = await _start_or_poll_video(client, entry)
        except RateLimitError:
            deferred_until = now + _COMPUTE_REFRESH_DELAY
            batch["not_before"] = deferred_until.isoformat()
            _save_batches(batches)
            return {
                "pending": pending_weekly_video_count(),
                "deferred_until": deferred_until,
                "rate_limited": True,
            }
        except Exception as exc:
            outcome = "failed"
            entry["state"] = "queued"
            entry["last_error"] = type(exc).__name__
            logger.warning(
                "Cinematic Video check failed for %r (%s); it remains queued.",
                entry.get("source_name", "source"),
                type(exc).__name__,
            )
        _save_batches(batches)
        if outcome == "started":
            logger.info(
                "Cinematic Video started for %r; cooling down %ds.",
                entry.get("source_name", "source"),
                _GENERATION_COOLDOWN,
            )
            await asyncio.sleep(_GENERATION_COOLDOWN)

    entries = batch.get("entries", [])
    all_completed = bool(entries) and all(
        entry.get("state") == "completed" for entry in entries
    )
    if batch.get("sealed") and all_completed:
        await _download_and_rotate(client, batch)
        batch["downloaded"] = True
        batch["downloaded_at"] = datetime.now(timezone.utc).isoformat()
        batch.pop("not_before", None)
        _save_batches(batches)
        remaining = pending_weekly_video_count()
        return {
            "pending": remaining,
            "deferred_until": (
                datetime.now(timezone.utc) + _VIDEO_POLL_DELAY if remaining else None
            ),
            "rate_limited": False,
        }

    deferred_until = now + _VIDEO_POLL_DELAY
    batch["not_before"] = deferred_until.isoformat()
    _save_batches(batches)
    return {
        "pending": pending_weekly_video_count(),
        "deferred_until": deferred_until,
        "rate_limited": False,
    }
