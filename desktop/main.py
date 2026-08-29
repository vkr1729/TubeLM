"""
main.py — TubeLM Weekly Sync

Entry point. Orchestrates:
  1. Pre-run cookie refresh
  2. Auth gate
  3. RSS video discovery + multi-layer Shorts filtering
  4. NotebookLM notebook creation, source upload, and summary
  5. Per-source email delivery and checkpointing
  6. Optional cross-source Top 10 selection and email
  7. Independent conditional Audio and opt-in Cinematic Video generation
  8. Durable background resume when compute is limited

Usage:
  python main.py              # Full run
  python main.py --dry-run    # Discover videos only, no API calls
  python main.py --skip-email # Full run but skip email delivery
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import ConfigurationError, load_config
from email_service import send_artifact_completion_email, send_channel_email
import paths
from notebooklm_service import (
    process_source_items,
    resume_deferred_artifacts,
    schedule_artifacts_after_delivery,
    verify_notebooklm_auth,
)
from notebooklm import NotebookLMClient
from notebooklm.exceptions import NotebookLimitError
from sources_loader import load_sources
from source_handlers.factory import create_handler
from source_handlers import SourceItem
from run_control import (
    PipelineAlreadyRunningError,
    PipelineRunLock,
    clear_resume_request,
    load_compute_deferral,
    load_resume_request,
    request_system_shutdown,
    save_compute_deferral,
    save_resume_request,
)
from weekly_video_service import (
    mark_video_completion_email_sent,
    pending_weekly_video_count,
    resume_weekly_video_batches,
    seal_weekly_video_batch,
    unnotified_completed_video_batches,
)
from weekly_audio_service import (
    mark_audio_completion_email_sent,
    pending_weekly_audio_count,
    resume_weekly_audio_batches,
    seal_weekly_audio_batch,
    unnotified_completed_audio_batches,
)
from top10_service import (
    generate_and_send_top10_digest,
    prepare_top10_batch,
    record_top10_source,
)

# ── Logging setup ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_LOOKBACK_DAYS = 7

# Inter-channel cooldown to avoid NotebookLM rate-limiting (seconds)
INTER_CHANNEL_COOLDOWN = 120

# Discovery is network-bound (RSS, webpages, YouTube feeds). Keep a modest
# ceiling so a large source list is fast without creating a request burst.
DISCOVERY_CONCURRENCY = 6


# ── Cookie refresh ─────────────────────────────────────────────────────────────

def _get_notebooklm_bin() -> str:
    return paths.get_notebooklm_bin()


def refresh_cookies() -> bool:
    """Refresh NotebookLM cookies before the run.

    Loads the custom browser setting and performs cookie extraction in-process.
    Returns True if successful, False otherwise.
    """
    try:
        browser = os.getenv("NOTEBOOKLM_BROWSER", "chrome")
        from notebooklm.paths import get_storage_path
        from notebooklm.cli.services.login.refresh import _login_with_browser_cookies

        storage_path = get_storage_path()
        logger.info("Refreshing NotebookLM cookies from %s in-process...", browser)

        try:
            _login_with_browser_cookies(storage_path, browser)
            logger.info("Cookie refresh successful.")
            return True
        except SystemExit as e:
            success = (e.code == 0 or e.code is None)
            if success:
                logger.info("Cookie refresh successful.")
            else:
                logger.warning("Cookie refresh failed.")
            return success
        except Exception as e:
            logger.warning("Cookie refresh failed: %s", e)
            return False
    except Exception:
        logger.exception("Unexpected error during cookie refresh.")
        return False


# ── State management ───────────────────────────────────────────────────────────

def load_source_state(state_file: Path, state_key: str) -> datetime:
    """Return the last-run datetime for a specific source (UTC, timezone-aware).

    Lookup priority:
      1. state["sources"][state_key]
      2. state["last_run_time"] (global fallback)
      3. DEFAULT_LOOKBACK_DAYS ago (hard fallback)
    """
    default = datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    try:
        if not state_file.exists():
            return default
        text = state_file.read_text(encoding="utf-8")
        data = json.loads(text)

        sources_state = data.get("sources", {})
        if isinstance(sources_state, dict):
            ts = sources_state.get(state_key)
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt

        ts = data.get("last_run_time")
        if ts:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        return default
    except Exception as exc:
        logger.warning("Could not parse state for %s (%s) — using %d-day lookback.", state_key, exc, DEFAULT_LOOKBACK_DAYS)
        return default


def save_state(state_file: Path, processed_keys: list[str]) -> None:
    """Update state.json with the current UTC timestamp for processed sources."""
    now = datetime.now(timezone.utc).isoformat()
    data = {}
    try:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass

    if "sources" not in data or not isinstance(data["sources"], dict):
        data["sources"] = {}
    data.pop("channels", None)

    for key in processed_keys:
        data["sources"][key] = now

    data["last_run_time"] = now
    _write_state_file(state_file, data)
    logger.info("state.json updated for keys: %s", ", ".join(processed_keys))


def _write_state_file(state_file: Path, data: dict) -> None:
    """Atomically replace the state file so interrupted runs cannot truncate it."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_file.with_name(f".{state_file.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp_path, state_file)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def materialize_source_checkpoints(state_file: Path, handlers: list) -> None:
    """Give every selected source an explicit checkpoint before discovery.

    Without this, a failed new source can inherit a newer global timestamp when
    another source succeeds, silently skipping content on its retry.
    """
    data = {}
    try:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read state while materializing source checkpoints.")

    sources_state = data.setdefault("sources", {})
    if not isinstance(sources_state, dict):
        sources_state = {}
        data["sources"] = sources_state

    changed = False
    for handler in handlers:
        state_key = handler.state_key()
        if sources_state.get(state_key):
            continue
        sources_state[state_key] = load_source_state(state_file, state_key).isoformat()
        changed = True

    if changed:
        _write_state_file(state_file, data)
        logger.info("Materialized explicit checkpoints for selected sources.")


def load_seen_urls(state_file: Path, state_key: str) -> set[str]:
    """Load previously seen URLs for a source key from state.json."""
    try:
        if not state_file.exists():
            return set()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        seen = data.get("seen_urls", {})
        if isinstance(seen, dict):
            return set(seen.get(state_key, []))
    except Exception:
        pass
    return set()


def save_seen_urls(state_file: Path, state_key: str, urls: set[str]) -> None:
    """Save seen URLs for a source key to state.json."""
    data = {}
    try:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    if "seen_urls" not in data or not isinstance(data["seen_urls"], dict):
        data["seen_urls"] = {}
    existing = set(data["seen_urls"].get(state_key, []))
    existing.update(urls)
    data["seen_urls"][state_key] = sorted(existing)
    _write_state_file(state_file, data)


async def discover_sources(handlers: list, state_file: Path) -> list[tuple]:
    """Discover source items concurrently while preserving handler order."""
    semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

    async def discover_one(handler):
        state_key = handler.state_key()
        since_dt = load_source_state(state_file, state_key)
        seen_urls = load_seen_urls(state_file, state_key) if handler.source_type == "webpage" else None
        logger.info("[%s] Discovering content published after %s…", handler.name, since_dt.isoformat())
        try:
            async with semaphore:
                items = await asyncio.to_thread(handler.discover, since_dt, seen_urls)
        except Exception:
            logger.exception("[%s] Discovery failed unexpectedly.", handler.name)
            items = None
        return handler, items

    return await asyncio.gather(*(discover_one(handler) for handler in handlers))


# ── Markdown digest writer ─────────────────────────────────────────────────────

def write_markdown_digest(sources_data: list[dict], run_date: str) -> Path:
    """Write a Markdown digest file to summaries/{date}_digest.md.

    Args:
        sources_data: List of source result dicts.
        run_date: Date string for the filename (YYYY-MM-DD).

    Returns:
        Path to the written file.
    """
    summaries_dir = paths.get_summaries_dir()
    summaries_dir.mkdir(parents=True, exist_ok=True)
    out_path = summaries_dir / f"{run_date}_digest.md"

    total_items = sum(len(ch.get("videos", [])) for ch in sources_data)
    lines = [
        f"# TubeLM Digest — {run_date}",
        "",
        f"**{len(sources_data)} source(s) · {total_items} new item(s)**",
        "",
        "---",
        "",
    ]

    for ch in sources_data:
        lines.append(f"## {ch['channel_name']}")
        lines.append("")
        if ch.get("notebook_url"):
            lines.append(f"📒 [Open in NotebookLM]({ch['notebook_url']})")
            lines.append("")
        if ch.get("error"):
            lines.append(f"> ⚠️ **Error:** {ch['error']}")
            lines.append("")
        items_list = ch.get("videos", ch.get("items", []))
        lines.append(f"### New Items ({len(items_list)})")
        lines.append("")
        for item in items_list:
            if item.get("url"):
                lines.append(f"- [{item['title']}]({item['url']}) — {item['published']}")
            else:
                lines.append(f"- {item['title']} — {item['published']}")
        lines.append("")
        if ch.get("summary_text"):
            lines.append("### AI Summary")
            lines.append("")
            lines.append(ch["summary_text"])
        else:
            lines.append("*Summary unavailable.*")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Markdown digest written: %s", out_path)
    return out_path


# ── Main orchestration ─────────────────────────────────────────────────────────

async def _finish_background_artifacts(
    cfg, *, seal_video_batch: bool, send_completion_emails: bool = True
) -> bool:
    """Advance independent Audio, Video, and optional infographic queues."""
    if seal_video_batch:
        seal_weekly_video_batch()
        seal_weekly_audio_batch()

    audio_batch = {"pending": 0, "deferred_until": None, "rate_limited": False}
    video_batch = {"pending": 0, "deferred_until": None, "rate_limited": False}
    if pending_weekly_audio_count() or pending_weekly_video_count():
        async with NotebookLMClient.from_storage(keepalive=600) as client:
            if pending_weekly_audio_count():
                audio_batch = await resume_weekly_audio_batches(client)
            # Video is always attempted separately, even when Audio is limited.
            if pending_weekly_video_count():
                video_batch = await resume_weekly_video_batches(client)

    if audio_batch["pending"]:
        logger.info(
            "%d weekly Audio Overview(s) remain; background resume is scheduled.",
            audio_batch["pending"],
        )
    if video_batch["pending"]:
        logger.info(
            "%d weekly Cinematic Video(s) remain; background resume is scheduled.",
            video_batch["pending"],
        )

    deferred_artifacts = await resume_deferred_artifacts(
        generate_infographics=getattr(cfg, "generate_infographics", False)
    )

    notification_failed = False
    audio_notifications = unnotified_completed_audio_batches()
    video_notifications = unnotified_completed_video_batches()
    if not send_completion_emails:
        for batch in audio_notifications:
            mark_audio_completion_email_sent(batch["week_start"])
        for batch in video_notifications:
            mark_video_completion_email_sent(batch["week_start"])
        if audio_notifications or video_notifications:
            logger.info("Artifact completion emails were skipped by configuration.")
    else:
        for batch in audio_notifications:
            try:
                send_artifact_completion_email("audio", batch, cfg)
            except Exception:
                logger.exception("Audio completion email failed and will be retried.")
                notification_failed = True
            else:
                mark_audio_completion_email_sent(batch["week_start"])
        for batch in video_notifications:
            try:
                send_artifact_completion_email("video", batch, cfg)
            except Exception:
                logger.exception("Cinematic Video completion email failed and will be retried.")
                notification_failed = True
            else:
                mark_video_completion_email_sent(batch["week_start"])

    pending = bool(
        audio_batch["pending"]
        or video_batch["pending"]
        or deferred_artifacts["pending"]
        or notification_failed
    )
    if pending:
        retry_times = [
            value
            for value in (
                audio_batch.get("deferred_until"),
                video_batch.get("deferred_until"),
                deferred_artifacts.get("deferred_until"),
            )
            if value is not None
        ]
        if notification_failed:
            retry_times.append(datetime.now(timezone.utc) + timedelta(minutes=15))
        deferred_until = min(retry_times) if retry_times else (
            datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        save_compute_deferral(
            paths.get_compute_deferral_file(),
            deferred_until,
            "Background artifacts or their completion email are waiting to resume.",
        )
        return False
    return True


async def async_main(
    dry_run: bool,
    skip_email: bool,
    channels_filter: str | None = None,
    artifacts_only: bool = False,
) -> bool:
    """Async entry point.

    Args:
        dry_run: If True, only discover and print videos — no NotebookLM calls.
        skip_email: If True, skip email delivery after processing.
        channels_filter: Comma-separated list of channel IDs to run selectively.
    """
    # ── Load configuration ─────────────────────────────────────────────────
    try:
        cfg = load_config()
    except ConfigurationError as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    completion_emails_enabled = not skip_email
    if artifacts_only:
        skip_email = True

    # ── Validate SMTP connection ───────────────────────────────────────────
    has_smtp = all([cfg.smtp_server, cfg.smtp_username, cfg.smtp_password, cfg.sender_email, cfg.recipient_email])
    if not has_smtp:
        logger.warning("SMTP configuration is incomplete. Automatically skipping email delivery.")
        skip_email = True
        completion_emails_enabled = False

    if not dry_run and not skip_email:
        try:
            from email_service import verify_smtp_connection
            verify_smtp_connection(cfg)
        except Exception as exc:
            logger.warning(
                "SMTP validation failed: %s. "
                "Local digests will still be written, but email delivery will be skipped.",
                exc,
            )
            skip_email = True
            completion_emails_enabled = False


    # ── Auth gate & Cookie refresh ─────────────────────────────────────────
    if not dry_run:
        logger.info("Checking existing NotebookLM authentication…")
        if await verify_notebooklm_auth():
            logger.info("Authentication verified with existing cached session. Skipping cookie refresh.")
        else:
            logger.info("Existing auth invalid or expired. Attempting cookie refresh...")
            refresh_cookies()
            logger.info("Verifying authentication after cookie refresh…")
            if not await verify_notebooklm_auth():
                print("AUTH_REQUIRED", flush=True)
                sys.exit(2)
            logger.info("Authentication verified after cookie refresh.")

        if artifacts_only:
            logger.info("Resuming Studio artifacts only; source discovery is skipped.")
            return await _finish_background_artifacts(
                cfg,
                seal_video_batch=False,
                send_completion_emails=completion_emails_enabled,
            )

    # ── Load sources and state ────────────────────────────────────────────
    sources = load_sources(cfg.sources_file)
    handlers = [create_handler(src, cfg) for src in sources]
    channel_orders = {
        handler.state_key(): index
        for index, handler in enumerate(handlers, start=1)
    }
    cinematic_selection = {
        handler.state_key(): bool(
            source.get("generate_cinematic_video", False)
            if isinstance(source, dict)
            else False
        )
        for source, handler in zip(sources, handlers)
    }

    if channels_filter:
        selected = {s.strip() for s in channels_filter.split(",") if s.strip()}
        filtered_handlers = []
        for h in handlers:
            match = h.state_key() in selected or h.name in selected
            if not match and hasattr(h, 'channel_id'):
                match = h.channel_id in selected
            if match:
                filtered_handlers.append(h)
        handlers = filtered_handlers
        logger.info(
            "Running selectively for %d source(s): %s",
            len(handlers),
            ", ".join(h.name for h in handlers),
        )
        if not handlers:
            logger.error("No configured sources matched the selective run filter.")
            return False

    if not dry_run:
        materialize_source_checkpoints(cfg.state_file, handlers)

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    top10_enabled = bool(
        getattr(cfg, "generate_top10_digest", False)
        and not dry_run
        and not skip_email
    )
    top10_run_date = (
        prepare_top10_batch(run_date) if top10_enabled else run_date
    )

    retry_stages = [
        {"name": "Initial Run", "delay_hours": 0},
        {"name": "1-Hour Retry Run", "delay_hours": 1},
        {"name": "3-Hour Retry Run", "delay_hours": 2},
    ]

    active_handlers = list(handlers)
    quota_deferred_until = None

    for stage_idx, stage in enumerate(retry_stages):
        if not active_handlers:
            break

        if stage["delay_hours"] > 0:
            delay_sec = stage["delay_hours"] * 3600
            if dry_run:
                logger.info(
                    "[%s] DRY-RUN: Simulating sleep delay of %d hour(s) (%d seconds). Sleeping 1s for dry-run.",
                    stage["name"], stage["delay_hours"], delay_sec,
                )
                await asyncio.sleep(1)
            else:
                logger.info(
                    "[%s] Sleeping %d hour(s) before retry run...",
                    stage["name"], stage["delay_hours"],
                )
                await asyncio.sleep(delay_sec)

        logger.info("=== Starting Stage: %s ===", stage["name"])

        successful_keys = []
        failed_handlers = []
        stage_handler_items: list[tuple] = []

        discovered_sources = await discover_sources(active_handlers, cfg.state_file)
        for handler, items in discovered_sources:
            state_key = handler.state_key()

            if items is None:
                logger.warning("[%s] Skipping source in this stage due to transient failure.", handler.name)
                failed_handlers.append(handler)
                continue

            if not items:
                logger.info("[%s] No new content found.", handler.name)
                successful_keys.append(state_key)
                if not dry_run:
                    save_state(cfg.state_file, [state_key])
                continue

            logger.info("[%s] %d new item(s) to process.", handler.name, len(items))
            stage_handler_items.append((handler, items))

        if dry_run:
            if not stage_handler_items:
                logger.info("[%s] [DRY-RUN] No new content found across sources.", stage["name"])
            else:
                logger.info("[%s] [DRY-RUN] Would process sources:", stage["name"])
                for handler, items in stage_handler_items:
                    logger.info("  📂 [%s] %s (%d item(s))", handler.source_type, handler.name, len(items))
                    for item in items:
                        logger.info("      • %s (%s)", item.title, item.published)
                        logger.info("        %s", item.url)
            if successful_keys:
                logger.info("[%s] [DRY-RUN] Would mark %d source(s) as successful.", stage["name"], len(successful_keys))
            active_handlers = failed_handlers
            continue

        stage_results: list[dict] = []
        if not stage_handler_items:
            logger.info("[%s] No sources have new content in this stage.", stage["name"])
        else:
            for idx, (handler, items) in enumerate(stage_handler_items):
                if idx > 0:
                    logger.info("Cooling down %ds before next source…", INTER_CHANNEL_COOLDOWN)
                    await asyncio.sleep(INTER_CHANNEL_COOLDOWN)

                try:
                    result = await process_source_items(handler, items, cfg)
                    stage_results.append(result)
                except NotebookLimitError:
                    logger.critical("Notebook quota exceeded — stopping source processing.")
                    failed_handlers.extend(pair[0] for pair in stage_handler_items[idx:])
                    break

                if result.get("error"):
                    logger.warning(
                        "[%s] Channel is incomplete and will be retried: %s",
                        handler.name,
                        result["error"],
                    )
                    failed_handlers.append(handler)
                    if result.get("rate_limited"):
                        quota_deferred_until = result.get("deferred_until")
                        logger.warning(
                            "NotebookLM compute is limited; deferring the remaining %d source(s) until the next refresh.",
                            len(stage_handler_items) - idx - 1,
                        )
                        failed_handlers.extend(pair[0] for pair in stage_handler_items[idx + 1:])
                        break
                    continue

                try:
                    from email_service import _render_channel_html

                    safe_name = paths.safe_channel_name(result.get("channel_name", "source"))
                    html_body = _render_channel_html(result, run_date, None)
                    html_path = paths.get_summaries_dir() / f"{run_date}_{safe_name}_digest.html"
                    html_path.write_text(html_body, encoding="utf-8")
                    logger.info("Local HTML digest saved to %s", html_path)

                    if top10_enabled:
                        record_top10_source(
                            handler.state_key(), result, top10_run_date
                        )

                    if skip_email:
                        logger.info("[%s] Email delivery skipped by configuration.", handler.name)
                    else:
                        send_channel_email(result, cfg)
                except Exception:
                    logger.exception(
                        "[%s] Finalization/email failed; its checkpoint will not advance.",
                        handler.name,
                    )
                    failed_handlers.append(handler)
                    continue

                if handler.source_type == "webpage":
                    urls = {item.url for item in items}
                    if urls:
                        save_seen_urls(cfg.state_file, handler.state_key(), urls)

                schedule_artifacts_after_delivery(
                    result,
                    channel_order=channel_orders[handler.state_key()],
                    generate_cinematic_video=cinematic_selection.get(
                        handler.state_key(), False
                    ),
                    generate_infographics=getattr(cfg, "generate_infographics", False),
                )

                # Checkpoint immediately after this channel is fully finalized.
                # A shutdown now resumes at the next channel instead of
                # recreating every notebook from the stage.
                save_state(cfg.state_file, [handler.state_key()])
                successful_keys.append(handler.state_key())
                logger.info(
                    "[%s] Summary delivered; background artifacts are durably queued.",
                    handler.name,
                )

            if not stage_results:
                logger.warning("[%s] No sources were successfully processed in this stage.", stage["name"])
            else:
                md_path = write_markdown_digest(stage_results, f"{run_date}_stage_{stage_idx}")
                logger.info("[%s] Markdown digest saved to %s", stage["name"], md_path)

        seen_failed_keys = set()
        active_handlers = []
        for handler in failed_handlers:
            key = handler.state_key()
            if key not in seen_failed_keys:
                seen_failed_keys.add(key)
                active_handlers.append(handler)
        logger.info(
            "=== Finished Stage: %s. Succeeded/Skipped: %d, Failed (to be retried): %d ===",
            stage["name"],
            len(successful_keys),
            len(active_handlers),
        )
        if quota_deferred_until:
            break

    if quota_deferred_until:
        save_compute_deferral(
            paths.get_compute_deferral_file(),
            quota_deferred_until,
            "Gemini Notebook compute limit reached; TubeLM will resume automatically.",
        )
        logger.warning(
            "Run paused until %s; completed summaries and emails will not be repeated.",
            quota_deferred_until.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        )
        return False

    if active_handlers:
        logger.error(
            "Run incomplete after all retry stages; %d source(s) remain safely checkpointed for resume.",
            len(active_handlers),
        )
        return False

    if dry_run:
        logger.info("Dry run complete; no notebooks or artifacts were created or resumed.")
        return True

    if top10_enabled:
        try:
            generate_and_send_top10_digest(cfg, top10_run_date)
        except Exception:
            logger.exception(
                "The optional Top 10 digest failed; its durable batch is preserved for retry."
            )
            return False

    # Studio work starts only after every summary/email has been finalized.
    # Audio and selected Cinematic Videos then advance as independent queues.
    if not await _finish_background_artifacts(
        cfg,
        seal_video_batch=True,
        send_completion_emails=completion_emails_enabled,
    ):
        return False

    logger.info("Weekly sync complete. Summaries and all queued artifacts are finalized.")
    return True


def main() -> None:
    paths.ensure_data_dir()
    parser = argparse.ArgumentParser(
        description="TubeLM: Premium YouTube to NotebookLM Weekly Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py              # Full sync run\n"
            "  python main.py --dry-run    # Discover videos only, no API calls\n"
            "  python main.py --skip-email # Full run, skip email delivery\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch RSS feeds and print new videos without calling NotebookLM.",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Run full pipeline but skip email delivery.",
    )
    parser.add_argument(
        "--shutdown-after-run",
        action="store_true",
        help="Power off the computer only after every selected source finishes successfully.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume the durable request left by an interrupted live run.",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Queue a durable scheduled run and wait for any active dashboard run.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the TubeLM Local Web Dashboard GUI.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to run the GUI server on (default: 5000).",
    )
    parser.add_argument(
        "--channels",
        type=str,
        help="Comma-separated list of YouTube Channel IDs to run selectively.",
    )
    parser.add_argument(
        "--sources",
        type=str,
        help="Comma-separated list of source state keys or names to run selectively.",
    )
    args = parser.parse_args()

    if args.gui:
        try:
            import flask
        except ImportError:
            print("Error: TubeLM GUI requires additional dependencies to run.")
            print("Please install them by running:\n")
            print("    pip install -r desktop/requirements.txt")
            print()
            sys.exit(1)
        
        # Import and run GUI server
        try:
            from gui import run_gui
            run_gui(port=args.port)
        except Exception as e:
            print(f"Error launching GUI: {e}")
            sys.exit(1)
        sys.exit(0)

    if args.dry_run and args.shutdown_after_run:
        parser.error("--shutdown-after-run cannot be used with --dry-run")
    if args.resume and args.scheduled:
        parser.error("--resume and --scheduled cannot be used together")
    if args.dry_run and args.scheduled:
        parser.error("--scheduled cannot be used with --dry-run")

    resume_file = paths.get_resume_request_file()
    scheduled_file = paths.get_scheduled_request_file()
    request_file = resume_file
    wait_for_lock = False

    if args.resume:
        resume_request = load_resume_request(resume_file)
        if not resume_request:
            resume_request = load_resume_request(scheduled_file)
            request_file = scheduled_file
        if not resume_request:
            logger.info("No interrupted or scheduled TubeLM run is waiting to resume.")
            return
        dry_run = False
        skip_email = bool(resume_request.get("skip_email", False))
        sources_filter = resume_request.get("sources_filter") or None
        shutdown_after_run = bool(resume_request.get("shutdown_after_run", False))
        artifacts_only = bool(resume_request.get("artifacts_only", False))
        wait_for_lock = True
        logger.info("Resuming the durable TubeLM request from %s.", request_file)
    elif args.scheduled:
        request_file = scheduled_file
        resume_request = load_resume_request(scheduled_file)
        if not resume_request:
            resume_request = {
                "request_kind": "scheduled",
                "skip_email": args.skip_email,
                "sources_filter": args.sources or args.channels,
                "shutdown_after_run": args.shutdown_after_run,
            }
            save_resume_request(scheduled_file, resume_request)
            logger.info("Queued the scheduled TubeLM request in %s.", scheduled_file)
        else:
            logger.info("Coalescing with the scheduled TubeLM request already queued.")
        dry_run = False
        skip_email = bool(resume_request.get("skip_email", False))
        sources_filter = resume_request.get("sources_filter") or None
        shutdown_after_run = bool(resume_request.get("shutdown_after_run", False))
        artifacts_only = False
        wait_for_lock = True
    else:
        dry_run = args.dry_run
        skip_email = args.skip_email
        sources_filter = args.sources or args.channels
        shutdown_after_run = args.shutdown_after_run
        artifacts_only = False

    if dry_run:
        completed = asyncio.run(
            async_main(dry_run=True, skip_email=skip_email, channels_filter=sources_filter)
        )
        if not completed:
            sys.exit(1)
        return

    lock = PipelineRunLock(paths.get_pipeline_lock_file())
    completed = True
    try:
        if wait_for_lock:
            lock.acquire(
                wait=True,
                on_wait=lambda: logger.info(
                    "Another TubeLM run is active; the durable request will start when it finishes."
                ),
            )
        else:
            lock.acquire()

        try:
            if not args.resume and not args.scheduled:
                save_resume_request(
                    resume_file,
                    {
                        "request_kind": "interactive",
                        "skip_email": skip_email,
                        "sources_filter": sources_filter,
                        "shutdown_after_run": shutdown_after_run,
                    },
                )
                request_file = resume_file
            else:
                # A second scheduled/resume process may have completed this
                # coalesced request while we were waiting for the lock.
                active_request = load_resume_request(request_file)
                if not active_request:
                    logger.info(
                        "The queued TubeLM request was already completed by another process."
                    )
                    completed = True
                    shutdown_after_run = False
                else:
                    skip_email = bool(active_request.get("skip_email", False))
                    sources_filter = active_request.get("sources_filter") or None
                    shutdown_after_run = bool(active_request.get("shutdown_after_run", False))
                    artifacts_only = bool(active_request.get("artifacts_only", False))

            if load_resume_request(request_file):
                compute_deferral = load_compute_deferral(paths.get_compute_deferral_file())
                if compute_deferral:
                    completed = False
                    logger.info(
                        "NotebookLM compute refresh is pending; TubeLM will resume after %s.",
                        compute_deferral["not_before_dt"].astimezone().strftime(
                            "%Y-%m-%d %H:%M %Z"
                        ),
                    )
                else:
                    completed = asyncio.run(
                        async_main(
                            dry_run=False,
                            skip_email=skip_email,
                            channels_filter=sources_filter,
                            artifacts_only=artifacts_only,
                        )
                    )
                    if not completed:
                        deferral = load_compute_deferral(
                            paths.get_compute_deferral_file()
                        )
                        if deferral and not deferral.get("reason", "").startswith(
                            "Gemini Notebook compute limit reached"
                        ):
                            active_request = load_resume_request(request_file) or {}
                            active_request["artifacts_only"] = True
                            save_resume_request(request_file, active_request)
                if completed:
                    clear_resume_request(request_file)

            # At boot, an interrupted dashboard request and a pending scheduled
            # request can coexist. Finish the dashboard selection first, then
            # consume the scheduled request under the same lock. Any concurrently
            # waiting scheduler will see the cleared marker and exit without a
            # duplicate run.
            if completed and args.resume and request_file == resume_file:
                pending_scheduled = load_resume_request(scheduled_file)
                if pending_scheduled:
                    logger.info(
                        "The interrupted request is complete; starting the queued scheduled run."
                    )
                    scheduled_shutdown = bool(
                        pending_scheduled.get("shutdown_after_run", False)
                    )
                    completed = asyncio.run(
                        async_main(
                            dry_run=False,
                            skip_email=bool(pending_scheduled.get("skip_email", False)),
                            channels_filter=pending_scheduled.get("sources_filter") or None,
                            artifacts_only=bool(
                                pending_scheduled.get("artifacts_only", False)
                            ),
                        )
                    )
                    if completed:
                        clear_resume_request(scheduled_file)
                        shutdown_after_run = shutdown_after_run or scheduled_shutdown
        finally:
            lock.release()
    except PipelineAlreadyRunningError as exc:
        logger.error("%s", exc)
        sys.exit(3)

    if not completed:
        compute_deferral = load_compute_deferral(paths.get_compute_deferral_file())
        if compute_deferral:
            logger.warning(
                "Run is safely deferred; the durable request was preserved for background resume."
            )
            if sys.platform.startswith("linux") and not os.getenv("INVOCATION_ID"):
                started = subprocess.run(
                    [
                        "systemctl",
                        "--user",
                        "start",
                        "--no-block",
                        "tubelm-resume.service",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if started.returncode != 0:
                    delay_seconds = max(
                        60,
                        int(
                            (
                                compute_deferral["not_before_dt"]
                                - datetime.now(timezone.utc)
                            ).total_seconds()
                        ),
                    )
                    subprocess.run(
                        [
                            "systemd-run",
                            "--user",
                            "--collect",
                            "--unit=tubelm-deferred-resume",
                            f"--on-active={delay_seconds}s",
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--resume",
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
            sys.exit(75)
        logger.error("Run remains incomplete; the durable resume request was preserved.")
        sys.exit(1)

    if shutdown_after_run:
        logger.info("All work completed successfully. Requesting system shutdown…")
        try:
            request_system_shutdown()
        except RuntimeError as exc:
            logger.error("%s", exc)
            sys.exit(1)


if __name__ == "__main__":
    main()
