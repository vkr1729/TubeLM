from pathlib import Path
from types import SimpleNamespace

import pytest

import main


@pytest.mark.asyncio
async def test_each_channel_is_checkpointed_before_the_next_is_processed(tmp_path, monkeypatch):
    events = []

    class Handler:
        source_type = "youtube"
        category = "tech"

        def __init__(self, name):
            self.name = name

        def state_key(self):
            return f"youtube:{self.name}"

    handlers = [Handler("First"), Handler("Second")]
    item = SimpleNamespace(title="Video", url="https://example.com/video", published="2026-08-15")
    cfg = SimpleNamespace(
        smtp_server="smtp.example.com",
        smtp_username="user",
        smtp_password="pass",
        sender_email="from@example.com",
        recipient_email="to@example.com",
        sources_file=tmp_path / "sources.json",
        state_file=tmp_path / "state.json",
    )

    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "load_sources", lambda _: ["first", "second"])
    monkeypatch.setattr(main, "create_handler", lambda source, _: handlers[0] if source == "first" else handlers[1])
    monkeypatch.setattr(main, "materialize_source_checkpoints", lambda *_: None)
    monkeypatch.setattr(main, "verify_notebooklm_auth", lambda: _true())
    monkeypatch.setattr(main, "resume_deferred_artifacts", _no_deferred_artifacts)
    monkeypatch.setattr(main, "discover_sources", lambda selected, _: _discover(selected, item))
    monkeypatch.setattr(main, "process_source_items", lambda handler, items, _: _process(handler, events))
    monkeypatch.setattr(
        main,
        "schedule_artifacts_after_delivery",
        lambda result, **_kwargs: events.append(("artifacts_queued", result["channel_name"])),
    )
    monkeypatch.setattr(main, "seal_weekly_video_batch", lambda: None)
    monkeypatch.setattr(main, "seal_weekly_audio_batch", lambda: None)
    monkeypatch.setattr(main, "pending_weekly_video_count", lambda: 0)
    monkeypatch.setattr(main, "pending_weekly_audio_count", lambda: 0)
    monkeypatch.setattr(main, "unnotified_completed_audio_batches", lambda: [])
    monkeypatch.setattr(main, "unnotified_completed_video_batches", lambda: [])
    monkeypatch.setattr(main, "save_state", lambda _, keys: events.append(("checkpoint", keys[0])))
    monkeypatch.setattr(main, "write_markdown_digest", lambda *_: tmp_path / "digest.md")
    monkeypatch.setattr(main.paths, "get_summaries_dir", lambda: tmp_path)
    monkeypatch.setattr(main.asyncio, "sleep", _no_sleep)

    completed = await main.async_main(dry_run=False, skip_email=True)

    assert completed is True
    assert events == [
        ("process", "First"),
        ("artifacts_queued", "First"),
        ("checkpoint", "youtube:First"),
        ("process", "Second"),
        ("artifacts_queued", "Second"),
        ("checkpoint", "youtube:Second"),
    ]


async def _true():
    return True


async def _discover(handlers, item):
    return [(handler, [item]) for handler in handlers]


async def _no_deferred_artifacts(**_kwargs):
    return {"pending": 0, "rate_limited": False, "deferred_until": None}


async def _process(handler, events):
    events.append(("process", handler.name))
    return {
        "channel_name": handler.name,
        "source_type": "youtube",
        "notebook_url": "https://notebooklm.google.com/notebook/test",
        "summary_text": "## Video\n\nA complete summary.",
        "infographic_path": "",
        "videos": [],
        "error": None,
    }


async def _no_sleep(_):
    return None
