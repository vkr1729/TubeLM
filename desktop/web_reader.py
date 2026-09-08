"""
web_reader.py — TubeLM v4.0 Static Web Reader, 2-Week Rolling Purge & GitHub Pages Deployer.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

import paths
from sources_loader import load_sources

try:
    from dotenv import load_dotenv
    load_dotenv(paths.get_env_file())
except Exception:
    pass

logger = logging.getLogger("TubeLM-WebReader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def purge_old_digests_and_audio(summaries_dir: Path, audio_dir: Path, max_age_days: int = 14) -> list[str]:
    """Purge HTML digests and audio files older than max_age_days (strictly 2 weeks)."""
    purged = []
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
    logger.info("Enforcing 2-week rolling retention: Purging files older than %s...", cutoff_date)

    if summaries_dir.exists():
        for f in summaries_dir.iterdir():
            if f.is_file() and f.name.endswith((".html", ".json", ".md", ".png", ".jpg")):
                match = re.match(r"^(\d{4}-\d{2}-\d{2})_", f.name)
                if match:
                    try:
                        file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                        if file_date < cutoff_date:
                            logger.info("Purging stale digest file: %s (date: %s)", f.name, file_date)
                            f.unlink(missing_ok=True)
                            purged.append(f.name)
                    except ValueError:
                        pass

    if audio_dir.exists():
        for f in audio_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".mp3", ".m4a", ".wav"):
                match = re.match(r"^(\d{4}-\d{2}-\d{2})_", f.name)
                if match:
                    try:
                        file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                        if file_date < cutoff_date:
                            logger.info("Purging stale audio file: %s (date: %s)", f.name, file_date)
                            f.unlink(missing_ok=True)
                            purged.append(f.name)
                    except ValueError:
                        pass

    # Clean up stale entries in read_state.json older than cutoff
    read_state_file = paths.get_read_state_file()
    if read_state_file.exists():
        try:
            cur_data = json.loads(read_state_file.read_text(encoding="utf-8"))
            cur_ids = cur_data.get("read_ids", [])
            valid_ids = []
            for rid in cur_ids:
                m = re.match(r"^(\d{4}-\d{2}-\d{2})_", rid)
                if m:
                    try:
                        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                        if d >= cutoff_date:
                            valid_ids.append(rid)
                    except ValueError:
                        valid_ids.append(rid)
                else:
                    valid_ids.append(rid)
            if len(valid_ids) != len(cur_ids):
                read_state_file.write_text(json.dumps({"read_ids": valid_ids}, indent=2), encoding="utf-8")
        except Exception:
            pass

    return purged


def extract_youtube_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return ""
    match = re.search(r"(?:v=|\/embed\/|youtu\.be\/|\/v\/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)
    match_mock = re.search(r"(?:v=|\/embed\/|youtu\.be\/|\/v\/)([0-9A-Za-z_-]{5,})", url)
    return match_mock.group(1) if match_mock else ""


def optimize_audio_for_web(input_audio: Path, output_audio: Path) -> bool:
    """
    Transcode speech audio to high-efficiency 64kbps mono MP3.
    Reduces file size by ~75% and ensures seamless buffering on mobile Safari/Chrome.
    """
    output_audio.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_audio),
            "-ac", "1",
            "-ar", "44100",
            "-b:a", "64k",
            str(output_audio),
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if res.returncode == 0 and output_audio.exists() and output_audio.stat().st_size > 0:
            logger.info("Optimized audio %s (%d KB) -> %s (%d KB)",
                        input_audio.name, input_audio.stat().st_size // 1024,
                        output_audio.name, output_audio.stat().st_size // 1024)
            return True
    except Exception as exc:
        logger.warning("ffmpeg audio transcoding failed for %s: %s", input_audio, exc)

    shutil.copy(input_audio, output_audio)
    return False


def parse_top20_digest(top20_file: Path) -> dict[str, Any]:
    """Parse clean ranked items from a TubeLM Top 20 digest HTML file."""
    if not top20_file.exists():
        return {"items": [], "candidate_count": 0}

    soup = BeautifulSoup(top20_file.read_text(encoding="utf-8", errors="replace"), "html.parser")
    items = []
    seen_titles = set()

    for tr in soup.find_all("tr"):
        rank_td = tr.find(class_="rank-cell")
        if rank_td:
            rank_text = rank_td.get_text(strip=True)
            title_elem = tr.find(class_="item-title") or tr.find("h2")
            title = title_elem.get_text(" ", strip=True) if title_elem else ""
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            try:
                rank_num = int(rank_text)
            except ValueError:
                rank_num = len(items) + 1

            link_elem = tr.find("a", href=True)
            url = link_elem["href"] if link_elem else ""

            p_elem = tr.find("p")
            why_it_matters = p_elem.get_text(" ", strip=True) if p_elem else ""

            meta_div = tr.find("div", style=lambda s: s and "uppercase" in s)
            source_name = ""
            published = ""
            if meta_div:
                parts = [p.strip() for p in meta_div.get_text(strip=True).split("/")]
                if len(parts) >= 2:
                    source_name = parts[1]
                if len(parts) >= 3:
                    published = parts[2]

            source_type = "youtube" if ("youtube.com" in url or "youtu.be" in url) else "web"
            video_id = extract_youtube_video_id(url) if source_type == "youtube" else ""

            items.append({
                "rank": rank_num,
                "title": title,
                "url": url,
                "video_id": video_id,
                "why_it_matters": why_it_matters,
                "source_name": source_name,
                "published": published,
                "source_type": source_type,
            })

    items.sort(key=lambda x: x["rank"])
    return {
        "items": items,
        "candidate_count": len(items),
    }


_WORD_RE = re.compile(r"\w+")


def _read_minutes_for(text: str) -> tuple[int, int]:
    """Return (word_count, read_minutes) for plain text at 230 wpm, minimum 1 minute."""
    words = len(_WORD_RE.findall(text or ""))
    return words, max(1, round(words / 230))


def _lead_for(text: str, max_words: int = 60) -> str:
    """First max_words of plain text, ending with … when truncated."""
    parts = (text or "").split()
    if len(parts) <= max_words:
        return " ".join(parts)
    return " ".join(parts[:max_words]) + "…"


def _audio_seconds_for(audio_path: str | None) -> int:
    """MP3 duration in seconds: mutagen when available, else size estimate at 128 kbps."""
    if not audio_path:
        return 0
    p = Path(audio_path)
    try:
        if not p.exists() or p.stat().st_size == 0:
            return 0
    except OSError:
        return 0
    try:
        from mutagen.mp3 import MP3
        length = MP3(str(p)).info.length or 0
        return int(length)
    except Exception:
        pass
    try:
        return int(p.stat().st_size * 8 / 128_000)
    except OSError:
        return 0


def _load_audio_manifest(audio_dir: Path) -> dict[str, Any]:
    path = audio_dir / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def sync_audio_manifest(audio_dir: Path) -> None:
    """Sync manifest.json with completed weekly audio batches across all ISO week dates."""
    batches_file = paths.get_weekly_audio_batches_file()
    if not batches_file.exists():
        return
    try:
        data = json.loads(batches_file.read_text(encoding="utf-8"))
    except Exception:
        return
    manifest_path = audio_dir / "manifest.json"
    manifest = _load_audio_manifest(audio_dir)
    modified = False
    for batch in data.get("batches", []):
        week_start_str = batch.get("week_start")
        if not week_start_str:
            continue
        try:
            ws_date = datetime.strptime(week_start_str, "%Y-%m-%d").date()
            week_dates = [ws_date + timedelta(days=i) for i in range(7)]
        except ValueError:
            continue
        for entry in batch.get("entries", []):
            if entry.get("state") != "completed":
                continue
            safe = paths.safe_channel_name(entry.get("source_name", ""))
            filename = entry.get("audio_file") or f"{week_start_str}_{safe}.mp3"
            nb_id = entry.get("notebook_id", "")
            for d in week_dates:
                key = f"{d.isoformat()}|{safe}"
                if key not in manifest or manifest[key].get("file") != filename:
                    manifest[key] = {"notebook_id": nb_id, "file": filename}
                    modified = True
    if modified:
        try:
            audio_dir.mkdir(parents=True, exist_ok=True)
            tmp = manifest_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            os.replace(tmp, manifest_path)
            logger.info("Synchronized %d audio manifest entries.", len(manifest))
        except Exception:
            logger.exception("Failed to write updated audio manifest:")



def parse_channel_digest_json(json_file: Path, sources_map: dict[str, dict], audio_dir: Path) -> dict[str, Any] | None:
    """Build reader dict from structured sidecar JSON without HTML scraping."""
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    channel_name = str(data.get("channel_name") or json_file.stem)
    run_date = str(data.get("run_date") or "")
    safe_name = paths.safe_channel_name(channel_name)
    src_info = sources_map.get(channel_name) or sources_map.get(safe_name) or {}
    category = data.get("category") or src_info.get("category", "tech")
    subscribers = src_info.get("subscribers", "")
    notebook_url = str(data.get("notebook_url") or "")
    items = data.get("items") or []
    summary_text = str(data.get("summary_text") or "")
    videos = []
    try:
        from email_service import _split_markdown_summary_by_videos, _strip_citations
        from markdown_it import MarkdownIt
        _md = MarkdownIt("commonmark", {"html": False})
        per_item = _split_markdown_summary_by_videos(_strip_citations(summary_text), items, channel_name)
    except Exception:
        per_item = {}
        _md = None
    for it in items:
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "")
        title = str(it.get("title") or "")
        summary_html = ""
        if _md is not None:
            try:
                summary_html = _md.render(per_item.get(url, ""))
            except Exception:
                summary_html = ""
        videos.append({
            "title": title,
            "url": url,
            "video_id": str(it.get("video_id") or extract_youtube_video_id(url)),
            "published": str(it.get("published") or ""),
            "summary_html": summary_html,
            "lead": _lead_for(BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True) if summary_html else ""),
        })
    full_summary_html = "".join(v.get("summary_html", "") for v in videos)
    summary_preview = ""
    if summary_text:
        summary_preview = summary_text.strip().replace("\n", " ")[:140] + "…"
    if videos and all(not v.get("lead") for v in videos) and summary_text.strip():
        first_para = re.split(r"\n\s*\n", summary_text.strip(), maxsplit=1)[0]
        videos[0]["lead"] = _lead_for(re.sub(r"[#>*`]", "", first_para))
    word_count, read_minutes = _read_minutes_for(summary_text)
    has_audio = False
    audio_filename = None
    audio_path = None
    audio_url = None
    if audio_dir.exists():
        manifest = _load_audio_manifest(audio_dir)
        hit = manifest.get(f"{run_date}|{safe_name}")
        if hit and isinstance(hit, dict):
            p = audio_dir / str(hit.get("file", ""))
            if p.name and p.exists() and p.stat().st_size > 0:
                has_audio, audio_path, audio_filename = True, p, p.name
        if not has_audio and len(videos) > 1:
            p = audio_dir / f"{run_date}_{safe_name}.mp3"
            if p.exists() and p.stat().st_size > 0:
                has_audio, audio_path, audio_filename = True, p, p.name
        if has_audio and audio_filename:
            audio_url = f"audio/{audio_filename}"
    audio_seconds = _audio_seconds_for(str(audio_path)) if has_audio else 0
    return {
        "id": safe_name,
        "name": channel_name,
        "category": category,
        "subscribers": subscribers,
        "notebook_url": notebook_url,
        "video_count": len(videos),
        "videos": videos,
        "full_summary_html": full_summary_html,
        "summary_preview": summary_preview,
        "has_audio": has_audio,
        "audio_filename": audio_filename,
        "audio_path": str(audio_path) if audio_path else None,
        "audio_url": audio_url,
        "word_count": word_count,
        "read_minutes": read_minutes,
        "audio_seconds": audio_seconds,
        "brief": [
            {"title": v.get("title", ""), "url": v.get("url", ""),
             "video_id": v.get("video_id", ""), "lead": v.get("lead", "")}
            for v in videos
        ],
    }


def parse_channel_digest(html_file: Path, sources_map: dict[str, dict], audio_dir: Path, run_date: str) -> dict[str, Any] | None:
    """Parse single channel digest HTML into structured reader dictionary."""
    content = html_file.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(content, "html.parser")

    h1 = soup.find("h1")
    channel_name = h1.get_text(strip=True) if h1 else html_file.stem.split("_digest")[0]
    safe_name = paths.safe_channel_name(channel_name)

    src_info = sources_map.get(channel_name) or sources_map.get(safe_name) or {}
    category = src_info.get("category", "tech")
    subscribers = src_info.get("subscribers", "")

    # Extract Notebook URL
    nb_elem = soup.find("a", href=lambda h: h and ("notebooklm.google.com" in h or "notebook.google.com" in h))
    notebook_url = nb_elem["href"] if nb_elem else ""

    # Extract Videos
    videos = []
    for card in soup.find_all(class_="item-card"):
        h2 = card.find("h2") or card.find("h3")
        title = h2.get_text(" ", strip=True) if h2 else ""

        a_elem = card.find("a", href=lambda h: h and ("youtube.com" in h or "youtu.be" in h or "http" in h))
        url = a_elem["href"] if a_elem else ""
        video_id = extract_youtube_video_id(url)

        pub_elem = card.find("div", string=lambda s: s and "Published" in s)
        published = pub_elem.get_text(strip=True).replace("Published", "").strip() if pub_elem else ""

        summary_div = card.find(class_="summary-html")
        summary_html = str(summary_div) if summary_div else ""
        card_text = summary_div.get_text(" ", strip=True) if summary_div else ""

        videos.append({
            "title": title,
            "url": url,
            "video_id": video_id,
            "published": published,
            "summary_html": summary_html,
            "lead": _lead_for(card_text),
        })

    summary_blocks = soup.find_all(class_="summary-html")
    full_summary_html = "".join(str(b) for b in summary_blocks) if summary_blocks else ""
    full_summary_text = " ".join(b.get_text(" ", strip=True) for b in summary_blocks)

    summary_preview = ""
    first_p = soup.find("p", class_=None) or (summary_blocks[0].find("p") if summary_blocks else None)
    if first_p:
        summary_preview = first_p.get_text(" ", strip=True)[:140] + "…"
    if videos and all(not v.get("lead") for v in videos) and full_summary_text.strip():
        videos[0]["lead"] = _lead_for(full_summary_text)
    word_count, read_minutes = _read_minutes_for(full_summary_text)

    # Audio Overview Condition:
    has_audio = False
    audio_filename = None
    audio_path = None

    if audio_dir.exists():
        manifest = _load_audio_manifest(audio_dir)
        hit = manifest.get(f"{run_date}|{safe_name}")
        if hit and isinstance(hit, dict):
            p = audio_dir / str(hit.get("file", ""))
            if p.name and p.exists() and p.stat().st_size > 0:
                has_audio, audio_path, audio_filename = True, p, p.name
        # fallback ONLY for legacy files: exact run_date prefix, never a glob
        if not has_audio and len(videos) > 1:
            p = audio_dir / f"{run_date}_{safe_name}.mp3"
            if p.exists() and p.stat().st_size > 0:
                has_audio, audio_path, audio_filename = True, p, p.name

    audio_seconds = _audio_seconds_for(str(audio_path)) if has_audio else 0
    return {
        "id": safe_name,
        "name": channel_name,
        "category": category,
        "subscribers": subscribers,
        "notebook_url": notebook_url,
        "video_count": len(videos),
        "videos": videos,
        "full_summary_html": full_summary_html,
        "summary_preview": summary_preview,
        "has_audio": has_audio,
        "audio_filename": audio_filename,
        "audio_path": str(audio_path) if audio_path else None,
        "audio_url": f"audio/{audio_filename}" if audio_filename else None,
        "word_count": word_count,
        "read_minutes": read_minutes,
        "audio_seconds": audio_seconds,
        "brief": [
            {"title": v.get("title", ""), "url": v.get("url", ""),
             "video_id": v.get("video_id", ""), "lead": v.get("lead", "")}
            for v in videos
        ],
    }


def generate_rss_feed(site_data: dict[str, Any], output_path: Path, base_url: str = "https://vkr1729.github.io/TubeLM/") -> None:
    """Generate valid RSS 2.0 feed containing the 2-week rolling digests."""
    from xml.sax.saxutils import escape as xml_escape

    def _cdata(s: str) -> str:
        return "<![CDATA[" + (s or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"

    def _pub_date(run_date: str) -> str:
        try:
            dt = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        except (ValueError, TypeError):
            return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    current_week = site_data.get("weeks", {}).get("current", {})
    run_date = str(current_week.get("run_date") or "")
    channels = current_week.get("channels", [])
    top20_items = current_week.get("top20", {}).get("items", [])

    rss_items = []

    if top20_items:
        desc = "<ul>" + "".join(f"<li><strong>#{it['rank']} {it['title']}</strong> ({it['source_name']}): {it['why_it_matters']}</li>" for it in top20_items[:10]) + "</ul>"
        rss_items.append(f"""
    <item>
      <title>{xml_escape(f"TubeLM Executive Top 20 · Week of {run_date}")}</title>
      <link>{xml_escape(base_url)}</link>
      <guid isPermaLink="false">{xml_escape(f"{base_url}#top20-{run_date}")}</guid>
      <pubDate>{_pub_date(run_date)}</pubDate>
      <description>{_cdata(desc)}</description>
    </item>""")

    for ch in channels:
        desc = ch.get("full_summary_html") or ch.get("summary_preview") or "Weekly briefing"
        link = ch.get("notebook_url") or base_url
        rss_items.append(f"""
    <item>
      <title>{xml_escape(f"[{ch.get('category', 'Digest').upper()}] {ch.get('name', 'Source')} — TubeLM Briefing")}</title>
      <link>{xml_escape(link)}</link>
      <guid isPermaLink="false">{xml_escape(f"{base_url}#{ch.get('id')}-{run_date}")}</guid>
      <pubDate>{_pub_date(run_date)}</pubDate>
      <description>{_cdata(desc)}</description>
    </item>""")

    rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>TubeLM High-Signal Intelligence</title>
    <link>{xml_escape(base_url)}</link>
    <description>Personal 2-week rolling NotebookLM intelligence digests across 37 curated channels.</description>
    <lastBuildDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>
    <generator>TubeLM v4.0</generator>
    {"".join(rss_items)}
  </channel>
</rss>"""
    output_path.write_text(rss_content, encoding="utf-8")
    logger.info("Generated RSS feed at %s", output_path)


def generate_pwa_assets(site_dir: Path) -> None:
    """Generate iOS Safari and PWA manifest & logo icons with neon backdrop (#d9ff63) and bold obsidian 'TL'."""
    site_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate icon.svg
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#d9ff63"/>
  <text x="50%" y="54%" font-family="-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, 'Helvetica Neue', 'Liberation Sans', sans-serif" font-weight="900" font-size="250" fill="#171815" text-anchor="middle" dominant-baseline="middle" letter-spacing="-6">TL</text>
</svg>"""
    (site_dir / "icon.svg").write_text(svg_content, encoding="utf-8")

    # 2. Generate PNG icons using Pillow
    try:
        from PIL import Image, ImageDraw, ImageFont
        font_candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/System/Library/Fonts/SFPro-Bold.ttf",
            "Arial Bold.ttf",
        ]
        found_font = None
        for fc in font_candidates:
            if os.path.exists(fc):
                found_font = fc
                break

        def render_png(size: int, output_file: Path) -> None:
            img = Image.new("RGB", (size, size), color=(217, 255, 99))  # #d9ff63
            draw = ImageDraw.Draw(img)
            text = "TL"
            font_size = int(size * 0.52)
            if found_font:
                try:
                    font = ImageFont.truetype(found_font, font_size)
                except Exception:
                    font = ImageFont.load_default()
            else:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = (size - w) / 2 - bbox[0]
            y = (size - h) / 2 - bbox[1]
            draw.text((x, y), text, font=font, fill=(23, 24, 21))  # #171815
            img.save(output_file, format="PNG", optimize=True)

        render_png(180, site_dir / "apple-touch-icon.png")
        render_png(180, site_dir / "apple-touch-icon-180x180.png")
        render_png(192, site_dir / "icon-192.png")
        render_png(512, site_dir / "icon-512.png")
        render_png(32, site_dir / "favicon-32x32.png")
        logger.info("Generated PWA and Apple Touch Icon assets at %s", site_dir)
    except Exception as exc:
        logger.warning("Could not generate PNG icons with Pillow: %s", exc)

    # 3. Generate manifest.json
    manifest = {
        "name": "TubeLM — Personal Intelligence",
        "short_name": "TubeLM",
        "description": "Personal 2-week rolling NotebookLM intelligence digests and audio overviews.",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#11120f",
        "theme_color": "#d9ff63",
        "icons": [
            {
                "src": "icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "apple-touch-icon.png",
                "sizes": "180x180",
                "type": "image/png"
            }
        ]
    }
    (site_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_reader_site(
    summaries_dir: Path,
    audio_dir: Path,
    site_dir: Path,
    sources_file: Path,
    compress_audio: bool = False,
    generate_tts: bool = True,
) -> Path:
    """Build the complete static Web Reader site from 2-week rolling digests."""
    site_dir.mkdir(parents=True, exist_ok=True)
    site_audio_dir = site_dir / "audio"
    site_audio_dir.mkdir(exist_ok=True)
    generate_pwa_assets(site_dir)

    if not compress_audio:
        env_val = os.environ.get("TUBELM_COMPRESS_AUDIO") or os.environ.get("COMPRESS_AUDIO", "")
        compress_audio = env_val.strip().lower() in ("1", "true", "yes")

    logger.info("Building Web Reader site (compress_audio=%s)...", compress_audio)

    # Ensure audio manifest reflects all completed weekly batches
    sync_audio_manifest(audio_dir)

    # Pure build: no destructive purge here (main.py purges post-deploy).
    # 1. Map channels
    sources = load_sources(sources_file)
    sources_map = {s["name"]: s for s in sources}
    for s in sources:
        sources_map[paths.safe_channel_name(s["name"])] = s

    # 2. Discover dates and bucket by ISO calendar week (no drift).
    files = [f for f in summaries_dir.iterdir() if f.is_file() and f.name.endswith(".html")] if summaries_dir.exists() else []
    date_map: dict[datetime.date, list[Path]] = {}
    for f in files:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})_", f.name)
        if m:
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            date_map.setdefault(d, []).append(f)

    week_buckets: dict[tuple[int, int], list] = {}
    for d, flist in date_map.items():
        week_buckets.setdefault(d.isocalendar()[:2], []).append(d)
    sorted_weeks = sorted(week_buckets.keys(), reverse=True)
    if not sorted_weeks:
        today = datetime.now(timezone.utc).date()
        sorted_weeks = [today.isocalendar()[:2]]
        week_buckets[sorted_weeks[0]] = []
        date_map[today] = []
    current_week_key = sorted_weeks[0]
    prev_week_key = sorted_weeks[1] if len(sorted_weeks) > 1 else None
    current_dates = sorted(week_buckets.get(current_week_key, []), reverse=True)
    prev_dates = sorted(week_buckets.get(prev_week_key, []), reverse=True) if prev_week_key else []

    logger.info("Partitioning into Current Week (%s) and Previous Week (%s)...", current_dates, prev_dates)

    weeks_data: dict[str, Any] = {}

    try:
        import audio_storage as _audio_storage
    except ImportError:  # pragma: no cover
        _audio_storage = None  # type: ignore

    for week_key, dates_list in [("current", current_dates), ("prev", prev_dates)]:
        if not dates_list:
            weeks_data[week_key] = {"run_date": "None", "channels": [], "top20": {"items": []},
                                    "total_read_minutes": 0, "total_audio_seconds": 0, "channel_count": 0}
            continue

        channels = []
        top20_data = {"items": [], "candidate_count": 0}
        run_date_label = dates_list[0].strftime("%Y-%m-%d")

        seen_channels = set()
        for d in dates_list:
            d_str = d.strftime("%Y-%m-%d")
            for f in sorted(date_map.get(d, [])):
                if "Top_20" in f.name or "Top_10" in f.name:
                    if not top20_data.get("items"):
                        sidecar_top = f.with_suffix(".json")
                        if sidecar_top.exists():
                            try:
                                tdata = json.loads(sidecar_top.read_text(encoding="utf-8"))
                                if isinstance(tdata, dict) and tdata.get("items"):
                                    top20_data = {"items": tdata["items"], "candidate_count": tdata.get("candidate_count", len(tdata["items"]))}
                                    continue
                            except (OSError, json.JSONDecodeError):
                                pass
                        top20_data = parse_top20_digest(f)
                else:
                    ch_data = None
                    sidecar = f.with_suffix(".json")
                    if sidecar.exists():
                        ch_data = parse_channel_digest_json(sidecar, sources_map, audio_dir)
                    if ch_data is None:
                        ch_data = parse_channel_digest(f, sources_map, audio_dir, d_str)
                    if ch_data and ch_data["name"] not in seen_channels:
                        seen_channels.add(ch_data["name"])
                        tts_filename = f"summary_{d_str}_{ch_data['id']}.mp3"
                        tts_path = audio_dir / tts_filename
                        if generate_tts and not os.environ.get("PYTEST_CURRENT_TEST"):
                            try:
                                from tts_service import generate_summary_tts
                                # Build-time backfill: synthesize missing summary audio from existing text.
                                if not tts_path.exists() or tts_path.stat().st_size == 0:
                                    summary_text = ch_data.get("full_summary_html") or ch_data.get("summary_preview") or ""
                                    generate_summary_tts(summary_text, tts_path)
                            except Exception:
                                logger.exception("Summary TTS backfill failed for %s.", ch_data.get("name"))
                        if tts_path.exists() and tts_path.stat().st_size > 0:
                            remote = (_audio_storage.upload_audio(tts_path, d_str) if (_audio_storage is not None and _audio_storage.is_configured()) else "")
                            if remote:
                                ch_data["summary_audio_url"] = remote
                                (site_audio_dir / tts_filename).unlink(missing_ok=True)
                            else:
                                dest_tts = site_audio_dir / tts_filename
                                shutil.copy(tts_path, dest_tts)
                                ch_data["summary_audio_url"] = f"audio/{tts_filename}"
                            ch_data["summary_audio_seconds"] = _audio_seconds_for(str(tts_path))
                        if ch_data.get("audio_path") and Path(ch_data["audio_path"]).exists():
                            src_audio = Path(ch_data["audio_path"])
                            remote = (_audio_storage.upload_audio(src_audio, d_str) if (_audio_storage is not None and _audio_storage.is_configured()) else "")
                            if remote:
                                ch_data["audio_url"] = remote
                                (site_audio_dir / src_audio.name).unlink(missing_ok=True)
                            else:
                                dest_audio = site_audio_dir / src_audio.name
                                if compress_audio:
                                    if not dest_audio.exists() or dest_audio.stat().st_size > 15 * 1024 * 1024:
                                        optimize_audio_for_web(src_audio, dest_audio)
                                else:
                                    if not dest_audio.exists() or dest_audio.stat().st_size != src_audio.stat().st_size:
                                        shutil.copy(src_audio, dest_audio)
                                        logger.info("Retained original uncompressed audio: %s (%d KB)",
                                                    dest_audio.name, src_audio.stat().st_size // 1024)
                                ch_data["audio_url"] = f"audio/{src_audio.name}"
                        channels.append(ch_data)

        channels.sort(key=lambda c: c["name"])

        weeks_data[week_key] = {
            "run_date": run_date_label,
            "channels": channels,
            "top20": top20_data,
            "total_read_minutes": sum(int(ch.get("read_minutes") or 0) for ch in channels),
            "total_audio_seconds": sum(int(ch.get("audio_seconds") or 0) for ch in channels),
            "channel_count": len(channels),
        }

    read_state_file = paths.get_read_state_file()
    saved_read_ids = []
    if read_state_file.exists():
        try:
            saved_read_ids = json.loads(read_state_file.read_text(encoding="utf-8")).get("read_ids", [])
        except Exception:
            saved_read_ids = []

    site_data = {
        "version": "4.0.0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "read_ids": saved_read_ids,
        "weeks": weeks_data,
    }

    # Render index.html
    env = Environment(
        loader=FileSystemLoader(str(paths.get_templates_dir())),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("reader.html")
    site_data_json = json.dumps(site_data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    rendered_html = template.render(
        site_data_json=site_data_json,
        site_data=site_data,
    )

    index_path = site_dir / "index.html"
    index_path.write_text(rendered_html, encoding="utf-8")
    logger.info("Successfully built Web Reader at %s", index_path)

    # Render RSS feed
    rss_path = site_dir / "feed.xml"
    generate_rss_feed(site_data, rss_path)

    # Write .nojekyll
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    if _audio_storage is not None and _audio_storage.is_configured() and site_audio_dir.exists():
        for f in site_audio_dir.iterdir():
            if f.is_file() and f.stat().st_size > 5 * 1024 * 1024:
                logger.info("Cleaning up large file from site/audio as R2 is active: %s", f.name)
                f.unlink(missing_ok=True)

    return index_path


def deploy_to_gh_pages(site_dir: Path, repo_url: str = "https://github.com/vkr1729/TubeLM.git") -> bool:
    """Deploy site_dir contents to orphan gh-pages branch with force push."""
    logger.info("Deploying Web Reader to GitHub Pages (gh-pages branch)...")

    if not shutil.which("git"):
        logger.error("Git is not installed or not in PATH; skipping gh-pages deploy.")
        return False

    big = [p for p in site_dir.rglob("*") if p.is_file() and p.stat().st_size > 5 * 1024 * 1024]
    if big:
        logger.error("Refusing to deploy: %d file(s) over 5 MB in site dir (binary assets belong on R2): %s",
                     len(big), ", ".join(p.name for p in big[:5]))
        return False

    temp_git_dir = site_dir / ".git"
    try:
        if temp_git_dir.exists():
            shutil.rmtree(temp_git_dir, ignore_errors=True)

        subprocess.run(["git", "init"], cwd=site_dir, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.name", "TubeLM Bot"], cwd=site_dir, check=True)
        subprocess.run(["git", "config", "user.email", "tubelm@bot.local"], cwd=site_dir, check=True)
        subprocess.run(["git", "checkout", "-b", "gh-pages"], cwd=site_dir, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "add", "."], cwd=site_dir, check=True)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subprocess.run(["git", "commit", "-m", f"TubeLM v4.0 Web Reader sync: {now_str}"], cwd=site_dir, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=site_dir, check=True)

        logger.info("Pushing to origin gh-pages (force)...")
        res = subprocess.run(["git", "push", "-f", "origin", "gh-pages"], cwd=site_dir, capture_output=True, text=True)
        if res.returncode == 0:
            logger.info("Successfully deployed to GitHub Pages! Live URL: https://vkr1729.github.io/TubeLM/")
            return True
        else:
            logger.warning("Failed to push to gh-pages: %s", res.stderr)
            return False
    except Exception:
        logger.exception("Exception during gh-pages deployment:")
        return False
    finally:
        if temp_git_dir.exists():
            shutil.rmtree(temp_git_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="TubeLM v4.0 Web Reader Builder & Deployer")
    parser.add_argument("--build-only", action="store_true", help="Build site locally without deploying to gh-pages")
    parser.add_argument("--deploy", action="store_true", help="Build site and deploy to gh-pages")
    parser.add_argument(
        "--compress-audio",
        action="store_true",
        default=False,
        help="Enable optional lossy audio transcoding (64k mono MP3). Default: disabled (retains original high-fidelity audio).",
    )
    args = parser.parse_args()

    summaries_dir = paths.get_summaries_dir()
    if not any(summaries_dir.glob("*.html")) and Path("summaries").exists():
        summaries_dir = Path("summaries").resolve()

    audio_dir = paths.get_audio_dir()
    site_dir = paths.get_site_dir()
    sources_file = paths.get_sources_file()

    index_path = build_reader_site(
        summaries_dir,
        audio_dir,
        site_dir,
        sources_file,
        compress_audio=args.compress_audio,
    )
    print(f"Reader build complete: {index_path}")

    if args.deploy or not args.build_only:
        deploy_to_gh_pages(site_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
