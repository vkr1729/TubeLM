import json
from pathlib import Path
from sources_loader import load_sources


class TestBackwardCompat:
    def test_legacy_channels_json_auto_typed(self, tmp_path):
        legacy = [
            {"name": "Test Channel", "channel_id": "UCpcvPcHJVOkO9Qp79BOagTg"},
            {"name": "Another", "channel_id": "UC2D2CMWXMOVW7xgiW1n3LIg"},
        ]
        f = tmp_path / "channels.json"
        f.write_text(json.dumps(legacy))
        result = load_sources(f)
        assert len(result) == 2
        for entry in result:
            assert entry["type"] == "youtube"

    def test_mixed_format_loads(self, tmp_path):
        mixed = [
            {"name": "Legacy", "channel_id": "UCpcvPcHJVOkO9Qp79BOagTg"},
            {"name": "RSS", "type": "rss", "url": "https://example.com/feed.xml"},
        ]
        f = tmp_path / "mixed.json"
        f.write_text(json.dumps(mixed))
        result = load_sources(f)
        assert len(result) == 2
        assert result[0]["type"] == "youtube"
        assert result[1]["type"] == "rss"

    def test_invalid_entries_skipped(self, tmp_path):
        data = [
            {"name": "Good", "channel_id": "UCpcvPcHJVOkO9Qp79BOagTg"},
            {"bad_entry": True},
            {"name": "Also Good", "type": "webpage", "url": "https://example.com"},
        ]
        f = tmp_path / "mixed.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert len(result) == 2


class TestNewFormat:
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
