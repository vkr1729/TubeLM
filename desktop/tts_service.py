"""Neural summary TTS via edge-tts (Option C).

Generates a short studio-grade spoken MP3 for each channel's text summary so
commute listening works with the screen off through the reader Mini-Player.
All failures degrade to False — TTS must never break a pipeline run.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import html
from pathlib import Path

from bs4 import BeautifulSoup
import edge_tts

logger = logging.getLogger(__name__)

# High-signal, natural expressive voice (Andrew Multilingual default)
DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_RATE = "+0%"

# Upper bound for one edge-tts synthesis (default 300s / 5 minutes)
# Dynamic scaling ensures long summaries (>1,000 words) get proportional time.
TTS_TIMEOUT_SECONDS = int(os.getenv("TTS_TIMEOUT_SECONDS", "300"))


def get_configured_voice() -> str:
    return os.getenv("TTS_VOICE", "").strip() or DEFAULT_VOICE


def get_configured_rate() -> str:
    return os.getenv("TTS_RATE", "").strip() or DEFAULT_RATE


def clean_text_for_speech(text: str) -> str:
    """Strip HTML, markdown links, citations, URLs, and formatting for clean natural narration."""
    if not text:
        return ""
    t = text
    # Strip HTML tags and unescape HTML entities if present
    if "<" in t and ">" in t:
        try:
            soup = BeautifulSoup(t, "html.parser")
            t = soup.get_text(" ", strip=True)
        except Exception:
            t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)

    # Strip citation brackets like [1], [1, 2], [1-3]
    t = re.sub(r"\s*\[\d+(?:[\s\d,\-–—]*\d+)*\]", "", t)
    # Remove markdown links, leave link text: [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    # Remove raw URLs so voice never spells out http/https
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\bwww\.\S+", "", t)
    # Remove headers #, ##, ###
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    # Remove bold/italics
    t = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", t)
    t = re.sub(r"[*_]", "", t)
    # Remove list bullet markers
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.MULTILINE)
    # Strip remaining angle brackets
    t = re.sub(r"[<>]", "", t)
    # Normalize whitespace
    return " ".join(t.split())


async def _generate_audio_async(
    text: str,
    output_path: Path,
    voice: str | None = None,
    rate: str | None = None,
    force: bool = False,
) -> bool:
    if not force and output_path.exists() and output_path.stat().st_size > 0:
        return True
    clean = clean_text_for_speech(text)
    if not clean or len(clean) < 20:
        return False
    effective_voice = voice or get_configured_voice()
    effective_rate = rate or get_configured_rate()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_out = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp.mp3")
    effective_timeout = max(TTS_TIMEOUT_SECONDS, int(len(clean.split()) * 0.4))
    try:
        communicate = edge_tts.Communicate(clean, effective_voice, rate=effective_rate)
        await asyncio.wait_for(communicate.save(str(temp_out)), timeout=effective_timeout)
        if not force and output_path.exists() and output_path.stat().st_size > 0:
            temp_out.unlink(missing_ok=True)
            return True
        temp_out.replace(output_path)
        logger.info(
            "Generated summary TTS audio: %s (%d bytes, voice=%s, rate=%s)",
            output_path.name,
            output_path.stat().st_size,
            effective_voice,
            effective_rate,
        )
        return True
    except asyncio.TimeoutError:
        logger.warning(
            "edge-tts generation timed out after %ds; skipping TTS for %s.",
            effective_timeout,
            output_path.name,
        )
        temp_out.unlink(missing_ok=True)
        return False
    except Exception as e:
        logger.warning("edge-tts generation failed: %s", e)
        temp_out.unlink(missing_ok=True)
        return False


def generate_summary_tts(
    text: str,
    output_path: Path,
    voice: str | None = None,
    rate: str | None = None,
    force: bool = False,
) -> bool:
    """Synchronous entrypoint for pipeline calls."""
    if not force and output_path.exists() and output_path.stat().st_size > 0:
        return True
    try:
        return asyncio.run(_generate_audio_async(text, output_path, voice=voice, rate=rate, force=force))
    except Exception as e:
        logger.warning("Failed running async TTS: %s", e)
        return False


def _plain_text_from_digest(path: Path) -> str:
    """Extract plain summary text from a *_digest.json sidecar or *_digest.html file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if path.suffix == ".json":
        try:
            import json
            data = json.loads(raw)
        except ValueError:
            return ""
        if isinstance(data, dict):
            text = str(data.get("summary_text") or "")
            if text.strip():
                return text
            items = data.get("items") or []
            return " ".join(str(it.get("title") or "") for it in items if isinstance(it, dict))
        return ""
    # HTML fallback: concatenate summary blocks as text
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"<[^>]+>", " ", raw)
    soup = BeautifulSoup(raw, "html.parser")
    blocks = soup.find_all(class_="summary-html")
    if blocks:
        return " ".join(b.get_text(" ", strip=True) for b in blocks)
    body = soup.find("body")
    return body.get_text(" ", strip=True) if body else ""


async def _backfill_week_async(
    summaries_dir: Path,
    audio_dir: Path,
    run_date: str,
    voice: str | None = None,
    rate: str | None = None,
    force: bool = False,
    concurrency: int = 3,
) -> dict[str, int]:
    """Generate missing summary_*.mp3 files concurrently."""
    from paths import safe_channel_name

    stats = {"scanned": 0, "generated": 0, "skipped": 0, "failed": 0}
    if not summaries_dir.exists():
        return stats
    seen: set[str] = set()
    files = sorted(summaries_dir.glob(f"{run_date}_*.json")) + sorted(summaries_dir.glob(f"{run_date}_*.html"))
    tasks = []
    sem = asyncio.Semaphore(concurrency)

    async def process_one(digest: Path, tts_path: Path):
        async with sem:
            text = _plain_text_from_digest(digest)
            return await asyncio.to_thread(
                generate_summary_tts, text, tts_path, voice=voice, rate=rate, force=force
            )

    for digest in files:
        if "Top_20" in digest.name or "Top_10" in digest.name:
            continue
        safe = safe_channel_name(digest.stem[len(run_date) + 1:].removesuffix("_digest"))
        if not safe or safe in seen:
            continue
        seen.add(safe)
        stats["scanned"] += 1
        tts_path = audio_dir / f"summary_{run_date}_{safe}.mp3"
        if not force and tts_path.exists() and tts_path.stat().st_size > 0:
            stats["skipped"] += 1
            continue
        tasks.append(process_one(digest, tts_path))

    if tasks:
        results = await asyncio.gather(*tasks)
        for ok in results:
            if ok:
                stats["generated"] += 1
            else:
                stats["failed"] += 1
    return stats


def backfill_week(
    summaries_dir: Path,
    audio_dir: Path,
    run_date: str,
    voice: str | None = None,
    rate: str | None = None,
    force: bool = False,
    concurrency: int = 3,
) -> dict[str, int]:
    """Generate missing (or force-regenerated) summary_*.mp3 files for one run date. Returns counts."""
    return asyncio.run(
        _backfill_week_async(
            summaries_dir, audio_dir, run_date, voice=voice, rate=rate, force=force, concurrency=concurrency
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill neural summary TTS audio.")
    parser.add_argument("--backfill", action="store_true", help="Generate missing summary MP3s.")
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: latest in summaries dir).")
    parser.add_argument("--force", action="store_true", help="Force re-generation of existing summary MP3s.")
    parser.add_argument("--voice", default=None, help="TTS voice override (e.g. en-US-BrianMultilingualNeural).")
    parser.add_argument("--rate", default=None, help="TTS rate override (e.g. +5%%).")
    args = parser.parse_args(argv)

    if not args.backfill:
        parser.print_help()
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import paths

    summaries_dir = paths.get_summaries_dir()
    audio_dir = paths.get_audio_dir()
    run_date = args.date
    if not run_date:
        dates = sorted(
            {m.group(1) for f in summaries_dir.glob("*_digest.*")
             if (m := re.match(r"^(\d{4}-\d{2}-\d{2})_", f.name))},
            reverse=True,
        )
        if not dates:
            print("No digests found.")
            return 1
        run_date = dates[0]
    stats = backfill_week(
        summaries_dir,
        audio_dir,
        run_date,
        voice=args.voice,
        rate=args.rate,
        force=args.force,
    )
    print(f"Backfill {run_date}: scanned={stats['scanned']} generated={stats['generated']} "
          f"skipped={stats['skipped']} failed={stats['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
