import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from source_handlers.webpage_handler import WebpageScraperHandler
from source_handlers import SourceItem


class TestWebpageDiscovery:
    def test_single_page_returns_one_item(self):
        handler = WebpageScraperHandler("My Article", "https://example.com/article", is_index_page=False)
        items = handler.discover(datetime.now(timezone.utc))
        assert items is not None
        assert len(items) == 1
        assert items[0].url == "https://example.com/article"
        assert items[0].title == "My Article"

    def test_index_page_extracts_links(self, index_html):
        handler = WebpageScraperHandler("Essays", "https://paulgraham.com/articles.html",
                                        is_index_page=True, link_selector="td a[href]", max_items=5)
        with patch("source_handlers.webpage_handler.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = index_html
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp
            items = handler.discover(datetime.now(timezone.utc))
        assert items is not None
        assert len(items) > 0
        for item in items:
            assert item.url.startswith("http")

    def test_index_page_relative_url_resolution(self):
        handler = WebpageScraperHandler("Index", "https://example.com/index.html",
                                        is_index_page=True, link_selector="a[href]")
        html = '<html><body><a href="/article1">Article 1</a></body></html>'
        with patch("source_handlers.webpage_handler.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp
            items = handler.discover(datetime.now(timezone.utc))
        assert items is not None
        assert len(items) == 1
        assert items[0].url == "https://example.com/article1"

    def test_respects_max_items_on_index(self, index_html):
        handler = WebpageScraperHandler("Essays", "https://paulgraham.com/articles.html",
                                        is_index_page=True, link_selector="td a[href]", max_items=2)
        with patch("source_handlers.webpage_handler.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = index_html
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp
            items = handler.discover(datetime.now(timezone.utc))
        assert items is not None
        assert len(items) <= 2

    def test_deduplicates_duplicate_hrefs(self):
        handler = WebpageScraperHandler("DupTest", "https://example.com/index.html",
                                        is_index_page=True, link_selector="a[href]", max_items=10)
        html = '<html><body><a href="/same">Link 1</a><a href="/same">Link 2 Same</a><a href="/different">Link 3</a></body></html>'
        with patch("source_handlers.webpage_handler.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp
            items = handler.discover(datetime.now(timezone.utc))
        assert items is not None
        urls = [i.url for i in items]
        assert len(urls) == len(set(urls)), "No duplicate URLs"

    def test_seen_urls_filtered_out_on_index(self):
        handler = WebpageScraperHandler("SeenTest", "https://example.com/index.html",
                                        is_index_page=True, link_selector="a[href]", max_items=10)
        html = '<html><body><a href="/a">Link A</a><a href="/b">Link B</a><a href="/c">Link C</a></body></html>'
        with patch("source_handlers.webpage_handler.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = html
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp
            items = handler.discover(datetime.now(timezone.utc),
                                     seen_urls={"https://example.com/a", "https://example.com/b"})
        assert items is not None
        discovered_urls = {i.url for i in items}
        assert "https://example.com/a" not in discovered_urls, "Previously seen URL should be excluded"
        assert "https://example.com/b" not in discovered_urls, "Previously seen URL should be excluded"
        assert len(items) <= 1


class TestWebpageIngestion:
    @pytest.mark.asyncio
    async def test_always_uses_add_text(self):
        client = AsyncMock()
        client.sources.add_text.return_value = MagicMock(id="src_text_001")
        handler = WebpageScraperHandler("Page", "https://example.com/article", is_index_page=False)
        item = SourceItem(title="Article", url="https://example.com/article", published="2025-01-01",
                          extracted_text="This is the full article text with enough content for a meaningful extraction test.")
        items = [item]
        ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        client.sources.add_text.assert_called_once()
        client.sources.add_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_items_with_empty_extraction(self):
        client = AsyncMock()
        handler = WebpageScraperHandler("Page", "https://example.com/article", is_index_page=False)
        item = SourceItem(title="Article", url="https://example.com/article", published="2025-01-01",
                          extracted_text="")  # No text
        items = [item]
        with patch("source_handlers.extractor.extract_clean_text", return_value=""):
            ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 0
        client.sources.add_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_truncates_long_text_before_add_text(self):
        client = AsyncMock()
        client.sources.add_text.return_value = MagicMock(id="src_text_001")
        handler = WebpageScraperHandler("Page", "https://example.com/article", is_index_page=False)
        long_text = "x" * 600_000
        item = SourceItem(title="Article", url="https://example.com/article", published="2025-01-01",
                          extracted_text=long_text)
        items = [item]
        ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        call_args = client.sources.add_text.call_args
        text_passed = call_args[0][2]
        assert len(text_passed) <= 500_000, f"Expected <=500000 chars, got {len(text_passed)}"