from types import SimpleNamespace

import pytest

import weekly_video_service


def _artifact(artifact_id, title, *, completed):
    return SimpleNamespace(
        id=artifact_id,
        title=title,
        is_completed=completed,
        is_processing=not completed,
        is_pending=False,
    )


@pytest.mark.asyncio
async def test_completed_batch_rotates_and_downloads_with_channel_order(tmp_path, monkeypatch):
    manifest = tmp_path / "weekly.json"
    current = tmp_path / "TubeLM"
    previous = tmp_path / "TubeLM_Prev"
    current.mkdir()
    previous.mkdir()
    (current / "old.mp4").write_bytes(b"old")
    (previous / "stale.mp4").write_bytes(b"stale")

    monkeypatch.setattr(weekly_video_service.paths, "get_weekly_video_batches_file", lambda: manifest)
    monkeypatch.setattr(weekly_video_service.paths, "get_video_download_dir", lambda: current)
    monkeypatch.setattr(weekly_video_service.paths, "get_previous_video_download_dir", lambda: previous)

    weekly_video_service.register_weekly_video(
        notebook_id="nb-1",
        source_name="Doctor Alex",
        channel_order=3,
        source_ids=["source-1"],
        instructions="Make it cinematic.",
        week_start="2026-08-24",
    )
    weekly_video_service.seal_weekly_video_batch("2026-08-24")

    class Artifacts:
        async def list_video(self, _notebook_id):
            return [_artifact("video-1", "The Healthspan Blueprint", completed=True)]

        async def download_video(self, _notebook_id, output_path, artifact_id=None):
            assert artifact_id == "video-1"
            with open(output_path, "wb") as output:
                output.write(b"video")

    outcome = await weekly_video_service.resume_weekly_video_batches(
        SimpleNamespace(artifacts=Artifacts())
    )

    assert outcome["pending"] == 0
    assert [path.name for path in current.iterdir()] == [
        "TubeLM 03 - Doctor Alex - The Healthspan Blueprint.mp4"
    ]
    assert [path.name for path in previous.iterdir()] == ["old.mp4"]


@pytest.mark.asyncio
async def test_processing_video_stays_durable_for_next_poll(tmp_path, monkeypatch):
    manifest = tmp_path / "weekly.json"
    monkeypatch.setattr(weekly_video_service.paths, "get_weekly_video_batches_file", lambda: manifest)

    weekly_video_service.register_weekly_video(
        notebook_id="nb-1",
        source_name="Doctor Alex",
        channel_order=3,
        source_ids=["source-1"],
        instructions="Make it cinematic.",
        week_start="2026-08-24",
    )
    weekly_video_service.seal_weekly_video_batch("2026-08-24")

    class Artifacts:
        async def list_video(self, _notebook_id):
            return [_artifact("video-1", "", completed=False)]

    outcome = await weekly_video_service.resume_weekly_video_batches(
        SimpleNamespace(artifacts=Artifacts())
    )

    assert outcome["pending"] == 1
    assert outcome["deferred_until"] is not None
    batch = weekly_video_service._load_batches()[0]
    assert batch["entries"][0]["state"] == "processing"
    assert batch["entries"][0]["artifact_id"] == "video-1"
