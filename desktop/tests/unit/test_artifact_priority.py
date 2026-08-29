import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import main
import notebooklm_service


@pytest.mark.asyncio
async def test_artifacts_use_video_then_audio_and_skip_infographic(monkeypatch):
    events = []

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    async def record_audio(_client, _job):
        events.append("audio")
        return "completed"

    async def record_video(_client, _job):
        events.append("video")
        return "completed"

    async def record_infographic(_client, _job):
        events.append("infographic")
        return "completed"

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(
        notebooklm_service.NotebookLMClient,
        "from_storage",
        lambda **_kwargs: ClientContext(),
    )
    monkeypatch.setattr(notebooklm_service, "_resume_audio", record_audio)
    monkeypatch.setattr(notebooklm_service, "_resume_video", record_video)
    monkeypatch.setattr(notebooklm_service, "_resume_infographic", record_infographic)
    monkeypatch.setattr(notebooklm_service, "_existing_infographic_path", lambda *_: "")
    monkeypatch.setattr(notebooklm_service.asyncio, "sleep", no_sleep)

    outcome = await notebooklm_service.generate_artifacts_after_delivery(
        {
            "notebook_id": "notebook-1",
            "channel_name": "Personal feed",
            "source_ids": ["source-1", "source-2"],
            "audio_instructions": "Summarize it.",
        }
    )

    assert events == ["video", "audio"]
    assert outcome["rate_limited"] is False


@pytest.mark.asyncio
async def test_single_source_skips_audio(monkeypatch):
    events = []

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    async def record_video(_client, _job):
        events.append("video")
        return "completed"

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(
        notebooklm_service.NotebookLMClient,
        "from_storage",
        lambda **_kwargs: ClientContext(),
    )
    monkeypatch.setattr(notebooklm_service, "_resume_video", record_video)
    monkeypatch.setattr(notebooklm_service.asyncio, "sleep", no_sleep)

    result = {
        "notebook_id": "notebook-1",
        "channel_name": "Personal feed",
        "source_ids": ["source-1"],
        "audio_instructions": "Summarize it.",
    }
    await notebooklm_service.generate_artifacts_after_delivery(result)

    assert events == ["video"]
    assert result["audio_status"] == "skipped_single_source"


@pytest.mark.asyncio
async def test_audio_and_video_queues_advance_independently(monkeypatch):
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

    async def resume_video(_client):
        events.append("video")
        return {"pending": 0, "deferred_until": None, "rate_limited": False}

    async def no_deferred(**_kwargs):
        return {"pending": 0, "deferred_until": None, "rate_limited": False}

    monkeypatch.setattr(main, "pending_weekly_audio_count", lambda: 1)
    monkeypatch.setattr(main, "pending_weekly_video_count", lambda: 1)
    monkeypatch.setattr(main, "resume_weekly_audio_batches", resume_audio)
    monkeypatch.setattr(main, "resume_weekly_video_batches", resume_video)
    monkeypatch.setattr(main, "resume_deferred_artifacts", no_deferred)
    monkeypatch.setattr(main, "unnotified_completed_audio_batches", lambda: [])
    monkeypatch.setattr(main, "unnotified_completed_video_batches", lambda: [])
    monkeypatch.setattr(main, "save_compute_deferral", lambda *_: None)
    monkeypatch.setattr(
        main.NotebookLMClient, "from_storage", lambda **_kwargs: ClientContext()
    )

    completed = await main._finish_background_artifacts(
        SimpleNamespace(generate_infographics=False), seal_video_batch=False
    )

    assert completed is False
    assert events == ["audio", "video"]


def test_scheduling_queues_audio_but_only_opted_in_video(monkeypatch):
    events = []
    result = {
        "notebook_id": "notebook-1",
        "notebook_url": "https://notebooklm.google.com/notebook/notebook-1",
        "channel_name": "Personal feed",
        "source_ids": ["source-1", "source-2"],
        "audio_instructions": "Summarize it.",
    }
    monkeypatch.setattr(
        notebooklm_service,
        "register_weekly_audio",
        lambda **_kwargs: events.append("audio"),
    )
    monkeypatch.setattr(
        notebooklm_service,
        "register_weekly_video",
        lambda **_kwargs: events.append("video"),
    )

    notebooklm_service.schedule_artifacts_after_delivery(
        result, channel_order=1, generate_cinematic_video=False
    )
    notebooklm_service.schedule_artifacts_after_delivery(
        result, channel_order=1, generate_cinematic_video=True
    )

    assert events == ["audio", "video", "audio"]


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
