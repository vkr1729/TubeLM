from source_handlers.factory import create_handler
from source_handlers.youtube_handler import YouTubeHandler
from source_handlers.rss_handler import GenericRSSHandler
from source_handlers.webpage_handler import WebpageScraperHandler


class TestFactory:
    def test_creates_youtube_handler(self):
        config = {"name": "Test YT", "type": "youtube", "channel_id": "UCtest123"}
        handler = create_handler(config)
        assert isinstance(handler, YouTubeHandler)
        assert handler.name == "Test YT"

    def test_creates_rss_handler(self):
        config = {"name": "Test RSS", "type": "rss", "url": "https://example.com/feed.xml"}
        handler = create_handler(config)
        assert isinstance(handler, GenericRSSHandler)
        assert handler.name == "Test RSS"

    def test_creates_webpage_handler(self):
        config = {"name": "Test Web", "type": "webpage", "url": "https://example.com/article"}
        handler = create_handler(config)
        assert isinstance(handler, WebpageScraperHandler)
        assert handler.name == "Test Web"

    def test_unknown_type_raises(self):
        import pytest
        config = {"name": "Bad", "type": "unknown", "url": "https://example.com"}
        with pytest.raises(ValueError, match="Unknown source type"):
            create_handler(config)
