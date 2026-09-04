"""Download ranked weekly Top 10 YouTube videos and manage rotating archive folders."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import paths

logger = logging.getLogger(__name__)

DEFAULT_YOUTUBE_FORMAT = "bv*[height<=1080]+ba/b[height<=1080]/b"
DOWNLOAD_TIMEOUT_SECONDS = 900


def sanitize_filename_part(text: str, max_length: int = 150) -> str:
    """Sanitize a string for safe filesystem usage across Linux/macOS/Windows."""
    cleaned = re.sub(r'[\/\\:*?"<>|]', "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ")
    return cleaned


def is_youtube_video_item(item: dict[str, Any]) -> bool:
    """Determine if a ranked item represents a downloadable YouTube video."""
    source_type = str(item.get("source_type") or "").strip().lower()
    url = str(item.get("url") or "").strip()
    video_id = str(item.get("video_id") or "").strip()

    if source_type in {"rss", "webpage", "article", "web"}:
        return False

    if video_id and len(video_id) == 11:
        return True

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if "youtube.com" in hostname or "youtu.be" in hostname:
        return True

    return source_type == "youtube"


def build_video_filename(rank: int, source_name: str, title: str) -> str:
    """Build the standardized video filename: {rank:02d} - {source_name} - {title}.mp4."""
    clean_source = sanitize_filename_part(source_name, max_length=60)
    clean_title = sanitize_filename_part(title, max_length=140)
    return f"{rank:02d} - {clean_source} - {clean_title}.mp4"


def extract_items_from_top10_html(html_path: Path) -> list[dict[str, Any]]:
    """Parse a TubeLM Top 10 digest HTML file into ranked candidate items."""
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    items = []

    # Each item is rendered inside a table with rank-cell and item-title
    for rank_cell in soup.select(".rank-cell"):
        rank_str = rank_cell.get_text(strip=True)
        try:
            rank = int(rank_str)
        except ValueError:
            rank = len(items) + 1

        parent_table = rank_cell.find_parent("table")
        if not parent_table:
            continue

        title_elem = parent_table.select_one(".item-title a[href]")
        if not title_elem:
            continue

        url = title_elem.get("href", "").strip()
        title = title_elem.get_text(" ", strip=True)

        # Extract source name from kicker div (e.g., "Watch / Dr Brad Stanfield / 2026-08-25")
        source_name = "YouTube"
        kicker_elem = parent_table.select_one("div[style*='uppercase']")
        if kicker_elem:
            kicker_text = kicker_elem.get_text(" ", strip=True)
            parts = [p.strip() for p in kicker_text.split("/") if p.strip()]
            if len(parts) >= 2:
                source_name = parts[1]

        items.append({
            "rank": rank,
            "source_name": source_name,
            "title": title,
            "url": url,
            "source_type": "youtube" if "youtube.com" in url or "youtu.be" in url else "unknown",
        })

    return items


def rotate_top10_folders(dest_dir: Path, prev_dir: Path) -> None:
    """Rotate video archive folders safely.

    1. Permanently purge all files and subdirectories inside `prev_dir`.
    2. Move all remaining unwatched files from `dest_dir` into `prev_dir`.
    3. Ensure `dest_dir` is clean and ready for new downloads.
    """
    prev_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Purge all content from prev_dir
    for item in prev_dir.iterdir():
        try:
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove old file in %s: %s (%s)", prev_dir, item.name, exc)

    # Step 2: Move remaining items in dest_dir to prev_dir
    for item in dest_dir.iterdir():
        target = prev_dir / item.name
        try:
            if target.exists():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            shutil.move(str(item), str(target))
        except OSError as exc:
            logger.warning("Failed to move %s to %s: %s", item.name, prev_dir, exc)

    dest_dir.mkdir(parents=True, exist_ok=True)


def resolve_yt_dlp_bin() -> str:
    """Resolve the best yt-dlp binary path."""
    local_venv = paths.PROJECT_DIR / ".venv" / "bin" / "yt-dlp"
    if local_venv.exists():
        return str(local_venv)
    return shutil.which("yt-dlp") or "yt-dlp"


def download_single_video(
    url: str,
    output_path: Path,
    yt_dlp_bin: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Download a single video via yt-dlp to the exact target path."""
    bin_path = yt_dlp_bin or resolve_yt_dlp_bin()

    if output_path.exists() and output_path.stat().st_size > 1024:
        logger.info("Video %s already exists (%d bytes); skipping download.", output_path.name, output_path.stat().st_size)
        return True

    # If the video already exists with a different rank prefix (e.g. from interim run), rename it!
    if " - " in output_path.name and output_path.parent.exists():
        suffix = output_path.name.split(" - ", 1)[-1]
        for candidate in output_path.parent.glob("*.mp4"):
            if candidate.name.endswith(f" - {suffix}") and candidate.stat().st_size > 1024:
                try:
                    logger.info("Renaming existing download %s -> %s", candidate.name, output_path.name)
                    candidate.rename(output_path)
                    return True
                except OSError:
                    pass

    # Use output template matching target filename
    output_template = str(output_path.with_suffix("")) + ".%(ext)s"

    command = [
        bin_path,
        "--format",
        DEFAULT_YOUTUBE_FORMAT,
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        "--no-mtime",
    ]
    if shutil.which("node"):
        command.extend(["--js-runtimes", "node"])
    command.extend([
        "--output",
        output_template,
        url,
    ])

    if dry_run:
        logger.info("[DRY RUN] Would execute: %s", " ".join(command))
        return True

    logger.info("Downloading %s -> %s", url, output_path.name)
    try:
        completed = subprocess.run(
            command,
            cwd=output_path.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Download timed out after %d seconds: %s", DOWNLOAD_TIMEOUT_SECONDS, url)
        return False
    except OSError as exc:
        logger.error("Could not run yt-dlp (%s): %s", bin_path, exc)
        return False

    if completed.returncode != 0:
        logger.warning(
            "yt-dlp failed (exit code %d) for %s: %s",
            completed.returncode,
            url,
            (completed.stderr or completed.stdout or "").strip()[:500],
        )
        return False

    return True


def download_top10_videos(
    selection: dict[str, Any],
    dest_dir: Path | None = None,
    prev_dir: Path | None = None,
    yt_dlp_bin: str | None = None,
    dry_run: bool = False,
    rotate: bool = True,
) -> dict[str, Any]:
    """Filter YouTube items from the Top 10 digest, rotate folders, and download videos."""
    items = selection.get("items", [])
    if not isinstance(items, list) or not items:
        logger.info("No items provided in Top 10 selection for downloading.")
        return {"downloaded": 0, "failed": 0, "skipped_non_video": 0, "total_videos": 0}

    target_dest_dir = dest_dir or paths.get_top10_video_download_dir()
    target_prev_dir = prev_dir or paths.get_top10_previous_video_download_dir()

    # Filter and prepare download tasks
    download_tasks: list[dict[str, Any]] = []
    skipped_non_video = 0

    for item in items:
        if not is_youtube_video_item(item):
            skipped_non_video += 1
            logger.info("Skipping non-video Top 10 item #%s: %s", item.get("rank"), item.get("title"))
            continue

        rank = int(item.get("rank") or len(download_tasks) + 1)
        source_name = str(item.get("source_name") or "YouTube")
        title = str(item.get("title") or "Untitled")
        url = str(item.get("url") or "").strip()
        filename = build_video_filename(rank, source_name, title)
        output_path = target_dest_dir / filename

        download_tasks.append({
            "rank": rank,
            "url": url,
            "filename": filename,
            "output_path": output_path,
            "source_name": source_name,
            "title": title,
        })

    # Register any non-YouTube article items for NotebookLM Cinematic Video generation
    queued_articles = []
    try:
        from top_article_video_service import register_top_article_videos
        queued_articles = register_top_article_videos(selection)
    except Exception as exc:
        logger.warning("Could not register top article videos: %s", exc)

    if not download_tasks:
        logger.info("No YouTube videos found in the Top list; skipping folder rotation and download.")
        return {
            "downloaded": 0,
            "failed": 0,
            "skipped_non_video": skipped_non_video,
            "queued_articles": len(queued_articles),
            "total_videos": 0,
        }

    logger.info(
        "Preparing to download %d Top video(s) to %s (queued %d article video(s)).",
        len(download_tasks),
        target_dest_dir,
        len(queued_articles),
    )

    # Perform just-in-time folder rotation before downloading
    if not dry_run and rotate:
        rotate_top10_folders(target_dest_dir, target_prev_dir)

    downloaded = 0
    failed = 0

    for task in download_tasks:
        success = download_single_video(
            url=task["url"],
            output_path=task["output_path"],
            yt_dlp_bin=yt_dlp_bin,
            dry_run=dry_run,
        )
        if success:
            downloaded += 1
        else:
            failed += 1

    summary = {
        "downloaded": downloaded,
        "failed": failed,
        "skipped_non_video": skipped_non_video,
        "queued_articles": len(queued_articles),
        "total_videos": len(download_tasks),
        "dest_dir": str(target_dest_dir),
        "prev_dir": str(target_prev_dir),
    }
    logger.info("Top video download finished: %s", summary)
    return summary
