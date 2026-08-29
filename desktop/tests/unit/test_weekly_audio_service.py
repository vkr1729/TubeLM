import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import weekly_audio_service


@pytest.mark.asyncio
async def test_completed_audio_batch_is_durable_and_ready_for_one_email(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "weekly-audio.json"
    monkeypatch.setattr(
        weekly_audio_service.paths,
        "get_weekly_audio_batches_file",
        lambda: manifest,
    )
    weekly_audio_service.register_weekly_audio(
        notebook_id="notebook-1",
        notebook_url="https://notebooklm.google.com/notebook/notebook-1",
        source_name="Doctor Alex",
        channel_order=3,
        source_ids=["source-1", "source-2"],
        instructions="Keep it concise.",
        week_start="2026-08-24",
    )
    weekly_audio_service.seal_weekly_audio_batch("2026-08-24")

    class Artifacts:
        async def list_audio(self, _notebook_id):
            return [SimpleNamespace(
                id="audio-1",
                title="A Better Longevity Plan",
                is_completed=True,
                is_processing=False,
                is_pending=False,
            )]

    outcome = await weekly_audio_service.resume_weekly_audio_batches(
        SimpleNamespace(artifacts=Artifacts())
    )

    assert outcome["pending"] == 0
    batches = weekly_audio_service.unnotified_completed_audio_batches()
    assert batches[0]["entries"][0]["artifact_title"] == "A Better Longevity Plan"
    weekly_audio_service.mark_audio_completion_email_sent("2026-08-24")
    assert weekly_audio_service.unnotified_completed_audio_batches() == []


@pytest.mark.asyncio
async def test_persisted_retry_time_survives_restart_without_api_call(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "weekly-audio.json"
    monkeypatch.setattr(
        weekly_audio_service.paths,
        "get_weekly_audio_batches_file",
        lambda: manifest,
    )
    retry_at = datetime.now(timezone.utc) + timedelta(hours=4)
    manifest.write_text(json.dumps({"batches": [{
        "week_start": "2026-08-24",
        "sealed": True,
        "completed": False,
        "not_before": retry_at.isoformat(),
        "entries": [{"notebook_id": "notebook-1", "state": "queued"}],
    }]}))

    class Artifacts:
        async def list_audio(self, _notebook_id):
            raise AssertionError("NotebookLM must not be called before the persisted time")

    outcome = await weekly_audio_service.resume_weekly_audio_batches(
        SimpleNamespace(artifacts=Artifacts())
    )

    assert outcome["pending"] == 1
    assert outcome["deferred_until"] == retry_at
