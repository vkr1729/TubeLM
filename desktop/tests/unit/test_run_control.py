import threading
import time
from datetime import datetime, timedelta, timezone

from run_control import (
    PipelineAlreadyRunningError,
    PipelineRunLock,
    clear_resume_request,
    get_shutdown_command,
    is_pipeline_running,
    load_compute_deferral,
    load_resume_request,
    save_compute_deferral,
    save_resume_request,
)


def test_pipeline_lock_blocks_a_second_process_handle(tmp_path):
    lock_path = tmp_path / "pipeline.lock"
    with PipelineRunLock(lock_path):
        assert is_pipeline_running(lock_path) is True
        try:
            PipelineRunLock(lock_path).acquire()
        except PipelineAlreadyRunningError:
            pass
        else:
            raise AssertionError("second lock unexpectedly succeeded")
    assert is_pipeline_running(lock_path) is False


def test_pipeline_lock_can_wait_for_the_current_owner(tmp_path):
    lock_path = tmp_path / "pipeline.lock"
    first = PipelineRunLock(lock_path).acquire()
    acquired = threading.Event()

    def wait_for_lock():
        second = PipelineRunLock(lock_path).acquire(wait=True, poll_interval=0.01)
        acquired.set()
        second.release()

    waiter = threading.Thread(target=wait_for_lock)
    waiter.start()
    time.sleep(0.03)
    assert acquired.is_set() is False
    first.release()
    waiter.join(timeout=1)
    assert acquired.is_set() is True


def test_resume_request_round_trip(tmp_path):
    request_path = tmp_path / "resume.json"
    save_resume_request(
        request_path,
        {"sources_filter": "Aevy TV", "skip_email": False, "shutdown_after_run": True},
    )
    loaded = load_resume_request(request_path)
    assert loaded["sources_filter"] == "Aevy TV"
    assert loaded["shutdown_after_run"] is True
    assert "saved_at" in loaded
    clear_resume_request(request_path)
    assert load_resume_request(request_path) is None


def test_resume_request_expires_stale_marker(tmp_path):
    request_path = tmp_path / "resume_stale.json"
    save_resume_request(
        request_path,
        {"sources_filter": "Aevy TV", "skip_email": False},
    )
    # Marker fresh (< 3h) should load
    assert load_resume_request(request_path, max_age_hours=3.0) is not None

    # Artificially age the saved_at timestamp to 4 hours ago
    import json
    data = json.loads(request_path.read_text(encoding="utf-8"))
    stale_time = datetime.now(timezone.utc) - timedelta(hours=4)
    data["saved_at"] = stale_time.isoformat()
    request_path.write_text(json.dumps(data), encoding="utf-8")

    # Now load_resume_request should detect stale marker, clear it, and return None
    assert load_resume_request(request_path, max_age_hours=3.0) is None
    assert request_path.exists() is False


def test_resume_request_corrupt_saved_at_clears_and_returns_none(tmp_path):
    request_path = tmp_path / "resume.json"
    request_path.write_text('{"sources_filter": "Chan", "saved_at": "NOT-A-DATE"}', encoding="utf-8")
    assert load_resume_request(request_path, max_age_hours=3.0) is None
    assert request_path.exists() is False


def test_resume_request_missing_saved_at_falls_back_to_mtime(tmp_path):
    import os
    request_path = tmp_path / "resume.json"
    request_path.write_text('{"sources_filter": "Chan"}', encoding="utf-8")
    # Fresh file mtime -> should load
    assert load_resume_request(request_path, max_age_hours=3.0) is not None
    assert request_path.exists() is True

    # Set mtime to 4 hours ago -> should expire and clear
    stale_mtime = time.time() - (4 * 3600)
    os.utime(str(request_path), (stale_mtime, stale_mtime))
    assert load_resume_request(request_path, max_age_hours=3.0) is None
    assert request_path.exists() is False


def test_compute_deferral_expires_cleanly(tmp_path):
    marker_path = tmp_path / "compute_deferral.json"
    future = datetime.now(timezone.utc) + timedelta(hours=5)
    save_compute_deferral(marker_path, future, "quota")
    assert load_compute_deferral(marker_path)["reason"] == "quota"

    save_compute_deferral(
        marker_path,
        datetime.now(timezone.utc) - timedelta(seconds=1),
        "expired",
    )
    assert load_compute_deferral(marker_path) is None
    assert marker_path.exists() is False


def test_shutdown_commands_are_platform_specific():
    assert get_shutdown_command("linux") == ["systemctl", "poweroff"]
    assert get_shutdown_command("win32") == ["shutdown", "/s", "/t", "0"]
    assert get_shutdown_command("darwin")[0] == "osascript"
