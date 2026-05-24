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
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

from config import ConfigurationError, load_config
from email_service import send_channel_email
from notebooklm_service import process_channel_videos, verify_notebooklm_auth
from notebooklm.exceptions import NotebookLimitError

# ── Logging setup ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
DEFAULT_LOOKBACK_DAYS = 7
MIN_VIDEO_DURATION_SECONDS = 180  # 3 minutes
SHORTS_KEYWORDS = re.compile(r"#shorts?", re.IGNORECASE)

# Inter-channel cooldown to avoid NotebookLM rate-limiting (seconds)
INTER_CHANNEL_COOLDOWN = 60


# ── Cookie refresh ─────────────────────────────────────────────────────────────

def refresh_cookies() -> bool:
    """Refresh NotebookLM cookies from Chrome before the run.

    Calls `notebooklm login --browser-cookies chrome` as a subprocess.
    Returns True if successful, False otherwise (non-fatal — existing cookies
    may still be valid).
    """
    bin_dir = os.path.dirname(sys.executable)
    notebooklm_bin = os.path.join(bin_dir, "notebooklm")

    logger.info("Refreshing NotebookLM cookies from Chrome…")
    try:
        result = subprocess.run(
            [notebooklm_bin, "login", "--browser-cookies", "chrome"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Cookie refresh successful.")
            return True
        logger.warning(
            "Cookie refresh failed (exit %d): %s",
            result.returncode,
            (result.stdout + result.stderr).strip()[:200],
        )
        return False
    except FileNotFoundError:
        logger.warning(
            "notebooklm binary not found at %s — skipping cookie refresh.",
            notebooklm_bin,
        )
        return False
    except subprocess.TimeoutExpired:
        logger.warning("Cookie refresh timed out after 30 seconds.")
        return False
    except Exception:
        logger.exception("Unexpected error during cookie refresh.")
        return False


# ── State management ───────────────────────────────────────────────────────────

def load_channel_state(state_file: Path, channel_id: str) -> datetime:
    """Return the last-run datetime for a specific channel (UTC, timezone-aware).

    Falls back to global last_run_time or DEFAULT_LOOKBACK_DAYS ago if not found.
    """
    default = datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    try:
        if not state_file.exists():
            return default
        text = state_file.read_text(encoding="utf-8")
        data = json.loads(text)
        
        # Check channel-specific timestamp
        channels_state = data.get("channels", {})
        ts = channels_state.get(channel_id) if isinstance(channels_state, dict) else None
        
        # Fallback to global last_run_time
        if not ts:
            ts = data.get("last_run_time")
            
        if not ts:
            return default
            
        dt = datetime.fromisoformat(ts)
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:
        logger.warning("Could not parse state for channel %s (%s) — using %d-day lookback.", channel_id, exc, DEFAULT_LOOKBACK_DAYS)
        return default


def save_state(state_file: Path, processed_channels: list[str]) -> None:
    """Update state.json with the current UTC timestamp for processed channels."""
    now = datetime.now(timezone.utc).isoformat()
    data = {}
    try:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    
    if "channels" not in data or not isinstance(data["channels"], dict):
        data["channels"] = {}
        
    for ch_id in processed_channels:
        data["channels"][ch_id] = now
        
    data["last_run_time"] = now  # update global last_run_time as well
    state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("state.json updated for channels: %s", ", ".join(processed_channels))


# ── Channel list loader ────────────────────────────────────────────────────────

def load_channels(channels_file: Path) -> list[dict]:
    """Load channel list from JSON. Each entry must have 'name' and 'channel_id'.

    Raises:
        SystemExit: If the file is missing, malformed, or has invalid entries.
    """
    try:
        data = json.loads(channels_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.critical("channels.json not found at %s. Exiting.", channels_file)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        logger.critical("channels.json is not valid JSON: %s. Exiting.", exc)
        sys.exit(1)

    valid = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict) or not entry.get("name") or not entry.get("channel_id"):
            logger.warning("channels.json entry %d missing 'name' or 'channel_id' — skipping.", i)
            continue
        valid.append(entry)

    if not valid:
        logger.critical("No valid channels found in channels.json. Exiting.")
        sys.exit(1)

    logger.info("Loaded %d channel(s) from %s.", len(valid), channels_file)
    return valid


# ── RSS feed fetching ──────────────────────────────────────────────────────────

def _parse_rss_datetime(entry) -> datetime:
    """Extract published datetime from a feedparser entry.

    Returns a timezone-aware UTC datetime.
    Falls back to epoch (1970-01-01) if unparseable so the video is
    excluded from the new-video window rather than crashing.
    """
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import calendar
            ts = calendar.timegm(entry.published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        logger.debug("Could not parse published_parsed for entry; defaulting to epoch.", exc_info=True)
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _extract_video_id(entry) -> str | None:
    """Extract YouTube video ID from a feedparser entry."""
    # yt:videoId tag is the most reliable source
    vid_id = getattr(entry, "yt_videoid", None)
    if vid_id:
        return vid_id
    # Fallback: parse from the entry link
    link = getattr(entry, "link", "")
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", link)
    return match.group(1) if match else None


def fetch_channel_videos(channel_id: str, since_dt: datetime) -> list[dict]:
    """Fetch new videos from a YouTube channel RSS feed.

    Args:
        channel_id: YouTube channel ID.
        since_dt: Only return videos published after this datetime (UTC-aware).

    Returns:
        List of dicts: {title, url, video_id, published, description}.
        Returns [] on any error (non-fatal — logged at WARNING).
    """
    url = YOUTUBE_RSS_URL.format(channel_id=channel_id)
    try:
        feed = feedparser.parse(url)
    except Exception:
        logger.warning("feedparser.parse() raised for channel %s.", channel_id, exc_info=True)
        return []

    if feed.bozo and not feed.entries:
        logger.warning(
            "RSS feed for channel %s appears malformed (bozo=%s). Skipping.",
            channel_id,
            feed.bozo_exception,
        )
        return []

    videos = []
    for entry in feed.entries:
        pub_dt = _parse_rss_datetime(entry)
        if pub_dt <= since_dt:
            continue  # Older than the lookback window

        video_id = _extract_video_id(entry)
        if not video_id:
            logger.warning("Could not extract video ID for entry: %s", getattr(entry, "link", "?"))
            continue

        title = getattr(entry, "title", "")
        description = ""
        if hasattr(entry, "summary"):
            description = entry.summary
        elif hasattr(entry, "description"):
            description = entry.description

        videos.append({
            "title": title,
            "url": YOUTUBE_WATCH_URL.format(video_id=video_id),
            "video_id": video_id,
            "published": pub_dt.strftime("%Y-%m-%d"),
            "description": description,
        })

    return videos


# ── Shorts filtering (3 layers) ───────────────────────────────────────────────

def filter_shorts(videos: list[dict]) -> list[dict]:
    """Layer 1: Remove videos whose title or description contains #shorts.

    Args:
        videos: List of video dicts from fetch_channel_videos().

    Returns:
        Filtered list (Shorts excluded).
    """
    filtered = []
    for v in videos:
        if SHORTS_KEYWORDS.search(v["title"]) or SHORTS_KEYWORDS.search(v.get("description", "")):
            logger.debug("Filtered #shorts: %s", v["title"])
            continue
        filtered.append(v)
    removed = len(videos) - len(filtered)
    if removed:
        logger.info("Filtered %d Shorts video(s) by keyword.", removed)
    return filtered


def filter_shorts_by_title_heuristics(videos: list[dict]) -> list[dict]:
    """Layer 2: Filter likely Shorts by title pattern analysis.

    Flags videos whose titles are primarily hashtags (≥3 hashtags AND
    hashtag characters make up >50% of the title length). These are
    almost always short-form content.

    Args:
        videos: List of video dicts.

    Returns:
        Filtered list with hashtag-heavy titles removed.
    """
    filtered = []
    for v in videos:
        title = v["title"]
        hashtags = re.findall(r"#\w+", title)
        hashtag_count = len(hashtags)
        hashtag_chars = sum(len(h) for h in hashtags)
        title_len = max(len(title), 1)

        if hashtag_count >= 3 and hashtag_chars / title_len > 0.5:
            logger.debug("Filtered by title heuristic (hashtag-heavy): %s", title)
            continue
        filtered.append(v)

    removed = len(videos) - len(filtered)
    if removed:
        logger.info("Filtered %d video(s) by title heuristic (hashtag-heavy).", removed)
    return filtered


# ── ISO 8601 duration parser (no external dependency) ─────────────────────────

def _parse_iso8601_duration(duration: str) -> int:
    """Parse ISO 8601 duration string to total seconds.

    Examples: "PT3M30S" → 210, "PT1H" → 3600, "P1DT2H" → 93600

    Returns 0 on parse failure (treated as "short", so filtered out —
    conservative approach to avoid processing non-video content).
    """
    pattern = re.compile(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", re.IGNORECASE
    )
    match = pattern.match(duration or "")
    if not match:
        return 0
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def fetch_durations_and_filter(videos: list[dict], api_key: str) -> list[dict]:
    """Layer 3: Filter videos under MIN_VIDEO_DURATION_SECONDS using YouTube Data API.

    Fetches durations in batches of 50 to conserve API quota.
    Videos that fail duration lookup are kept (conservative — better to
    include an uncertain video than silently drop it).

    Args:
        videos: List of video dicts (must have 'video_id').
        api_key: YouTube Data API v3 key.

    Returns:
        Filtered list with only videos >= MIN_VIDEO_DURATION_SECONDS.
    """
    if not videos:
        return videos

    # Build {video_id: video_dict} map
    video_map = {v["video_id"]: v for v in videos}
    all_ids = list(video_map.keys())
    short_ids: set[str] = set()

    batch_size = 50
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i : i + batch_size]
        try:
            resp = requests.get(
                YOUTUBE_API_URL,
                params={
                    "id": ",".join(batch),
                    "part": "contentDetails",
                    "key": api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception:
            logger.warning(
                "YouTube API duration fetch failed for batch %d-%d — keeping those videos.",
                i,
                i + len(batch),
                exc_info=True,
            )
            continue  # Keep videos in this batch

        for item in items:
            vid_id = item.get("id", "")
            duration_str = item.get("contentDetails", {}).get("duration", "")
            secs = _parse_iso8601_duration(duration_str)
            if secs < MIN_VIDEO_DURATION_SECONDS:
                short_ids.add(vid_id)
                logger.debug(
                    "Filtered short video (%ds < %ds): %s",
                    secs,
                    MIN_VIDEO_DURATION_SECONDS,
                    vid_id,
                )

    filtered = [v for v in videos if v["video_id"] not in short_ids]
    if short_ids:
        logger.info(
            "Filtered %d video(s) under %ds by YouTube API duration.",
            len(short_ids),
            MIN_VIDEO_DURATION_SECONDS,
        )
    return filtered


# ── Markdown digest writer ─────────────────────────────────────────────────────

def write_markdown_digest(channels_data: list[dict], run_date: str) -> Path:
    """Write a Markdown digest file to summaries/{date}_digest.md.

    Args:
        channels_data: List of channel result dicts.
        run_date: Date string for the filename (YYYY-MM-DD).

    Returns:
        Path to the written file.
    """
    summaries_dir = Path("summaries")
    summaries_dir.mkdir(exist_ok=True)
    out_path = summaries_dir / f"{run_date}_digest.md"

    total_videos = sum(len(ch.get("videos", [])) for ch in channels_data)
    lines = [
        f"# YouTube Digest — {run_date}",
        "",
        f"**{len(channels_data)} channel(s) · {total_videos} new video(s)**",
        "",
        "---",
        "",
    ]

    for ch in channels_data:
        lines.append(f"## {ch['channel_name']}")
        lines.append("")
        if ch.get("notebook_url"):
            lines.append(f"📒 [Open in NotebookLM]({ch['notebook_url']})")
            lines.append("")
        if ch.get("error"):
            lines.append(f"> ⚠️ **Error:** {ch['error']}")
            lines.append("")
        lines.append(f"### New Videos ({len(ch['videos'])})")
        lines.append("")
        for v in ch["videos"]:
            lines.append(f"- [{v['title']}]({v['url']}) — {v['published']}")
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
            logger.critical("SMTP validation failed: %s", exc)
            sys.exit(1)


    # ── Pre-run cookie refresh ─────────────────────────────────────────────
    if not dry_run:
        refresh_cookies()

    # ── Auth gate ──────────────────────────────────────────────────────────
    if not dry_run:
        logger.info("Checking NotebookLM authentication…")
        if not verify_notebooklm_auth():
            print("AUTH_REQUIRED", flush=True)
            sys.exit(2)
        logger.info("Authentication verified.")

    # ── Load channels and state ────────────────────────────────────────────
    channels = load_channels(cfg.channels_file)
    if channels_filter:
        selected_ids = {cid.strip() for cid in channels_filter.split(",") if cid.strip()}
        channels = [ch for ch in channels if ch["channel_id"] in selected_ids]
        logger.info(
            "Running selectively for %d channel(s): %s",
            len(channels),
            ", ".join(ch["name"] for ch in channels),
        )

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # We will track which channels were successfully checked/processed
    successful_channel_ids = []

    # ── Discover new videos per channel ───────────────────────────────────
    channel_videos: list[tuple[dict, list[dict]]] = []

    for ch in channels:
        name = ch["name"]
        channel_id = ch["channel_id"]
        since_dt = load_channel_state(cfg.state_file, channel_id)

        logger.info("[%s] Discovering videos published after %s…", name, since_dt.isoformat())
        raw_videos = fetch_channel_videos(channel_id, since_dt)
        if not raw_videos:
            logger.info("[%s] No new videos found.", name)
            successful_channel_ids.append(channel_id)
            continue

        # Layer 1: Keyword filter (#shorts)
        filtered = filter_shorts(raw_videos)
        if not filtered:
            logger.info("[%s] All %d video(s) were Shorts — skipping.", name, len(raw_videos))
            successful_channel_ids.append(channel_id)
            continue

        # Layer 2: Title heuristic filter (hashtag-heavy)
        filtered = filter_shorts_by_title_heuristics(filtered)
        if not filtered:
            logger.info("[%s] All videos filtered by title heuristic — skipping.", name)
            successful_channel_ids.append(channel_id)
            continue

        # Layer 3: Duration filter via YouTube Data API (skipped if API key is not set)
        if cfg.youtube_api_key:
            filtered = fetch_durations_and_filter(filtered, cfg.youtube_api_key)
            if not filtered:
                logger.info("[%s] All videos filtered by duration — skipping.", name)
                successful_channel_ids.append(channel_id)
                continue
        else:
            logger.warning("[%s] YouTube API Key is not set. Skipping duration-based Shorts filtering layer.", name)

        logger.info("[%s] %d new video(s) to process.", name, len(filtered))
        channel_videos.append((ch, filtered))

    # ── Dry-run: just print and exit ──────────────────────────────────────
    if dry_run:
        if not channel_videos:
            print("\n[DRY-RUN] No new videos found across all channels.")
            return
        print(f"\n[DRY-RUN] Would process {len(channel_videos)} channel(s):\n")
        for ch, videos in channel_videos:
            print(f"  📺 {ch['name']}  ({len(videos)} video(s))")
            for v in videos:
                print(f"      • {v['title']}  ({v['published']})")
                print(f"        {v['url']}")
            print()
        return

    if not channel_videos:
        logger.info("No channels have new videos. Updating state and exiting.")
        if successful_channel_ids:
            save_state(cfg.state_file, successful_channel_ids)
        return

    # ── Process each channel sequentially ─────────────────────────────────
    results: list[dict] = []
    quota_exceeded = False

    for idx, (ch, videos) in enumerate(channel_videos):
        if quota_exceeded:
            logger.warning(
                "Notebook quota was exceeded — skipping remaining channels."
            )
            break

        # Inter-channel cooldown (skip before first channel)
        if idx > 0:
            logger.info(
                "Cooling down %ds before next channel…", INTER_CHANNEL_COOLDOWN
            )
            await asyncio.sleep(INTER_CHANNEL_COOLDOWN)

        try:
            result = await process_channel_videos(ch["name"], videos, cfg)
            results.append(result)
            if not result.get("error"):
                successful_channel_ids.append(ch["channel_id"])
        except NotebookLimitError:
            quota_exceeded = True
            logger.critical("Notebook quota exceeded — stopping channel processing.")

    if not results:
        logger.warning("No channels were successfully processed.")
        if successful_channel_ids:
            save_state(cfg.state_file, successful_channel_ids)
        return

    # ── Write Markdown digest ──────────────────────────────────────────────
    md_path = write_markdown_digest(results, run_date)
    logger.info("Markdown digest saved to %s", md_path)

    # ── Write per-channel HTML digests locally ──────────────────────────────
    from email_service import _render_channel_html
    for ch_result in results:
        try:
            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', ch_result.get("channel_name", "channel"))
            html_body = _render_channel_html(ch_result, run_date, None)
            html_path = Path("summaries") / f"{run_date}_{safe_name}_digest.html"
            html_path.write_text(html_body, encoding="utf-8")
            logger.info("Local HTML digest saved to %s", html_path)
        except Exception:
            logger.exception(
                "Failed to write local HTML digest for channel %r.",
                ch_result.get("channel_name", "unknown")
            )

    # ── Update state BEFORE sending email ─────────────────────────────────
    if successful_channel_ids:
        save_state(cfg.state_file, successful_channel_ids)

    # ── Send per-channel email digests ─────────────────────────────────────
    if skip_email:
        logger.info("Email delivery skipped (--skip-email flag or missing SMTP credentials).")
    else:
        for ch_result in results:
            try:
                send_channel_email(ch_result, cfg)
            except Exception:
                logger.exception(
                    "Failed to send email for channel %r. "
                    "state.json was already updated; videos will not be reprocessed.",
                    ch_result.get("channel_name", "unknown"),
                )

    logger.info("Weekly sync complete. Processed %d channel(s).", len(results))


def main() -> None:
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
    args = parser.parse_args()

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

    asyncio.run(async_main(dry_run=args.dry_run, skip_email=args.skip_email, channels_filter=args.channels))


if __name__ == "__main__":
    main()
