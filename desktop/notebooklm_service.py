"""
notebooklm_service.py — NotebookLM integration layer.

Responsibilities:
  - Verify authentication via CLI subprocess
  - Pre-run cookie refresh via rookiepy
  - Create notebooks, add source items, and generate summaries via chat
  - Trigger Cinematic Video first and Audio for multi-source notebooks
  - Retain infographic generation as an opt-in feature
  - Persist quota-blocked artifacts for background resume
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import paths

from notebooklm import (
    NotebookLMClient,
    InfographicOrientation,
    InfographicDetail,
    InfographicStyle,
)
from notebooklm.exceptions import (
    NotebookLimitError,
    RateLimitError,
    SourceAddError,
    SourceTimeoutError,
)

from source_handlers import BaseSourceHandler, SourceItem
from summary_quality import strip_follow_up_offers
from weekly_video_service import register_weekly_video
from weekly_audio_service import register_weekly_audio

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

_SOURCE_WAIT_TIMEOUT = 300.0
_COOLDOWN_BEFORE_VIDEO = 60
_COOLDOWN_BEFORE_INFOGRAPHIC = 60
_COOLDOWN_BEFORE_PODCAST = 60
_SUMMARY_RETRY_DELAY = 20
_SUMMARY_MAX_ATTEMPTS = 3
_COMPUTE_REFRESH_DELAY = timedelta(hours=5, minutes=15)

_SUMMARY_PROMPT_TEMPLATE = """\
You are a research analyst. The following content from "{channel_name}" \
has been added as sources. Provide a narrative digest: for each item, \
write 2-3 short paragraphs retelling the core argument as a story. \
**Bold** key terms, names, and data points inline. \
Be specific, cite items directly, and avoid generic statements.\
"""

_PODCAST_PROMPT_TEMPLATE = """\
Create an engaging podcast-style deep dive into the latest \
content from '{channel_name}'. Target 10-15 minutes. \
Discuss key insights, themes, and takeaways in a conversational tone. \
Host 1 presents the core findings, Host 2 challenges with caveats and risks.\
"""

_VIDEO_PROMPT_TEMPLATE = """\
Create a cinematic video overview of the latest content from '{channel_name}'. \
Build a clear narrative around the most important ideas, use concrete details \
from the sources, and end with the practical takeaways.\
"""

_SUMMARY_OUTPUT_CONTRACT = """

CRITICAL OUTPUT CONTRACT:
- Return the complete briefing directly in this chat response.
- Do not create, save, propose, or refer to a file, note, report, Markdown
  document, download, or Studio panel.
- Do not ask for confirmation and do not describe what you could do next.
- Do not end with an offer, recommendation for another generated artifact, or
  phrases such as "if you want", "I can generate", or "would you like".
- Begin immediately with a `##` heading.
- Include exactly one `##` section for every supplied source item.
"""

_SUMMARY_PLACEHOLDER_PATTERNS = (
    r"\bstudio panel\b",
    r"\b(?:saved (?:as|to)|available (?:as|in)|see|check|created|generated|as)\s+[a-z0-9_-]+\.md\b",
    r"\bonce you (?:give|confirm|approve)\b",
    r"\bdoes this (?:plan|outline) look\b",
    r"\bi (?:have|will) (?:created|create|write|written|saved|save|compiled) (?:a |the |this )?(?:note|briefing|report|deliverable|file|document|summary|outline)\b",
    r"\bfull deliverable\b",
    r"\bproposed (?:briefing )?outline\b",
)


def _validate_summary_text(text: str, item_count: int) -> tuple[bool, str]:
    """Reject empty, partial, or file-pointer responses before email rendering."""
    normalized = (text or "").strip()
    if not normalized:
        return False, "the response was empty"

    for pattern in _SUMMARY_PLACEHOLDER_PATTERNS:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            logger.warning("Summary rejected by pattern %r (matched: %r)", pattern, match.group(0))
            return False, "the response referred to a file, plan, or Studio action"

    min_chars = max(120, min(800, item_count * 100))
    if len(normalized) < min_chars:
        return False, f"the response was too short ({len(normalized)} characters)"

    heading_count = len(re.findall(r"(?m)^##\s+\S", normalized))
    if heading_count < item_count:
        return False, f"only {heading_count} of {item_count} required sections were returned"

    return True, ""


async def _ask_for_valid_summary(client, notebook_id: str, prompt: str, item_count: int) -> str:
    """Ask for a direct summary and retry malformed or placeholder responses."""
    request_prompt = prompt.rstrip() + _SUMMARY_OUTPUT_CONTRACT
    last_reason = "unknown validation failure"
    for attempt in range(1, _SUMMARY_MAX_ATTEMPTS + 1):
        if attempt > 1:
            logger.info(
                "Retrying summary after %ds (attempt %d/%d)…",
                _SUMMARY_RETRY_DELAY,
                attempt,
                _SUMMARY_MAX_ATTEMPTS,
            )
            await asyncio.sleep(_SUMMARY_RETRY_DELAY)
            request_prompt = (
                "Your previous response was rejected because "
                f"{last_reason}. Return the complete briefing now."
                + _SUMMARY_OUTPUT_CONTRACT
            )
        try:
            chat_result = await client.chat.ask(notebook_id, request_prompt)
            answer = strip_follow_up_offers(chat_result.answer or "")
        except RateLimitError:
            raise
        except Exception as exc:
            last_reason = f"NotebookLM returned {type(exc).__name__}"
            logger.warning(
                "Summary request attempt %d/%d failed (%s).",
                attempt,
                _SUMMARY_MAX_ATTEMPTS,
                type(exc).__name__,
            )
            continue

        valid, reason = _validate_summary_text(answer, item_count)
        if valid:
            return answer.strip()
        last_reason = reason
        logger.warning(
            "Summary response attempt %d/%d rejected: %s.",
            attempt,
            _SUMMARY_MAX_ATTEMPTS,
            reason,
        )

    raise RuntimeError(f"Summary generation failed validation: {last_reason}")


def _next_compute_retry() -> datetime:
    """Return a conservative retry time just beyond Gemini Notebook's refresh."""
    return datetime.now(timezone.utc) + _COMPUTE_REFRESH_DELAY


def _load_deferred_artifact_jobs() -> list[dict]:
    path = paths.get_deferred_artifacts_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    return [job for job in jobs if isinstance(job, dict)]


def _save_deferred_artifact_jobs(jobs: list[dict]) -> None:
    path = paths.get_deferred_artifacts_file()
    if not jobs:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps({"jobs": jobs}, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _queue_deferred_artifacts(
    *,
    notebook_id: str,
    source_name: str,
    source_ids: list[str],
    artifact_types: list[str],
    video_instructions: str,
    audio_instructions: str,
    not_before: datetime,
) -> None:
    """Upsert one small, credential-free artifact retry job per notebook."""
    jobs = _load_deferred_artifact_jobs()
    existing = next((job for job in jobs if job.get("notebook_id") == notebook_id), None)
    if existing is None:
        existing = {"notebook_id": notebook_id}
        jobs.append(existing)
    existing.update(
        {
            "source_name": source_name,
            "source_ids": list(source_ids),
            "artifact_types": [
                artifact_type
                for artifact_type in ("video", "audio", "infographic")
                if artifact_type
                in (set(existing.get("artifact_types", [])) | set(artifact_types))
            ],
            "video_instructions": video_instructions,
            "audio_instructions": audio_instructions,
            "not_before": not_before.astimezone(timezone.utc).isoformat(),
        }
    )
    _save_deferred_artifact_jobs(jobs)


def _job_not_before(job: dict) -> datetime:
    try:
        value = datetime.fromisoformat(str(job.get("not_before", "")).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


async def _resume_infographic(client, job: dict) -> str:
    notebook_id = job["notebook_id"]
    source_name = job.get("source_name", "source")
    existing = [
        artifact
        for artifact in await client.artifacts.list_infographics(notebook_id)
        if artifact.is_completed or artifact.is_processing or artifact.is_pending
    ]
    artifact_id = None
    if existing:
        artifact = existing[-1]
        artifact_id = artifact.id
        if not artifact.is_completed:
            completed = await client.artifacts.wait_for_completion(
                notebook_id, artifact_id, timeout=900
            )
            if completed.is_rate_limited:
                return "rate_limited"
            if not completed.is_complete:
                return "failed"
    else:
        async def generate_infographic():
            return await client.artifacts.generate_infographic(
                notebook_id,
                source_ids=job.get("source_ids") or None,
                instructions=f"Create a visual infographic summarizing the key insights from the latest content by '{source_name}'.",
                orientation=InfographicOrientation.LANDSCAPE,
                detail_level=InfographicDetail.STANDARD,
                style=InfographicStyle.AUTO_SELECT,
            )

        status = await _with_artifact_retry("Deferred infographic generation", generate_infographic)
        if not status or status.is_rate_limited:
            return "rate_limited" if status and status.is_rate_limited else "failed"
        if not status.task_id:
            return "failed"
        artifact_id = status.task_id
        completed = await client.artifacts.wait_for_completion(
            notebook_id, artifact_id, timeout=900
        )
        if completed.is_rate_limited:
            return "rate_limited"
        if not completed.is_complete:
            return "failed"

    today = date.today().isoformat()
    safe_name = paths.safe_channel_name(source_name)
    out_path = str(paths.get_summaries_dir() / f"{today}_{safe_name}_infographic.png")
    await client.artifacts.download_infographic(
        notebook_id, out_path, artifact_id=artifact_id
    )
    _compress_infographic(out_path)
    return "completed"


async def _resume_audio(client, job: dict) -> str:
    notebook_id = job["notebook_id"]
    existing = [
        artifact
        for artifact in await client.artifacts.list_audio(notebook_id)
        if artifact.is_completed or artifact.is_processing or artifact.is_pending
    ]
    if existing:
        return "completed"

    async def generate_audio():
        return await client.artifacts.generate_audio(
            notebook_id,
            source_ids=job.get("source_ids") or None,
            instructions=job.get("audio_instructions") or None,
        )

    status = await _with_artifact_retry("Deferred Audio Overview generation", generate_audio)
    if not status or status.is_rate_limited:
        return "rate_limited" if status and status.is_rate_limited else "failed"
    return "completed" if status.task_id and not status.is_failed else "failed"


async def _resume_video(client, job: dict) -> str:
    notebook_id = job["notebook_id"]
    existing = [
        artifact
        for artifact in await client.artifacts.list_video(notebook_id)
        if artifact.is_completed or artifact.is_processing or artifact.is_pending
    ]
    if existing:
        return "completed"

    async def generate_video():
        return await client.artifacts.generate_cinematic_video(
            notebook_id,
            source_ids=job.get("source_ids") or None,
            instructions=job.get("video_instructions") or None,
        )

    status = await _with_artifact_retry(
        "Cinematic Video Overview generation", generate_video
    )
    if not status or status.is_rate_limited:
        return "rate_limited" if status and status.is_rate_limited else "failed"
    return "completed" if status.task_id and not status.is_failed else "failed"


async def resume_deferred_artifacts(generate_infographics: bool = False) -> dict:
    """Resume due artifact jobs once, stopping immediately on a fresh quota block."""
    jobs = _load_deferred_artifact_jobs()
    if not generate_infographics:
        for job in jobs:
            job["artifact_types"] = [
                item for item in job.get("artifact_types", []) if item != "infographic"
            ]
        jobs = [job for job in jobs if job.get("artifact_types")]
        _save_deferred_artifact_jobs(jobs)
    if not jobs:
        return {"pending": 0, "rate_limited": False, "deferred_until": None}

    now = datetime.now(timezone.utc)
    future_times = [_job_not_before(job) for job in jobs if _job_not_before(job) > now]
    due_jobs = [job for job in jobs if _job_not_before(job) <= now]
    if not due_jobs:
        return {
            "pending": len(jobs),
            "rate_limited": False,
            "deferred_until": min(future_times),
        }

    async with NotebookLMClient.from_storage(keepalive=600) as client:
        for job in list(due_jobs):
            pending_types = set(job.get("artifact_types", []))
            previous_artifact_attempted = False
            for artifact_type in (
                artifact_type
                for artifact_type in ("video", "audio", "infographic")
                if artifact_type in pending_types
            ):
                if previous_artifact_attempted:
                    logger.info(
                        "Cooling down %ds before deferred %s generation…",
                        _COOLDOWN_BEFORE_PODCAST,
                        artifact_type,
                    )
                    await asyncio.sleep(_COOLDOWN_BEFORE_PODCAST)
                try:
                    if artifact_type == "video":
                        outcome = await _resume_video(client, job)
                    elif artifact_type == "infographic":
                        outcome = await _resume_infographic(client, job)
                    elif artifact_type == "audio":
                        outcome = await _resume_audio(client, job)
                    else:
                        outcome = "failed"
                except RateLimitError:
                    outcome = "rate_limited"
                except Exception as exc:
                    outcome = "failed"
                    logger.warning(
                        "Deferred %s failed for %r (%s); continuing without it.",
                        artifact_type,
                        job.get("source_name", "source"),
                        type(exc).__name__,
                    )

                if outcome == "rate_limited":
                    not_before = _next_compute_retry()
                    job["not_before"] = not_before.isoformat()
                    _save_deferred_artifact_jobs(jobs)
                    return {
                        "pending": len(jobs),
                        "rate_limited": True,
                        "deferred_until": not_before,
                    }

                previous_artifact_attempted = True
                job["artifact_types"].remove(artifact_type)
                if outcome == "completed":
                    logger.info(
                        "Deferred %s completed for %r.",
                        artifact_type,
                        job.get("source_name", "source"),
                    )

            if not job.get("artifact_types"):
                jobs.remove(job)
            _save_deferred_artifact_jobs(jobs)

    future_times = [_job_not_before(job) for job in jobs if _job_not_before(job) > now]
    return {
        "pending": len(jobs),
        "rate_limited": False,
        "deferred_until": min(future_times) if future_times else None,
    }


async def generate_artifacts_after_delivery(
    result: dict, *, generate_infographics: bool = False
) -> dict:
    """Generate Cinematic Video, conditional Audio, then optional infographic."""
    job = {
        "notebook_id": result["notebook_id"],
        "source_name": result["channel_name"],
        "source_ids": result.get("source_ids", []),
        "video_instructions": _VIDEO_PROMPT_TEMPLATE.format(
            channel_name=result["channel_name"]
        ),
        "audio_instructions": result.get("audio_instructions", ""),
    }
    artifact_types = ["video"]
    if len(job["source_ids"]) > 1:
        artifact_types.append("audio")
    else:
        result["audio_status"] = "skipped_single_source"
        logger.info(
            "[%s] Skipping Audio Overview because the notebook has one source.",
            result["channel_name"],
        )
    if generate_infographics:
        artifact_types.append("infographic")

    async with NotebookLMClient.from_storage(keepalive=600) as client:
        for index, artifact_type in enumerate(artifact_types):
            delay = (
                _COOLDOWN_BEFORE_VIDEO
                if artifact_type == "video"
                else _COOLDOWN_BEFORE_PODCAST
                if artifact_type == "audio"
                else _COOLDOWN_BEFORE_INFOGRAPHIC
            )
            logger.info(
                "Digest delivered; cooling down %ds before %s generation…",
                delay,
                {
                    "video": "Cinematic Video Overview",
                    "audio": "Audio Overview",
                    "infographic": "infographic",
                }[artifact_type],
            )
            await asyncio.sleep(delay)
            try:
                if artifact_type == "video":
                    outcome = await _resume_video(client, job)
                elif artifact_type == "audio":
                    outcome = await _resume_audio(client, job)
                elif _existing_infographic_path(
                    date.today().isoformat(), result["channel_name"]
                ):
                    outcome = "completed"
                else:
                    outcome = await _resume_infographic(client, job)
            except RateLimitError:
                outcome = "rate_limited"
            except Exception as exc:
                outcome = "failed"
                logger.warning(
                    "%s generation failed for %r (%s); the delivered digest remains complete.",
                    {
                        "video": "Cinematic Video Overview",
                        "audio": "Audio Overview",
                        "infographic": "Infographic",
                    }[artifact_type],
                    result["channel_name"],
                    type(exc).__name__,
                )

            if outcome == "rate_limited":
                not_before = _next_compute_retry()
                remaining = artifact_types[index:]
                _queue_deferred_artifacts(
                    notebook_id=result["notebook_id"],
                    source_name=result["channel_name"],
                    source_ids=result.get("source_ids", []),
                    artifact_types=remaining,
                    video_instructions=job["video_instructions"],
                    audio_instructions=result.get("audio_instructions", ""),
                    not_before=not_before,
                )
                logger.warning(
                    "NotebookLM compute limit reached; deferred %s until %s.",
                    ", ".join(remaining),
                    not_before.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                return {
                    "rate_limited": True,
                    "deferred_until": not_before,
                    "pending": remaining,
                }

            result[f"{artifact_type}_status"] = outcome

    return {"rate_limited": False, "deferred_until": None, "pending": []}


def schedule_artifacts_after_delivery(
    result: dict,
    *,
    channel_order: int,
    generate_cinematic_video: bool = False,
    generate_infographics: bool = False,
) -> None:
    """Persist Studio work without delaying any remaining summary emails."""
    video_instructions = _VIDEO_PROMPT_TEMPLATE.format(
        channel_name=result["channel_name"]
    )
    if generate_cinematic_video:
        register_weekly_video(
            notebook_id=result["notebook_id"],
            notebook_url=result.get("notebook_url", ""),
            source_name=result["channel_name"],
            channel_order=channel_order,
            source_ids=result.get("source_ids", []),
            instructions=video_instructions,
        )

    artifact_types = []
    if len(result.get("source_ids", [])) > 1:
        register_weekly_audio(
            notebook_id=result["notebook_id"],
            notebook_url=result.get("notebook_url", ""),
            source_name=result["channel_name"],
            channel_order=channel_order,
            source_ids=result.get("source_ids", []),
            instructions=result.get("audio_instructions", ""),
        )
    else:
        result["audio_status"] = "skipped_single_source"
    if generate_infographics:
        artifact_types.append("infographic")
    if artifact_types:
        _queue_deferred_artifacts(
            notebook_id=result["notebook_id"],
            source_name=result["channel_name"],
            source_ids=result.get("source_ids", []),
            artifact_types=artifact_types,
            video_instructions=video_instructions,
            audio_instructions=result.get("audio_instructions", ""),
            not_before=datetime.now(timezone.utc),
        )


def _source_identity(title: str | None, url: str | None) -> tuple[str, str]:
    return ((title or "").strip().casefold(), (url or "").strip())


async def _get_or_create_daily_notebook(client, title: str):
    """Reuse an exact-title notebook so retries cannot create duplicates."""
    matches = [nb for nb in await client.notebooks.list() if nb.title == title]
    if not matches:
        logger.info("Creating notebook: %r", title)
        notebook = await client.notebooks.create(title)
        try:
            await client.sharing.set_public(notebook.id, True)
            logger.info("Set notebook %s to public sharing.", notebook.id)
        except Exception:
            logger.warning("Could not set notebook %s to public sharing; continuing.", notebook.id)
        return notebook, []

    candidates = []
    for notebook in matches:
        try:
            sources = await client.sources.list(notebook.id, strict=True)
        except Exception:
            logger.warning("Could not inspect existing notebook %s; treating it as empty.", notebook.id)
            sources = []
        created_at = notebook.created_at or datetime.fromtimestamp(0, tz=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        candidates.append((len(sources), created_at, notebook, sources))

    _, _, notebook, sources = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    if len(matches) > 1:
        logger.warning(
            "Found %d pre-existing notebooks titled %r; reusing the most complete one (%s).",
            len(matches),
            title,
            notebook.id,
        )
    else:
        logger.info("Resuming existing notebook %r (%s).", title, notebook.id)
    try:
        await client.sharing.set_public(notebook.id, True)
    except Exception:
        pass
    return notebook, sources


def _existing_infographic_path(today: str, source_name: str) -> str:
    base = paths.get_summaries_dir() / f"{today}_{paths.safe_channel_name(source_name)}_infographic"
    for suffix in (".jpg", ".jpeg", ".png"):
        candidate = base.with_suffix(suffix)
        if candidate.is_file() and candidate.stat().st_size > 0:
            return str(candidate)
    return ""


async def _with_artifact_retry(label: str, generate):
    # The first quota rejection defines the absolute compute-refresh anchor.
    # Propagate it immediately so the durable marker records that first event.
    return await generate()


def _get_notebooklm_bin() -> str:
    return paths.get_notebooklm_bin()


async def verify_notebooklm_auth() -> bool:
    try:
        async with NotebookLMClient.from_storage(keepalive=15) as client:
            await client.notebooks.list()
        return True
    except Exception as e:
        logger.warning("NotebookLM auth check failed: %s", e)
        return False


def _refresh_cookies_for_retry() -> bool:
    try:
        browser = os.getenv("NOTEBOOKLM_BROWSER", "chrome")
        from notebooklm.paths import get_storage_path
        from notebooklm.cli.services.login.refresh import _login_with_browser_cookies
        storage_path = get_storage_path()
        try:
            _login_with_browser_cookies(storage_path, browser)
            return True
        except SystemExit as e:
            return e.code == 0 or e.code is None
        except Exception:
            return False
    except Exception:
        logger.exception("Cookie re-extraction failed during retry.")
        return False



def _compress_infographic(png_path: str) -> str:
    """Compress the high-resolution PNG infographic to a JPEG to save space.
    Returns the path to the compressed JPG file, or the original if failed.
    """
    from PIL import Image
    from pathlib import Path
    try:
        p = Path(png_path)
        jpg_path = p.with_suffix(".jpg")
        with Image.open(p) as img:
            img.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba_img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(rgba_img, mask=rgba_img.getchannel("A"))
                rgb_img = background
            else:
                rgb_img = img.convert("RGB")
            rgb_img.save(jpg_path, "JPEG", quality=78, optimize=True, progressive=True)
        p.unlink(missing_ok=True)
        logger.info("Compressed infographic from %s to %s", p.name, jpg_path.name)
        return str(jpg_path)
    except Exception as e:
        logger.exception("Failed to compress infographic image %s", png_path)
        return png_path


async def process_source_items(
    handler: BaseSourceHandler,
    items: list[SourceItem],
    cfg: "Config",
) -> dict:
    today = date.today().isoformat()
    source_name = handler.name
    notebook_title = f"{source_name} Digest — {today}"

    videos_list = []
    for i in items:
        entry = {"title": i.title, "url": i.url, "published": i.published}
        if handler.source_type == "youtube" or "youtube.com/watch?v=" in i.url:
            match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", i.url)
            if match:
                entry["video_id"] = match.group(1)
        videos_list.append(entry)

    result: dict = {
        "channel_name": source_name,
        "source_type": handler.source_type,
        "notebook_url": "",
        "notebook_id": "",
        "summary_text": "",
        "infographic_path": "",
        "infographic_status": "pending",
        "video_status": "pending",
        "audio_status": "pending",
        "rate_limited": False,
        "deferred_until": None,
        "items": videos_list,
        "videos": videos_list,
        "error": None,
    }


    try:
        async with NotebookLMClient.from_storage(keepalive=600) as client:
            try:
                nb, existing_sources = await _get_or_create_daily_notebook(client, notebook_title)
            except NotebookLimitError as exc:
                logger.critical("NotebookLM notebook quota exceeded (%s). Stopping notebook creation for this and remaining sources.", exc)
                result["error"] = f"Notebook quota exceeded: {exc}"
                raise

            notebook_id = nb.id
            notebook_url = client.notebooks.get_share_url(notebook_id)
            result["notebook_id"] = notebook_id
            result["notebook_url"] = notebook_url
            logger.info("Using notebook: %s  url=%s", notebook_id, notebook_url)

            source_ids = []
            missing_items = []
            for item in items:
                item_identity = _source_identity(item.title, item.url)
                matched = next(
                    (
                        source
                        for source in existing_sources
                        if _source_identity(source.title, source.url) == item_identity
                        or (
                            item_identity[0]
                            and _source_identity(source.title, source.url)[0] == item_identity[0]
                        )
                    ),
                    None,
                )
                if matched:
                    source_ids.append(matched.id)
                    item.source_id = matched.id
                else:
                    missing_items.append(item)

            if missing_items:
                logger.info(
                    "Adding %d missing source(s); %d already exist in the resumed notebook.",
                    len(missing_items),
                    len(source_ids),
                )
                source_ids.extend(await handler.ingest(client, notebook_id, missing_items))
            else:
                logger.info("All %d requested source(s) already exist in the resumed notebook.", len(items))

            successful_items = [
                item for item in items
                if getattr(item, "source_id", None) and item.source_id in source_ids
            ]

            if not source_ids or not successful_items:
                result["error"] = f"None of {len(items)} source items could be added to notebook."
                logger.error("%s", result["error"])
                return result

            if len(successful_items) < len(items):
                logger.warning(
                    "Proceeding with %d of %d source items (%d failed to ingest and were skipped).",
                    len(successful_items),
                    len(items),
                    len(items) - len(successful_items),
                )
                items = successful_items
                successful_urls = {it.url for it in successful_items}
                result["items"] = [
                    entry for entry in videos_list if entry.get("url") in successful_urls
                ]
                result["videos"] = result["items"]

            logger.info("Waiting for %d source(s) to process (timeout=%ds)…", len(source_ids), int(_SOURCE_WAIT_TIMEOUT))
            try:
                await client.sources.wait_for_sources(notebook_id, source_ids, timeout=_SOURCE_WAIT_TIMEOUT)
                logger.info("All sources are ready.")
            except SourceTimeoutError as exc:
                result["error"] = "Source processing timed out; the channel will be retried."
                logger.warning("Source processing timed out for %r: %s", source_name, exc)
                return result

            from config import load_category_prompt
            summary_prompt_text = load_category_prompt(handler.category, "summary")
            if summary_prompt_text:
                prompt = summary_prompt_text.replace("{channel_name}", source_name)
            else:
                prompt = _SUMMARY_PROMPT_TEMPLATE.format(channel_name=source_name)

            logger.info("Requesting chat summary for %r…", source_name)
            try:
                result["summary_text"] = await _ask_for_valid_summary(
                    client,
                    notebook_id,
                    prompt,
                    len(items),
                )
                logger.info("Summary received (%d chars).", len(result["summary_text"]))
            except RateLimitError:
                not_before = _next_compute_retry()
                result["rate_limited"] = True
                result["deferred_until"] = not_before
                result["error"] = "NotebookLM compute limit reached while generating the summary."
                logger.warning(
                    "Summary generation reached the compute limit; retrying after %s.",
                    not_before.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
                )
                return result
            except Exception as exc:
                result["error"] = str(exc)
                logger.warning("Summary generation failed for %r: %s", source_name, exc)
                return result

            from config import load_category_prompt
            podcast_prompt_text = load_category_prompt(handler.category, "podcast")
            if podcast_prompt_text:
                audio_instructions = podcast_prompt_text.replace("{channel_name}", source_name)
            else:
                audio_instructions = _PODCAST_PROMPT_TEMPLATE.format(channel_name=source_name)
            result["source_ids"] = source_ids
            result["audio_instructions"] = audio_instructions

            retention_limit = getattr(cfg, "notebooks_retention_limit", 0)
            if retention_limit > 0:
                logger.info("Checking notebook retention policy for %r (limit=%d)…", source_name, retention_limit)
                try:
                    all_notebooks = await client.notebooks.list()
                    prefix = f"{source_name} Digest — "
                    ch_notebooks = []
                    for nb in all_notebooks:
                        if nb.title.startswith(prefix):
                            created_dt = nb.created_at
                            if not created_dt:
                                date_str = nb.title[len(prefix):]
                                try:
                                    created_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                except Exception:
                                    created_dt = datetime.fromtimestamp(0, tz=timezone.utc)
                            ch_notebooks.append((nb, created_dt))
                    ch_notebooks.sort(key=lambda x: x[1], reverse=True)
                    if len(ch_notebooks) > retention_limit:
                        to_delete = ch_notebooks[retention_limit:]
                        logger.info("Retaining %d latest, deleting %d old notebooks…", retention_limit, len(to_delete))
                        for nb_to_del, _ in to_delete:
                            logger.info("Deleting old notebook: %r (ID: %s)", nb_to_del.title, nb_to_del.id)
                            try:
                                await client.notebooks.delete(nb_to_del.id)
                                logger.info("Deleted notebook %s successfully.", nb_to_del.id)
                            except Exception:
                                logger.exception("Failed to delete notebook %s", nb_to_del.id)
                except Exception:
                    logger.exception("Error checking/deleting old notebooks for %r", source_name)

    except NotebookLimitError:
        raise
    except ValueError as exc:
        auth_msg = str(exc)
        if "Authentication expired" in auth_msg or "Redirected" in auth_msg:
            logger.warning("Authentication expired mid-run for %r. Attempting cookie re-extraction…", source_name)
            if _refresh_cookies_for_retry():
                logger.info("Cookie re-extraction succeeded. Retrying %r…", source_name)
                try:
                    return await process_source_items(handler, items, cfg)
                except ValueError as retry_exc:
                    if "Authentication expired" in str(retry_exc) or "Redirected" in str(retry_exc):
                        logger.critical("Authentication still expired after cookie refresh: %s", retry_exc)
                        print("AUTH_REQUIRED", flush=True)
                        sys.exit(2)
                    raise
            else:
                logger.critical("Cookie re-extraction failed. Cannot continue: %s", auth_msg)
                print("AUTH_REQUIRED", flush=True)
                sys.exit(2)
        logger.exception("Unexpected ValueError processing %r.", source_name)
        result["error"] = f"ValueError: {exc}"
    except Exception:
        logger.exception("Unexpected error processing %r.", source_name)
        result["error"] = "Unexpected error — see log for details."

    return result
