#!/usr/bin/env python3
"""Send an Editor's Top 10 from existing local TubeLM HTML digests."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

DESKTOP_DIR = Path(__file__).resolve().parents[1]
if str(DESKTOP_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_DIR))

from config import load_config  # noqa: E402
import paths  # noqa: E402
from top10_service import send_top10_from_html_digests  # noqa: E402


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a date in YYYY-MM-DD format.") from exc


def main() -> None:
    cfg = load_config()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    parser = argparse.ArgumentParser(
        description="Select and send a Top digest from existing TubeLM HTML digests."
    )
    parser.add_argument("--since", type=_iso_date, default=week_start)
    parser.add_argument("--until", type=_iso_date, default=today)
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of items to select (defaults to TOP_DIGEST_COUNT in config).",
    )
    args = parser.parse_args()
    if args.since > args.until:
        parser.error("--since must be on or before --until")

    digest_paths = []
    for digest_path in paths.get_summaries_dir().glob("*_digest.html"):
        if "TubeLM_Top_" in digest_path.name:
            continue
        try:
            digest_date = date.fromisoformat(digest_path.name[:10])
        except ValueError:
            continue
        if args.since <= digest_date <= args.until:
            digest_paths.append(digest_path)
    if not digest_paths:
        parser.error("No local HTML digests were found in the requested date range.")

    selection, output_path = send_top10_from_html_digests(
        cfg, digest_paths, args.until.isoformat(), target_count=args.count
    )
    print(
        f"Sent Top {len(selection['items'])} selected from "
        f"{selection['candidate_count']} items."
    )
    print(output_path)


if __name__ == "__main__":
    main()
