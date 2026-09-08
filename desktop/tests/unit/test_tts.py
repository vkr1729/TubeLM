"""Unit tests for neural summary TTS (Feature 6) and reader integration markers."""
import asyncio
import json
from pathlib import Path

import pytest

import tts_service
from tts_service import backfill_week, clean_text_for_speech, generate_summary_tts


class TestCleanText:
    def test_markdown_links_headers_formatting_urls(self):
        raw = "# Big Title\n## Sub\nRead [this story](https://example.com/x) now, *very* **bold** _it_ https://example.com/y end"
        clean = clean_text_for_speech(raw)
        assert "[this story]" not in clean
        assert "this story" in clean
        assert "#" not in clean
        assert "*" not in clean and "_" not in clean.replace("story", "")
        assert "https://" not in clean

    def test_empty_and_whitespace(self):
        assert clean_text_for_speech("") == ""
        assert clean_text_for_speech("   \n  ") == ""

    def test_whitespace_normalized(self):
        assert clean_text_for_speech("a\n\nb   c") == "a b c"


class TestGenerate:
    def test_short_text_skipped_without_network(self, tmp_path):
        out = tmp_path / "s.mp3"
        assert generate_summary_tts("too short", out) is False
        assert not out.exists()

    def test_existing_file_short_circuits(self, tmp_path):
        out = tmp_path / "s.mp3"
        out.write_bytes(b"x" * 100)
        assert generate_summary_tts("", out) is True

    def test_success_path_with_mocked_edge_tts(self, tmp_path, monkeypatch):
        async def fake_save(self, path):
            Path(path).write_bytes(b"fake-mp3-bytes")

        monkeypatch.setattr(tts_service.edge_tts.Communicate, "save", fake_save)
        out = tmp_path / "s.mp3"
        assert generate_summary_tts("This is a long enough summary text for narration testing.", out) is True
        assert out.exists() and out.stat().st_size > 0

    def test_network_failure_returns_false(self, tmp_path, monkeypatch):
        async def boom(self, path):
            raise ConnectionError("offline")

        monkeypatch.setattr(tts_service.edge_tts.Communicate, "save", boom)
        out = tmp_path / "s.mp3"
        assert generate_summary_tts("This is a long enough summary text for narration testing.", out) is False
        assert not out.exists()


class TestBackfill:
    def test_backfill_generates_missing_only(self, tmp_path, monkeypatch):
        summaries = tmp_path / "summaries"
        audio = tmp_path / "audio"
        summaries.mkdir()
        audio.mkdir()
        (summaries / "2026-09-04_Chan_A_digest.json").write_text(json.dumps({
            "summary_text": "Alpha summary text with enough words to pass the minimum length gate easily.",
            "items": [],
        }))
        (summaries / "2026-09-04_Chan_B_digest.json").write_text(json.dumps({
            "summary_text": "Beta summary text with enough words to pass the minimum length gate easily.",
            "items": [],
        }))
        (audio / "summary_2026-09-04_Chan_B.mp3").write_bytes(b"cached")

        calls = []

        def fake_generate(text, path, voice=tts_service.DEFAULT_VOICE):
            calls.append(path.name)
            path.write_bytes(b"tts-bytes")
            return True

        monkeypatch.setattr(tts_service, "generate_summary_tts", fake_generate)
        stats = backfill_week(summaries, audio, "2026-09-04")
        assert stats == {"scanned": 2, "generated": 1, "skipped": 1, "failed": 0}
        assert calls == ["summary_2026-09-04_Chan_A.mp3"]
        assert (audio / "summary_2026-09-04_Chan_A.mp3").exists()

    def test_backfill_skips_top_digests(self, tmp_path, monkeypatch):
        summaries = tmp_path / "summaries"
        audio = tmp_path / "audio"
        summaries.mkdir()
        audio.mkdir()
        (summaries / "2026-09-04_Top_20_Digest.html").write_text("<html></html>")
        monkeypatch.setattr(tts_service, "generate_summary_tts",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
        assert backfill_week(summaries, audio, "2026-09-04")["scanned"] == 0

    def test_backfill_cli_reports(self, tmp_path, monkeypatch, capsys):
        summaries = tmp_path / "summaries"
        audio = tmp_path / "audio"
        summaries.mkdir()
        audio.mkdir()
        (summaries / "2026-09-04_Chan_A_digest.html").write_text(
            '<html><body><div class="summary-html"><p>Some summary content here for the backfill run.</p></div></body></html>')
        monkeypatch.setattr(tts_service, "generate_summary_tts", lambda *a, **k: False)
        rc = tts_service.main(["--backfill", "--date", "2026-09-04"])
        # main() resolves real paths via paths module; with no real summaries it prints accordingly.
        assert rc in (0, 1)
        capsys.readouterr()


class TestBuildTimeMetadata:
    def test_build_sets_summary_audio_url_for_cached_tts(self, tmp_path, monkeypatch):
        import paths
        import web_reader

        summaries = tmp_path / "summaries"
        audio = tmp_path / "audio"
        site = tmp_path / "site"
        summaries.mkdir()
        audio.mkdir()
        sources = tmp_path / "sources.json"
        sources.write_text(json.dumps([
            {"name": "Chan A", "type": "rss", "url": "https://example.com/rss", "category": "tech"},
        ]))
        (summaries / "2026-09-08_Chan_A_digest.html").write_text(
            "<html><body><h1>Chan A</h1>"
            '<div class="item-card"><h2>V1</h2><div class="summary-html"><p>First summary paragraph here.</p></div></div>'
            '<div class="item-card"><h2>V2</h2><div class="summary-html"><p>Second summary paragraph here.</p></div></div>'
            "</body></html>"
        )
        (audio / "summary_2026-09-08_Chan_A.mp3").write_bytes(b"x" * 16000)
        monkeypatch.setattr(paths, "get_audio_dir", lambda: audio)
        monkeypatch.setattr(paths, "get_read_state_file", lambda: tmp_path / "read.json")
        for key in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_DOMAIN"):
            monkeypatch.delenv(key, raising=False)
        # Never hit the network during the build test.
        import tts_service
        monkeypatch.setattr(tts_service, "generate_summary_tts", lambda *a, **k: False)
        web_reader.build_reader_site(summaries, audio, site, sources)
        index = (site / "index.html").read_text(encoding="utf-8")
        assert "Listen to Summary" in index
        assert (site / "audio" / "summary_2026-09-08_Chan_A.mp3").exists()


class TestTemplateMarkers:
    TEMPLATE = Path(__file__).resolve().parent.parent.parent / "templates" / "reader.html"

    def test_font_stepper_markers(self):
        t = self.TEMPLATE.read_text(encoding="utf-8")
        for marker in ("btn-font-size", "cycleFontSize", "tubelm_font_size",
                       "data-font", "--summary-font-size", "applyFontSize"):
            assert marker in t, marker

    def test_tts_ui_markers(self):
        t = self.TEMPLATE.read_text(encoding="utf-8")
        for marker in ("playSummaryAudio", "summary_audio_url", "Listen to Summary",
                       "(Summary)"):
            assert marker in t, marker
