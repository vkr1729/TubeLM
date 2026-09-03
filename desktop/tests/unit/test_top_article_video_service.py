import json
from pathlib import Path
from types import SimpleNamespace
import pytest

import top_article_video_service


@pytest.fixture
def top_selection():
    return {
        "run_date": "2026-08-29",
        "items": [
            {
                "rank": 1,
                "source_name": "MIT Tech Review",
                "source_type": "webpage",
                "title": "OpenAI Agents Analysis",
                "url": "https://example.com/openai-agents",
                "summary": "Detailed technical analysis of OpenAI agents.",
            },
            {
                "rank": 2,
                "source_name": "Caleb Writes Code",
                "source_type": "youtube",
                "title": "Jalapeno Chip",
                "url": "https://www.youtube.com/watch?v=12345678901",
                "video_id": "12345678901",
            },
            {
                "rank": 3,
                "source_name": "Research Daily",
                "source_type": "rss",
                "title": "Novel Cancer Vaccine Study",
                "url": "https://example.com/vaccine-study",
                "summary": "Phase 3 clinical trial findings on personalized vaccines.",
            },
        ],
    }


def test_register_top_article_videos(tmp_path, monkeypatch, top_selection):
    manifest_path = tmp_path / "top_article_videos.json"
    monkeypatch.setattr(top_article_video_service.paths, "get_top_article_videos_file", lambda: manifest_path)

    registered = top_article_video_service.register_top_article_videos(top_selection)

    assert len(registered) == 2
    assert registered[0]["rank"] == 1
    assert registered[0]["title"] == "OpenAI Agents Analysis"
    assert registered[0]["filename"] == "01 - MIT Tech Review - OpenAI Agents Analysis.mp4"
    assert registered[1]["rank"] == 3
    assert registered[1]["title"] == "Novel Cancer Vaccine Study"
    assert registered[1]["filename"] == "03 - Research Daily - Novel Cancer Vaccine Study.mp4"

    # Idempotent re-registration
    again = top_article_video_service.register_top_article_videos(top_selection)
    assert len(again) == 2

    data = json.loads(manifest_path.read_text())
    assert len(data["jobs"]) == 2
    assert top_article_video_service.pending_top_article_video_count() == 2


@pytest.mark.asyncio
async def test_process_top_article_videos_lifecycle(tmp_path, monkeypatch, top_selection):
    manifest_path = tmp_path / "top_article_videos.json"
    download_dir = tmp_path / "Top_10"
    monkeypatch.setattr(top_article_video_service.paths, "get_top_article_videos_file", lambda: manifest_path)
    monkeypatch.setattr(top_article_video_service.paths, "get_top10_video_download_dir", lambda: download_dir)

    top_article_video_service.register_top_article_videos(top_selection)

    created_notebooks = []
    created_sources = []
    generated_videos = []
    downloaded_videos = []

    class MockArtifact:
        def __init__(self, task_id, is_completed=False, is_failed=False):
            self.id = task_id
            self.task_id = task_id
            self.artifact_type = "video"
            self.is_completed = is_completed
            self.is_failed = is_failed

    class MockNotebooks:
        async def create(self, title):
            nb_id = f"nb-{len(created_notebooks) + 1}"
            created_notebooks.append((nb_id, title))
            return SimpleNamespace(id=nb_id, title=title)

    class MockSources:
        async def add_url(self, notebook_id, url):
            src_id = f"src-{url}"
            created_sources.append((notebook_id, url))
            return SimpleNamespace(id=src_id)

        async def add_text(self, notebook_id, title, content):
            src_id = f"src-{title}"
            created_sources.append((notebook_id, title, content))
            return SimpleNamespace(id=src_id)

    class MockArtifacts:
        async def generate_cinematic_video(self, notebook_id, source_ids=None, instructions=None):
            task_id = f"task-{notebook_id}"
            generated_videos.append((notebook_id, source_ids, instructions))
            return SimpleNamespace(task_id=task_id, id=task_id, is_failed=False)

        async def list(self, notebook_id):
            return [MockArtifact(f"task-{notebook_id}", is_completed=True)]

        async def download_video(self, notebook_id, output_path, artifact_id=None):
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"dummy mp4 video bytes")
            downloaded_videos.append((notebook_id, output_path))

    client = SimpleNamespace(
        notebooks=MockNotebooks(),
        sources=MockSources(),
        artifacts=MockArtifacts(),
    )

    # Step 1: Trigger generation
    outcome = await top_article_video_service.process_top_article_videos(client, dest_dir=download_dir)

    assert len(created_notebooks) == 2
    assert len(generated_videos) == 2
    assert len(downloaded_videos) == 2
    assert (download_dir / "01 - MIT Tech Review - OpenAI Agents Analysis.mp4").exists()
    assert (download_dir / "03 - Research Daily - Novel Cancer Vaccine Study.mp4").exists()
    assert outcome["pending"] == 0
