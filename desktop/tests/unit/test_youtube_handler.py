import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from source_handlers.youtube_handler import YouTubeHandler


class TestYouTubeHandlerDiscovery:
    def test_state_key_format(self):
        handler = YouTubeHandler("Test", "UCpcvPcHJVOkO9Qp79BOagTg")
        assert handler.state_key() == "youtube:UCpcvPcHJVOkO9Qp79BOagTg"
        assert handler.source_type == "youtube"
        assert handler.name == "Test"

    def test_rss_404_without_api_key_preserves_checkpoint(self):
        handler = YouTubeHandler("Unavailable", "UCunknown")
        with patch("source_handlers.youtube_handler.requests.get") as mock_get:
            response = MagicMock(status_code=404)
            mock_get.return_value = response
            videos = handler._fetch_channel_videos(datetime.now(timezone.utc))
        assert videos is None
        mock_get.assert_called_once()

    def test_rss_404_uses_official_api_fallback(self):
        handler = YouTubeHandler("Valid", "UCvalid", youtube_api_key="fake_key")
        rss_response = MagicMock(status_code=404)
        channel_response = MagicMock(status_code=200)
        channel_response.json.return_value = {
            "items": [{
                "contentDetails": {
                    "relatedPlaylists": {"uploads": "UUvalid"}
                }
            }]
        }
        playlist_response = MagicMock(status_code=200)
        playlist_response.json.return_value = {
            "items": [{
                "snippet": {
                    "title": "A useful new upload",
                    "description": "Long-form briefing",
                },
                "contentDetails": {
                    "videoId": "abcdefghijk",
                    "videoPublishedAt": "2026-08-14T10:00:00Z",
                },
            }]
        }

        with patch(
            "source_handlers.youtube_handler.requests.get",
            side_effect=[rss_response, channel_response, playlist_response],
        ) as mock_get:
            videos = handler._fetch_channel_videos(
                datetime(2026, 8, 1, tzinfo=timezone.utc)
            )

        assert videos == [{
            "title": "A useful new upload",
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "video_id": "abcdefghijk",
            "published": "2026-08-14",
            "description": "Long-form briefing",
        }]
        assert mock_get.call_count == 3

    def test_api_fallback_failure_preserves_checkpoint(self):
        handler = YouTubeHandler("Valid", "UCvalid", youtube_api_key="fake_key")
        rss_response = MagicMock(status_code=404)
        api_response = MagicMock(status_code=500)
        api_response.raise_for_status.side_effect = RuntimeError("API unavailable")

        with patch(
            "source_handlers.youtube_handler.requests.get",
            side_effect=[rss_response, api_response],
        ):
            videos = handler._fetch_channel_videos(
                datetime(2026, 8, 1, tzinfo=timezone.utc)
            )

        assert videos is None


class TestYouTubeHandlerFiltering:
    def test_keyword_filter_removes_shorts(self):
        handler = YouTubeHandler("Test", "UCtest")
        videos = [
            {"title": "#shorts funny moment", "url": "http://youtube.com/watch?v=abc", "video_id": "abc", "published": "2025-01-01", "description": ""},
            {"title": "Real Documentary", "url": "http://youtube.com/watch?v=def", "video_id": "def", "published": "2025-01-02", "description": ""},
        ]
        filtered = handler._filter_by_keyword(videos)
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Real Documentary"

    def test_title_heuristic_removes_hashtag_heavy(self):
        handler = YouTubeHandler("Test", "UCtest")
        videos = [
            {"title": "#funny #comedy #viral #lol", "url": "http://youtube.com/watch?v=abc", "video_id": "abc", "published": "2025-01-01", "description": ""},
            {"title": "In-depth Analysis of Machine Learning", "url": "http://youtube.com/watch?v=def", "video_id": "def", "published": "2025-01-02", "description": ""},
        ]
        filtered = handler._filter_by_title_heuristics(videos)
        assert len(filtered) == 1

    def test_duration_filter_with_mock_api(self):
        handler = YouTubeHandler("Test", "UCtest", youtube_api_key="fake_key")
        videos = [{"title": "Short vid", "url": "http://youtube.com/watch?v=short1", "video_id": "short1", "published": "2025-01-01", "description": ""}]
        with patch("source_handlers.youtube_handler.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "items": [{"id": "short1", "contentDetails": {"duration": "PT1M30S"}}]
            }
            mock_get.return_value = mock_resp
            filtered = handler._filter_by_duration(videos)
            assert len(filtered) == 0


class TestYouTubeHandlerIngestion:
    @pytest.mark.asyncio
    async def test_uses_add_url(self):
        from unittest.mock import AsyncMock, MagicMock
        client = AsyncMock()
        client.sources.add_url.return_value = MagicMock(id="src_test_001")
        from source_handlers import SourceItem
        handler = YouTubeHandler("Test", "UCtest")
        items = [SourceItem(title="Video", url="https://youtube.com/watch?v=abc", published="2025-01-01")]
        ids = await handler.ingest(client, "nb_id", items)
        assert len(ids) == 1
        client.sources.add_url.assert_called_once()
