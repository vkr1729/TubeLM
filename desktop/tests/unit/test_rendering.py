import pytest
from pathlib import Path
from email_service import (
    _render_artifact_completion_html,
    _render_artifact_completion_text,
    _render_channel_html,
    _render_channel_text,
)

class TestTemplateRendering:
    def test_youtube_rendering(self):
        channel_data = {
            "channel_name": "Test YouTube Channel",
            "source_type": "youtube",
            "notebook_url": "https://notebooklm.google.com/notebook/test",
            "summary_text": "## Amazing Video\n\nA nice video summary",
            "videos": [
                {
                    "title": "Amazing Video",
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "video_id": "dQw4w9WgXcQ",
                    "published": "2026-05-30"
                }
            ]
        }
        
        html = _render_channel_html(channel_data, "2026-05-30", None)
        assert "New Videos" in html
        assert "YouTube" in html
        assert "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg" in html
        assert "A nice video summary" in html
        assert ".summary-html h4" in html
        assert "Visual brief" not in html
        assert 'width="50%"' in html

        text = _render_channel_text(channel_data, "2026-05-30")
        assert "TUBELM BRIEFING" in text
        assert "Amazing Video" in text
        assert "https://www.youtube.com/watch" in text

    def test_rss_rendering_no_thumbnails(self):
        channel_data = {
            "channel_name": "OpenAI RSS News",
            "source_type": "rss",
            "notebook_url": "https://notebooklm.google.com/notebook/test",
            "summary_text": "## OpenAI Releases New Model\n\nA breakthrough in model capability",
            "videos": [
                {
                    "title": "OpenAI Releases New Model",
                    "url": "https://openai.com/blog/new-model",
                    "published": "2026-05-30"
                }
            ]
        }
        
        html = _render_channel_html(channel_data, "2026-05-30", None)
        assert "New Articles" in html
        assert "RSS Feed" in html
        assert "Article Entry" in html
        assert "img.youtube.com" not in html  # Thumbnail wrapper should be omitted
        assert "A breakthrough in model capability" in html
        assert ".summary-html h4" in html

    def test_local_infographic_rendering(self, tmp_path):
        # Create a mock infographic file
        mock_info_file = tmp_path / "2026-05-30_OpenAI_News_infographic.jpg"
        mock_info_file.write_text("dummy content")
        
        channel_data = {
            "channel_name": "OpenAI News",
            "source_type": "rss",
            "infographic_path": str(mock_info_file),
            "videos": []
        }
        
        # When infographic_cid is None, it should resolve the local filename relatively
        html = _render_channel_html(channel_data, "2026-05-30", None)
        assert "2026-05-30_OpenAI_News_infographic.jpg" in html
        assert "cid:" not in html
        assert "📊" in html  # Stats bar should show infographic emoji

    def test_infographic_compression(self, tmp_path):
        from PIL import Image
        from notebooklm_service import _compress_infographic
        
        # 1. Create a dummy PNG file with an alpha channel
        png_path = tmp_path / "test_infographic.png"
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        img.save(png_path, "PNG")
        
        assert png_path.exists()
        
        # 2. Compress the image
        jpg_path_str = _compress_infographic(str(png_path))
        jpg_path = Path(jpg_path_str)
        
        # 3. Assert PNG was deleted and JPG was created
        assert not png_path.exists()
        assert jpg_path.exists()
        assert jpg_path.suffix == ".jpg"
        
        # 4. Assert JPEG file size is non-zero
        assert jpg_path.stat().st_size > 0

    def test_partial_item_mapping_falls_back_to_complete_global_summary(self):
        channel_data = {
            "channel_name": "Test Channel",
            "source_type": "youtube",
            "summary_text": "## First Video — Test Channel\n\nOnly the first title maps, but this complete response must stay visible.",
            "videos": [
                {"title": "First Video", "url": "https://example.com/1", "published": "2026-08-15"},
                {"title": "Completely Different", "url": "https://example.com/2", "published": "2026-08-15"},
            ],
        }

        html = _render_channel_html(channel_data, "2026-08-15", None)

        assert "Only the first title maps" in html
        assert "The throughline" in html
        assert "Why it matters" not in html

    def test_completion_email_is_clean_without_external_assets(self):
        batch = {
            "week_start": "2026-08-24",
            "entries": [
                {
                    "notebook_id": "notebook-1",
                    "source_name": "Doctor Alex",
                    "channel_order": 3,
                    "artifact_title": "The Healthspan Blueprint",
                    "filename": "TubeLM 03 - Doctor Alex - The Healthspan Blueprint.mp4",
                }
            ],
        }

        html = _render_artifact_completion_html("video", batch)
        text = _render_artifact_completion_text("video", batch)

        assert "Cinematic Videos ready" in html
        assert "TubeLM 03 - Doctor Alex - The Healthspan Blueprint.mp4" in html
        assert "https://notebooklm.google.com/notebook/notebook-1" in html
        assert "@media screen and (max-width:640px)" in html
        assert "<img" not in html
        assert "Doctor Alex" in text
