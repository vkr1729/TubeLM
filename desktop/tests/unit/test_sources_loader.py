import json
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


class TestIdLessEntriesSkipped:
    """BUG-006: entries missing their type-specific id must be skipped, not kept."""

    def test_id_less_entries_skipped(self, tmp_path):
        data = [
            {"name": "YT No ID", "type": "youtube"},
            {"name": "RSS No URL", "type": "rss"},
            {"name": "Page Empty URL", "type": "webpage", "url": ""},
            {"name": "Good", "type": "youtube", "channel_id": "UC123"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert [e["name"] for e in result] == ["Good"]

    def test_one_bad_entry_does_not_kill_handler_construction(self, tmp_path):
        """End of BUG-006 chain: every loaded entry must build a handler."""
        from source_handlers.factory import create_handler

        data = [
            {"name": "YT No ID", "type": "youtube"},
            {"name": "Good RSS", "type": "rss", "url": "https://example.com/feed"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        handlers = [create_handler(src) for src in result]  # must not raise
        assert len(handlers) == 1


class TestGeneratePodcastNotForced:
    """BUG-007: absent per-source flag must stay absent so the global fallback applies."""

    def test_absent_flag_stays_absent(self, tmp_path):
        data = [{"name": "YT", "type": "youtube", "channel_id": "UC123"}]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert "generate_podcast" not in result[0]

    def test_explicit_flag_preserved_and_coerced(self, tmp_path):
        data = [
            {"name": "On", "type": "youtube", "channel_id": "UC1", "generate_podcast": 1},
            {"name": "Off", "type": "youtube", "channel_id": "UC2", "generate_podcast": 0},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert result[0]["generate_podcast"] is True
        assert result[1]["generate_podcast"] is False

    def test_string_flags_use_shared_vocabulary(self, tmp_path):
        data = [
            {"name": "S1", "type": "youtube", "channel_id": "UC1", "generate_podcast": "false"},
            {"name": "S2", "type": "youtube", "channel_id": "UC2", "generate_podcast": "YES"},
            {"name": "S3", "type": "youtube", "channel_id": "UC3", "generate_podcast": "on"},
            {"name": "S4", "type": "youtube", "channel_id": "UC4", "generate_podcast": "bogus"},
        ]
        f = tmp_path / "sources.json"
        f.write_text(json.dumps(data))
        result = load_sources(f)
        assert [e["generate_podcast"] for e in result] == [False, True, True, False]
