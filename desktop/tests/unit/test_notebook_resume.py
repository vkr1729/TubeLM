from types import SimpleNamespace

import pytest

from notebooklm_service import _get_or_create_daily_notebook


@pytest.mark.asyncio
async def test_reuses_most_complete_exact_title_notebook():
    title = "Aevy TV Digest — 2026-08-15"
    sparse = SimpleNamespace(id="sparse", title=title, created_at=None)
    complete = SimpleNamespace(id="complete", title=title, created_at=None)
    sources_by_notebook = {
        "sparse": [SimpleNamespace(id="one")],
        "complete": [SimpleNamespace(id="one"), SimpleNamespace(id="two")],
    }

    class Notebooks:
        async def list(self):
            return [sparse, complete]

        async def create(self, _):
            raise AssertionError("an exact-title notebook should have been reused")

    class Sources:
        async def list(self, notebook_id, strict=False):
            assert strict is True
            return sources_by_notebook[notebook_id]

    client = SimpleNamespace(notebooks=Notebooks(), sources=Sources())

    notebook, sources = await _get_or_create_daily_notebook(client, title)

    assert notebook.id == "complete"
    assert len(sources) == 2


@pytest.mark.asyncio
async def test_creates_notebook_only_when_exact_title_is_absent():
    created = SimpleNamespace(id="new", title="Aevy TV Digest — 2026-08-15")

    class Notebooks:
        async def list(self):
            return [SimpleNamespace(id="old", title="Aevy TV Digest — 2026-08-08")]

        async def create(self, title):
            assert title == created.title
            return created

    client = SimpleNamespace(notebooks=Notebooks())

    notebook, sources = await _get_or_create_daily_notebook(client, created.title)

    assert notebook.id == "new"
    assert sources == []
