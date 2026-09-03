"""Durable NotebookLM Cinematic Video generation and downloads for Top Digest articles."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from notebooklm.exceptions import RateLimitError
import paths
from top10_downloader import build_video_filename, is_youtube_video_item

logger = logging.getLogger(__name__)

_COMPUTE_REFRESH_DELAY = timedelta(hours=5, minutes=15)
_GENERATION_COOLDOWN = 15


def _load_jobs() -> list[dict[str, Any]]:
    path = paths.get_top_article_videos_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    return [job for job in jobs if isinstance(job, dict)]


def _save_jobs(jobs: list[dict[str, Any]]) -> None:
    path = paths.get_top_article_videos_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps({"jobs": jobs}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _job_not_before(job: dict[str, Any]) -> datetime:
    raw = job.get("not_before")
    if not raw:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def register_top_article_videos(
    selection: dict[str, Any], run_date: str | None = None
) -> list[dict[str, Any]]:
    """Identify non-YouTube articles in the Top Digest and idempotently queue them."""
    date_key = str(run_date or selection.get("run_date") or datetime.now(timezone.utc).date().isoformat())
    items = selection.get("items", [])
    jobs = _load_jobs()
    registered = []

    for item in items:
        if is_youtube_video_item(item):
            continue

        rank = int(item.get("rank") or (len(registered) + 1))
        url = str(item.get("url") or "").strip()
        source_name = str(item.get("source_name") or "Article").strip()
        title = str(item.get("title") or "Untitled").strip()
        summary = str(item.get("summary") or item.get("why_it_matters") or "").strip()
        filename = build_video_filename(rank, source_name, title)

        # Match existing by run_date + rank or run_date + url
        existing = next(
            (
                j
                for j in jobs
                if j.get("run_date") == date_key
                and (j.get("rank") == rank or (url and j.get("url") == url))
            ),
            None,
        )
        if existing is None:
            job = {
                "run_date": date_key,
                "rank": rank,
                "source_name": source_name,
                "source_type": str(item.get("source_type") or "article"),
                "title": title,
                "url": url,
                "summary": summary,
                "filename": filename,
                "notebook_id": "",
                "source_id": "",
                "artifact_id": "",
                "state": "queued",
                "not_before": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            jobs.append(job)
            registered.append(job)
        else:
            # Update mutable metadata if still queued
            if existing.get("state") == "queued":
                existing.update({
                    "source_name": source_name,
                    "title": title,
                    "summary": summary,
                    "filename": filename,
                })
            registered.append(existing)

    _save_jobs(jobs)
    return registered


def pending_top_article_video_count() -> int:
    """Return the number of top article video jobs awaiting start or completion."""
    jobs = _load_jobs()
    return sum(1 for j in jobs if j.get("state") in {"queued", "processing"})


async def process_top_article_videos(
    client: Any, dest_dir: Path | None = None
) -> dict[str, Any]:
    """Trigger queued article video generations and download completed videos."""
    destination = dest_dir or paths.get_top10_video_download_dir()
    jobs = _load_jobs()
    now = datetime.now(timezone.utc)
    rate_limited = False
    next_retry_time: datetime | None = None

    # Step 1: Trigger queued jobs
    for job in jobs:
        if job.get("state") != "queued":
            continue

        not_before = _job_not_before(job)
        if now < not_before:
            next_retry_time = not_before if not next_retry_time or not_before < next_retry_time else next_retry_time
            continue

        # Create single-article notebook if missing
        if not job.get("notebook_id"):
            nb_title = f"TubeLM Top {job['rank']:02d} - {job['source_name']} - {job['title']}"
            if len(nb_title) > 100:
                nb_title = nb_title[:100].rstrip()
            try:
                notebook = await client.notebooks.create(nb_title)
                job["notebook_id"] = notebook.id
                logger.info("Created single-article notebook %s for %r", notebook.id, job["title"])
            except RateLimitError:
                rate_limited = True
                deferred_until = now + _COMPUTE_REFRESH_DELAY
                job["not_before"] = deferred_until.isoformat()
                next_retry_time = deferred_until
                logger.warning("Rate limit hit while creating notebook for %r; deferred until %s", job["title"], deferred_until)
                break
            except Exception as exc:
                logger.error("Failed to create notebook for top article %r: %s", job["title"], exc)
                continue

        # Ingest full article content via local extractor
        if not job.get("source_id") and job.get("notebook_id"):
            article_text = ""
            if job.get("url"):
                try:
                    from source_handlers.extractor import extract_clean_text
                    article_text = extract_clean_text(url=job["url"], fallback_html="")
                    if article_text and len(article_text.strip()) >= 100:
                        logger.info("Extracted %d chars of full article content from %s", len(article_text), job["url"])
                except Exception as exc:
                    logger.warning("Local article extraction failed for %s: %s", job["url"], exc)

            if not article_text or len(article_text.strip()) < 100:
                article_text = job.get("summary") or job.get("title") or "Article Content"
                logger.info("Falling back to summary text (%d chars) for %r", len(article_text), job["title"])

            from source_handlers.extractor import truncate_for_notebooklm
            truncated_content = truncate_for_notebooklm(article_text)
            try:
                source = await client.sources.add_text(job["notebook_id"], job["title"], truncated_content)
                logger.info("Added text source (%d chars) for %r to notebook %s", len(truncated_content), job["title"], job["notebook_id"])
                job["source_id"] = getattr(source, "id", str(source))
            except Exception as exc:
                logger.error("Failed to add text source for %r: %s", job["title"], exc)
                continue

        # Trigger Cinematic Video generation
        if job.get("notebook_id") and job.get("state") == "queued":
            source_ids = [job["source_id"]] if job.get("source_id") else None
            try:
                status = await client.artifacts.generate_cinematic_video(
                    job["notebook_id"],
                    source_ids=source_ids,
                    instructions=None,
                )
                if status and not getattr(status, "is_failed", False):
                    job["artifact_id"] = getattr(status, "task_id", "") or getattr(status, "id", "")
                    job["state"] = "processing"
                    logger.info("Started Cinematic Video generation for top article #%02d: %r", job["rank"], job["title"])
                    await asyncio.sleep(_GENERATION_COOLDOWN)
                else:
                    logger.warning("Cinematic Video generation failed to start for #%02d: %r", job["rank"], job["title"])
            except RateLimitError:
                rate_limited = True
                deferred_until = now + _COMPUTE_REFRESH_DELAY
                job["not_before"] = deferred_until.isoformat()
                next_retry_time = deferred_until
                logger.warning(
                    "NotebookLM compute limit reached; deferred Top article video #%02d until %s.",
                    job["rank"],
                    deferred_until.isoformat(),
                )
                break
            except Exception as exc:
                logger.error("Error generating cinematic video for #%02d: %s", job["rank"], exc)

    # Step 2: Poll and download processing jobs
    for job in jobs:
        if job.get("state") != "processing" or not job.get("notebook_id"):
            continue

        try:
            artifacts = await client.artifacts.list(job["notebook_id"])
        except Exception as exc:
            logger.warning("Could not list artifacts for notebook %s: %s", job["notebook_id"], exc)
            continue

        target_artifact = None
        for art in artifacts:
            # Match video artifact by task_id or artifact_type
            if getattr(art, "artifact_type", None) == "video" or (job.get("artifact_id") and art.id == job["artifact_id"]):
                target_artifact = art
                break

        if target_artifact is None:
            continue

        if getattr(target_artifact, "is_failed", False):
            job["state"] = "failed"
            logger.error("Cinematic Video generation failed on NotebookLM for #%02d: %r", job["rank"], job["title"])
            continue

        if getattr(target_artifact, "is_completed", False):
            destination.mkdir(parents=True, exist_ok=True)
            output_path = destination / job["filename"]
            logger.info("Downloading completed top article video #%02d to %s…", job["rank"], output_path)
            try:
                await client.artifacts.download_video(
                    job["notebook_id"],
                    str(output_path),
                    artifact_id=target_artifact.id,
                )
                if output_path.is_file() and output_path.stat().st_size > 0:
                    job["state"] = "downloaded"
                    job["downloaded_at"] = datetime.now(timezone.utc).isoformat()
                    logger.info("Successfully downloaded top article video: %s", output_path.name)
                else:
                    logger.warning("Download produced empty file for %s", output_path.name)
            except Exception as exc:
                logger.error("Failed to download video for #%02d: %s", job["rank"], exc)

    _save_jobs(jobs)
    pending = sum(1 for j in jobs if j.get("state") in {"queued", "processing"})
    return {
        "pending": pending,
        "rate_limited": rate_limited,
        "deferred_until": next_retry_time,
    }
