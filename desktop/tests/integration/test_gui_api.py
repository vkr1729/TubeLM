import json
import os

import pytest
from unittest.mock import MagicMock
from gui import app


@pytest.fixture(autouse=True)
def _restore_process_env():
    """POST /api/config reloads .env into os.environ; never leak that."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    import gui
    import paths
    sources_file = tmp_path / "sources.json"
    monkeypatch.setattr(paths, "get_sources_file", lambda: sources_file)
    monkeypatch.setattr(paths, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(gui, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(gui, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(gui, "SUMMARIES_DIR", tmp_path / "summaries")
    tmp_path.mkdir(parents=True, exist_ok=True)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestSourcesAPI:
    def test_run_api_passes_shutdown_flag(self, flask_client, monkeypatch):
        import gui

        captured = {}

        def fake_start(args):
            captured["args"] = args
            return True, "Pipeline started."

        monkeypatch.setattr(gui.runner, "start", fake_start)
        rv = flask_client.post("/api/run", json={"shutdown_after_run": True, "channels": ["Aevy TV"]})

        assert rv.status_code == 200
        assert "--shutdown-after-run" in captured["args"]
        assert captured["args"][-2:] == ["--channels", "Aevy TV"]

    def test_config_api_masks_credentials(self, flask_client, tmp_path):
        (tmp_path / ".env").write_text(
            "SMTP_PASSWORD=mail-secret\nYOUTUBE_API_KEY=youtube-secret\nSMTP_SERVER=smtp.example.com\n"
        )
        rv = flask_client.get("/api/config")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["SMTP_PASSWORD"] == "********"
        assert data["YOUTUBE_API_KEY"] == "********"
        assert data["SMTP_SERVER"] == "smtp.example.com"

    def test_config_api_accepts_top10_toggle(self, flask_client, tmp_path):
        rv = flask_client.post(
            "/api/config", json={"GENERATE_TOP_10_DIGEST": "true"}
        )
        assert rv.status_code == 200
        assert "GENERATE_TOP_10_DIGEST=true" in (tmp_path / ".env").read_text()

    def test_config_api_rejects_unknown_key(self, flask_client):
        """BUG-013: unknown keys 400 loudly instead of vanishing with 200 OK."""
        rv = flask_client.post("/api/config", json={"TTS_VOIC": "x"})
        assert rv.status_code == 400
        assert "Unknown configuration key" in rv.get_json()["error"]

    def test_config_api_persists_every_documented_key(self, flask_client, tmp_path):
        """BUG-012/013: .env.example keys and the GUI allowlist stay in parity."""
        from pathlib import Path

        example = Path(__file__).resolve().parents[3] / ".env.example"
        keys = []
        for line in example.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            keys.append(line.split("=", 1)[0].strip())
        assert keys, ".env.example must document keys"
        for key in keys:
            rv = flask_client.post("/api/config", json={key: "probe-value"})
            assert rv.status_code == 200, f"{key} rejected by /api/config"
        persisted = (tmp_path / ".env").read_text()
        for key in keys:
            assert f"{key}=probe-value" in persisted

    def test_get_sources_returns_all(self, flask_client):
        rv = flask_client.get("/api/sources")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, list)

    def test_add_youtube_source(self, flask_client):
        rv = flask_client.post("/api/sources", json={
            "name": "Test YT", "type": "youtube", "channel_id": "UCpcvPcHJVOkO9Qp79BOagTg"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

    def test_podcast_toggle_is_saved_per_source(self, flask_client):
        """BUG-008: the per-source toggle writes the pipeline-visible flag."""
        flask_client.post("/api/sources", json={
            "name": "Selected Channel",
            "type": "youtube",
            "channel_id": "UCselected123",
        })

        rv = flask_client.post("/api/sources/podcast", json={
            "identifier": "UCselected123",
            "enabled": True,
        })

        assert rv.status_code == 200
        sources = flask_client.get("/api/sources").get_json()
        assert sources[0]["generate_podcast"] is True

    def test_created_source_carries_pipeline_podcast_flag(self, flask_client):
        """BUG-008: GUI-created sources carry generate_podcast, no dead flags."""
        rv = flask_client.post("/api/sources", json={
            "name": "Pod Channel", "type": "youtube",
            "channel_id": "UCpod123", "generate_podcast": True,
        })
        assert rv.status_code == 200
        sources = flask_client.get("/api/sources").get_json()
        assert sources[0]["generate_podcast"] is True
        assert "generate_cinematic_video" not in sources[0]

    def test_created_source_omits_podcast_flag_by_default(self, flask_client):
        """RES-003: an unchecked box stores no key so the global default applies."""
        rv = flask_client.post("/api/sources", json={
            "name": "Plain Channel", "type": "youtube", "channel_id": "UCplain01",
        })
        assert rv.status_code == 200
        sources = flask_client.get("/api/sources").get_json()
        assert "generate_podcast" not in sources[0]

    def test_add_rss_source(self, flask_client):
        rv = flask_client.post("/api/sources", json={
            "name": "Test RSS", "type": "rss", "url": "https://example.com/feed.xml"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

    def test_reject_invalid_source_category(self, flask_client):
        rv = flask_client.post("/api/sources", json={
            "name": "Bad category", "type": "rss",
            "url": "https://example.com/feed.xml", "category": "anything",
        })
        assert rv.status_code == 400

    def test_clamps_source_item_limit(self, flask_client):
        rv = flask_client.post("/api/sources", json={
            "name": "Large feed", "type": "rss",
            "url": "https://example.com/large.xml", "max_items": 5000,
        })
        assert rv.status_code == 200
        assert rv.get_json()["sources"][0]["max_items"] == 50

    def test_add_webpage_source(self, flask_client):
        rv = flask_client.post("/api/sources", json={
            "name": "Test Web", "type": "webpage", "url": "https://example.com/article"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

    def test_reject_duplicate_url(self, flask_client):
        flask_client.post("/api/sources", json={
            "name": "First", "type": "rss", "url": "https://example.com/feed.xml"
        })
        rv = flask_client.post("/api/sources", json={
            "name": "Second", "type": "rss", "url": "https://example.com/feed.xml"
        })
        assert rv.status_code == 400

    def test_delete_source(self, flask_client):
        flask_client.post("/api/sources", json={
            "name": "ToDelete", "type": "youtube", "channel_id": "UCtodelete1"
        })
        rv = flask_client.delete("/api/sources/UCtodelete1")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

    def test_delete_unmatched_numeric_returns_404(self, flask_client, tmp_path):
        """BUG-024: no positional-index fallback; unmatched id is a 404."""
        flask_client.post("/api/sources", json={
            "name": "Keeper", "type": "youtube", "channel_id": "UCkeeper01"
        })
        before = (tmp_path / "sources.json").read_text()
        rv = flask_client.delete("/api/sources/0")
        assert rv.status_code == 404
        assert (tmp_path / "sources.json").read_text() == before

    def test_delete_preserves_unknown_entries(self, flask_client, tmp_path):
        """BUG-014: deleting one source must not vaporize filtered-out rows."""
        legacy = {"name": "Legacy", "type": "future-type", "url": "https://example.com/x"}
        good = {"name": "Good", "type": "rss", "url": "https://example.com/good.xml"}
        (tmp_path / "sources.json").write_text(json.dumps([legacy, good]))
        rv = flask_client.post("/api/sources/delete", json={
            "identifier": "https://example.com/good.xml"
        })
        assert rv.status_code == 200
        remaining = json.loads((tmp_path / "sources.json").read_text())
        assert remaining == [legacy]

    def test_status_reports_source_types(self, flask_client):
        rv = flask_client.get("/api/status")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "source_types" in data
        assert "source_count" in data

    def test_post_delete_source(self, flask_client):
        flask_client.post("/api/sources", json={
            "name": "ToDelete", "type": "rss", "url": "https://example.com/delete-post.xml"
        })
        rv = flask_client.post("/api/sources/delete", json={
            "identifier": "https://example.com/delete-post.xml"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

    def test_state_key_update(self, flask_client):
        """BUG-015: Zulu input is normalized on write and honored on read."""
        from datetime import datetime, timezone

        from main import load_source_state
        import gui as gui_module

        rv = flask_client.post("/api/state/channel", json={
            "state_key": "rss:abcd1234efgh",
            "timestamp": "2026-05-30T12:00:00Z"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True
        assert data["state"]["sources"]["rss:abcd1234efgh"] == "2026-05-30T12:00:00+00:00"
        # Round-trip: the pipeline parser must return that exact instant.
        parsed = load_source_state(gui_module.STATE_FILE, "rss:abcd1234efgh")
        assert parsed == datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)

    def test_reader_endpoints(self, flask_client, tmp_path, monkeypatch):
        import paths
        site_dir = tmp_path / "site"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text("<html><body>TubeLM Web Reader</body></html>")
        (site_dir / "feed.xml").write_text("<rss></rss>")
        monkeypatch.setattr(paths, "get_site_dir", lambda: site_dir)

        rv = flask_client.get("/reader")
        assert rv.status_code == 200
        assert "TubeLM Web Reader" in rv.get_data(as_text=True)

        rv_feed = flask_client.get("/reader/feed.xml")
        assert rv_feed.status_code == 200
        assert "<rss></rss>" in rv_feed.get_data(as_text=True)

    def test_api_build_reader_optional_compression(self, flask_client, monkeypatch):
        import web_reader

        mock_build = MagicMock(return_value="/mock/site/index.html")
        monkeypatch.setattr(web_reader, "build_reader_site", mock_build)

        # Default / false
        rv = flask_client.post("/api/reader/build", json={"compress_audio": False})
        assert rv.status_code == 200
        assert mock_build.call_args.kwargs["compress_audio"] is False

        # Explicit true
        rv2 = flask_client.post("/api/reader/build", json={"compress_audio": True})
        assert rv2.status_code == 200
        assert mock_build.call_args.kwargs["compress_audio"] is True

    def test_api_build_reader_rejects_non_boolean_compression(self, flask_client, monkeypatch):
        from unittest.mock import MagicMock
        import web_reader

        mock_build = MagicMock(return_value="/mock/site/index.html")
        monkeypatch.setattr(web_reader, "build_reader_site", mock_build)

        rv = flask_client.post("/api/reader/build", json={"compress_audio": "false"})
        assert rv.status_code == 400
        mock_build.assert_not_called()


class TestNotebookLoopAndLogin:
    def test_login_helper_symbol_is_importable(self):
        """BUG-025: fail loudly at test time if upstream renames the helper."""
        from notebooklm.cli.services.login.refresh import _login_with_browser_cookies

        assert callable(_login_with_browser_cookies)

    def test_delete_notebook_uses_scoped_loop(self, flask_client, monkeypatch):
        """BUG-026: the handler must not touch the thread-global event loop."""
        import asyncio

        def _forbid_set_loop(loop):
            raise AssertionError("handler must not call set_event_loop")

        monkeypatch.setattr(asyncio, "set_event_loop", _forbid_set_loop)

        class _Notebooks:
            async def delete(self, notebook_id):
                assert notebook_id == "nb-1"
                return True

        class _Client:
            @property
            def notebooks(self):
                return _Notebooks()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _ClientCls:
            @classmethod
            def from_storage(cls, **kwargs):
                return _Client()

        monkeypatch.setattr("notebooklm.NotebookLMClient", _ClientCls)
        rv = flask_client.delete("/api/notebooks/real/nb-1")
        assert rv.status_code == 200
        assert rv.get_json() == {"success": True}

