import json
from pathlib import Path
from sources_loader import load_sources


class TestValidation:
    def test_invalid_entries_skipped(self, tmp_path):
        data = [
            {"name": "Good", "type": "youtube", "channel_id": "UCpcvPcHJVOkO9Qp79BOagTg"},
            {"bad_entry": True},
            {"name": "Also Good", "type": "webpage", "url": "https://example.com"},
        ]
        f = tmp_path / "mixed.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert len(result) == 2


class TestNewFormat:
    def test_rejects_non_array_document(self, tmp_path):
        f = tmp_path / "sources.json"
        f.write_text(json.dumps({"name": "Not a list"}))
        assert load_sources(f) == []

    def test_skips_unsupported_source_type(self, tmp_path):
        f = tmp_path / "sources.json"
        f.write_text(json.dumps([{"name": "Bad", "type": "database", "url": "https://example.com"}]))
        assert load_sources(f) == []

    def test_all_types_load(self, tmp_path):
        data = [
            {"name": "YT", "type": "youtube", "channel_id": "UCpcvPcHJVOkO9Qp79BOagTg"},
            {"name": "RSS", "type": "rss", "url": "https://example.com/feed.xml"},
            {"name": "Web", "type": "webpage", "url": "https://example.com/article"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert len(result) == 3
        types = {e["type"] for e in result}
        assert types == {"youtube", "rss", "webpage"}

    def test_type_specific_defaults(self, tmp_path):
        data = [
            {"name": "Minimal RSS", "type": "rss", "url": "https://example.com/feed"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert len(result) == 1
        assert result[0]["type"] == "rss"
        assert result[0]["name"] == "Minimal RSS"


class TestCategoryField:
    def test_category_preserved(self, tmp_path):
        data = [
            {"name": "Health Channel", "type": "youtube", "channel_id": "UC123", "category": "health"},
            {"name": "Tech RSS", "type": "rss", "url": "https://example.com/feed", "category": "tech"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert len(result) == 2
        assert result[0]["category"] == "health"
        assert result[1]["category"] == "tech"

    def test_missing_category_has_no_default(self, tmp_path):
        """sources_loader passes through raw dicts; factory sets the default."""
        data = [
            {"name": "No Cat", "type": "youtube", "channel_id": "UC456"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert len(result) == 1
        assert "category" not in result[0]  # Factory handles the default
