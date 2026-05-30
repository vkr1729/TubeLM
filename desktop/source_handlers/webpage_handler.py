import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from source_handlers import BaseSourceHandler, SourceItem

if TYPE_CHECKING:
    from notebooklm import NotebookLMClient

logger = logging.getLogger(__name__)

USER_AGENT = "TubeLM/2.0"


class WebpageScraperHandler(BaseSourceHandler):
    def __init__(self, name: str, url: str, is_index_page: bool = False,
                 link_selector: str = "", max_items: int = 10):
        self._name = name
        self._url = url
        self._is_index_page = is_index_page
        self._link_selector = link_selector
        self._max_items = max_items

    @property
    def source_type(self) -> str:
        return "webpage"

    @property
    def name(self) -> str:
        return self._name

    @property
    def url(self) -> str:
        return self._url

    def state_key(self) -> str:
        hash_digest = hashlib.sha256(self._url.encode()).hexdigest()[:12]
        return f"webpage:{hash_digest}"

    def discover(self, since_dt: datetime, seen_urls: set[str] | None = None) -> list[SourceItem] | None:
        if self._is_index_page:
            return self._discover_index_links(seen_urls or set())
        else:
            return self._discover_single_page()

    def _discover_single_page(self) -> list[SourceItem]:
        title = self._name
        return [SourceItem(
            title=title,
            url=self._url,
            published=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            description="",
        )]

    def _discover_index_links(self, seen_urls: set[str]) -> list[SourceItem] | None:
        try:
            resp = requests.get(self._url, timeout=15, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            logger.warning("Failed to fetch index page %s: %s", self._url, exc)
            return None

        soup = BeautifulSoup(html, "html.parser")
        links = []

        if self._link_selector:
            elements = soup.select(self._link_selector)
        else:
            elements = soup.find_all("a", href=True)

        seen = set()
        base_url = self._url

        for el in elements:
            href = el.get("href", "")
            if not href:
                continue
            absolute = urljoin(base_url, href)
            if absolute in seen or absolute in seen_urls:
                continue
            if not absolute.startswith(("http://", "https://")):
                continue
            seen.add(absolute)
            text = el.get_text(strip=True) or absolute
            links.append((text, absolute))

        if not links:
            logger.warning("No links found on index page %s", self._url)
            return []

        if len(links) > self._max_items:
            links = links[:self._max_items]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        items = []
        for title, link_url in links:
            items.append(SourceItem(
                title=title,
                url=link_url,
                published=today,
                description="",
            ))
        return items

    async def ingest(
        self,
        client: "NotebookLMClient",
        notebook_id: str,
        items: list[SourceItem],
    ) -> list[str]:
        source_ids = []

        for item in items:
            text = item.extracted_text
            if not text:
                from source_handlers.extractor import extract_clean_text
                try:
                    text = extract_clean_text(url=item.url, fallback_html="")
                except Exception as exc:
                    logger.warning("Extraction failed for %s: %s", item.url, exc)
                    continue

            if not text or len(text.strip()) < 50:
                logger.warning("Skipping %s — extracted text too short (%d chars)", item.url, len(text) if text else 0)
                continue

            item.extracted_text = text
            from source_handlers.extractor import truncate_for_notebooklm
            truncated = truncate_for_notebooklm(text)
            try:
                source = await client.sources.add_text(notebook_id, item.title, truncated)
                source_ids.append(source.id)
                item.source_id = source.id
                logger.info("Added text source for %r", item.title)
            except Exception as exc:
                logger.warning("Failed to add_text for %r: %s", item.title, exc)

        return source_ids
