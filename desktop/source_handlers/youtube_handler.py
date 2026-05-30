import calendar
import logging
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import feedparser
import requests

from source_handlers import BaseSourceHandler, SourceItem

if TYPE_CHECKING:
    from notebooklm import NotebookLMClient

logger = logging.getLogger(__name__)

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
MIN_VIDEO_DURATION_SECONDS = 180
SHORTS_KEYWORDS = re.compile(r"#shorts?", re.IGNORECASE)


def _parse_rss_datetime(entry) -> datetime:
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts = calendar.timegm(entry.published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        logger.debug("Could not parse published_parsed for entry; defaulting to epoch.", exc_info=True)
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _parse_iso8601_duration(duration: str) -> int:
    pattern = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", re.IGNORECASE)
    match = pattern.match(duration or "")
    if not match:
        return 0
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _extract_video_id(entry) -> str | None:
    vid_id = getattr(entry, "yt_videoid", None)
    if vid_id:
        return vid_id
    link = getattr(entry, "link", "")
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", link)
    return match.group(1) if match else None


class YouTubeHandler(BaseSourceHandler):
    def __init__(self, name: str, channel_id: str, youtube_api_key: str = ""):
        self._name = name
        self._channel_id = channel_id
        self._api_key = youtube_api_key

    @property
    def source_type(self) -> str:
        return "youtube"

    @property
    def name(self) -> str:
        return self._name

    @property
    def channel_id(self) -> str:
        return self._channel_id

    def state_key(self) -> str:
        return f"youtube:{self._channel_id}"

    def discover(self, since_dt: datetime, seen_urls: set[str] | None = None) -> list[SourceItem] | None:
        raw_videos = self._fetch_channel_videos(since_dt)
        if raw_videos is None:
            return None
        if not raw_videos:
            return []

        filtered = self._filter_by_keyword(raw_videos)
        if not filtered:
            return []

        filtered = self._filter_by_title_heuristics(filtered)
        if not filtered:
            return []

        if self._api_key:
            filtered = self._filter_by_duration(filtered)

        items = []
        for v in filtered:
            items.append(SourceItem(
                title=v["title"],
                url=v["url"],
                published=v["published"],
                description=v.get("description", ""),
            ))
        return items

    def _fetch_channel_videos(self, since_dt: datetime) -> list[dict] | None:
        url = YOUTUBE_RSS_URL.format(channel_id=self._channel_id)
        max_attempts = 3
        attempt = 0
        feed = None

        while attempt < max_attempts:
            attempt += 1
            try:
                feed = feedparser.parse(url)
                status_code = feed.get("status")
                if status_code in (403, 404):
                    logger.error(
                        "RSS feed for channel %s returned hard error HTTP %s.",
                        self._channel_id, status_code,
                    )
                    break
                if not feed.bozo or feed.entries:
                    break
                logger.warning(
                    "RSS feed for channel %s appears malformed (bozo=%s). Attempt %d/%d.",
                    self._channel_id, feed.bozo_exception, attempt, max_attempts,
                )
            except Exception as exc:
                logger.warning(
                    "feedparser.parse() raised for channel %s on attempt %d/%d: %s",
                    self._channel_id, attempt, max_attempts, exc, exc_info=True,
                )
            if attempt < max_attempts:
                time.sleep(5 * attempt)

        if feed is None or (feed.bozo and not feed.entries):
            logger.error("RSS feed for channel %s remains malformed after %d attempts.", self._channel_id, max_attempts)
            return None

        videos = []
        for entry in feed.entries:
            pub_dt = _parse_rss_datetime(entry)
            if pub_dt <= since_dt:
                continue
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

    def _filter_by_keyword(self, videos: list[dict]) -> list[dict]:
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

    def _filter_by_title_heuristics(self, videos: list[dict]) -> list[dict]:
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
            logger.info("Filtered %d video(s) by title heuristic.", removed)
        return filtered

    def _filter_by_duration(self, videos: list[dict]) -> list[dict]:
        if not videos:
            return videos
        video_map = {v["video_id"]: v for v in videos}
        all_ids = list(video_map.keys())
        short_ids: set[str] = set()
        batch_size = 50
        for i in range(0, len(all_ids), batch_size):
            batch = all_ids[i : i + batch_size]
            try:
                resp = requests.get(
                    YOUTUBE_API_URL,
                    params={"id": ",".join(batch), "part": "contentDetails", "key": self._api_key},
                    timeout=15,
                )
                resp.raise_for_status()
                items = resp.json().get("items", [])
            except Exception:
                logger.warning("YouTube API duration fetch failed for batch %d-%d — keeping those videos.", i, i + len(batch), exc_info=True)
                continue
            for item in items:
                vid_id = item.get("id", "")
                duration_str = item.get("contentDetails", {}).get("duration", "")
                secs = _parse_iso8601_duration(duration_str)
                if secs < MIN_VIDEO_DURATION_SECONDS:
                    short_ids.add(vid_id)
                    logger.debug("Filtered short video (%ds < %ds): %s", secs, MIN_VIDEO_DURATION_SECONDS, vid_id)
        filtered = [v for v in videos if v["video_id"] not in short_ids]
        if short_ids:
            logger.info("Filtered %d video(s) under %ds by YouTube API duration.", len(short_ids), MIN_VIDEO_DURATION_SECONDS)
        return filtered

    async def ingest(
        self,
        client: "NotebookLMClient",
        notebook_id: str,
        items: list[SourceItem],
    ) -> list[str]:
        source_ids = []
        for item in items:
            try:
                source = await client.sources.add_url(notebook_id, item.url, wait=False)
                source_ids.append(source.id)
                item.source_id = source.id
                logger.info("Queued YouTube source: %s (%s)", item.url, source.id)
            except Exception as exc:
                logger.warning("Failed to add YouTube source %s — skipping: %s", item.url, exc)
        return source_ids
