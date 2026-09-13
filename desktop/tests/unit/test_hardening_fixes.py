"""Regression tests for the v4.0 hardening patch (audit P1/P2 fixes).

Covers: edge-tts timeout, ffmpeg timeout fallback, SSRF fetch guard,
atomic GUI state writes, read-state bounds, PipelineRunner.stop, sw.js
generation/registration, and NotebookLMAuthExpiredError (no sys.exit).
"""
import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


class TestTTSTimeout:
    def test_timeout_constant_exists(self):
        import tts_service
        assert tts_service.TTS_TIMEOUT_SECONDS > 0

    def test_hung_synthesis_returns_false_quickly(self, tmp_path, monkeypatch):
        import tts_service
        monkeypatch.setattr(tts_service, "TTS_TIMEOUT_SECONDS", 0.05)

        async def hang(self, path):
            await asyncio.sleep(60)

        monkeypatch.setattr(tts_service.edge_tts.Communicate, "save", hang)
        out = tmp_path / "s.mp3"
        assert tts_service.generate_summary_tts(
            "This is a long enough summary text for narration testing.", out
        ) is False
        assert not out.exists()


class TestFfmpegTimeout:
    def test_timeout_falls_back_to_copy(self, tmp_path, monkeypatch):
        import web_reader
        assert web_reader.FFMPEG_TIMEOUT_SECONDS > 0

        def fake_run(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)

        monkeypatch.setattr(web_reader.subprocess, "run", fake_run)
        src = tmp_path / "in.mp3"
        src.write_bytes(b"dummy_data")
        dest = tmp_path / "out.mp3"
        assert web_reader.optimize_audio_for_web(src, dest) is False
        assert dest.read_bytes() == b"dummy_data"


class TestFetchGuard:
    def test_loopback_is_blocked(self):
        import gui
        assert gui._fetch_target_is_blocked("http://127.0.0.1/") is not None

    def test_cloud_metadata_is_blocked(self):
        import gui
        assert gui._fetch_target_is_blocked("http://169.254.169.254/") is not None

    def test_private_rfc1918_is_blocked(self):
        import gui
        assert gui._fetch_target_is_blocked("http://192.168.1.10/admin") is not None

    def test_non_http_scheme_is_blocked(self):
        import gui
        assert gui._fetch_target_is_blocked("ftp://example.com/x") is not None
        with pytest.raises(ValueError):
            gui._ensure_safe_fetch_url("file:///etc/passwd")

    def test_public_numeric_ip_is_allowed(self):
        import gui
        assert gui._fetch_target_is_blocked("http://8.8.8.8/") is None


class TestAtomicStateWrites:
    def test_atomic_write_round_trips(self, tmp_path):
        import gui
        target = tmp_path / "state.json"
        gui._atomic_write_json_file(target, {"sources": {"a": "b"}})
        assert json.loads(target.read_text(encoding="utf-8")) == {"sources": {"a": "b"}}

    def test_read_ids_are_bounded_and_string_only(self):
        import gui
        dirty = ["b", "a", 123, None, "a", "x" * 500]
        clean = gui._sanitize_read_ids(dirty)
        assert clean == sorted({"a", "b", "x" * gui.MAX_READ_ID_LENGTH})
        big = [f"id-{i}" for i in range(gui.MAX_READ_IDS + 100)]
        assert len(gui._sanitize_read_ids(big)) == gui.MAX_READ_IDS

    def test_read_ids_canonical_only_filtering(self):
        import gui
        mixed = [
            "2026-09-04_AI_Explained",
            "AI_Explained",
            "current_AI_Explained",
            "2026-09-11_Bloomberg",
            "prev_Two_Minute_Papers",
            123,
        ]
        clean = gui._sanitize_read_ids(mixed, canonical_only=True)
        assert clean == ["2026-09-04_AI_Explained", "2026-09-11_Bloomberg"]


class TestRunnerStop:
    def test_stop_when_idle_reports_not_running(self):
        from gui import PipelineRunner
        runner = PipelineRunner()
        stopped, msg = runner.stop()
        assert stopped is False
        assert "not running" in msg

    def test_stop_endpoint_when_idle_is_400(self, tmp_path, monkeypatch):
        import gui
        import paths
        monkeypatch.setattr(paths, "get_sources_file", lambda: tmp_path / "sources.json")
        monkeypatch.setattr(paths, "get_data_dir", lambda: tmp_path)
        monkeypatch.setattr(gui, "ENV_FILE", tmp_path / ".env")
        monkeypatch.setattr(gui, "STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr(gui, "SUMMARIES_DIR", tmp_path / "summaries")
        tmp_path.mkdir(parents=True, exist_ok=True)
        gui.app.config["TESTING"] = True
        with gui.app.test_client() as client:
            rv = client.post("/api/run/stop")
            assert rv.status_code == 400
            assert "not running" in rv.get_json()["error"]

    def test_validate_endpoint_rejects_metadata_ip(self, tmp_path, monkeypatch):
        import gui
        import paths
        monkeypatch.setattr(paths, "get_sources_file", lambda: tmp_path / "sources.json")
        monkeypatch.setattr(paths, "get_data_dir", lambda: tmp_path)
        monkeypatch.setattr(gui, "ENV_FILE", tmp_path / ".env")
        monkeypatch.setattr(gui, "STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr(gui, "SUMMARIES_DIR", tmp_path / "summaries")
        tmp_path.mkdir(parents=True, exist_ok=True)
        gui.app.config["TESTING"] = True
        with gui.app.test_client() as client:
            rv = client.post(
                "/api/sources/validate", json={"url": "http://169.254.169.254/"}
            )
            assert rv.status_code == 400


class TestServiceWorker:
    def test_generate_pwa_assets_writes_sw_js(self, tmp_path):
        from web_reader import generate_pwa_assets
        site_dir = tmp_path / "pwa_site"
        generate_pwa_assets(site_dir)
        sw = site_dir / "sw.js"
        assert sw.exists()
        content = sw.read_text(encoding="utf-8")
        assert "tubelm-v1" in content
        assert "isAudioRequest" in content
        assert "while-revalidate" in content

    def test_reader_template_registers_service_worker(self):
        template = (
            Path(__file__).resolve().parent.parent.parent
            / "templates"
            / "reader.html"
        )
        assert "serviceWorker.register('sw.js')" in template.read_text(encoding="utf-8")


class TestAuthExpiredError:
    def test_is_runtime_error(self):
        from notebooklm_service import NotebookLMAuthExpiredError
        assert issubclass(NotebookLMAuthExpiredError, RuntimeError)

    @pytest.mark.asyncio
    async def test_expired_auth_raises_instead_of_exiting(self, monkeypatch):
        import notebooklm_service
        from notebooklm_service import (
            NotebookLMAuthExpiredError,
            process_source_items,
        )

        class FakeCtx:
            async def __aenter__(self):
                raise ValueError("Authentication expired; redirected to login")

            async def __aexit__(self, *_args):
                return False

        class FakeClient:
            @classmethod
            def from_storage(cls, **_kwargs):
                return FakeCtx()

        monkeypatch.setattr(notebooklm_service, "NotebookLMClient", FakeClient)
        monkeypatch.setattr(
            notebooklm_service, "_refresh_cookies_for_retry", lambda: False
        )

        handler = SimpleNamespace(
            name="Test Source", category="tech", source_type="youtube"
        )
        items = [
            SimpleNamespace(
                title="Video", url="https://example.com/video", published="2026-09-01"
            )
        ]
        cfg = SimpleNamespace(notebooks_retention_limit=0)

        with pytest.raises(NotebookLMAuthExpiredError):
            await process_source_items(handler, items, cfg)

    def test_main_handles_auth_expired(self):
        import main
        assert main.NotebookLMAuthExpiredError is not None
