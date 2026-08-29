import json
import pytest
from unittest.mock import patch, MagicMock
from gui import app


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

    def test_cinematic_toggle_is_saved_per_source(self, flask_client):
        flask_client.post("/api/sources", json={
            "name": "Selected Channel",
            "type": "youtube",
            "channel_id": "UCselected123",
        })

        rv = flask_client.post("/api/sources/cinematic", json={
            "identifier": "UCselected123",
            "enabled": True,
        })

        assert rv.status_code == 200
        sources = flask_client.get("/api/sources").get_json()
        assert sources[0]["generate_cinematic_video"] is True

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
            "name": "ToDelete", "type": "rss", "url": "https://example.com/to-delete.xml"
        })
        rv = flask_client.delete("/api/sources/0")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

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
        rv = flask_client.post("/api/state/channel", json={
            "state_key": "rss:abcd1234efgh",
            "timestamp": "2026-05-30T12:00:00Z"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True
        assert data["state"]["sources"]["rss:abcd1234efgh"] == "2026-05-30T12:00:00Z"
