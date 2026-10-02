"""Unit tests for YouTube playlist publisher service."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import paths
import youtube_playlist_service
from youtube_playlist_service import (
    YouTubeAuthError,
    YouTubePlaylistError,
    backfill_playlists,
    create_weekly_playlist,
    get_oauth_client_info,
    get_valid_access_token,
    load_playlist_history,
    load_token,
    refresh_access_token,
    save_playlist_history,
    save_token,
)


@pytest.fixture
def mock_paths(tmp_path, monkeypatch):
    """Isolate token and playlist files to tmp_path."""
    token_file = tmp_path / "youtube_token.json"
    client_secret_file = tmp_path / "client_secret.json"
    playlists_file = tmp_path / "youtube_playlists.json"
    summaries_dir = tmp_path / "summaries"
    summaries_dir.mkdir()

    monkeypatch.setattr(paths, "get_youtube_token_file", lambda: token_file)
    monkeypatch.setattr(paths, "get_youtube_client_secret_file", lambda: client_secret_file)
    monkeypatch.setattr(paths, "get_youtube_playlists_file", lambda: playlists_file)
    monkeypatch.setattr(paths, "get_summaries_dir", lambda: summaries_dir)
    monkeypatch.setattr(
        youtube_playlist_service,
        "get_authenticated_channel_info",
        lambda token: {"id": "UCtest", "title": "Test Channel", "custom_url": "@test"},
    )

    return {
        "token_file": token_file,
        "client_secret_file": client_secret_file,
        "playlists_file": playlists_file,
        "summaries_dir": summaries_dir,
    }


def test_get_oauth_client_info_from_file(mock_paths):
    secret_data = {
        "installed": {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-secret-123",
        }
    }
    mock_paths["client_secret_file"].write_text(json.dumps(secret_data), encoding="utf-8")

    info = get_oauth_client_info()
    assert info["client_id"] == "test-client-id.apps.googleusercontent.com"
    assert info["client_secret"] == "test-secret-123"
    assert info["source"] == str(mock_paths["client_secret_file"])


def test_get_oauth_client_info_from_env(mock_paths, monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "env-client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "env-client-secret")

    info = get_oauth_client_info()
    assert info["client_id"] == "env-client-id"
    assert info["client_secret"] == "env-client-secret"
    assert info["source"] == "environment"


def test_get_oauth_client_info_missing_raises(mock_paths, monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)

    with pytest.raises(YouTubeAuthError, match="credentials not found"):
        get_oauth_client_info()


def test_token_save_and_load(mock_paths):
    assert load_token() is None

    token_data = {
        "access_token": "ya29.test",
        "refresh_token": "1//test-refresh",
        "expires_at": time.time() + 3600,
    }
    save_token(token_data)

    loaded = load_token()
    assert loaded is not None
    assert loaded["access_token"] == "ya29.test"
    assert loaded["refresh_token"] == "1//test-refresh"


def test_get_valid_access_token_unexpired(mock_paths, monkeypatch):
    token_data = {
        "access_token": "ya29.valid-now",
        "refresh_token": "1//refresh",
        "expires_at": time.time() + 1800,  # 30 min left
    }
    save_token(token_data)
    mock_paths["client_secret_file"].write_text(
        json.dumps({"installed": {"client_id": "c1", "client_secret": "s1"}}),
        encoding="utf-8",
    )

    with patch("requests.post") as mock_post:
        token = get_valid_access_token()
        assert token == "ya29.valid-now"
        mock_post.assert_not_called()


def test_get_valid_access_token_expired_triggers_refresh(mock_paths, monkeypatch):
    token_data = {
        "access_token": "ya29.expired",
        "refresh_token": "1//refresh-token",
        "expires_at": time.time() - 100,  # expired
    }
    save_token(token_data)
    mock_paths["client_secret_file"].write_text(
        json.dumps({"installed": {"client_id": "c1", "client_secret": "s1"}}),
        encoding="utf-8",
    )

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "access_token": "ya29.new-refreshed-token",
        "expires_in": 3600,
    }

    with patch("requests.post", return_value=fake_response) as mock_post:
        token = get_valid_access_token()
        assert token == "ya29.new-refreshed-token"
        assert mock_post.called
        # Check that new token was persisted
        persisted = load_token()
        assert persisted["access_token"] == "ya29.new-refreshed-token"
        assert persisted["expires_at"] > time.time()


def test_create_weekly_playlist_success_and_idempotency(mock_paths):
    token_data = {
        "access_token": "ya29.token",
        "refresh_token": "1//refresh",
        "expires_at": time.time() + 3600,
    }
    save_token(token_data)
    mock_paths["client_secret_file"].write_text(
        json.dumps({"installed": {"client_id": "c1", "client_secret": "s1"}}),
        encoding="utf-8",
    )

    items = [
        {"title": "Video 1", "video_id": "abc12345678", "url": "https://www.youtube.com/watch?v=abc12345678"},
        {"title": "Video 2", "video_id": "def12345678", "url": "https://www.youtube.com/watch?v=def12345678"},
    ]

    create_resp = MagicMock()
    create_resp.status_code = 200
    create_resp.json.return_value = {"id": "PL_test_12345"}

    item_resp = MagicMock()
    item_resp.status_code = 200
    item_resp.json.return_value = {"id": "item_1"}

    with patch("requests.post") as mock_post:
        mock_post.side_effect = [create_resp, item_resp, item_resp]

        res = create_weekly_playlist("2026-09-25", items, privacy_status="public")
        assert res["playlist_id"] == "PL_test_12345"
        assert res["playlist_url"] == "https://www.youtube.com/playlist?list=PL_test_12345"
        assert res["title"] == "TubeLM Top 2 - 2026-09-25"
        assert res["added_videos_count"] == 2
        assert mock_post.call_count == 3  # 1 playlist + 2 items

        # Verify initial playlist payload
        first_call = mock_post.call_args_list[0]
        assert first_call.kwargs["json"]["snippet"]["title"] == "TubeLM Top 2 - 2026-09-25"
        assert first_call.kwargs["json"]["status"]["privacyStatus"] == "public"

        # Verify idempotency: calling again with same run_date returns from history without API calls
        res_cached = create_weekly_playlist("2026-09-25", items, privacy_status="public")
        assert res_cached["playlist_id"] == "PL_test_12345"
        assert mock_post.call_count == 3  # No additional calls


def test_create_weekly_playlist_resilience_to_individual_video_failure(mock_paths):
    token_data = {
        "access_token": "ya29.token",
        "refresh_token": "1//refresh",
        "expires_at": time.time() + 3600,
    }
    save_token(token_data)
    mock_paths["client_secret_file"].write_text(
        json.dumps({"installed": {"client_id": "c1", "client_secret": "s1"}}),
        encoding="utf-8",
    )

    items = [
        {"title": "Good Video", "video_id": "abc12345678"},
        {"title": "Bad Video", "video_id": "bad12345678"},
        {"title": "Good Video 2", "video_id": "xyz12345678"},
    ]

    create_resp = MagicMock(status_code=200)
    create_resp.json.return_value = {"id": "PL_resilient"}

    ok_item = MagicMock(status_code=200)
    fail_item = MagicMock(status_code=404, text="Video not found")

    with patch("requests.post") as mock_post:
        mock_post.side_effect = [create_resp, ok_item, fail_item, ok_item]

        res = create_weekly_playlist("2026-09-18", items, privacy_status="public")
        assert res["playlist_id"] == "PL_resilient"
        assert res["added_videos_count"] == 2
        assert res["failed_videos_count"] == 1


def test_backfill_playlists(mock_paths):
    token_data = {
        "access_token": "ya29.token",
        "refresh_token": "1//refresh",
        "expires_at": time.time() + 3600,
    }
    save_token(token_data)
    mock_paths["client_secret_file"].write_text(
        json.dumps({"installed": {"client_id": "c1", "client_secret": "s1"}}),
        encoding="utf-8",
    )

    # Seed summary sidecar
    digest_json = mock_paths["summaries_dir"] / "2026-09-25_TubeLM_Top_20_digest.json"
    digest_json.write_text(
        json.dumps({
            "items": [
                {"title": "Item 1", "video_id": "vid00000001"},
                {"title": "Item 2", "video_id": "vid00000002"},
            ]
        }),
        encoding="utf-8",
    )

    create_resp = MagicMock(status_code=200)
    create_resp.json.return_value = {"id": "PL_backfill_25"}
    item_resp = MagicMock(status_code=200)

    with patch("requests.post") as mock_post:
        mock_post.side_effect = [create_resp, item_resp, item_resp]

        results = backfill_playlists(["2026-09-25"])
        assert len(results) == 1
        assert results[0]["playlist_id"] == "PL_backfill_25"

        # Check sidecar was updated with playlist_url
        updated = json.loads(digest_json.read_text(encoding="utf-8"))
        assert updated["playlist_url"] == "https://www.youtube.com/playlist?list=PL_backfill_25"
        assert updated["playlist_id"] == "PL_backfill_25"


def test_save_token_permissions(mock_paths):
    save_token({"access_token": "ya29.test", "refresh_token": "ref"})
    mode = mock_paths["token_file"].stat().st_mode & 0o777
    assert mode == 0o600


def test_create_weekly_playlist_invalid_privacy(mock_paths):
    with pytest.raises(YouTubePlaylistError, match="Invalid privacyStatus"):
        create_weekly_playlist("2026-09-25", [{"title": "v1", "video_id": "12345678901"}], privacy_status="invalid")


def test_create_weekly_playlist_empty_items(mock_paths):
    with pytest.raises(YouTubePlaylistError, match="zero items"):
        create_weekly_playlist("2026-09-25", [])


def test_create_weekly_playlist_invalid_date(mock_paths):
    with pytest.raises(YouTubePlaylistError, match="Invalid run_date format"):
        create_weekly_playlist("2026/09/25", [{"title": "v1", "video_id": "12345678901"}])


def test_create_weekly_playlist_deduplicates_and_skips_non_videos(mock_paths):
    token_data = {"access_token": "ya29.token", "refresh_token": "ref", "expires_at": time.time() + 3600}
    save_token(token_data)
    mock_paths["client_secret_file"].write_text(
        json.dumps({"installed": {"client_id": "c1", "client_secret": "s1"}}),
        encoding="utf-8",
    )
    items = [
        {"title": "Video 1", "video_id": "abc12345678"},
        {"title": "Video 1 Duplicate", "video_id": "abc12345678"},
        {"title": "Article without video", "url": "https://example.com/article"},
    ]
    create_resp = MagicMock(status_code=200)
    create_resp.json.return_value = {"id": "PL_dedupe"}
    item_resp = MagicMock(status_code=200)
    item_resp.json.return_value = {"id": "item_1"}

    with patch("requests.post") as mock_post:
        mock_post.side_effect = [create_resp, item_resp]
        res = create_weekly_playlist("2026-09-25", items)
        assert res["added_videos_count"] == 1
        assert res["skipped_non_videos_count"] == 1
        assert mock_post.call_count == 2


def test_create_weekly_playlist_zero_videos_added_raises_and_cleans_up(mock_paths):
    token_data = {"access_token": "ya29.token", "refresh_token": "ref", "expires_at": time.time() + 3600}
    save_token(token_data)
    items = [{"title": "Video 1", "video_id": "abc12345678"}]
    create_resp = MagicMock(status_code=200)
    create_resp.json.return_value = {"id": "PL_failed"}
    failed_item_resp = MagicMock(status_code=400, text="Invalid video")
    delete_resp = MagicMock(status_code=204)

    with patch("requests.post") as mock_post, patch("requests.delete") as mock_delete:
        mock_post.side_effect = [create_resp, failed_item_resp]
        mock_delete.return_value = delete_resp

        with pytest.raises(YouTubePlaylistError, match="0 of 1 added"):
            create_weekly_playlist("2026-09-25", items)

        # Confirm playlist was cleaned up
        mock_delete.assert_called_once()
        assert "PL_failed" in mock_delete.call_args[0][0]

    # Confirm history was NOT saved with empty record
    history = load_playlist_history()
    assert "2026-09-25" not in history


def test_extract_video_id_embed_live_formats():
    from youtube_playlist_service import _extract_video_id
    assert _extract_video_id({"url": "https://www.youtube.com/embed/dQw4w9WgXcQ"}) == "dQw4w9WgXcQ"
    assert _extract_video_id({"url": "https://www.youtube.com/live/dQw4w9WgXcQ?feature=share"}) == "dQw4w9WgXcQ"
    assert _extract_video_id({"url": "https://www.youtube.com/v/dQw4w9WgXcQ"}) == "dQw4w9WgXcQ"


def test_refresh_access_token_invalid_grant_unlinks_token(mock_paths):
    mock_paths["token_file"].write_text(json.dumps({"refresh_token": "bad_token"}), encoding="utf-8")
    resp = MagicMock(status_code=400, text='{"error": "invalid_grant"}')
    with patch("requests.post", return_value=resp):
        with pytest.raises(YouTubeAuthError, match="invalid_grant"):
            refresh_access_token({"refresh_token": "bad_token"}, {"client_id": "c", "client_secret": "s"})
    assert not mock_paths["token_file"].exists()


def test_get_valid_access_token_does_not_load_client_secret_if_unexpired(mock_paths):
    token_data = {"access_token": "ya29.valid", "refresh_token": "ref", "expires_at": time.time() + 3600}
    save_token(token_data)
    # Notice: client_secret.json does NOT exist in mock_paths!
    token = get_valid_access_token()
    assert token == "ya29.valid"
