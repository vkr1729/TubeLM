#!/usr/bin/env python3
"""Download Top 10 YouTube videos from the latest or specified TubeLM Top 10 digest."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

DESKTOP_DIR = Path(__file__).resolve().parents[1]
if str(DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_DIR))

import paths  # noqa: E402
from top10_downloader import (  # noqa: E402
    download_top10_videos,
    extract_items_from_top10_html,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("download_top10")


def find_latest_top10_digest() -> Path | None:
    """Find the most recent Top 10 digest HTML file."""
    summaries_dir = paths.get_summaries_dir()
    digests = sorted(summaries_dir.glob("*_TubeLM_Top_10_digest.html"))
    return digests[-1] if digests else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Top 10 videos from a TubeLM Top 10 HTML digest."
    )
    parser.add_argument(
        "--digest-file",
        type=Path,
        help="Path to the Top 10 digest HTML file (defaults to the most recent).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate actions and print commands without moving files or downloading.",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=paths.get_top10_video_download_dir(),
        help="Directory to save downloaded videos.",
    )
    parser.add_argument(
        "--prev-dir",
        type=Path,
        default=paths.get_top10_previous_video_download_dir(),
        help="Directory to archive previous videos.",
    )
    args = parser.parse_args()

    digest_file = args.digest_file or find_latest_top10_digest()
    if not digest_file or not digest_file.exists():
        parser.error("No Top 10 digest HTML file found in ~/.tubelm/summaries/")

    logger.info("Reading Top 10 items from %s", digest_file)
    items = extract_items_from_top10_html(digest_file)
    if not items:
        parser.error(f"No valid items found inside {digest_file}")

    selection = {
        "items": items,
        "run_date": digest_file.name[:10],
    }

    summary = download_top10_videos(
        selection=selection,
        dest_dir=args.dest_dir,
        prev_dir=args.prev_dir,
        dry_run=args.dry_run,
    )
    print("\n--- Summary ---")
    print(f"Total videos: {summary['total_videos']}")
    print(f"Downloaded: {summary['downloaded']}")
    print(f"Failed: {summary['failed']}")
    print(f"Skipped non-video items: {summary['skipped_non_video']}")
    print(f"Destination: {summary['dest_dir']}")
    print(f"Previous archive: {summary['prev_dir']}")


if __name__ == "__main__":
    main()
