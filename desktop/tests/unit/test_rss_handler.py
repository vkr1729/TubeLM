import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

from source_handlers.rss_handler import GenericRSSHandler
from source_handlers import SourceItem


class TestRSSDiscovery:
    def test_discovers_entries_after_date(self, rss_techblog_xml):
        handler = GenericRSSHandler("TechBlog", "https://example.com/feed.xml")
        since_dt = datetime(2025, 5, 20, tzinfo=timezone.utc)

        with patch("source_handlers.rss_handler.feedparser.parse") as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.entries = [
                MagicMock(
                    title="Async Python",
                    link="https://example.com/async",
                    published_parsed=(2025, 5, 22, 10, 0, 0, 3, 142, 0),
                    summary="Async post",
                    description="",
                ),
                MagicMock(
                    title="Docker 2025",
                    link="https://example.com/docker",
                    published_parsed=(2025, 5, 21, 14, 0, 0, 2, 141, 0),
                    summary="Docker post",
                    description="",
                ),
                MagicMock(
                    title="Old Post",
                    link="https://example.com/old",
                    published_parsed=(2025, 5, 15, 10, 0, 0, 3, 135, 0),
                    summary="Old post",
                    description="",
                ),
            ]
            mock_parse.return_value = mock_feed
            items = handler.discover(since_dt)

        assert items is not None
        assert len(items) == 2
        titles = {i.title for i in items}
        assert "Async Python" in titles
        assert "Old Post" not in titles

    def test_returns_none_on_feed_failure(self):
        handler = GenericRSSHandler("BadFeed", "https://example.com/bad.xml")
        with patch("source_handlers.rss_handler.feedparser.parse", side_effect=Exception("Connection refused")):
            items = handler.discover(datetime.now(timezone.utc))
        assert items is None

    def test_respects_max_items(self):
        handler = GenericRSSHandler("Many", "https://example.com/feed.xml", max_items=2)
        since_dt = datetime(2025, 5, 1, tzinfo=timezone.utc)
        with patch("source_handlers.rss_handler.feedparser.parse") as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.entries = [
                MagicMock(title=f"Post {i}", link=f"https://example.com/{i}",
                          published_parsed=(2025, 5, 10 + i, 10, 0, 0, 0, 0, 0),
                          summary="", description="")
                for i in range(10)
            ]
            mock_parse.return_value = mock_feed
            items = handler.discover(since_dt)
        assert items is not None
        assert len(items) <= 2

    def test_parses_atom_format(self, rss_atom_xml):
        handler = GenericRSSHandler("AtomFeed", "https://example.com/atom.xml")
        since_dt = datetime(2025, 5, 1, tzinfo=timezone.utc)

        with patch("source_handlers.rss_handler.feedparser.parse") as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.entries = [
                MagicMock(
                    title="Building tools with LLMs",
                    link="https://simonwillison.net/2025/May/22/llm-tools/",
                    published_parsed=(2025, 5, 22, 12, 0, 0, 3, 142, 0),
                    summary="Thoughts on building useful tools with LLMs.",
                    description="",
                ),
                MagicMock(
                    title="Datasette 2.0",
                    link="https://simonwillison.net/2025/May/20/datasette-2/",
                    published_parsed=(2025, 5, 20, 15, 0, 0, 1, 140, 0),
                    summary="Announcing Datasette 2.0.",
                    description="",
                ),
            ]
            mock_parse.return_value = mock_feed
            items = handler.discover(since_dt)

        assert items is not None
        assert len(items) == 2

    def test_extracts_entry_url_and_title(self):
        handler = GenericRSSHandler("Test", "https://example.com/feed.xml")
        since_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with patch("source_handlers.rss_handler.feedparser.parse") as mock_parse:
            mock_feed = MagicMock()
            mock_feed.bozo = False
            mock_feed.entries = [
                MagicMock(
                    title="Test Post",
                    link="https://example.com/test",
                    published_parsed=(2025, 5, 15, 10, 0, 0, 3, 135, 0),
                    summary="Test summary",
                    description="",
                ),
            ]
            mock_parse.return_value = mock_feed
            items = handler.discover(since_dt)
        assert items is not None
        assert len(items) == 1
        assert items[0].title == "Test Post"
        assert items[0].url == "https://example.com/test"
        assert items[0].published == "2025-05-15"


class TestRSSIngestion:
    @pytest.mark.asyncio
    async def test_uses_add_url_by_default(self):
        client = AsyncMock()
        client.sources.add_url.return_value = MagicMock(id="src_url_001")
        handler = GenericRSSHandler("Blog", "https://example.com/feed.xml")
        items = [SourceItem(title="Post", url="https://example.com/post", published="2025-01-01")]
        ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        client.sources.add_url.assert_called_once()
        client.sources.add_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_add_text_when_forced(self):
        client = AsyncMock()
        client.sources.add_text.return_value = MagicMock(id="src_text_001")
        handler = GenericRSSHandler("Blog", "https://example.com/feed.xml", force_text_extraction=True)
        item = SourceItem(title="Post", url="https://example.com/post", published="2025-01-01",
                          extracted_text="")  # Empty — must be extracted on-demand
        items = [item]
        with patch("source_handlers.extractor.extract_clean_text",
                   return_value="Extracted content from URL"):
            ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        client.sources.add_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_truncates_long_text_before_add_text(self):
        client = AsyncMock()
        client.sources.add_text.return_value = MagicMock(id="src_text_001")
        handler = GenericRSSHandler("Blog", "https://example.com/feed.xml", force_text_extraction=True)
        item = SourceItem(title="Post", url="https://example.com/post", published="2025-01-01",
                          extracted_text="")
        items = [item]
        long_extracted = "y" * 600_000
        with patch("source_handlers.extractor.extract_clean_text", return_value=long_extracted):
            ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        call_args = client.sources.add_text.call_args
        text_passed = call_args[0][2]
        assert len(text_passed) <= 500_000, f"Expected <=500000 chars, got {len(text_passed)}"
        client.sources.add_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_text_on_source_add_error(self):
        client = AsyncMock()
        client.sources.add_url.side_effect = Exception("SourceAddError")
        client.sources.add_text.return_value = MagicMock(id="src_text_001")
        handler = GenericRSSHandler("Blog", "https://example.com/feed.xml")
        item = SourceItem(title="Post", url="https://example.com/post", published="2025-01-01",
                          extracted_text="")  # Empty — must be extracted on-demand
        items = [item]
        with patch("source_handlers.extractor.extract_clean_text",
                   return_value="Fallback extracted content"):
            ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        client.sources.add_text.assert_called_once()
