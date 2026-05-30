"""
main.py — TubeLM Weekly Sync

Entry point. Orchestrates:
  1. Pre-run cookie refresh
  2. Auth gate
  3. RSS video discovery + multi-layer Shorts filtering
  4. NotebookLM notebook creation, source upload, summary, infographic, audio
  5. Markdown digest export
  6. state.json update
  7. Per-channel email delivery

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
from email_service import send_channel_email
import paths
from notebooklm_service import process_source_items, verify_notebooklm_auth
from notebooklm.exceptions import NotebookLimitError
from sources_loader import load_sources
from source_handlers.factory import create_handler
from source_handlers import SourceItem

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
INTER_CHANNEL_COOLDOWN = 60


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
      1. state["sources"][state_key] (new format)
      2. state["channels"][channel_id] (legacy YouTube backward compat)
      3. state["last_run_time"] (global fallback)
      4. DEFAULT_LOOKBACK_DAYS ago (hard fallback)
    """
    default = datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    try:
        if not state_file.exists():
            return default
        text = state_file.read_text(encoding="utf-8")
        data = json.loads(text)

        # 1. Check new sources format
        sources_state = data.get("sources", {})
        if isinstance(sources_state, dict):
            ts = sources_state.get(state_key)
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt

        # 2. Legacy channels format (YouTube backward compat)
        channels_state = data.get("channels", {})
        if isinstance(channels_state, dict):
            ts = channels_state.get(state_key)
            # If not found by full key, strip "youtube:" prefix for bare channel_id lookup
            if not ts and state_key.startswith("youtube:"):
                channel_id = state_key[len("youtube:"):]
                ts = channels_state.get(channel_id)
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt

        # 3. Fallback to global last_run_time
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


# Backward-compat alias
load_channel_state = load_source_state


def save_state(state_file: Path, processed_keys: list[str]) -> None:
    """Update state.json with the current UTC timestamp for processed source keys.

    Writes to both 'sources' (new format) and 'channels' (legacy backward compat
    for YouTube channels where the key is bare channel_id without prefix).
    """
    now = datetime.now(timezone.utc).isoformat()
    data = {}
    try:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass

    if "channels" not in data or not isinstance(data["channels"], dict):
        data["channels"] = {}

    if "sources" not in data or not isinstance(data["sources"], dict):
        data["sources"] = {}

    for key in processed_keys:
        data["sources"][key] = now
        # YouTube backward compat: strip "youtube:" prefix
        if key.startswith("youtube:"):
            channel_id = key[len("youtube:"):]
            data["channels"][channel_id] = now

    data["last_run_time"] = now
    state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("state.json updated for keys: %s", ", ".join(processed_keys))


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
    state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


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

async def async_main(dry_run: bool, skip_email: bool, channels_filter: str | None = None) -> None:
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

    # ── Validate SMTP connection ───────────────────────────────────────────
    has_smtp = all([cfg.smtp_server, cfg.smtp_username, cfg.smtp_password, cfg.sender_email, cfg.recipient_email])
    if not has_smtp:
        logger.warning("SMTP configuration is incomplete. Automatically skipping email delivery.")
        skip_email = True

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

    # ── Load sources and state ────────────────────────────────────────────
    sources = load_sources(cfg.sources_file)
    handlers = [create_handler(src, cfg) for src in sources]

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

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    retry_stages = [
        {"name": "Initial Run", "delay_hours": 0},
        {"name": "1-Hour Retry Run", "delay_hours": 1},
        {"name": "3-Hour Retry Run", "delay_hours": 2},
    ]

    active_handlers = list(handlers)

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

        for handler in active_handlers:
            state_key = handler.state_key()
            since_dt = load_source_state(cfg.state_file, state_key)
            seen_urls = load_seen_urls(cfg.state_file, state_key) if handler.source_type == "webpage" else None

            logger.info("[%s] Discovering content published after %s…", handler.name, since_dt.isoformat())
            items = handler.discover(since_dt, seen_urls=seen_urls)

            if items is None:
                logger.warning("[%s] Skipping source in this stage due to transient failure.", handler.name)
                failed_handlers.append(handler)
                continue

            if not items:
                logger.info("[%s] No new content found.", handler.name)
                successful_keys.append(state_key)
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
        quota_exceeded = False

        if not stage_handler_items:
            logger.info("[%s] No sources have new content in this stage.", stage["name"])
            if successful_keys:
                save_state(cfg.state_file, successful_keys)
        else:
            for idx, (handler, items) in enumerate(stage_handler_items):
                if quota_exceeded:
                    logger.warning("Notebook quota was exceeded — skipping remaining sources.")
                    break

                if idx > 0:
                    logger.info("Cooling down %ds before next source…", INTER_CHANNEL_COOLDOWN)
                    await asyncio.sleep(INTER_CHANNEL_COOLDOWN)

                try:
                    result = await process_source_items(handler, items, cfg)
                    stage_results.append(result)
                    if not result.get("error"):
                        successful_keys.append(handler.state_key())
                except NotebookLimitError:
                    quota_exceeded = True
                    logger.critical("Notebook quota exceeded — stopping source processing.")

            # Save seen URLs for successfully processed webpage handlers
            for handler, items in stage_handler_items:
                if handler.source_type == "webpage" and handler.state_key() in successful_keys:
                    urls = {item.url for item in items}
                    if urls:
                        save_seen_urls(cfg.state_file, handler.state_key(), urls)

            if not stage_results:
                logger.warning("[%s] No sources were successfully processed in this stage.", stage["name"])
                if successful_keys:
                    save_state(cfg.state_file, successful_keys)
            else:
                md_path = write_markdown_digest(stage_results, f"{run_date}_stage_{stage_idx}")
                logger.info("[%s] Markdown digest saved to %s", stage["name"], md_path)

                from email_service import _render_channel_html
                for ch_result in stage_results:
                    try:
                        safe_name = paths.safe_channel_name(ch_result.get("channel_name", "source"))
                        html_body = _render_channel_html(ch_result, run_date, None, cfg.email_theme)
                        html_path = paths.get_summaries_dir() / f"{run_date}_{safe_name}_digest.html"
                        html_path.write_text(html_body, encoding="utf-8")
                        logger.info("Local HTML digest saved to %s", html_path)
                    except Exception:
                        logger.exception("Failed to write local HTML digest for %r.", ch_result.get("channel_name", "unknown"))

                if successful_keys:
                    save_state(cfg.state_file, successful_keys)

                if skip_email:
                    logger.info("Email delivery skipped (--skip-email flag or missing SMTP credentials).")
                else:
                    for ch_result in stage_results:
                        try:
                            send_channel_email(ch_result, cfg)
                        except Exception:
                            logger.exception(
                                "Failed to send email for %r. state.json was already updated.",
                                ch_result.get("channel_name", "unknown"),
                            )

        active_handlers = failed_handlers
        logger.info(
            "=== Finished Stage: %s. Succeeded/Skipped: %d, Failed (to be retried): %d ===",
            stage["name"],
            len(successful_keys) + len(stage_handler_items) - len(failed_handlers),
            len(failed_handlers),
        )

    logger.info("Weekly sync complete. Processed all stages.")


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

    sources_filter = args.sources or args.channels

    if args.gui:
        try:
            import flask
        except ImportError:
            print("Error: TubeLM GUI requires additional dependencies to run.")
            print("Please install them by running:\n")
            print("    pip install -r requirements-gui.txt")
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

    asyncio.run(async_main(dry_run=args.dry_run, skip_email=args.skip_email, channels_filter=sources_filter))


if __name__ == "__main__":
    main()
