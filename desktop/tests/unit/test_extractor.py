from unittest.mock import patch, MagicMock
from source_handlers.extractor import (
    extract_article_text,
    extract_metadata,
    extract_with_beautifulsoup,
    extract_clean_text,
)


class TestTrafilaturaExtraction:
    def test_strips_navigation_elements(self, article_html):
        text = extract_article_text("", fallback_html=article_html)
        assert len(text) > 500, f"Expected >500 chars, got {len(text)}"
        assert "Home" not in text or text.count("Home") < 3, "Nav links should be stripped"
        assert "Accept" not in text, "Cookie banner should be stripped"
        assert "console.log" not in text, "Script content should be stripped"

    def test_preserves_article_body(self, article_html):
        text = extract_article_text("", fallback_html=article_html)
        assert "coroutine" in text.lower() or "asyncio" in text.lower(), "Core article content should be preserved"
        assert "event loop" in text.lower(), "Technical content should be preserved"

    def test_returns_empty_on_empty_html(self):
        result = extract_article_text("", fallback_html="")
        assert result == ""

    def test_includes_tables_when_present(self, article_html):
        text = extract_article_text("", fallback_html=article_html)
        assert "asyncio" in text.lower() or "threading" in text.lower() or "multiprocessing" in text.lower(), "Table content should be included"


class TestBeautifulSoupFallback:
    def test_extracts_from_article_tag(self, article_html):
        with patch("source_handlers.extractor.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = article_html
            mock_get.return_value = mock_resp
            text = extract_with_beautifulsoup("http://example.com")
        assert "coroutine" in text.lower() or "asyncio" in text.lower()
        assert "console.log" not in text

    def test_removes_script_and_style(self, article_html):
        with patch("source_handlers.extractor.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = article_html
            mock_get.return_value = mock_resp
            text = extract_with_beautifulsoup("http://example.com")
        assert "console.log" not in text
        assert "Analytics loaded" not in text

    def test_falls_back_to_body(self, minimal_html):
        with patch("source_handlers.extractor.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.text = minimal_html
            mock_get.return_value = mock_resp
            text = extract_with_beautifulsoup("http://example.com")
        assert "Short page." in text


class TestCombinedExtraction:
    def test_trafilatura_preferred(self, article_html):
        text = extract_clean_text(fallback_html=article_html)
        assert len(text) > 100, "Trafilatura should return substantial content"

    def test_bs4_fallback_on_short_trafilatura(self, js_heavy_html):
        with patch("source_handlers.extractor.extract_article_text", return_value="short") as mock_tra, \
             patch("source_handlers.extractor.extract_with_beautifulsoup") as mock_bs4:
            mock_bs4.return_value = "Fallback content from BS4 with more than one hundred characters to pass the length check."
            text = extract_clean_text(url="http://example.com", fallback_html=js_heavy_html)
            assert mock_bs4.called, "BS4 fallback should be called when trafilatura returns short content"
