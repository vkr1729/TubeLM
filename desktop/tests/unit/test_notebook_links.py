from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
import threading
import time

import gui
from gui import (
    _latest_notebook_links,
    _load_notebook_links_cache,
    _save_notebook_links_cache,
)


def _notebook(identifier, title, sources_count, hour=0):
    return SimpleNamespace(
        id=identifier,
        title=title,
        sources_count=sources_count,
        created_at=datetime(2026, 8, 15, hour, tzinfo=timezone.utc),
    )


def test_latest_notebook_links_keeps_every_source_and_latest_week():
    links = _latest_notebook_links(
        [
            _notebook("a-old", "Aevy TV Digest — 2026-08-08", 5),
            _notebook("a-new", "Aevy TV Digest — 2026-08-15", 1),
            _notebook("b-new", "ColdFusion Digest — 2026-08-15", 3),
            _notebook("manual", "Research notes", 10),
        ]
    )

    assert links == {
        "Aevy TV": "https://notebooklm.google.com/notebook/a-new",
        "ColdFusion": "https://notebooklm.google.com/notebook/b-new",
    }


def test_latest_notebook_links_prefers_complete_duplicate_then_creation_time():
    title = "Aevy TV Digest — 2026-08-15"
    links = _latest_notebook_links(
        [
            _notebook("new-empty", title, 0, hour=3),
            _notebook("complete-old", title, 4, hour=1),
            _notebook("complete-new", title, 4, hour=2),
        ]
    )

    assert links["Aevy TV"].endswith("/complete-new")


def test_last_successful_workspace_index_round_trips_atomically(tmp_path, monkeypatch):
    cache_path = tmp_path / "notebook_links_cache.json"
    monkeypatch.setattr(
        gui.paths,
        "get_notebook_links_cache_file",
        lambda: cache_path,
    )
    expected = {
        "Aevy TV": "https://notebooklm.google.com/notebook/aevy",
        "ColdFusion": "https://notebooklm.google.com/notebook/coldfusion",
    }

    _save_notebook_links_cache(expected)

    assert _load_notebook_links_cache() == expected
    assert list(tmp_path.glob(".*.tmp")) == []


def test_workspace_endpoint_uses_successful_index_during_timeout(monkeypatch):
    expected = {
        "Aevy TV": "https://notebooklm.google.com/notebook/aevy",
    }
    monkeypatch.setattr(
        gui,
        "_fetch_real_notebooks",
        lambda: (_ for _ in ()).throw(TimeoutError()),
    )
    monkeypatch.setattr(gui, "_load_notebook_links_cache", lambda: expected)
    gui._invalidate_runtime_caches()

    with gui.app.test_client() as client:
        response = client.get("/api/notebooks")

    assert response.status_code == 200
    assert response.get_json() == expected


def test_simultaneous_workspace_requests_share_one_notebooklm_fetch(monkeypatch):
    calls = 0
    calls_lock = threading.Lock()
    notebook = _notebook("aevy", "Aevy TV Digest — 2026-08-15", 3)

    def slow_fetch():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return [notebook]

    monkeypatch.setattr(gui, "_fetch_real_notebooks", slow_fetch)
    monkeypatch.setattr(gui, "_save_notebook_links_cache", lambda _: None)
    monkeypatch.setattr(gui, "_notebook_state_mtime_ns", lambda: None)
    gui._invalidate_runtime_caches()

    def request_workspaces():
        with gui.app.test_client() as client:
            return client.get("/api/notebooks").get_json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: request_workspaces(), range(2)))

    assert calls == 1
    assert results[0] == results[1]
