import os
import subprocess
import sys

import pytest

from gui import PipelineRunner


def test_log_stream_replays_each_line_once():
    runner = PipelineRunner()
    runner._publish_log("first\n")
    runner._publish_log("second\n")

    streamed = list(runner.stream_logs())

    assert streamed == ["data: first\n\n", "data: second\n\n"]


def test_stop_when_idle_reports_not_running():
    runner = PipelineRunner()
    ok, message = runner.stop()
    assert ok is False
    assert "not running" in message.lower()


@pytest.mark.skipif(os.name != "posix", reason="process-group kill is POSIX-only")
def test_stop_kills_single_child_process_group():
    """BUG-001: stop() must leave zero survivors in the pipeline process group."""
    runner = PipelineRunner()
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **runner._popen_kwargs(),
    )
    runner.process = proc
    runner.is_running = True
    try:
        ok, _ = runner.stop()
        assert ok is True
        assert proc.poll() is not None
        with pytest.raises(ProcessLookupError):
            os.killpg(proc.pid, 0)
    finally:
        try:
            proc.kill()
        except Exception:
            pass


@pytest.mark.skipif(os.name != "posix", reason="process-group kill is POSIX-only")
def test_stop_kills_grandchild_holding_stdout_pipe():
    """BUG-001: a grandchild inheriting the pipe must not wedge the runner."""
    runner = PipelineRunner()
    proc = subprocess.Popen(
        [
            sys.executable, "-c",
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "print('child-ready', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **runner._popen_kwargs(),
    )
    runner.process = proc
    runner.is_running = True
    try:
        assert proc.stdout.readline().strip() == "child-ready"
        ok, _ = runner.stop()
        assert ok is True
        proc.wait(timeout=15)
        with pytest.raises(ProcessLookupError):
            os.killpg(proc.pid, 0)
    finally:
        try:
            proc.kill()
        except Exception:
            pass
