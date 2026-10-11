"""Neural summary TTS via edge-tts (Option C).

Generates a short studio-grade spoken MP3 for each channel's text summary so
commute listening works with the screen off through the reader Mini-Player.
All failures degrade to False — TTS must never break a pipeline run.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import re
import sys
import html
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import edge_tts

logger = logging.getLogger(__name__)

# High-signal, natural expressive voice (Andrew Multilingual default)
DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_RATE = "+0%"

# Upper bound for one edge-tts synthesis (default 300s / 5 minutes)
# Dynamic scaling ensures long summaries (>1,000 words) get proportional time.
DEFAULT_TTS_TIMEOUT_SECONDS = 300
MAX_TTS_TIMEOUT_SECONDS = 86400  # a day; beyond this the value is a typo


def parse_tts_timeout_seconds(raw: str | None) -> int:
    """Parse TTS_TIMEOUT_SECONDS tolerantly: TTS degrades, never crashes.

    A typo'd value warns and falls back to the default instead of killing the
    module import (and the pipeline) with a bare ValueError. Float strings are
    accepted; absurd magnitudes are clamped.
    """
    text = (raw or "").strip() or str(DEFAULT_TTS_TIMEOUT_SECONDS)
    try:
        parsed = float(text)
        if not parsed == parsed or parsed in (float("inf"), float("-inf")):
            raise ValueError(text)
        value = int(parsed)
    except (ValueError, OverflowError):
        logger.warning(
            "Invalid TTS_TIMEOUT_SECONDS=%r; using default %d.",
            raw, DEFAULT_TTS_TIMEOUT_SECONDS,
        )
        return DEFAULT_TTS_TIMEOUT_SECONDS
    if value <= 0:
        logger.warning(
            "Non-positive TTS_TIMEOUT_SECONDS=%r; using default %d.",
            raw, DEFAULT_TTS_TIMEOUT_SECONDS,
        )
        return DEFAULT_TTS_TIMEOUT_SECONDS
    if value > MAX_TTS_TIMEOUT_SECONDS:
        logger.warning(
            "TTS_TIMEOUT_SECONDS=%r exceeds %d; clamping.",
            raw, MAX_TTS_TIMEOUT_SECONDS,
        )
        return MAX_TTS_TIMEOUT_SECONDS
    return value


TTS_TIMEOUT_SECONDS = parse_tts_timeout_seconds(os.getenv("TTS_TIMEOUT_SECONDS"))


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

    # Remove escaped characters e.g. \$ -> $ (so voice says "thirty five dollars", not "backslash dollar")
    t = t.replace(r"\$", "$").replace(r"\_", "_").replace(r"\*", "*").replace("\\", "")

    # Strategic pause insertion for Markdown headers (BEFORE stripping hashes and collapsing whitespace):
    # Match any header line (e.g. "### 1. The Hook" or "## Key Takeaways")
    # If it doesn't end with terminal punctuation (. ! ? :), append ". " so neural TTS pauses naturally!
    def _header_replacer(m):
        header_text = m.group(1).strip()
        if not header_text:
            return ""
        if header_text[-1] not in ".!?:":
            return f"\n{header_text}.\n\n"
        return f"\n{header_text}\n\n"

    t = re.sub(r"^#{1,6}\s+(.+)$", _header_replacer, t, flags=re.MULTILINE)
    # Remove any remaining leading/isolated hashes so "#" is never verbalized
    t = re.sub(r"#+", "", t)

    # Remove bold/italics
    t = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", t)
    t = re.sub(r"[*_]", "", t)

    # Remove backticks
    t = re.sub(r"`+([^`]+)`+", r"\1", t)
    t = re.sub(r"`+", "", t)

    # Handle slashes gracefully:
    # Convert 'and/or' -> 'and or', 'w/' -> 'with', 'w/o' -> 'without'
    t = re.sub(r"\band/or\b", "and or", t, flags=re.IGNORECASE)
    t = re.sub(r"\bw/(?=\s|$)", "with", t, flags=re.IGNORECASE)
    t = re.sub(r"\bw/o(?=\s|$)", "without", t, flags=re.IGNORECASE)
    # Isolated slashes surrounded by spaces ' / ' -> ', '
    t = re.sub(r"\s+/\s+", ", ", t)
    # Slashes between letters e.g. "input/output" -> "input, output"
    t = re.sub(r"(?<=[a-zA-Z])/(?=[a-zA-Z])", ", ", t)

    # Remove list bullet markers
    t = re.sub(r"^\s*[-*+•]\s+", "", t, flags=re.MULTILINE)
    # Strip remaining angle brackets
    t = re.sub(r"[<>]", "", t)

    # Normalize multiple punctuation or spaces, maintaining clean pauses
    t = re.sub(r"\s*\.\s*\.", ".", t)
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
    """Synchronous entrypoint for pipeline calls. Loop-agnostic."""
    if not force and output_path.exists() and output_path.stat().st_size > 0:
        return True
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                def _run_in_worker():
                    return asyncio.run(_generate_audio_async(text, output_path, voice=voice, rate=rate, force=force))
                future = pool.submit(_run_in_worker)
                return future.result()
        else:
            return asyncio.run(_generate_audio_async(text, output_path, voice=voice, rate=rate, force=force))
    except Exception as e:
        logger.warning("Failed running async TTS: %s", e)
        return False


def clean_video_safe_id(video: dict[str, Any]) -> str:
    """Return a deterministic filesystem-safe identifier for video-level audio.

    YouTube videos get their exact 11-char video ID. Non-YouTube items
    (e.g. RSS articles) or items with invalid IDs get sha256(url)[:12]
    or sha256(title)[:12].
    """
    raw_id = str(video.get("video_id") or "").strip()
    if re.fullmatch(r"^[A-Za-z0-9_-]{11}$", raw_id):
        return raw_id
    url = str(video.get("url") or video.get("link") or "").strip()
    if url:
        yt_match = re.search(r"(?:v=|\/embed\/|youtu\.be\/|\/v\/|\/shorts\/)([0-9A-Za-z_-]{11})", url)
        if yt_match:
            return yt_match.group(1)
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    title = str(video.get("title") or "").strip().lower()
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]


def video_summary_filename(run_date: str, safe_id: str) -> str:
    """Return canonical filename for a video-level summary audio file."""
    return f"summary_video_{run_date}_{safe_id}.mp3"


def generate_video_summary_tts(
    title: str,
    channel_name: str,
    summary_md: str,
    output_path: Path,
    voice: str | None = None,
    rate: str | None = None,
    force: bool = False,
) -> bool:
    """Generate audio summary for a single video. Loop-agnostic."""
    clean_body = clean_text_for_speech(summary_md)
    if not clean_body or len(clean_body) < 20:
        return False
    clean_title = clean_text_for_speech(title)
    clean_channel = clean_text_for_speech(channel_name)
    spoken_text = f"{clean_title}, by {clean_channel}. {clean_body}"
    return generate_summary_tts(spoken_text, output_path, voice=voice, rate=rate, force=force)


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
    per_video: bool = False,
) -> dict[str, int]:
    import paths
    from paths import safe_channel_name

    stats = {"scanned": 0, "generated": 0, "skipped": 0, "failed": 0}
    if not summaries_dir.exists():
        return stats
    seen: set[str] = set()
    files = sorted(summaries_dir.glob(f"{run_date}_*.json")) + sorted(summaries_dir.glob(f"{run_date}_*.html"))
    tasks = []
    sem = asyncio.Semaphore(concurrency)

    if per_video:
        import json
        from email_service import _split_markdown_summary_by_videos, _strip_citations

        async def process_video(title: str, ch_name: str, vid_text: str, tts_path: Path):
            async with sem:
                generate_fn = globals().get("generate_video_summary_tts")
                try:
                    if generate_fn is not None:
                        return await asyncio.to_thread(
                            generate_fn, title, ch_name, vid_text, tts_path, voice=voice, rate=rate, force=force
                        )
                    clean_body = clean_text_for_speech(vid_text)
                    if not clean_body or len(clean_body) < 20:
                        return False
                    clean_title = clean_text_for_speech(title)
                    clean_channel = clean_text_for_speech(ch_name)
                    spoken_text = f"{clean_title}, by {clean_channel}. {clean_body}"
                    return await _generate_audio_async(spoken_text, tts_path, voice=voice, rate=rate, force=force)
                except Exception as exc:
                    logger.warning("Failed video TTS for %s: %s", tts_path.name, exc)
                    return False

        for digest in files:
            if paths.is_top_digest_file(digest) or digest.suffix != ".json":
                continue
            try:
                data = json.loads(digest.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            ch_name = str(data.get("channel_name") or digest.stem[len(run_date) + 1:].removesuffix("_digest"))
            items = data.get("items") or []
            summary_text = str(data.get("summary_text") or "")
            if not items or not summary_text:
                continue
            per_item = _split_markdown_summary_by_videos(_strip_citations(summary_text), items, ch_name)
            for v in items:
                if not isinstance(v, dict):
                    continue
                safe_id = clean_video_safe_id(v)
                vid_summary = per_item.get(v.get("url") or "")
                if not vid_summary and len(items) == 1:
                    vid_summary = summary_text
                if not vid_summary:
                    continue
                tts_filename = video_summary_filename(run_date, safe_id)
                tts_path = audio_dir / tts_filename
                stats["scanned"] += 1
                if not force and tts_path.exists() and tts_path.stat().st_size > 0:
                    stats["skipped"] += 1
                    continue
                tasks.append(process_video(str(v.get("title") or ""), ch_name, vid_summary, tts_path))
    else:
        async def process_one(digest: Path, tts_path: Path):
            async with sem:
                text = _plain_text_from_digest(digest)
                generate_fn = globals().get("generate_summary_tts")
                try:
                    if generate_fn is not None and generate_fn is not _generate_audio_async:
                        return await asyncio.to_thread(
                            generate_fn, text, tts_path, voice=voice, rate=rate, force=force
                        )
                    return await _generate_audio_async(text, tts_path, voice=voice, rate=rate, force=force)
                except Exception as exc:
                    logger.warning("Failed TTS for %s: %s", tts_path.name, exc)
                    return False

        for digest in files:
            if paths.is_top_digest_file(digest):
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
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for ok in results:
            if ok is True:
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
    per_video: bool = False,
) -> dict[str, int]:
    """Generate missing (or force-regenerated) summary MP3 files for one run date. Returns counts."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _backfill_week_async(
                summaries_dir, audio_dir, run_date, voice=voice, rate=rate, force=force,
                concurrency=concurrency, per_video=per_video
            )
        )
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run,
            _backfill_week_async(
                summaries_dir, audio_dir, run_date, voice=voice, rate=rate, force=force,
                concurrency=concurrency, per_video=per_video
            ),
        ).result()


def backfill_video_summaries(
    summaries_dir: Path,
    audio_dir: Path,
    run_date: str,
    voice: str | None = None,
    rate: str | None = None,
    force: bool = False,
    concurrency: int = 3,
) -> dict[str, int]:
    """Generate missing video-level summary MP3s for one run date. Returns counts."""
    return backfill_week(
        summaries_dir,
        audio_dir,
        run_date,
        voice=voice,
        rate=rate,
        force=force,
        concurrency=concurrency,
        per_video=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill neural summary TTS audio.")
    parser.add_argument("--backfill", action="store_true", help="Generate missing summary MP3s.")
    parser.add_argument("--videos", action="store_true", help="Generate video-level audio summaries instead of channel-level.")
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
    backfill_fn = backfill_video_summaries if args.videos else backfill_week
    stats = backfill_fn(
        summaries_dir,
        audio_dir,
        run_date,
        voice=args.voice,
        rate=args.rate,
        force=args.force,
    )
    label = "Video summary backfill" if args.videos else "Backfill"
    print(f"{label} {run_date}: scanned={stats['scanned']} generated={stats['generated']} "
          f"skipped={stats['skipped']} failed={stats['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
