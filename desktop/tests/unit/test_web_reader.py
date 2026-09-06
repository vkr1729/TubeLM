import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

from web_reader import (
    purge_old_digests_and_audio,
    parse_top20_digest,
    parse_channel_digest,
    generate_rss_feed,
    build_reader_site,
)


class TestPurgeRetention:
    def test_purge_older_than_14_days(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        audio_dir = tmp_path / "audio"
        summaries_dir.mkdir()
        audio_dir.mkdir()

        now = datetime.now(timezone.utc).date()
        d_today = now.strftime("%Y-%m-%d")
        d_5d = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        d_13d = (now - timedelta(days=13)).strftime("%Y-%m-%d")
        d_15d = (now - timedelta(days=15)).strftime("%Y-%m-%d")
        d_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        # Create files
        f_today = summaries_dir / f"{d_today}_ActiveChannel_digest.html"
        f_today.write_text("today")

        f_5d = summaries_dir / f"{d_5d}_RecentChannel_digest.html"
        f_5d.write_text("5 days old")

        f_13d = summaries_dir / f"{d_13d}_EdgeChannel_digest.html"
        f_13d.write_text("13 days old")

        f_15d = summaries_dir / f"{d_15d}_StaleChannel_digest.html"
        f_15d.write_text("15 days old - should purge")

        f_30d = summaries_dir / f"{d_30d}_AncientChannel_digest.html"
        f_30d.write_text("30 days old - should purge")

        # Audio files
        a_today = audio_dir / f"{d_today}_ActiveChannel.mp3"
        a_today.write_bytes(b"today_audio")

        a_15d = audio_dir / f"{d_15d}_StaleChannel.mp3"
        a_15d.write_bytes(b"stale_audio")

        # Non-dated file should be preserved
        non_dated = summaries_dir / "index_template.html"
        non_dated.write_text("template")

        purged = purge_old_digests_and_audio(summaries_dir, audio_dir, max_age_days=14)

        assert f_15d.name in purged
        assert f_30d.name in purged
        assert a_15d.name in purged

        assert not f_15d.exists()
        assert not f_30d.exists()
        assert not a_15d.exists()

        assert f_today.exists()
        assert f_5d.exists()
        assert f_13d.exists()
        assert a_today.exists()
        assert non_dated.exists()


class TestParseTop20:
    def test_parse_valid_top20_html(self, tmp_path):
        html_content = """
        <html>
          <body>
            <h1>TubeLM Executive Top 20</h1>
            <table>
              <tr>
                <td class="rank-cell">1</td>
                <td>
                  <a href="https://www.youtube.com/watch?v=video1">
                    <h2 class="item-title">Autonomous AI Agents in Production</h2>
                  </a>
                  <div style="text-transform: uppercase;">YOUTUBE / Andrej Karpathy / 2026-09-04</div>
                  <p>Groundbreaking breakdown of multi-agent architectures.</p>
                </td>
              </tr>
              <tr>
                <td class="rank-cell">2</td>
                <td>
                  <a href="https://example.com/deep-dive">
                    <h2 class="item-title">Quantum Computing Horizons</h2>
                  </a>
                  <div style="text-transform: uppercase;">WEBPAGE / Quanta Magazine / 2026-09-03</div>
                  <p>In-depth exploration of topological qubits.</p>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """
        top20_file = tmp_path / "2026-09-04_Top_20_Digest.html"
        top20_file.write_text(html_content, encoding="utf-8")

        result = parse_top20_digest(top20_file)
        assert result["candidate_count"] == 2
        assert len(result["items"]) == 2

        item1 = result["items"][0]
        assert item1["rank"] == 1
        assert item1["title"] == "Autonomous AI Agents in Production"
        assert item1["url"] == "https://www.youtube.com/watch?v=video1"
        assert item1["source_name"] == "Andrej Karpathy"
        assert item1["source_type"] == "youtube"
        assert "multi-agent" in item1["why_it_matters"]

        item2 = result["items"][1]
        assert item2["rank"] == 2
        assert item2["source_name"] == "Quanta Magazine"
        assert item2["source_type"] == "web"

    def test_parse_missing_file_returns_empty(self, tmp_path):
        result = parse_top20_digest(tmp_path / "nonexistent.html")
        assert result == {"items": [], "candidate_count": 0}


class TestParseChannelDigest:
    def test_audio_overview_only_for_multiple_videos(self, tmp_path):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()

        # Create audio file
        audio_file = audio_dir / "2026-09-04_SingleVideoChan.mp3"
        audio_file.write_bytes(b"fake_mp3")

        # Channel 1: Single video with audio on disk -> has_audio MUST be False
        single_video_html = """
        <html><body>
          <h1>SingleVideoChan</h1>
          <a href="https://notebooklm.google.com/notebook/123">Open NotebookLM</a>
          <div class="item-card">
            <h2>Video 1 Title</h2>
            <a href="https://youtube.com/watch?v=1">Watch</a>
            <div class="summary-html"><p>Summary of video 1</p></div>
          </div>
        </body></html>
        """
        digest_file_single = tmp_path / "2026-09-04_SingleVideoChan_digest.html"
        digest_file_single.write_text(single_video_html, encoding="utf-8")

        sources_map = {
            "SingleVideoChan": {"name": "SingleVideoChan", "category": "tech", "subscribers": "100K"}
        }

        parsed_single = parse_channel_digest(
            digest_file_single, sources_map, audio_dir, "2026-09-04"
        )
        assert parsed_single is not None
        assert parsed_single["video_count"] == 1
        assert parsed_single["has_audio"] is False, "Single-video channel must not display audio player!"

        # Channel 2: Multi-video (2 videos) with audio on disk -> has_audio MUST be True
        multi_audio = audio_dir / "2026-09-04_MultiVideoChan.mp3"
        multi_audio.write_bytes(b"fake_mp3")

        multi_video_html = """
        <html><body>
          <h1>MultiVideoChan</h1>
          <a href="https://notebooklm.google.com/notebook/456">Open NotebookLM</a>
          <div class="item-card">
            <h2>Video 1</h2>
            <a href="https://youtube.com/watch?v=1">Watch 1</a>
            <div class="summary-html"><p>Summary 1</p></div>
          </div>
          <div class="item-card">
            <h2>Video 2</h2>
            <a href="https://youtube.com/watch?v=2">Watch 2</a>
            <div class="summary-html"><p>Summary 2</p></div>
          </div>
        </body></html>
        """
        digest_file_multi = tmp_path / "2026-09-04_MultiVideoChan_digest.html"
        digest_file_multi.write_text(multi_video_html, encoding="utf-8")
        sources_map["MultiVideoChan"] = {"name": "MultiVideoChan", "category": "health", "subscribers": "250K"}

        parsed_multi = parse_channel_digest(
            digest_file_multi, sources_map, audio_dir, "2026-09-04"
        )
        assert parsed_multi is not None
        assert parsed_multi["video_count"] == 2
        assert parsed_multi["has_audio"] is True
        assert parsed_multi["audio_url"] == "audio/2026-09-04_MultiVideoChan.mp3"

        # Channel 3: Multi-video (2 videos) WITHOUT audio on disk -> has_audio MUST be False
        digest_file_no_audio = tmp_path / "2026-09-04_NoAudioChan_digest.html"
        digest_file_no_audio.write_text(multi_video_html.replace("MultiVideoChan", "NoAudioChan"), encoding="utf-8")
        sources_map["NoAudioChan"] = {"name": "NoAudioChan", "category": "tech"}

        parsed_no_audio = parse_channel_digest(
            digest_file_no_audio, sources_map, audio_dir, "2026-09-04"
        )
        assert parsed_no_audio is not None
        assert parsed_no_audio["video_count"] == 2
        assert parsed_no_audio["has_audio"] is False


class TestGenerateRSS:
    def test_rss_xml_structure(self, tmp_path):
        site_data = {
            "version": "4.0.0",
            "weeks": {
                "current": {
                    "run_date": "2026-09-04",
                    "top20": {
                        "items": [
                            {
                                "rank": 1,
                                "title": "Top Tech Video",
                                "source_name": "Lex Fridman",
                                "why_it_matters": "Deep conversation on robotics.",
                            }
                        ]
                    },
                    "channels": [
                        {
                            "id": "lex-fridman",
                            "name": "Lex Fridman",
                            "category": "deep_explainer",
                            "notebook_url": "https://notebooklm.google.com/notebook/test",
                            "full_summary_html": "<p>Lex discussed AI robotics with engineers.</p>",
                        }
                    ],
                }
            },
        }
        rss_file = tmp_path / "feed.xml"
        generate_rss_feed(site_data, rss_file)

        assert rss_file.exists()
        content = rss_file.read_text(encoding="utf-8")
        assert '<?xml version="1.0" encoding="UTF-8" ?>' in content
        assert '<rss version="2.0">' in content
        assert '<title>TubeLM High-Signal Intelligence</title>' in content
        assert "Top Tech Video" in content
        assert "Lex Fridman" in content


class TestBuildReaderSite:
    def test_build_reader_site_end_to_end(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        audio_dir = tmp_path / "audio"
        site_dir = tmp_path / "site"
        summaries_dir.mkdir()
        audio_dir.mkdir()

        # Create sources.json
        sources_file = tmp_path / "sources.json"
        sources_file.write_text(json.dumps([
            {"name": "3Blue1Brown", "type": "youtube", "channel_id": "UC1", "category": "deep_explainer"},
            {"name": "ArxivSanity", "type": "rss", "url": "https://example.com/rss", "category": "tech"},
        ]))

        # Current week digest: 3Blue1Brown (2 videos + audio)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ch1_html = f"""
        <html><body>
          <h1>3Blue1Brown</h1>
          <a href="https://notebooklm.google.com/notebook/3b1b">Notebook</a>
          <div class="item-card"><h2>Essence of Linear Algebra</h2><div class="summary-html"><p>Geometric vectors</p></div></div>
          <div class="item-card"><h2>Neural Networks from Scratch</h2><div class="summary-html"><p>Backpropagation calculus</p></div></div>
        </body></html>
        """
        (summaries_dir / f"{now_str}_3Blue1Brown_digest.html").write_text(ch1_html, encoding="utf-8")
        audio_f = audio_dir / f"{now_str}_3Blue1Brown.mp3"
        audio_f.write_bytes(b"mock_mp3_data")

        # Top 20 digest
        top20_html = f"""
        <html><body>
          <h1>Top 20 Digest</h1>
          <table><tr>
            <td class="rank-cell">1</td>
            <td>
              <a href="https://youtube.com/watch?v=vectors"><h2 class="item-title">Linear Algebra</h2></a>
              <div style="text-transform: uppercase;">YOUTUBE / 3Blue1Brown / {now_str}</div>
              <p>Geometric intuition</p>
            </td>
          </tr></table>
        </body></html>
        """
        (summaries_dir / f"{now_str}_Top_20_Digest.html").write_text(top20_html, encoding="utf-8")

        # Previous week digest: 7 days ago
        prev_str = (datetime.now(timezone.utc).date() - timedelta(days=7)).strftime("%Y-%m-%d")
        ch2_html = f"""
        <html><body>
          <h1>ArxivSanity</h1>
          <a href="https://notebooklm.google.com/notebook/arxiv">Notebook</a>
          <div class="item-card"><h2>Attention is All You Need</h2><div class="summary-html"><p>Transformer models</p></div></div>
        </body></html>
        """
        (summaries_dir / f"{prev_str}_ArxivSanity_digest.html").write_text(ch2_html, encoding="utf-8")

        # Build reader site
        out_site = build_reader_site(summaries_dir, audio_dir, site_dir, sources_file)
        assert out_site == site_dir / "index.html"

        index_html = site_dir / "index.html"
        feed_xml = site_dir / "feed.xml"
        copied_audio = site_dir / "audio" / f"{now_str}_3Blue1Brown.mp3"

        assert index_html.exists()
        assert feed_xml.exists()
        assert copied_audio.exists()
        assert copied_audio.read_bytes() == b"mock_mp3_data"

        content = index_html.read_text(encoding="utf-8")
        assert "TubeLM" in content
        assert "3Blue1Brown" in content
        assert "ArxivSanity" in content
        assert "Linear Algebra" in content
        assert 'data-theme="light"' in content

    def test_read_state_embedding_and_retention(self, tmp_path, monkeypatch):
        import paths
        fake_data_dir = tmp_path / ".tubelm"
        fake_data_dir.mkdir(parents=True)
        monkeypatch.setattr(paths, "get_data_dir", lambda: fake_data_dir)

        # Seed read_state.json with a fresh and a stale entry
        now = datetime.now(timezone.utc).date()
        fresh_date = now.strftime("%Y-%m-%d")
        stale_date = (now - timedelta(days=20)).strftime("%Y-%m-%d")
        read_file = paths.get_read_state_file()
        read_file.write_text(json.dumps({
            "read_ids": [f"{fresh_date}_channel_a", f"{stale_date}_channel_old"]
        }))

        summaries_dir = tmp_path / "summaries"
        audio_dir = tmp_path / "audio"
        site_dir = tmp_path / "site"
        sources_file = tmp_path / "sources.json"
        summaries_dir.mkdir()
        audio_dir.mkdir()
        sources_file.write_text("[]")

        # Purge
        purge_old_digests_and_audio(summaries_dir, audio_dir, max_age_days=14)
        purged_read_state = json.loads(read_file.read_text())
        assert f"{fresh_date}_channel_a" in purged_read_state["read_ids"]
        assert f"{stale_date}_channel_old" not in purged_read_state["read_ids"]

        # Build site should embed read_ids
        build_reader_site(summaries_dir, audio_dir, site_dir, sources_file)
        site_html = (site_dir / "index.html").read_text()
        assert f"{fresh_date}_channel_a" in site_html


class TestVideoExtractionAndOptimization:
    def test_extract_youtube_video_id(self):
        from web_reader import extract_youtube_video_id
        assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1") == "dQw4w9WgXcQ"
        assert extract_youtube_video_id("https://example.com/not-youtube") == ""
        assert extract_youtube_video_id("") == ""

    def test_parse_channel_digest_extracts_video_id(self, tmp_path):
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        digest_file = tmp_path / "2026-09-04_TestChan_digest.html"
        digest_file.write_text("""
        <html><body>
          <h1>TestChan</h1>
          <div class="item-card">
            <h2>Frontier Models</h2>
            <a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ">Watch</a>
            <div class="summary-html"><p>Detailed summary</p></div>
          </div>
        </body></html>
        """, encoding="utf-8")

        parsed = parse_channel_digest(digest_file, {"TestChan": {"category": "tech"}}, audio_dir, "2026-09-04")
        assert parsed is not None
        assert len(parsed["videos"]) == 1
        assert parsed["videos"][0]["video_id"] == "dQw4w9WgXcQ"

    def test_optimize_audio_for_web(self, tmp_path):
        from web_reader import optimize_audio_for_web
        src = tmp_path / "in.mp3"
        src.write_bytes(b"dummy_data")
        dest = tmp_path / "out.mp3"

        # Even with dummy non-audio data where ffmpeg might fail, fallback gracefully copies file
        optimize_audio_for_web(src, dest)
        assert dest.exists()

    def test_build_reader_site_retains_original_audio_by_default(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        audio_dir = tmp_path / "audio"
        site_dir = tmp_path / "site"
        summaries_dir.mkdir()
        audio_dir.mkdir()

        sources_file = tmp_path / "sources.json"
        sources_file.write_text(json.dumps([
            {"name": "Think School", "type": "youtube", "channel_id": "UC1", "category": "deep_explainer"}
        ]))

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ch_html = f"""
        <html><body>
          <h1>Think School</h1>
          <div class="item-card"><h2>Indian Railways Part 1</h2></div>
          <div class="item-card"><h2>Indian Railways Part 2</h2></div>
        </body></html>
        """
        (summaries_dir / f"{now_str}_Think_School_digest.html").write_text(ch_html, encoding="utf-8")
        original_bytes = b"high_fidelity_uncompressed_audio_stream" * 1000
        src_audio = audio_dir / f"{now_str}_Think_School.mp3"
        src_audio.write_bytes(original_bytes)

        # 1. Default: compress_audio=False -> original audio retained bit-for-bit
        build_reader_site(summaries_dir, audio_dir, site_dir, sources_file, compress_audio=False)
        dest_audio = site_dir / "audio" / f"{now_str}_Think_School.mp3"
        assert dest_audio.exists()
        assert dest_audio.read_bytes() == original_bytes

    def test_build_reader_site_compress_audio_flag(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        import web_reader

        summaries_dir = tmp_path / "summaries"
        audio_dir = tmp_path / "audio"
        site_dir = tmp_path / "site"
        summaries_dir.mkdir()
        audio_dir.mkdir()

        sources_file = tmp_path / "sources.json"
        sources_file.write_text(json.dumps([
            {"name": "Think School", "type": "youtube", "channel_id": "UC1", "category": "deep_explainer"}
        ]))

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ch_html = f"""
        <html><body>
          <h1>Think School</h1>
          <div class="item-card"><h2>Indian Railways Part 1</h2></div>
          <div class="item-card"><h2>Indian Railways Part 2</h2></div>
        </body></html>
        """
        (summaries_dir / f"{now_str}_Think_School_digest.html").write_text(ch_html, encoding="utf-8")
        src_audio = audio_dir / f"{now_str}_Think_School.mp3"
        # Large mock size (> 15MB) to test compression trigger
        src_audio.write_bytes(b"0" * (16 * 1024 * 1024))

        mock_optimize = MagicMock(return_value=True)
        monkeypatch.setattr(web_reader, "optimize_audio_for_web", mock_optimize)

        build_reader_site(summaries_dir, audio_dir, site_dir, sources_file, compress_audio=True)
        assert mock_optimize.called

    def test_generate_pwa_assets(self, tmp_path):
        from web_reader import generate_pwa_assets
        site_dir = tmp_path / "pwa_site"
        generate_pwa_assets(site_dir)

        assert (site_dir / "icon.svg").exists()
        assert "#d9ff63" in (site_dir / "icon.svg").read_text()
        assert "TL" in (site_dir / "icon.svg").read_text()

        assert (site_dir / "apple-touch-icon.png").exists()
        assert (site_dir / "apple-touch-icon.png").stat().st_size > 0
        assert (site_dir / "apple-touch-icon-180x180.png").exists()
        assert (site_dir / "icon-192.png").exists()
        assert (site_dir / "icon-512.png").exists()
        assert (site_dir / "favicon-32x32.png").exists()

        manifest_file = site_dir / "manifest.json"
        assert manifest_file.exists()
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest["short_name"] == "TubeLM"
        assert manifest["display"] == "standalone"
        assert manifest["theme_color"] == "#d9ff63"
        assert any(i["src"] == "apple-touch-icon.png" for i in manifest["icons"])


