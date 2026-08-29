import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import (
    load_source_state,
    materialize_source_checkpoints,
    save_seen_urls,
    save_state,
    load_seen_urls,
)


class TestSeenUrls:
    def test_save_and_load_roundtrip(self, tmp_path):
        state_file = tmp_path / "state.json"
        save_seen_urls(state_file, "webpage:abc123", {"https://example.com/a", "https://example.com/b"})
        loaded = load_seen_urls(state_file, "webpage:abc123")
        assert loaded == {"https://example.com/a", "https://example.com/b"}

    def test_accumulates_across_saves(self, tmp_path):
        state_file = tmp_path / "state.json"
        save_seen_urls(state_file, "webpage:abc123", {"https://example.com/a"})
        save_seen_urls(state_file, "webpage:abc123", {"https://example.com/b"})
        loaded = load_seen_urls(state_file, "webpage:abc123")
        assert len(loaded) == 2

    def test_returns_empty_for_unknown_key(self, tmp_path):
        state_file = tmp_path / "state.json"
        result = load_seen_urls(state_file, "nonexistent:key")
        assert result == set()

    def test_returns_empty_for_missing_file(self, tmp_path):
        state_file = tmp_path / "nonexistent.json"
        result = load_seen_urls(state_file, "any_key")
        assert result == set()


class TestStateManagement:
    def test_reads_from_sources_key(self, tmp_path):
        state_file = tmp_path / "state.json"
        now = datetime.now(timezone.utc)
        state = {
            "last_run_time": now.isoformat(),
            "sources": {
                "rss:a1b2c3d4e5f6": (now - timedelta(days=2)).isoformat(),
            },
        }
        state_file.write_text(json.dumps(state))
        dt = load_source_state(state_file, "rss:a1b2c3d4e5f6")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_falls_back_to_global_last_run(self, tmp_path):
        state_file = tmp_path / "state.json"
        now = datetime.now(timezone.utc)
        state = {"last_run_time": (now - timedelta(days=3)).isoformat()}
        state_file.write_text(json.dumps(state))
        dt = load_source_state(state_file, "nonexistent_key")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_returns_default_on_missing_file(self, tmp_path):
        state_file = tmp_path / "nonexistent.json"
        dt = load_source_state(state_file, "any_key")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_save_state_writes_sources_key(self, tmp_path):
        state_file = tmp_path / "state.json"
        save_state(state_file, ["youtube:UCtest123", "rss:a1b2c3d4e5f6"])
        data = json.loads(state_file.read_text())
        assert "sources" in data
        assert "youtube:UCtest123" in data["sources"]
        assert "rss:a1b2c3d4e5f6" in data["sources"]

    def test_save_state_removes_legacy_channels_key(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = {"channels": {"UCold": "2025-01-01T00:00:00+00:00"}}
        state_file.write_text(json.dumps(state))
        save_state(state_file, ["youtube:UCnew"])
        data = json.loads(state_file.read_text())
        assert "channels" not in data
        assert "sources" in data

    def test_failed_new_source_keeps_original_global_checkpoint(self, tmp_path):
        state_file = tmp_path / "state.json"
        original = "2026-07-31T01:51:02+00:00"
        state_file.write_text(json.dumps({"last_run_time": original}))

        class Handler:
            def __init__(self, key):
                self.key = key

            def state_key(self):
                return self.key

        successful = Handler("youtube:successful")
        failed = Handler("youtube:failed")
        materialize_source_checkpoints(state_file, [successful, failed])
        save_state(state_file, [successful.state_key()])

        data = json.loads(state_file.read_text())
        assert data["sources"][failed.state_key()] == original
        assert data["sources"][successful.state_key()] != original
