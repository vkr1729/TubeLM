"""
notebooklm_service.py — NotebookLM integration layer.

Responsibilities:
  - Verify authentication via CLI subprocess
  - Pre-run cookie refresh via rookiepy
  - Create notebooks, add video URL sources, generate summaries via chat,
    generate infographics (with download), and trigger Audio Overview
  - Sequential generation with anti-detection cooldowns
"""

import asyncio
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from notebooklm import (
    NotebookLMClient,
    InfographicOrientation,
    InfographicDetail,
    InfographicStyle,
)
from notebooklm.exceptions import (
    NotebookLimitError,
    SourceAddError,
    SourceTimeoutError,
)

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

# Timeout in seconds waiting for all sources to finish processing
_SOURCE_WAIT_TIMEOUT = 300.0

# Cooldown durations (seconds) to avoid NotebookLM rate-limiting
_COOLDOWN_BEFORE_INFOGRAPHIC = 30
_COOLDOWN_BEFORE_PODCAST = 45

# Structured research analyst prompt — injected with channel name at call time
_SUMMARY_PROMPT_TEMPLATE = """\
You are a research analyst. The following YouTube videos from the channel "{channel_name}" \
have been added as sources. Please provide a structured digest with:

1. **Executive Summary** (2-3 sentences overview of all videos)
2. **Video-by-Video Breakdown** (for each video: key topics, main arguments, notable insights)
3. **Cross-Video Themes** (recurring ideas or contradictions across the videos)
4. **Actionable Takeaways** (what a viewer should do or learn from this batch)

Be specific, cite video topics directly, and avoid generic statements.\
"""

_PODCAST_PROMPT_TEMPLATE = """\
Create an engaging podcast-style deep dive into the latest \
videos from the YouTube channel '{channel_name}'. \
Discuss key insights, themes, and takeaways in a conversational tone.\
"""


def _get_notebooklm_bin() -> str:
    exe_dir = os.path.dirname(sys.executable)
    proj_dir = os.path.dirname(os.path.abspath(__file__))
    paths_to_check = []
    if sys.platform == "win32":
        paths_to_check.extend([
            os.path.join(exe_dir, "notebooklm.exe"),
            os.path.join(exe_dir, "notebooklm"),
            os.path.join(exe_dir, "_internal", "Scripts", "notebooklm.exe"),
            os.path.join(exe_dir, "_internal", "Scripts", "notebooklm"),
            os.path.join(proj_dir, ".venv", "Scripts", "notebooklm.exe"),
            os.path.join(proj_dir, ".venv", "Scripts", "notebooklm")
        ])
    else:
        paths_to_check.extend([
            os.path.join(exe_dir, "notebooklm"),
            os.path.join(exe_dir, "_internal", "bin", "notebooklm"),
            os.path.join(proj_dir, ".venv", "bin", "notebooklm")
        ])
    for p in paths_to_check:
        if os.path.exists(p):
            return p
    return "notebooklm"


def verify_notebooklm_auth() -> bool:
    """Check whether NotebookLM authentication cookies are valid.

    Runs `notebooklm auth check --test` as a subprocess.
    Returns True if exit code is 0, False otherwise.

    This function never raises — all subprocess errors are caught and
    logged so the caller can decide how to handle the failure.
    """
    notebooklm_bin = _get_notebooklm_bin()

    try:
        result = subprocess.run(
            [notebooklm_bin, "auth", "check", "--test"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("NotebookLM auth check passed.")
            return True
        logger.warning(
            "NotebookLM auth check failed (exit %d): %s",
            result.returncode,
            (result.stdout + result.stderr).strip(),
        )
        return False
    except FileNotFoundError:
        logger.error(
            "notebooklm binary not found at %s. "
            "Run: pip install notebooklm-py[browser]",
            notebooklm_bin,
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error("notebooklm auth check timed out after 30 seconds.")
        return False
    except Exception:
        logger.exception("Unexpected error running notebooklm auth check.")
        return False


def _refresh_cookies_for_retry() -> bool:
    """Re-extract cookies from Chrome for mid-run auth recovery.

    Called when authentication expires during processing. Uses the same
    mechanism as the pre-run refresh in main.py.
    """
    notebooklm_bin = _get_notebooklm_bin()
    try:
        result = subprocess.run(
            [notebooklm_bin, "login", "--browser-cookies", "chrome"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        logger.exception("Cookie re-extraction failed during retry.")
        return False


async def process_channel_videos(
    channel_name: str,
    videos: list[dict],
    cfg: "Config",
) -> dict:
    """Create a NotebookLM notebook for a channel's new videos.

    Steps:
      1. Create notebook titled "[Channel Name] Digest — YYYY-MM-DD"
      2. Add all video URLs as sources (non-blocking batch)
      3. Wait for all sources to finish processing (up to 300 s)
      4. Ask chat API for structured research analyst summary
      5. Cooldown (30s) → Generate infographic → Wait → Download PNG
      6. Cooldown (45s) → Trigger Audio Overview (fire-and-forget)

    Args:
        channel_name: Human-readable channel name (used in notebook title & prompt).
        videos: List of dicts with keys: title, url, published.
        cfg: Loaded Config instance with prompt templates.

    Returns:
        dict with keys: channel_name, notebook_url, notebook_id,
                        summary_text, infographic_path, videos, error (str or None).

    Raises:
        SystemExit(2): If NotebookLM authentication has expired (signals AUTH_REQUIRED).
        NotebookLimitError: Re-raised so main.py can halt processing.

    All other errors are caught and surfaced in the returned dict's "error" key.
    """
    today = date.today().isoformat()
    notebook_title = f"{channel_name} Digest — {today}"

    result: dict = {
        "channel_name": channel_name,
        "notebook_url": "",
        "notebook_id": "",
        "summary_text": "",
        "infographic_path": "",
        "videos": videos,
        "error": None,
    }

    try:
        # Use keepalive=600 to prevent cookies from going stale during long runs
        client = await NotebookLMClient.from_storage(keepalive=600)
        async with client:
            # ── Step 1: Create notebook ───────────────────────────────────────
            logger.info("Creating notebook: %r", notebook_title)
            try:
                nb = await client.notebooks.create(notebook_title)
            except NotebookLimitError as exc:
                logger.critical(
                    "NotebookLM notebook quota exceeded (%s). "
                    "Stopping notebook creation for this and remaining channels.",
                    exc,
                )
                result["error"] = f"Notebook quota exceeded: {exc}"
                raise  # Re-raise so main.py can catch and halt further processing

            notebook_id = nb.id
            # get_share_url is a sync helper — no network call, just URL formatting
            notebook_url = client.notebooks.get_share_url(notebook_id)
            result["notebook_id"] = notebook_id
            result["notebook_url"] = notebook_url
            logger.info("Notebook created: %s  url=%s", notebook_id, notebook_url)

            # ── Step 2: Add video URLs as sources (non-blocking batch) ────────
            source_ids: list[str] = []
            for video in videos:
                url = video["url"]
                try:
                    source = await client.sources.add_url(notebook_id, url, wait=False)
                    source_ids.append(source.id)
                    logger.info("Queued source: %s  (%s)", url, source.id)
                except SourceAddError as exc:
                    logger.warning(
                        "Failed to add source %s — skipping: %s", url, exc
                    )

            if not source_ids:
                result["error"] = "All source URLs failed to add."
                logger.error(
                    "No sources were successfully added for channel %r.", channel_name
                )
                return result

            # ── Step 3: Wait for all sources to be processed ──────────────────
            logger.info(
                "Waiting for %d source(s) to process (timeout=%ds)…",
                len(source_ids),
                int(_SOURCE_WAIT_TIMEOUT),
            )
            try:
                await client.sources.wait_for_sources(
                    notebook_id, source_ids, timeout=_SOURCE_WAIT_TIMEOUT
                )
                logger.info("All sources are ready.")
            except SourceTimeoutError as exc:
                logger.warning(
                    "Source processing timed out for channel %r: %s. "
                    "Proceeding with summary anyway.",
                    channel_name,
                    exc,
                )

            # ── Step 4: Generate summary via chat API ─────────────────────────
            if cfg.summary_prompt:
                prompt = cfg.summary_prompt.format(channel_name=channel_name)
            else:
                prompt = _SUMMARY_PROMPT_TEMPLATE.format(channel_name=channel_name)

            logger.info("Requesting chat summary for %r…", channel_name)
            try:
                chat_result = await client.chat.ask(notebook_id, prompt)
                result["summary_text"] = chat_result.answer
                logger.info(
                    "Summary received (%d chars).", len(result["summary_text"])
                )
            except Exception:
                logger.exception(
                    "chat.ask() failed for channel %r. Summary will be empty.",
                    channel_name,
                )
                result["summary_text"] = ""

            # ── Step 4.5: Cooldown before infographic ─────────────────────────
            logger.info(
                "Cooling down %ds before infographic generation…",
                _COOLDOWN_BEFORE_INFOGRAPHIC,
            )
            await asyncio.sleep(_COOLDOWN_BEFORE_INFOGRAPHIC)

            # ── Step 5: Generate infographic → Wait → Download ────────────────
            logger.info("Generating infographic for notebook %s…", notebook_id)
            try:
                infographic_status = await client.artifacts.generate_infographic(
                    notebook_id,
                    instructions=(
                        f"Create a visual infographic summarizing the key insights "
                        f"from the latest videos by '{channel_name}'."
                    ),
                    orientation=InfographicOrientation.LANDSCAPE,
                    detail_level=InfographicDetail.STANDARD,
                    style=InfographicStyle.AUTO_SELECT,
                )
                if infographic_status.task_id:
                    completed = await client.artifacts.wait_for_completion(
                        notebook_id, infographic_status.task_id, timeout=300
                    )
                    if completed.is_complete:
                        safe_name = channel_name.replace(" ", "_").replace("/", "_")
                        out_path = f"summaries/{today}_{safe_name}_infographic.png"
                        await client.artifacts.download_infographic(
                            notebook_id, out_path
                        )
                        result["infographic_path"] = out_path
                        logger.info("Infographic saved: %s", out_path)
                    else:
                        logger.warning(
                            "Infographic generation did not complete: status=%s",
                            completed.status,
                        )
                else:
                    logger.warning("Infographic generation returned no task_id.")
            except Exception:
                logger.exception(
                    "Infographic generation failed for %r — skipping.",
                    channel_name,
                )

            # ── Step 5.5: Cooldown before podcast ─────────────────────────────
            logger.info(
                "Cooling down %ds before podcast generation…",
                _COOLDOWN_BEFORE_PODCAST,
            )
            await asyncio.sleep(_COOLDOWN_BEFORE_PODCAST)

            # ── Step 6: Trigger Audio Overview — FIRE AND FORGET ──────────────
            if cfg.podcast_prompt:
                audio_instructions = cfg.podcast_prompt.format(
                    channel_name=channel_name
                )
            else:
                audio_instructions = _PODCAST_PROMPT_TEMPLATE.format(
                    channel_name=channel_name
                )

            logger.info("Triggering Audio Overview for notebook %s…", notebook_id)
            try:
                await client.artifacts.generate_audio(
                    notebook_id,
                    instructions=audio_instructions,
                )
                logger.info("Audio Overview triggered (fire-and-forget).")
            except Exception:
                logger.exception(
                    "generate_audio() failed for channel %r — skipping audio.",
                    channel_name,
                )

            # ── Step 7: Enforce notebook retention limit ──────────────────────
            retention_limit = getattr(cfg, "notebooks_retention_limit", 0)
            if retention_limit > 0:
                logger.info(
                    "Checking notebook retention policy for %r (limit=%d)…",
                    channel_name,
                    retention_limit,
                )
                try:
                    all_notebooks = await client.notebooks.list()
                    prefix = f"{channel_name} Digest — "
                    ch_notebooks = []
                    for nb in all_notebooks:
                        if nb.title.startswith(prefix):
                            # Try parsing date from title if created_at is None
                            created_dt = nb.created_at
                            if not created_dt:
                                date_str = nb.title[len(prefix):]
                                try:
                                    created_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                except Exception:
                                    created_dt = datetime.fromtimestamp(0, tz=timezone.utc)
                            ch_notebooks.append((nb, created_dt))
                    
                    # Sort descending by date/time (latest first)
                    ch_notebooks.sort(key=lambda x: x[1], reverse=True)
                    
                    if len(ch_notebooks) > retention_limit:
                        to_delete = ch_notebooks[retention_limit:]
                        logger.info(
                            "Found %d notebooks for %r. Retaining %d latest, deleting %d old notebooks…",
                            len(ch_notebooks),
                            channel_name,
                            retention_limit,
                            len(to_delete),
                        )
                        for nb_to_del, _ in to_delete:
                            logger.info(
                                "Deleting old notebook: %r (ID: %s)",
                                nb_to_del.title,
                                nb_to_del.id,
                            )
                            try:
                                await client.notebooks.delete(nb_to_del.id)
                                logger.info("Deleted notebook %s successfully.", nb_to_del.id)
                            except Exception:
                                logger.exception("Failed to delete notebook %s", nb_to_del.id)
                    else:
                        logger.info(
                            "Found %d notebooks for %r, which is within the limit of %d. No deletion needed.",
                            len(ch_notebooks),
                            channel_name,
                            retention_limit,
                        )
                except Exception:
                    logger.exception("Error checking/deleting old notebooks for channel %r", channel_name)

    except NotebookLimitError:
        # Already logged as CRITICAL above; re-raise so main halts processing
        raise
    except ValueError as exc:
        # Auth expired during API call — attempt cookie re-extraction + retry
        auth_msg = str(exc)
        if "Authentication expired" in auth_msg or "Redirected" in auth_msg:
            logger.warning(
                "Authentication expired mid-run for channel %r. "
                "Attempting cookie re-extraction…",
                channel_name,
            )
            if _refresh_cookies_for_retry():
                logger.info("Cookie re-extraction succeeded. Retrying channel %r…", channel_name)
                try:
                    # Recursive retry (once only — no infinite loop risk because
                    # if cookies are still invalid, this will hit sys.exit(2))
                    return await process_channel_videos(channel_name, videos, cfg)
                except ValueError as retry_exc:
                    if "Authentication expired" in str(retry_exc) or "Redirected" in str(retry_exc):
                        logger.critical(
                            "Authentication still expired after cookie refresh: %s",
                            retry_exc,
                        )
                        print("AUTH_REQUIRED", flush=True)
                        sys.exit(2)
                    raise
            else:
                logger.critical(
                    "Cookie re-extraction failed. Cannot continue: %s",
                    auth_msg,
                )
                print("AUTH_REQUIRED", flush=True)
                sys.exit(2)
        # Other ValueError — treat as unexpected per-channel error
        logger.exception(
            "Unexpected ValueError processing channel %r.", channel_name
        )
        result["error"] = f"ValueError: {exc}"
    except Exception:
        logger.exception(
            "Unexpected error processing channel %r.", channel_name
        )
        result["error"] = "Unexpected error — see log for details."

    return result
