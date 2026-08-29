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
YOUTUBE_CHANNELS_API_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_PLAYLIST_ITEMS_API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
MIN_VIDEO_DURATION_SECONDS = 180
MAX_API_PLAYLIST_PAGES = 5
SHORTS_KEYWORDS = re.compile(r"#shorts?", re.IGNORECASE)
FEED_HEADERS = {
    "User-Agent": "TubeLM/2.0 (+https://github.com/vkr1729/TubeLM)",
    "Accept": "application/atom+xml, application/xml;q=0.9, text/xml;q=0.8",
}


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
    def __init__(self, name: str, channel_id: str, youtube_api_key: str = "", category: str = "tech"):
        self._name = name
        self._channel_id = channel_id
        self._api_key = youtube_api_key
        self._category = category

    @property
    def source_type(self) -> str:
        return "youtube"

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

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
        feed = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.get(url, headers=FEED_HEADERS, timeout=15)
                if response.status_code == 404:
                    logger.warning(
                        "YouTube RSS returned HTTP 404 for valid-or-unknown channel %s; "
                        "trying the official YouTube API fallback.",
                        self._channel_id,
                    )
                    return self._fetch_channel_videos_api(since_dt)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if not feed.bozo or feed.entries:
                    break
                logger.warning(
                    "RSS feed for channel %s appears malformed (bozo=%s). Attempt %d/%d.",
                    self._channel_id, feed.bozo_exception, attempt, max_attempts,
                )
            except Exception as exc:
                logger.warning(
                    "YouTube RSS request failed for channel %s on attempt %d/%d (%s).",
                    self._channel_id, attempt, max_attempts, type(exc).__name__,
                )
            if attempt < max_attempts:
                time.sleep(2 * attempt)

        if feed is None or (feed.bozo and not feed.entries):
            logger.warning(
                "YouTube RSS for channel %s remains unavailable after %d attempts; "
                "trying the official YouTube API fallback.",
                self._channel_id,
                max_attempts,
            )
            return self._fetch_channel_videos_api(since_dt)

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

    def _fetch_channel_videos_api(self, since_dt: datetime) -> list[dict] | None:
        """Discover uploads through the official API when the public RSS feed fails.

        ``None`` means discovery could not be completed and the caller must not
        advance this source's state. An empty list is returned only after the API
        successfully confirms that no uploads are newer than ``since_dt``.
        """
        if not self._api_key:
            logger.error(
                "Cannot fall back to the YouTube API for channel %s because "
                "YOUTUBE_API_KEY is not configured; preserving its checkpoint.",
                self._channel_id,
            )
            return None

        try:
            channel_response = requests.get(
                YOUTUBE_CHANNELS_API_URL,
                params={
                    "part": "contentDetails",
                    "id": self._channel_id,
                    "key": self._api_key,
                    "maxResults": 1,
                },
                timeout=15,
            )
            channel_response.raise_for_status()
            channel_items = channel_response.json().get("items", [])
            if not channel_items:
                logger.error(
                    "YouTube API did not recognize channel %s; preserving its checkpoint.",
                    self._channel_id,
                )
                return None

            uploads_id = (
                channel_items[0]
                .get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads")
            )
            if not uploads_id:
                logger.error(
                    "YouTube API returned no uploads playlist for channel %s; "
                    "preserving its checkpoint.",
                    self._channel_id,
                )
                return None

            videos: list[dict] = []
            page_token: str | None = None
            for _page_number in range(MAX_API_PLAYLIST_PAGES):
                params = {
                    "part": "snippet,contentDetails",
                    "playlistId": uploads_id,
                    "key": self._api_key,
                    "maxResults": 50,
                }
                if page_token:
                    params["pageToken"] = page_token

                playlist_response = requests.get(
                    YOUTUBE_PLAYLIST_ITEMS_API_URL,
                    params=params,
                    timeout=15,
                )
                playlist_response.raise_for_status()
                payload = playlist_response.json()
                reached_checkpoint = False

                for item in payload.get("items", []):
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    published_raw = (
                        content_details.get("videoPublishedAt")
                        or snippet.get("publishedAt")
                    )
                    if not published_raw:
                        continue
                    try:
                        published_dt = datetime.fromisoformat(
                            published_raw.replace("Z", "+00:00")
                        ).astimezone(timezone.utc)
                    except (TypeError, ValueError):
                        logger.debug(
                            "Ignoring YouTube API item with invalid publishedAt for channel %s.",
                            self._channel_id,
                        )
                        continue

                    if published_dt <= since_dt:
                        reached_checkpoint = True
                        continue

                    video_id = content_details.get("videoId") or (
                        snippet.get("resourceId", {}).get("videoId")
                    )
                    if not video_id:
                        continue
                    videos.append({
                        "title": snippet.get("title", ""),
                        "url": YOUTUBE_WATCH_URL.format(video_id=video_id),
                        "video_id": video_id,
                        "published": published_dt.strftime("%Y-%m-%d"),
                        "description": snippet.get("description", ""),
                    })

                page_token = payload.get("nextPageToken")
                if reached_checkpoint or not page_token:
                    break

            logger.info(
                "YouTube API fallback found %d upload(s) after the checkpoint for %s.",
                len(videos),
                self._channel_id,
            )
            return videos
        except Exception as exc:
            # Requests exceptions include the full URL, so do not log ``exc``:
            # the URL contains the configured API key.
            logger.error(
                "YouTube API fallback failed for channel %s (%s); preserving its checkpoint.",
                self._channel_id,
                type(exc).__name__,
            )
            return None

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
            except Exception as exc:
                # Do not log the exception URL: requests includes query params,
                # which would expose the configured YouTube API key.
                logger.warning(
                    "YouTube API duration fetch failed for batch %d-%d (%s) — keeping those videos.",
                    i, i + len(batch), type(exc).__name__,
                )
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
