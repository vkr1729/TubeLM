import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import main


def _configure_request_paths(tmp_path, monkeypatch):
    resume_file = tmp_path / "resume_request.json"
    scheduled_file = tmp_path / "scheduled_request.json"
    monkeypatch.setattr(main.paths, "ensure_data_dir", lambda: None)
    monkeypatch.setattr(main.paths, "get_pipeline_lock_file", lambda: tmp_path / "pipeline.lock")
    monkeypatch.setattr(main.paths, "get_resume_request_file", lambda: resume_file)
    monkeypatch.setattr(main.paths, "get_scheduled_request_file", lambda: scheduled_file)
    monkeypatch.setattr(
        main.paths,
        "get_compute_deferral_file",
        lambda: tmp_path / "compute_deferral.json",
    )
    return resume_file, scheduled_file


def test_scheduled_request_is_durable_until_the_run_completes(tmp_path, monkeypatch):
    _, scheduled_file = _configure_request_paths(tmp_path, monkeypatch)
    calls = []

    async def complete_run(*, dry_run, skip_email, channels_filter, artifacts_only=False):
        assert artifacts_only is False
        assert scheduled_file.exists()
        calls.append((dry_run, skip_email, channels_filter))
        return True

    monkeypatch.setattr(main, "async_main", complete_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--scheduled", "--skip-email", "--sources", "Aevy TV"],
    )

    main.main()

    assert calls == [(False, True, "Aevy TV")]
    assert scheduled_file.exists() is False


def test_boot_resume_finishes_interactive_then_scheduled_request(tmp_path, monkeypatch):
    resume_file, scheduled_file = _configure_request_paths(tmp_path, monkeypatch)
    main.save_resume_request(
        resume_file,
        {
            "request_kind": "interactive",
            "skip_email": True,
            "sources_filter": "Aevy TV",
            "shutdown_after_run": False,
        },
    )
    main.save_resume_request(
        scheduled_file,
        {
            "request_kind": "scheduled",
            "skip_email": False,
            "sources_filter": None,
            "shutdown_after_run": False,
        },
    )
    calls = []

    async def complete_run(*, dry_run, skip_email, channels_filter, artifacts_only=False):
        assert artifacts_only is False
        calls.append((dry_run, skip_email, channels_filter))
        return True

    monkeypatch.setattr(main, "async_main", complete_run)
    monkeypatch.setattr(sys, "argv", ["main.py", "--resume"])

    main.main()

    assert calls == [
        (False, True, "Aevy TV"),
        (False, False, None),
    ]
    assert resume_file.exists() is False
    assert scheduled_file.exists() is False


def test_resume_waits_for_compute_refresh_without_running_pipeline(tmp_path, monkeypatch):
    resume_file, _ = _configure_request_paths(tmp_path, monkeypatch)
    compute_file = tmp_path / "compute_deferral.json"
    monkeypatch.setattr(main.paths, "get_compute_deferral_file", lambda: compute_file)
    main.save_resume_request(
        resume_file,
        {
            "request_kind": "interactive",
            "skip_email": True,
            "sources_filter": None,
            "shutdown_after_run": False,
        },
    )
    main.save_compute_deferral(
        compute_file,
        datetime.now(timezone.utc) + timedelta(hours=5),
        "quota",
    )

    async def should_not_run(**_kwargs):
        raise AssertionError("pipeline ran before the compute refresh")

    monkeypatch.setattr(main, "async_main", should_not_run)
    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(sys, "argv", ["main.py", "--resume"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 75
    assert resume_file.exists() is True
