"""Durable weekly Audio Overview generation and completion tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from notebooklm.exceptions import RateLimitError

import paths
from weekly_video_service import current_week_start

logger = logging.getLogger(__name__)

_COMPUTE_REFRESH_DELAY = timedelta(hours=5, minutes=15)
_POLL_DELAY = timedelta(minutes=15)
_GENERATION_COOLDOWN = 60


def _load_batches() -> list[dict]:
    try:
        payload = json.loads(
            paths.get_weekly_audio_batches_file().read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []
    batches = payload.get("batches", []) if isinstance(payload, dict) else []
    return [batch for batch in batches if isinstance(batch, dict)]


def _save_batches(batches: list[dict]) -> None:
    path = paths.get_weekly_audio_batches_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps({"batches": batches}, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def register_weekly_audio(
    *,
    notebook_id: str,
    notebook_url: str,
    source_name: str,
    channel_order: int,
    source_ids: list[str],
    instructions: str,
    week_start: str | None = None,
) -> None:
    """Idempotently add one eligible notebook to its weekly Audio batch."""
    week_key = week_start or current_week_start()
    batches = _load_batches()
    batch = next((item for item in batches if item.get("week_start") == week_key), None)
    if batch is None:
        batch = {
            "week_start": week_key,
            "sealed": False,
            "completed": False,
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
            "notebook_url": notebook_url,
            "source_name": source_name,
            "channel_order": int(channel_order),
            "source_ids": list(source_ids),
            "instructions": instructions,
        }
    )
    batch["sealed"] = False
    batch["completed"] = False
    _save_batches(batches)


def seal_weekly_audio_batch(week_start: str | None = None) -> None:
    week_key = week_start or current_week_start()
    batches = _load_batches()
    batch = next((item for item in batches if item.get("week_start") == week_key), None)
    if batch and batch.get("entries"):
        batch["sealed"] = True
        _save_batches(batches)


def pending_weekly_audio_count() -> int:
    return sum(
        len(batch.get("entries", []))
        for batch in _load_batches()
        if not batch.get("completed")
    )


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


async def _start_or_poll_audio(client, entry: dict) -> str:
    artifact = _artifact_for_entry(
        await client.artifacts.list_audio(entry["notebook_id"]), entry
    )
    if artifact is not None:
        entry["artifact_id"] = artifact.id
        entry["artifact_title"] = (artifact.title or "").strip()
        if artifact.is_completed:
            entry["state"] = "completed"
            return "completed"
        entry["state"] = "processing"
        return "processing"

    status = await client.artifacts.generate_audio(
        entry["notebook_id"],
        source_ids=entry.get("source_ids") or None,
        instructions=entry.get("instructions") or None,
    )
    if not status or status.is_failed or not status.task_id:
        entry["state"] = "queued"
        return "failed"
    entry["artifact_id"] = status.task_id
    entry["state"] = "processing"
    return "started"


async def resume_weekly_audio_batches(client) -> dict:
    """Kick off or poll Audio independently of Cinematic Video quota."""
    batches = _load_batches()
    pending_batches = sorted(
        (batch for batch in batches if not batch.get("completed")),
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
                    "pending": pending_weekly_audio_count(),
                    "deferred_until": not_before,
                    "rate_limited": True,
                }
        except (TypeError, ValueError):
            batch.pop("not_before", None)

    for entry in sorted(
        batch.get("entries", []), key=lambda item: item.get("channel_order", 0)
    ):
        try:
            outcome = await _start_or_poll_audio(client, entry)
        except RateLimitError:
            deferred_until = now + _COMPUTE_REFRESH_DELAY
            batch["not_before"] = deferred_until.isoformat()
            _save_batches(batches)
            return {
                "pending": pending_weekly_audio_count(),
                "deferred_until": deferred_until,
                "rate_limited": True,
            }
        except Exception as exc:
            outcome = "failed"
            entry["state"] = "queued"
            entry["last_error"] = type(exc).__name__
            logger.warning(
                "Audio Overview check failed for %r (%s); it remains queued.",
                entry.get("source_name", "source"),
                type(exc).__name__,
            )
        _save_batches(batches)
        if outcome == "started":
            logger.info(
                "Audio Overview started for %r; cooling down %ds.",
                entry.get("source_name", "source"),
                _GENERATION_COOLDOWN,
            )
            await asyncio.sleep(_GENERATION_COOLDOWN)

    entries = batch.get("entries", [])
    if batch.get("sealed") and entries and all(
        entry.get("state") == "completed" for entry in entries
    ):
        batch["completed"] = True
        batch["completed_at"] = datetime.now(timezone.utc).isoformat()
        batch.pop("not_before", None)
        _save_batches(batches)
        remaining = pending_weekly_audio_count()
        return {
            "pending": remaining,
            "deferred_until": (
                datetime.now(timezone.utc) + _POLL_DELAY if remaining else None
            ),
            "rate_limited": False,
        }

    deferred_until = now + _POLL_DELAY
    batch["not_before"] = deferred_until.isoformat()
    _save_batches(batches)
    return {
        "pending": pending_weekly_audio_count(),
        "deferred_until": deferred_until,
        "rate_limited": False,
    }


def unnotified_completed_audio_batches() -> list[dict]:
    return [
        batch
        for batch in _load_batches()
        if batch.get("completed") and not batch.get("completion_email_sent_at")
    ]


def mark_audio_completion_email_sent(week_start: str) -> None:
    batches = _load_batches()
    batch = next((item for item in batches if item.get("week_start") == week_start), None)
    if batch:
        batch["completion_email_sent_at"] = datetime.now(timezone.utc).isoformat()
        _save_batches(batches)
