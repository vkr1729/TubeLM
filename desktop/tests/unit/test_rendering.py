import pytest
from pathlib import Path
from email_service import _render_channel_html

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
        
        # Test rendering default theme
        html = _render_channel_html(channel_data, "2026-05-30", None, "email_digest.html")
        assert "New Videos" in html
        assert "YouTube" in html
        assert "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg" in html
        assert "A nice video summary" in html
        assert ".summary-html h4" in html

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
        
        # Test rendering theme1 (Premium Dark)
        html = _render_channel_html(channel_data, "2026-05-30", None, "theme1_premium_dark.html")
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
        html = _render_channel_html(channel_data, "2026-05-30", None, "email_digest.html")
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

