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

logger = logging.getLogger("TubeLM-WebReader")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def purge_old_digests_and_audio(summaries_dir: Path, audio_dir: Path, max_age_days: int = 14) -> list[str]:
    """Purge HTML digests and audio files older than max_age_days (strictly 2 weeks)."""
    purged = []
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
    logger.info("Enforcing 2-week rolling retention: Purging files older than %s...", cutoff_date)

    if summaries_dir.exists():
        for f in summaries_dir.iterdir():
            if f.is_file() and f.name.endswith((".html", ".md", ".png", ".jpg")):
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

        videos.append({
            "title": title,
            "url": url,
            "video_id": video_id,
            "published": published,
            "summary_html": summary_html,
        })

    summary_blocks = soup.find_all(class_="summary-html")
    full_summary_html = "".join(str(b) for b in summary_blocks) if summary_blocks else ""

    summary_preview = ""
    first_p = soup.find("p", class_=None) or (summary_blocks[0].find("p") if summary_blocks else None)
    if first_p:
        summary_preview = first_p.get_text(" ", strip=True)[:140] + "…"

    # Audio Overview Condition:
    has_audio = False
    audio_filename = None
    audio_path = None

    if len(videos) > 1 and audio_dir.exists():
        candidate_audio_files = [
            audio_dir / f"{run_date}_{safe_name}.mp3",
            audio_dir / f"{safe_name}.mp3",
            audio_dir / f"{safe_name}_{run_date}.mp3",
        ]
        for p in candidate_audio_files:
            if p.exists() and p.stat().st_size > 0:
                has_audio = True
                audio_path = p
                audio_filename = p.name
                break

        if not has_audio:
            for p in sorted(audio_dir.glob(f"*{safe_name}*.mp3")):
                if p.is_file() and p.stat().st_size > 0:
                    has_audio = True
                    audio_path = p
                    audio_filename = p.name
                    break

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
    }


def generate_rss_feed(site_data: dict[str, Any], output_path: Path, base_url: str = "https://vkr1729.github.io/TubeLM/") -> None:
    """Generate valid RSS 2.0 feed containing the 2-week rolling digests."""
    current_week = site_data.get("weeks", {}).get("current", {})
    channels = current_week.get("channels", [])
    top20_items = current_week.get("top20", {}).get("items", [])

    rss_items = []

    if top20_items:
        desc = "<ul>" + "".join(f"<li><strong>#{it['rank']} {it['title']}</strong> ({it['source_name']}): {it['why_it_matters']}</li>" for it in top20_items[:10]) + "</ul>"
        rss_items.append(f"""
    <item>
      <title>TubeLM Executive Top 20 · Week of {current_week.get('run_date', '')}</title>
      <link>{base_url}</link>
      <guid>{base_url}#top20-{current_week.get('run_date', '')}</guid>
      <pubDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
      <description><![CDATA[{desc}]]></description>
    </item>""")

    for ch in channels:
        desc = ch.get("full_summary_html") or ch.get("summary_preview") or "Weekly briefing"
        link = ch.get("notebook_url") or base_url
        rss_items.append(f"""
    <item>
      <title>[{ch.get('category', 'Digest').upper()}] {ch.get('name', 'Source')} — TubeLM Briefing</title>
      <link>{link}</link>
      <guid>{base_url}#{ch.get('id')}-{current_week.get('run_date', '')}</guid>
      <pubDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
      <description><![CDATA[{desc}]]></description>
    </item>""")

    rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>TubeLM High-Signal Intelligence</title>
    <link>{base_url}</link>
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

    # 1. Purge older than 14 days
    purge_old_digests_and_audio(summaries_dir, audio_dir, max_age_days=14)

    # 2. Map channels
    sources = load_sources(sources_file)
    sources_map = {s["name"]: s for s in sources}
    for s in sources:
        sources_map[paths.safe_channel_name(s["name"])] = s

    # 3. Discover dates and group into Current Week and Previous Week
    files = [f for f in summaries_dir.iterdir() if f.is_file() and f.name.endswith(".html")]
    date_map: dict[datetime.date, list[Path]] = {}
    for f in files:
        m = re.match(r"^(\d{4}-\d{2}-\d{2})_", f.name)
        if m:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            date_map.setdefault(d, []).append(f)

    sorted_dates = sorted(date_map.keys(), reverse=True)
    if not sorted_dates:
        sorted_dates = [datetime.now(timezone.utc).date()]
        date_map[sorted_dates[0]] = []

    latest_date = sorted_dates[0]
    # Current batch: all runs within 4 days of latest
    current_dates = [d for d in sorted_dates if (latest_date - d).days <= 4]
    # Previous batch: runs between 5 and 14 days
    prev_dates = [d for d in sorted_dates if 5 <= (latest_date - d).days <= 14]

    logger.info("Partitioning into Current Week (%s) and Previous Week (%s)...", current_dates, prev_dates)

    weeks_data: dict[str, Any] = {}

    for week_key, dates_list in [("current", current_dates), ("prev", prev_dates)]:
        if not dates_list:
            weeks_data[week_key] = {"run_date": "None", "channels": [], "top20": {"items": []}}
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
                        top20_data = parse_top20_digest(f)
                else:
                    ch_data = parse_channel_digest(f, sources_map, audio_dir, d_str)
                    if ch_data and ch_data["name"] not in seen_channels:
                        seen_channels.add(ch_data["name"])
                        if ch_data.get("audio_path") and Path(ch_data["audio_path"]).exists():
                            src_audio = Path(ch_data["audio_path"])
                            dest_audio = site_audio_dir / src_audio.name
                            if compress_audio:
                                if not dest_audio.exists() or dest_audio.stat().st_size > 15 * 1024 * 1024:
                                    optimize_audio_for_web(src_audio, dest_audio)
                            else:
                                # Retain original audio quality without lossy compression
                                if not dest_audio.exists() or dest_audio.stat().st_size != src_audio.stat().st_size:
                                    shutil.copy(src_audio, dest_audio)
                                    logger.info("Retained original uncompressed audio: %s (%d KB)",
                                                dest_audio.name, src_audio.stat().st_size // 1024)
                        channels.append(ch_data)

        channels.sort(key=lambda c: c["name"])

        weeks_data[week_key] = {
            "run_date": run_date_label,
            "channels": channels,
            "top20": top20_data,
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
    rendered_html = template.render(
        site_data_json=json.dumps(site_data, ensure_ascii=False),
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

    return index_path


def deploy_to_gh_pages(site_dir: Path, repo_url: str = "https://github.com/vkr1729/TubeLM.git") -> bool:
    """Deploy site_dir contents to orphan gh-pages branch with force push."""
    logger.info("Deploying Web Reader to GitHub Pages (gh-pages branch)...")

    if not shutil.which("git"):
        logger.error("Git is not installed or not in PATH; skipping gh-pages deploy.")
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
