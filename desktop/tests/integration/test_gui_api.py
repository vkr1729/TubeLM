import json
import pytest
from unittest.mock import patch, MagicMock
from gui import app


@pytest.fixture
def flask_client(tmp_path, monkeypatch):
    import gui
    import paths
    sources_file = tmp_path / "sources.json"
    channels_file = tmp_path / "channels.json"
    monkeypatch.setattr(paths, "get_sources_file", lambda: sources_file)
    monkeypatch.setattr(paths, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(gui, "CHANNELS_FILE", channels_file)
    monkeypatch.setattr(gui, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(gui, "SUMMARIES_DIR", tmp_path / "summaries")
    tmp_path.mkdir(parents=True, exist_ok=True)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestSourcesAPI:
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

    def test_add_rss_source(self, flask_client):
        rv = flask_client.post("/api/sources", json={
            "name": "Test RSS", "type": "rss", "url": "https://example.com/feed.xml"
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["success"] is True

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

    def test_backward_compat_channels_alias(self, flask_client):
        rv = flask_client.get("/api/channels")
        assert rv.status_code == 200

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
