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


@pytest.mark.asyncio
async def test_interim_top10_triggered_at_seventy_percent_and_final_after_fast_retry(tmp_path, monkeypatch):
    class Handler:
        source_type = "youtube"
        category = "tech"

        def __init__(self, name):
            self.name = name

        def state_key(self):
            return f"youtube:{self.name}"

    handlers = [Handler(f"Chan{i}") for i in range(10)]
    item = SimpleNamespace(title="Video", url="https://example.com/video", published="2026-08-15")
    cfg = SimpleNamespace(
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="user",
        smtp_password="pass",
        sender_email="from@example.com",
        recipient_email="to@example.com",
        use_ssl=False,
        sources_file=tmp_path / "sources.json",
        state_file=tmp_path / "state.json",
        generate_top10_digest=True,
    )

    import email_service
    monkeypatch.setattr(email_service, "verify_smtp_connection", lambda _: None)
    monkeypatch.setattr(main, "send_channel_email", lambda *_: None)
    monkeypatch.setattr(main, "load_config", lambda: cfg)
    monkeypatch.setattr(main, "load_sources", lambda _: [h.name for h in handlers])
    name_to_handler = {h.name: h for h in handlers}
    monkeypatch.setattr(main, "create_handler", lambda src, _: name_to_handler[src])
    monkeypatch.setattr(main, "materialize_source_checkpoints", lambda *_: None)
    monkeypatch.setattr(main, "verify_notebooklm_auth", lambda: _true())
    monkeypatch.setattr(main, "resume_deferred_artifacts", _no_deferred_artifacts)
    monkeypatch.setattr(main, "_finish_background_artifacts", lambda *_, **__: _true())
    monkeypatch.setattr(main, "discover_sources", lambda selected, _: _discover(selected, item))

    attempt_counts = {}

    async def _mock_process(handler, items, _cfg):
        attempts = attempt_counts.get(handler.name, 0) + 1
        attempt_counts[handler.name] = attempts
        if handler.name in {"Chan7", "Chan8", "Chan9"} and attempts == 1:
            return {"channel_name": handler.name, "error": "Transient error"}
        return {
            "channel_name": handler.name,
            "source_type": "youtube",
            "notebook_url": "https://notebooklm.google.com/notebook/test",
            "summary_text": "## Video\n\nSummary.",
            "infographic_path": "",
            "videos": [],
            "error": None,
        }

    monkeypatch.setattr(main, "process_source_items", _mock_process)
    monkeypatch.setattr(main, "schedule_artifacts_after_delivery", lambda *_, **__: None)
    monkeypatch.setattr(main, "save_state", lambda *_: None)
    monkeypatch.setattr(main, "write_markdown_digest", lambda *_: tmp_path / "digest.md")
    monkeypatch.setattr(main.paths, "get_summaries_dir", lambda: tmp_path)

    sleep_delays = []
    async def _record_sleep(duration):
        sleep_delays.append(duration)
    monkeypatch.setattr(main.asyncio, "sleep", _record_sleep)

    top10_calls = []
    def _mock_top10(cfg, run_date, *, is_interim=False):
        top10_calls.append({"run_date": run_date, "is_interim": is_interim})
        return True
    monkeypatch.setattr(main, "generate_and_send_top10_digest", _mock_top10)
    monkeypatch.setattr(main, "prepare_top10_batch", lambda d: d)

    completed = await main.async_main(dry_run=False, skip_email=False)

    assert completed is True
    # Verify interim top10 was triggered after pass 1 (7/10 = 70%)
    assert len(top10_calls) == 2
    assert top10_calls[0]["is_interim"] is True
    assert top10_calls[1]["is_interim"] is False

    # Verify retry sleep delay was fast (30s), NOT 3600s!
    assert 30 in sleep_delays
    assert 3600 not in sleep_delays

