"""
notebooklm_service.py — NotebookLM integration layer.

Responsibilities:
  - Verify authentication via CLI subprocess
  - Pre-run cookie refresh via rookiepy
  - Create notebooks, add source items, generate summaries via chat,
    generate infographics (with download), and trigger Audio Overview
  - Sequential generation with anti-detection cooldowns
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
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
    SourceAddError,
    SourceTimeoutError,
)

from source_handlers import BaseSourceHandler, SourceItem

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

_SOURCE_WAIT_TIMEOUT = 300.0
_COOLDOWN_BEFORE_INFOGRAPHIC = 30
_COOLDOWN_BEFORE_PODCAST = 45

_SUMMARY_PROMPT_TEMPLATE = """\
You are a research analyst. The following content from "{channel_name}" \
has been added as sources. Please provide a structured digest with:

1. **Executive Summary** (2-3 sentences overview of all items)
2. **Item-by-Item Breakdown** (for each item: key topics, main arguments, notable insights)
3. **Cross-Item Themes** (recurring ideas or contradictions across the items)
4. **Actionable Takeaways** (what a reader/viewer should do or learn from this batch)

Be specific, cite items directly, and avoid generic statements.\
"""

_PODCAST_PROMPT_TEMPLATE = """\
Create an engaging podcast-style deep dive into the latest \
content from '{channel_name}'. \
Discuss key insights, themes, and takeaways in a conversational tone.\
"""


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
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                background = Image.new("RGB", img.size, (255, 255, 255))
                mask = img.split()[3] if img.mode == "RGBA" else None
                background.paste(img, mask=mask)
                rgb_img = background
            else:
                rgb_img = img.convert("RGB")
            rgb_img.save(jpg_path, "JPEG", quality=80, optimize=True)
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
        "items": videos_list,
        "videos": videos_list,
        "error": None,
    }


    try:
        async with NotebookLMClient.from_storage(keepalive=600) as client:
            logger.info("Creating notebook: %r", notebook_title)
            try:
                nb = await client.notebooks.create(notebook_title)
            except NotebookLimitError as exc:
                logger.critical("NotebookLM notebook quota exceeded (%s). Stopping notebook creation for this and remaining sources.", exc)
                result["error"] = f"Notebook quota exceeded: {exc}"
                raise

            notebook_id = nb.id
            notebook_url = client.notebooks.get_share_url(notebook_id)
            result["notebook_id"] = notebook_id
            result["notebook_url"] = notebook_url
            logger.info("Notebook created: %s  url=%s", notebook_id, notebook_url)

            source_ids = await handler.ingest(client, notebook_id, items)

            if not source_ids:
                result["error"] = "All source items failed to add."
                logger.error("No sources were successfully added for %r.", source_name)
                return result

            logger.info("Waiting for %d source(s) to process (timeout=%ds)…", len(source_ids), int(_SOURCE_WAIT_TIMEOUT))
            try:
                await client.sources.wait_for_sources(notebook_id, source_ids, timeout=_SOURCE_WAIT_TIMEOUT)
                logger.info("All sources are ready.")
            except SourceTimeoutError as exc:
                logger.warning("Source processing timed out for %r: %s. Proceeding with summary anyway.", source_name, exc)

            if cfg.summary_prompt:
                prompt = cfg.summary_prompt.format(channel_name=source_name)
            else:
                prompt = _SUMMARY_PROMPT_TEMPLATE.format(channel_name=source_name)

            logger.info("Requesting chat summary for %r…", source_name)
            try:
                chat_result = await client.chat.ask(notebook_id, prompt)
                result["summary_text"] = chat_result.answer
                logger.info("Summary received (%d chars).", len(result["summary_text"]))
            except Exception:
                logger.exception("chat.ask() failed for %r. Summary will be empty.", source_name)
                result["summary_text"] = ""

            logger.info("Cooling down %ds before infographic generation…", _COOLDOWN_BEFORE_INFOGRAPHIC)
            await asyncio.sleep(_COOLDOWN_BEFORE_INFOGRAPHIC)

            logger.info("Generating infographic for notebook %s…", notebook_id)
            try:
                infographic_status = await client.artifacts.generate_infographic(
                    notebook_id,
                    instructions=f"Create a visual infographic summarizing the key insights from the latest content by '{source_name}'.",
                    orientation=InfographicOrientation.LANDSCAPE,
                    detail_level=InfographicDetail.STANDARD,
                    style=InfographicStyle.AUTO_SELECT,
                )
                if infographic_status.task_id:
                    completed = await client.artifacts.wait_for_completion(notebook_id, infographic_status.task_id, timeout=900)
                    if completed.is_complete:
                        safe_name = paths.safe_channel_name(source_name)
                        out_path = str(paths.get_summaries_dir() / f"{today}_{safe_name}_infographic.png")
                        await client.artifacts.download_infographic(notebook_id, out_path, artifact_id=infographic_status.task_id)
                        compressed_path = _compress_infographic(out_path)
                        result["infographic_path"] = compressed_path
                        logger.info("Infographic saved: %s", compressed_path)
                    else:
                        logger.warning("Infographic generation did not complete: status=%s", completed.status)
                else:
                    logger.warning("Infographic generation returned no task_id.")
            except Exception:
                logger.exception("Infographic generation failed for %r — skipping.", source_name)

            logger.info("Cooling down %ds before podcast generation…", _COOLDOWN_BEFORE_PODCAST)
            await asyncio.sleep(_COOLDOWN_BEFORE_PODCAST)

            if cfg.podcast_prompt:
                audio_instructions = cfg.podcast_prompt.format(channel_name=source_name)
            else:
                audio_instructions = _PODCAST_PROMPT_TEMPLATE.format(channel_name=source_name)

            logger.info("Triggering Audio Overview for notebook %s…", notebook_id)
            try:
                await client.artifacts.generate_audio(notebook_id, source_ids=source_ids, instructions=audio_instructions)
                logger.info("Audio Overview triggered (fire-and-forget).")
            except Exception:
                logger.exception("generate_audio() failed for %r — skipping audio.", source_name)

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
