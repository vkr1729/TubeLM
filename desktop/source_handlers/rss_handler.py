import calendar
import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import feedparser

from source_handlers import BaseSourceHandler, SourceItem

if TYPE_CHECKING:
    from notebooklm import NotebookLMClient

logger = logging.getLogger(__name__)


def _parse_feed_datetime(entry) -> datetime:
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            ts = calendar.timegm(entry.published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            ts = calendar.timegm(entry.updated_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        logger.debug("Could not parse datetime for entry; defaulting to epoch.", exc_info=True)
    return datetime.fromtimestamp(0, tz=timezone.utc)


class GenericRSSHandler(BaseSourceHandler):
    def __init__(self, name: str, url: str, force_text_extraction: bool = False, max_items: int = 15):
        self._name = name
        self._url = url
        self._force_text_extraction = force_text_extraction
        self._max_items = max_items

    @property
    def source_type(self) -> str:
        return "rss"

    @property
    def name(self) -> str:
        return self._name

    @property
    def url(self) -> str:
        return self._url

    def state_key(self) -> str:
        hash_digest = hashlib.sha256(self._url.encode()).hexdigest()[:12]
        return f"rss:{hash_digest}"

    def discover(self, since_dt: datetime, seen_urls: set[str] | None = None) -> list[SourceItem] | None:
        try:
            feed = feedparser.parse(self._url)
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", self._url, exc)
            return None

        if feed.bozo and not feed.entries:
            logger.warning("Feed %s is malformed: %s", self._url, feed.bozo_exception)
            return None

        items = []
        for entry in feed.entries:
            pub_dt = _parse_feed_datetime(entry)
            if pub_dt <= since_dt:
                continue

            title = getattr(entry, "title", "Untitled")
            link = getattr(entry, "link", "")
            description = getattr(entry, "summary", "") or getattr(entry, "description", "")

            items.append(SourceItem(
                title=title,
                url=link,
                published=pub_dt.strftime("%Y-%m-%d"),
                description=description,
            ))

        items.sort(key=lambda x: x.published, reverse=True)
        if len(items) > self._max_items:
            items = items[:self._max_items]

        return items

    async def ingest(
        self,
        client: "NotebookLMClient",
        notebook_id: str,
        items: list[SourceItem],
    ) -> list[str]:
        from source_handlers.extractor import extract_clean_text, truncate_for_notebooklm
        source_ids = []

        for item in items:
            if self._force_text_extraction:
                if not item.extracted_text:
                    try:
                        item.extracted_text = extract_clean_text(url=item.url)
                    except Exception as exc:
                        logger.warning("Text extraction failed for %r: %s", item.title, exc)
                if item.extracted_text:
                    try:
                        source = await client.sources.add_text(
                            notebook_id, item.title, truncate_for_notebooklm(item.extracted_text)
                        )
                        source_ids.append(source.id)
                        item.source_id = source.id
                        logger.info("Added text source for %r", item.title)
                        continue
                    except Exception as exc:
                        logger.warning("Failed to add_text for %r: %s", item.title, exc)
            else:
                try:
                    source = await client.sources.add_url(notebook_id, item.url, wait=False)
                    source_ids.append(source.id)
                    item.source_id = source.id
                    logger.info("Added URL source for %r", item.title)
                    continue
                except Exception as exc:
                    logger.warning("add_url failed for %r (%s), falling back to add_text", item.title, exc)

            # Fallback: extract text and use add_text
            if not item.extracted_text:
                try:
                    item.extracted_text = extract_clean_text(url=item.url)
                except Exception as exc:
                    logger.warning("Fallback extraction failed for %r: %s", item.title, exc)
                    continue
            if item.extracted_text:
                try:
                    source = await client.sources.add_text(
                        notebook_id, item.title, truncate_for_notebooklm(item.extracted_text)
                    )
                    source_ids.append(source.id)
                    item.source_id = source.id
                    logger.info("Added text source (fallback) for %r", item.title)
                except Exception as exc:
                    logger.warning("add_text fallback also failed for %r: %s", item.title, exc)

        return source_ids
