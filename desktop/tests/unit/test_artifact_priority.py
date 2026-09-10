import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import main
import notebooklm_service


def test_single_source_skips_audio(monkeypatch):
    called = []
    monkeypatch.setattr(
        notebooklm_service,
        "register_weekly_audio",
        lambda **kwargs: called.append(kwargs),
    )

    result = {
        "notebook_id": "notebook-1",
        "channel_name": "Personal feed",
        "source_ids": ["source-1"],
        "audio_instructions": "Summarize it.",
    }
    notebooklm_service.schedule_artifacts_after_delivery(
        result, channel_order=1, generate_audio_overview=True
    )

    assert called == []
    assert result["audio_status"] == "skipped_single_source"


def test_scheduling_queues_audio_when_enabled(monkeypatch):
    events = []
    result = {
        "notebook_id": "notebook-1",
        "notebook_url": "https://notebooklm.google.com/notebook/notebook-1",
        "channel_name": "Tech Weekly",
        "source_ids": ["source-1", "source-2"],
        "audio_instructions": "Summarize it.",
    }
    monkeypatch.setattr(
        notebooklm_service,
        "register_weekly_audio",
        lambda **kwargs: events.append(kwargs),
    )

    # Disabled by default
    notebooklm_service.schedule_artifacts_after_delivery(
        result, channel_order=1, generate_audio_overview=False
    )
    assert events == []
    assert result["audio_status"] == "disabled"

    # Queues when opted-in
    notebooklm_service.schedule_artifacts_after_delivery(
        result, channel_order=1, generate_audio_overview=True
    )
    assert len(events) == 1
    assert events[0]["source_name"] == "Tech Weekly"


@pytest.mark.asyncio
async def test_audio_queue_advances_and_handles_deferral(monkeypatch):
    events = []
    retry_at = datetime.now(timezone.utc) + timedelta(hours=5)

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    async def resume_audio(_client):
        events.append("audio")
        return {"pending": 1, "deferred_until": retry_at, "rate_limited": True}

    monkeypatch.setattr(main, "pending_weekly_audio_count", lambda: 1)
    monkeypatch.setattr(main, "resume_weekly_audio_batches", resume_audio)
    monkeypatch.setattr(main, "unnotified_completed_audio_batches", lambda: [])
    deferrals = []
    monkeypatch.setattr(main, "save_compute_deferral", lambda *args: deferrals.append(args))
    monkeypatch.setattr(
        main.NotebookLMClient, "from_storage", lambda **_kwargs: ClientContext()
    )

    completed = await main._finish_background_artifacts(
        SimpleNamespace(), seal_audio_batch=False
    )

    ok, _new_audio = completed
    assert ok is False
    assert events == ["audio"]
    assert len(deferrals) == 1


@pytest.mark.asyncio
async def test_dry_run_never_resumes_artifacts(tmp_path, monkeypatch):
    cfg = SimpleNamespace(
        smtp_server="",
        smtp_username="",
        smtp_password="",
        sender_email="",
        recipient_email="",
        sources_file=tmp_path / "sources.json",
        state_file=tmp_path / "state.json",
    )

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("dry run must not touch the artifact queues")

    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "load_sources", lambda _path: [])
    monkeypatch.setattr(main, "_finish_background_artifacts", must_not_run)

    assert await main.async_main(dry_run=True, skip_email=True) is True
