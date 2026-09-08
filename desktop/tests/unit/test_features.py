"""Unit tests for high-impact features: reading metrics, brief, dispatch markers."""
import json
from pathlib import Path

import web_reader
from web_reader import (
    _audio_seconds_for,
    _lead_for,
    _read_minutes_for,
    build_reader_site,
    parse_channel_digest,
    parse_channel_digest_json,
)

TEMPLATE = Path(__file__).resolve().parent.parent.parent / "templates" / "reader.html"


def _words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


class TestReadingMetrics:
    def test_read_minutes_460_words(self):
        words, minutes = _read_minutes_for(_words(460))
        assert words == 460
        assert minutes == 2

    def test_read_minutes_minimum_one(self):
        assert _read_minutes_for("")[1] == 1
        assert _read_minutes_for(_words(10))[1] == 1

    def test_lead_truncation(self):
        lead = _lead_for(_words(100))
        assert len(lead.split()) == 60
        assert lead.endswith("…")
        short = _lead_for(_words(10))
        assert short == _words(10)
        assert not short.endswith("…")

    def test_audio_seconds_size_estimate(self, tmp_path):
        f = tmp_path / "x.mp3"
        f.write_bytes(b"x" * 16000)
        assert _audio_seconds_for(str(f)) == 1
        assert _audio_seconds_for(str(tmp_path / "missing.mp3")) == 0
        assert _audio_seconds_for(None) == 0

    def test_json_path_metrics(self, tmp_path, monkeypatch):
        import paths

        audio = tmp_path / "audio"
        audio.mkdir()
        (audio / "2026-09-08_Test_Ch.mp3").write_bytes(b"x" * 16000)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({
            "run_date": "2026-09-08",
            "channel_name": "Test Ch",
            "category": "tech",
            "notebook_url": "",
            "summary_text": _words(460),
            "items": [
                {"title": "V1", "url": "https://example.com/1", "published": "", "video_id": ""},
                {"title": "V2", "url": "https://example.com/2", "published": "", "video_id": ""},
            ],
        }))
        monkeypatch.setattr(paths, "get_audio_dir", lambda: audio)
        got = parse_channel_digest_json(sidecar, {}, audio)
        assert got["word_count"] == 460
        assert got["read_minutes"] == 2
        assert got["audio_seconds"] == 1
        assert len(got["brief"]) == 2
        assert len(got["brief"][0]["lead"].split()) == 60
        assert got["brief"][0]["lead"].endswith("…")

    def test_html_fallback_same_fields(self, tmp_path, monkeypatch):
        import paths

        audio = tmp_path / "audio"
        audio.mkdir()
        html = tmp_path / "2026-09-08_Test_Ch_digest.html"
        html.write_text(
            "<html><body><h1>Test Ch</h1>"
            + "".join(
                f'<div class="item-card"><h2>V{i}</h2>'
                f'<div class="summary-html"><p>{_words(70)}</p></div></div>'
                for i in (1, 2)
            )
            + "</body></html>"
        )
        monkeypatch.setattr(paths, "get_audio_dir", lambda: audio)
        got = parse_channel_digest(html, {}, audio, "2026-09-08")
        assert got["word_count"] == 140
        assert got["read_minutes"] == 1
        assert got["audio_seconds"] == 0
        assert len(got["brief"]) == 2
        assert len(got["brief"][0]["lead"].split()) == 60
        assert got["brief"][0]["lead"].endswith("…")

    def test_week_aggregates(self, tmp_path, monkeypatch):
        import paths

        summaries = tmp_path / "summaries"
        audio = tmp_path / "audio"
        site = tmp_path / "site"
        summaries.mkdir()
        audio.mkdir()
        sources = tmp_path / "sources.json"
        sources.write_text(json.dumps([
            {"name": "Chan A", "type": "rss", "url": "https://example.com/rss", "category": "tech"},
            {"name": "Chan B", "type": "rss", "url": "https://example.com/rss2", "category": "tech"},
        ]))
        for name, nwords in (("Chan_A", 460), ("Chan_B", 100)):
            (summaries / f"2026-09-08_{name}_digest.html").write_text(
                f"<html><body><h1>{name.replace('_', ' ')}</h1>"
                f'<div class="item-card"><h2>V1</h2><div class="summary-html"><p>{_words(nwords)}</p></div></div>'
                f'<div class="item-card"><h2>V2</h2><div class="summary-html"><p>{_words(nwords)}</p></div></div>'
                "</body></html>"
            )
        monkeypatch.setattr(paths, "get_audio_dir", lambda: audio)
        monkeypatch.setattr(paths, "get_read_state_file", lambda: tmp_path / "read.json")
        for key in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_DOMAIN"):
            monkeypatch.delenv(key, raising=False)
        build_reader_site(summaries, audio, site, sources)
        index = (site / "index.html").read_text(encoding="utf-8")
        assert "Chan A" in index and "Chan B" in index


class TestTemplateMarkers:
    def test_feature1_playlist_markers(self):
        t = TEMPLATE.read_text(encoding="utf-8")
        for marker in ("miniPlayer", "buildQueue", "playAllUnheard", "tubelm_player",
                       "tubelm_heard:", "MediaMetadata", "setPositionState",
                       "previoustrack", "nexttrack", "cyclePlayerSpeed"):
            assert marker in t, marker

    def test_feature2_brief_markers(self):
        t = TEMPLATE.read_text(encoding="utf-8")
        for marker in ("mode-brief", "briefView", "unread-summary", "tubelm_mode",
                       "Mark all above as read", "Read full"):
            assert marker in t, marker

    def test_feature3_dispatch_markers(self):
        t = TEMPLATE.read_text(encoding="utf-8")
        for marker in ("playVideo", "tubelm_player_pref", "youtube://watch?v=",
                       "Open in YouTube", "data-player-pref"):
            assert marker in t, marker
        assert "cdn.tailwindcss.com" not in t

    def test_feature4_sinking_markers(self):
        t = TEMPLATE.read_text(encoding="utf-8")
        for marker in ("tubelm_top20_read", "isTopItemRead", "toggleTopItemRead",
                       "Hide Seen", "Seen", "unreadChannels", "sortedPicks"):
            assert marker in t, marker
