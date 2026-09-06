"""
gui.py — TubeLM Local Web Dashboard GUI Backend

Serves API endpoints and streams live logs from the weekly sync execution.
Optionally launched via python main.py --gui or python gui.py.
"""

import os
import sys
import json
import re
import socket
import logging
import threading
import subprocess
import webbrowser
import time
import feedparser
import requests
import hashlib
import copy
import tempfile
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Timer
from urllib.parse import urlparse

from flask import Flask, jsonify, request, Response, send_from_directory, render_template_string

import paths
from sources_loader import load_sources
from run_control import is_pipeline_running, load_compute_deferral

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("TubeLM-GUI")

app = Flask(__name__)

# Base paths
PROJECT_DIR = paths.get_bundle_dir()
ENV_FILE = paths.get_env_file()
SOURCES_FILE = paths.get_sources_file()
STATE_FILE = paths.get_state_file()
SUMMARIES_DIR = paths.get_summaries_dir()

from dotenv import load_dotenv
load_dotenv(ENV_FILE)


# Global pipeline runner instance
class PipelineRunner:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.lock = threading.Lock()
        self.log_condition = threading.Condition()
        self.output_log = deque(maxlen=5000)
        self.log_sequence = 0

    def start(self, args_list):
        with self.lock:
            if self.is_running:
                return False, "Pipeline is already running."
            if is_pipeline_running(paths.get_pipeline_lock_file()):
                return False, "A scheduled or resumed pipeline is already running."
            
            self.is_running = True
            with self.log_condition:
                self.output_log.clear()
                self.log_sequence = 0

            threading.Thread(target=self._run, args=(args_list,), daemon=True).start()
            return True, "Pipeline started."

    def _run(self, args_list):
        if paths.is_frozen():
            cmd = [sys.executable, "--sync"] + args_list
        else:
            # Locate python binary from current venv or fallback to sys.executable
            venv_python = PROJECT_DIR.parent / ".venv" / "Scripts" / "python.exe"
            if not venv_python.exists():
                venv_python = PROJECT_DIR.parent / ".venv" / "bin" / "python"
            python_bin = str(venv_python) if venv_python.exists() else sys.executable
            main_script = str(PROJECT_DIR / "main.py")
            cmd = [python_bin, main_script] + args_list
        logger.info("Starting sync subprocess: %s", " ".join(cmd))
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_DIR)
            )
            
            for line in self.process.stdout:
                self._publish_log(line)
                    
            self.process.wait()
            exit_code = self.process.returncode
            end_msg = f"\n--- Pipeline finished with exit code {exit_code} ---\n"
            self._publish_log(end_msg)
        except Exception as e:
            err_msg = f"\n--- Pipeline execution error: {e} ---\n"
            self._publish_log(err_msg)
        finally:
            self.is_running = False
            with self.log_condition:
                self.log_condition.notify_all()

    def _publish_log(self, line):
        """Publish a bounded, replayable line to every connected browser."""
        with self.log_condition:
            self.log_sequence += 1
            self.output_log.append((self.log_sequence, line))
            self.log_condition.notify_all()

    def stream_logs(self):
        last_sequence = 0
        while True:
            with self.log_condition:
                pending = [(seq, line) for seq, line in self.output_log if seq > last_sequence]
                if not pending and not self.is_running:
                    return
                if not pending:
                    self.log_condition.wait(timeout=1.0)
                    continue

            for sequence, line in pending:
                last_sequence = sequence
                yield f"data: {line.rstrip()}\n\n"

runner = PipelineRunner()

_runtime_cache_lock = threading.Lock()
_notebooks_fetch_lock = threading.Lock()
_scheduler_cache = {"expires": 0.0, "value": None}
_auth_cache = {"expires": 0.0, "value": None}
_requirements_cache = {"expires": 0.0, "value": None}
_notebooks_cache = {
    "expires": 0.0,
    "state_mtime_ns": None,
    "value": None,
}


def _invalidate_runtime_caches():
    with _runtime_cache_lock:
        _scheduler_cache["expires"] = 0.0
        _auth_cache["expires"] = 0.0
        _requirements_cache["expires"] = 0.0
        _notebooks_cache["expires"] = 0.0

# ── Env Config Helpers ────────────────────────────────────────────────────────

def read_env_file():
    if not ENV_FILE.exists():
        return {}
    config = {}
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
    return config

def write_env_file(updates):
    allowed_keys = {
        "SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SENDER_EMAIL", "RECIPIENT_EMAIL", "YOUTUBE_API_KEY",
        "NOTEBOOKS_RETENTION_LIMIT", "NOTEBOOKLM_BROWSER",
        "GENERATE_INFOGRAPHICS", "GENERATE_TOP_10_DIGEST",
    }
    if not isinstance(updates, dict):
        raise ValueError("Configuration payload must be a JSON object.")

    sanitized_updates = {}
    for key, value in updates.items():
        if key not in allowed_keys:
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Invalid value for {key}.")
        string_value = str(value).strip()
        if "\n" in string_value or "\r" in string_value:
            raise ValueError(f"Invalid line break in {key}.")
        sanitized_updates[key] = string_value

    if not ENV_FILE.exists():
        # Create from example if possible
        if paths.is_frozen():
            example = paths.get_bundle_dir() / ".env.example"
        else:
            example = paths.get_bundle_dir().parent / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, ENV_FILE)

    # Final safety net: if ENV_FILE still doesn't exist (example was also missing),
    # create an empty file so the open() below doesn't crash.
    if not ENV_FILE.exists():
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENV_FILE.touch()

    with open(ENV_FILE, "r", encoding="utf-8") as f:
        existing_lines = f.readlines()

    lines = []
    keys_to_update = sanitized_updates.copy()
    
    for line in existing_lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            k, _ = trimmed.split("=", 1)
            k = k.strip()
            if k in keys_to_update:
                lines.append(f"{k}={keys_to_update.pop(k)}\n")
                continue
        lines.append(line)
        
    for k, v in keys_to_update.items():
        lines.append(f"{k}={v}\n")
        
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)

# ── Scheduler Helpers ─────────────────────────────────────────────────────────

def get_windows_status():
    status = {
        "timer_active": False,
        "timer_enabled": False,
        "next_run": "Not Scheduled",
        "service_running": False,
        "service_status": "Unknown",
        "installed": False,
        "day_of_week": "Sat",
        "time": "08:00",
        "scheduler_type": "Windows Task Scheduler"
    }
    
    try:
        res = subprocess.run(
            ["schtasks", "/query", "/tn", "TubeLM_Sync", "/fo", "list"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            status["installed"] = True
            props = {}
            for line in res.stdout.strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    props[k.strip().lower()] = v.strip()
            
            task_status = props.get("status", "unknown").lower()
            status["timer_active"] = "disabled" not in task_status
            status["timer_enabled"] = status["timer_active"]
            status["next_run"] = props.get("next run time", "Not Scheduled")
            status["service_status"] = props.get("status", "Unknown")
        else:
            status["installed"] = False
    except Exception:
        pass
        
    config_path = paths.get_data_dir() / "scheduler_config.json"
    if config_path.exists():
        try:
            s_conf = json.loads(config_path.read_text(encoding="utf-8"))
            status["day_of_week"] = s_conf.get("day_of_week", "Sat")
            status["time"] = s_conf.get("time", "08:00")
        except Exception:
            pass
            
    return status


def setup_windows_scheduler(day, time_str):
    script_path = paths.get_data_dir() / "run_weekly.bat"
    log_dir = paths.get_data_dir() / "logs"
    
    if paths.is_frozen():
        exec_cmd = f'"{sys.executable}" --sync'
    else:
        venv_python = PROJECT_DIR.parent / ".venv" / "Scripts" / "python.exe"
        if not venv_python.exists():
            venv_python = PROJECT_DIR.parent / ".venv" / "bin" / "python"
        python_bin = str(venv_python) if venv_python.exists() else sys.executable
        main_script = str(PROJECT_DIR / "main.py")
        exec_cmd = f'"{python_bin}" "{main_script}"'

    bat_content = f"""@echo off
rem Auto-generated by TubeLM GUI. DO NOT EDIT MANUALLY.
setlocal enabledelayedexpansion

set "LOG_DIR={log_dir}"
if not exist "!LOG_DIR!" mkdir "!LOG_DIR!"
set "LOG_FILE=!LOG_DIR!\\weekly_run.log"

echo === TubeLM Weekly Sync: %DATE% %TIME% === >> "!LOG_FILE!"

rem Check network connectivity by pinging google.com
echo Checking network connectivity... >> "!LOG_FILE!"
for /L %%i in (1,1,12) do (
    ping -n 1 -w 3000 google.com >nul 2>&1
    if !errorlevel! equ 0 (
        echo Network available. >> "!LOG_FILE!"
        goto :start_sync
    )
    echo Waiting for network... (%%i/12) >> "!LOG_FILE!"
    timeout /t 5 >nul
)

:start_sync
echo Starting sync pipeline... >> "!LOG_FILE!"
cd /d "{PROJECT_DIR}"
{exec_cmd} --scheduled >> "!LOG_FILE!" 2>&1
echo === Run complete: %DATE% %TIME% | Exit code: %ERRORLEVEL% === >> "!LOG_FILE!"
exit /b %ERRORLEVEL%
"""
    script_path.write_text(bat_content, encoding="utf-8")
    
    day_map = {
        "Mon": "MON",
        "Tue": "TUE",
        "Wed": "WED",
        "Thu": "THU",
        "Fri": "FRI",
        "Sat": "SAT",
        "Sun": "SUN"
    }
    win_day = day_map.get(day, "SAT")
    
    cmd = [
        "schtasks", "/create", 
        "/tn", "TubeLM_Sync", 
        "/tr", f'"{script_path}"', 
        "/sc", "weekly", 
        "/d", win_day, 
        "/st", time_str, 
        "/f"
    ]
    subprocess.run(cmd, capture_output=True, check=True, text=True)
    
    config_path = paths.get_data_dir() / "scheduler_config.json"
    config_path.write_text(json.dumps({"day_of_week": day, "time": time_str}), encoding="utf-8")


def toggle_windows_scheduler():
    status = get_windows_status()
    if not status["installed"]:
        raise ValueError("Task is not installed.")
    action = "enable" if not status["timer_active"] else "disable"
    cmd = ["schtasks", "/change", "/tn", "TubeLM_Sync", f"/{action}"]
    subprocess.run(cmd, capture_output=True, check=True, text=True)
    return not status["timer_active"]


def get_macos_status():
    status = {
        "timer_active": False,
        "timer_enabled": False,
        "next_run": "Not Scheduled",
        "service_running": False,
        "service_status": "Unknown",
        "installed": False,
        "day_of_week": "Sat",
        "time": "08:00",
        "scheduler_type": "Launch Agent"
    }
    
    plist_path = Path("~/Library/LaunchAgents/org.tubelm.sync.plist").expanduser()
    if plist_path.exists():
        status["installed"] = True
        
        config_path = paths.get_data_dir() / "scheduler_config.json"
        if config_path.exists():
            try:
                s_conf = json.loads(config_path.read_text(encoding="utf-8"))
                status["day_of_week"] = s_conf.get("day_of_week", "Sat")
                status["time"] = s_conf.get("time", "08:00")
            except Exception:
                pass
                
        try:
            res = subprocess.run(
                ["launchctl", "list"],
                capture_output=True, text=True, timeout=5
            )
            if "org.tubelm.sync" in res.stdout:
                status["timer_active"] = True
                status["timer_enabled"] = True
                status["service_status"] = "Loaded"
                status["next_run"] = f"Weekly on {status['day_of_week']} {status['time']}"
            else:
                status["service_status"] = "Unloaded"
        except Exception:
            pass
            
    return status


def setup_macos_scheduler(day, time_str):
    agents_dir = Path("~/Library/LaunchAgents").expanduser()
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / "org.tubelm.sync.plist"
    
    script_path = paths.get_data_dir() / "run_weekly.sh"
    
    if paths.is_frozen():
        exec_cmd = f'"{sys.executable}" --sync'
    else:
        venv_python = PROJECT_DIR.parent / ".venv" / "bin" / "python"
        python_bin = str(venv_python) if venv_python.exists() else sys.executable
        main_script = str(PROJECT_DIR / "main.py")
        exec_cmd = f'"{python_bin}" "{main_script}"'
        
    script_content = f"""#!/usr/bin/env bash
# Auto-generated by TubeLM GUI. DO NOT EDIT MANUALLY.
set -euo pipefail

LOG_DIR="{paths.get_data_dir()}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_run_$(date +%Y-%m-%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== TubeLM Weekly Sync: $(date) ==="
echo "Log file: $LOG_FILE"

# Wait for network (max 60s)
echo "Checking network connectivity..."
for i in $(seq 1 12); do
    if ping -c 1 -t 3 google.com &>/dev/null; then
        echo "Network available."
        break
    fi
    echo "Waiting for network... ($i/12)"
    sleep 5
done

# Run sync pipeline
echo "Starting sync pipeline..."
set +e
{exec_cmd} --scheduled
EXIT_CODE=$?
set -e

echo "=== Run complete: $(date) | Exit code: $EXIT_CODE ==="
find "$LOG_DIR" -name "weekly_run_*.log" -mtime +84 -delete 2>/dev/null || true
exit $EXIT_CODE
"""
    script_path.write_text(script_content, encoding="utf-8")
    
    try:
        import os
        os.chmod(str(script_path), 0o755)
    except Exception:
        pass
        
    mac_day_map = {
        "Sun": 0,
        "Mon": 1,
        "Tue": 2,
        "Wed": 3,
        "Thu": 4,
        "Fri": 5,
        "Sat": 6
    }
    weekday = mac_day_map.get(day, 6)
    
    try:
        hour, minute = map(int, time_str.split(":"))
    except ValueError:
        hour, minute = 8, 0
        
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>org.tubelm.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>{script_path}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>{weekday}</integer>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{paths.get_data_dir()}/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{paths.get_data_dir()}/logs/launchd_stderr.log</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")
    
    try:
        subprocess.run(["launchctl", "unload", "-w", str(plist_path)], capture_output=True)
    except Exception:
        pass
        
    subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True, check=True)
    
    config_path = paths.get_data_dir() / "scheduler_config.json"
    config_path.write_text(json.dumps({"day_of_week": day, "time": time_str}), encoding="utf-8")


def toggle_macos_scheduler():
    status = get_macos_status()
    if not status["installed"]:
        raise ValueError("LaunchAgent plist is not installed.")
        
    plist_path = Path("~/Library/LaunchAgents/org.tubelm.sync.plist").expanduser()
    if status["timer_active"]:
        cmd = ["launchctl", "unload", "-w", str(plist_path)]
    else:
        cmd = ["launchctl", "load", "-w", str(plist_path)]
    subprocess.run(cmd, capture_output=True, check=True, text=True)
    return not status["timer_active"]


def get_systemd_status():
    status = {
        "timer_active": False,
        "timer_enabled": False,
        "next_run": "Not Scheduled",
        "service_running": False,
        "service_status": "Unknown",
        "installed": False,
        "day_of_week": "Sat",
        "time": "08:00",
        "scheduler_type": "systemd timer"
    }
    
    if sys.platform != "linux":
        return status
        
    timer_path = Path("~/.config/systemd/user/tubelm-sync.timer").expanduser()
    service_path = Path("~/.config/systemd/user/tubelm-sync.service").expanduser()
    
    if timer_path.exists():
        try:
            content = timer_path.read_text(encoding="utf-8")
            match = re.search(r"OnCalendar=(\w+)\s+\*-\*-\*\s+(\d{2}:\d{2})", content)
            if match:
                status["day_of_week"] = match.group(1)
                status["time"] = match.group(2)
        except Exception:
            pass
            
    if not timer_path.exists() and not service_path.exists():
        return status
        
    status["installed"] = True
    
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", "tubelm-sync.timer"],
            capture_output=True, text=True, timeout=5
        )
        status["timer_active"] = res.stdout.strip() == "active"
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", "tubelm-sync.timer"],
            capture_output=True, text=True, timeout=5
        )
        status["timer_enabled"] = res.stdout.strip() == "enabled"
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["systemctl", "--user", "list-timers", "tubelm-sync.timer"],
            capture_output=True, text=True, timeout=5
        )
        lines = res.stdout.strip().split("\n")
        if len(lines) >= 2:
            data_line = lines[1]
            parts = re.split(r'\s{2,}', data_line)
            if len(parts) > 0:
                status["next_run"] = parts[0]
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["systemctl", "--user", "show", "tubelm-sync.service", "--property=ActiveState,SubState"],
            capture_output=True, text=True, timeout=5
        )
        props = {}
        for line in res.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
        status["service_status"] = f"{props.get('ActiveState', 'unknown')} ({props.get('SubState', 'unknown')})"
        status["service_running"] = props.get("ActiveState") == "active"
    except Exception:
        pass
        
    return status


def get_scheduler_status(force=False):
    now = time.monotonic()
    with _runtime_cache_lock:
        if not force and _scheduler_cache["value"] is not None and now < _scheduler_cache["expires"]:
            return copy.deepcopy(_scheduler_cache["value"])

    if sys.platform == "win32":
        status = get_windows_status()
    elif sys.platform == "darwin":
        status = get_macos_status()
    else:
        status = get_systemd_status()

    with _runtime_cache_lock:
        _scheduler_cache.update(value=copy.deepcopy(status), expires=now + 20)
    return status

# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # Load GUI template
    template_path = PROJECT_DIR / "templates" / "gui.html"
    if template_path.exists():
        content = template_path.read_text(encoding="utf-8")
        return render_template_string(content)
    return "Error: templates/gui.html not found.", 404

@app.route("/summaries/<path:filename>")
def serve_summary_file(filename):
    return send_from_directory(str(SUMMARIES_DIR), filename, conditional=True)

@app.route("/reader")
def serve_reader():
    site_dir = paths.get_site_dir()
    index_file = site_dir / "index.html"
    if not index_file.exists():
        from web_reader import build_reader_site
        build_reader_site(paths.get_summaries_dir(), paths.get_audio_dir(), site_dir, paths.get_sources_file())
    return send_from_directory(str(site_dir), "index.html")

@app.route("/reader/<path:filename>")
def serve_reader_static(filename):
    return send_from_directory(str(paths.get_site_dir()), filename, conditional=True)

@app.route("/audio/<path:filename>")
def serve_audio_file(filename):
    return send_from_directory(str(paths.get_audio_dir()), filename, conditional=True)

@app.route("/api/reader/build", methods=["POST"])
def api_build_reader():
    try:
        data = request.get_json(silent=True) or {}
        compress_audio = bool(data.get("compress_audio", False))
        from web_reader import build_reader_site
        build_reader_site(
            paths.get_summaries_dir(),
            paths.get_audio_dir(),
            paths.get_site_dir(),
            paths.get_sources_file(),
            compress_audio=compress_audio,
        )
        return jsonify({"success": True, "message": "Web Reader rebuilt successfully."})
    except Exception as exc:
        logger.exception("Failed to rebuild web reader site.")
        return jsonify({"error": str(exc)}), 500

@app.route("/api/reader/read-state", methods=["GET"])
def api_get_read_state():
    state_file = paths.get_read_state_file()
    if state_file.exists():
        try:
            return jsonify(json.loads(state_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return jsonify({"read_ids": []})

@app.route("/api/reader/read-state", methods=["POST"])
def api_save_read_state():
    data = request.get_json() or {}
    read_ids = data.get("read_ids")
    state_file = paths.get_read_state_file()
    
    if not isinstance(read_ids, list):
        item_id = data.get("id")
        if item_id:
            cur = []
            if state_file.exists():
                try:
                    cur = json.loads(state_file.read_text(encoding="utf-8")).get("read_ids", [])
                except Exception:
                    cur = []
            s = set(cur)
            if data.get("is_read", True):
                s.add(item_id)
            else:
                s.discard(item_id)
            read_ids = sorted(s)
        else:
            return jsonify({"error": "Missing read_ids or id"}), 400

    try:
        state_file.write_text(json.dumps({"read_ids": sorted(set(read_ids))}, indent=2), encoding="utf-8")
        return jsonify({"success": True, "read_ids": sorted(set(read_ids))})
    except Exception as exc:
        logger.exception("Failed to save read state file.")
        return jsonify({"error": str(exc)}), 500

@app.route("/api/status")
def api_status():
    source_count = 0
    source_types = {}
    sources_data = _load_existing_sources()
    source_count = len(sources_data)
    for s in sources_data:
        st = s.get("type", "youtube")
        source_types[st] = source_types.get(st, 0) + 1

    # Legacy channel count fallback
    channel_count = source_count

    last_run = "Never"
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            last_run = state.get("last_run_time", "Never")
        except Exception:
            pass

    systemd_info = get_scheduler_status()
    compute_deferral = load_compute_deferral(paths.get_compute_deferral_file())

    return jsonify({
        "source_count": source_count,
        "source_types": source_types,
        "channel_count": channel_count,
        "last_run": last_run,
        "systemd": systemd_info,
        "pipeline_running": runner.is_running or is_pipeline_running(paths.get_pipeline_lock_file()),
        "compute_deferred_until": (
            compute_deferral["not_before_dt"].isoformat() if compute_deferral else None
        ),
    })

# ── YouTube Channel Details Extractor Helper ──────────────────────────────────

def extract_youtube_channel_info(url):
    url = url.strip()
    if not url:
        raise ValueError("URL cannot be empty.")
        
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    if "youtube.com" not in url and "youtu.be" not in url:
        raise ValueError("Invalid YouTube URL. Please provide a valid youtube.com channel link.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        raise ValueError(f"Failed to fetch YouTube page: {e}")

    # Regex search for channelId
    channel_id = None
    
    # 1. Look for itemprop="channelId"
    m = re.search(r'<meta[^>]*itemprop="channelId"[^>]*content="([^"]+)"', html)
    if m:
        channel_id = m.group(1)
        
    # 2. Look for itemprop="identifier"
    if not channel_id:
        m = re.search(r'<meta[^>]*itemprop="identifier"[^>]*content="([^"]+)"', html)
        if m:
            channel_id = m.group(1)

    # 3. Look for browseId json key
    if not channel_id:
        m = re.search(r'"browseId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"', html)
        if m:
            channel_id = m.group(1)

    # 4. Look for channelId json key
    if not channel_id:
        m = re.search(r'"channelId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"', html)
        if m:
            channel_id = m.group(1)

    if not channel_id:
        # Check if URL itself has /channel/UC...
        m = re.search(r'/channel/(UC[a-zA-Z0-9_-]{22})', url)
        if m:
            channel_id = m.group(1)
        else:
            raise ValueError("Could not locate Channel ID on the page. Ensure this is a YouTube Channel page.")

    # Regex search for channel name
    channel_name = None
    # 1. Look for og:title
    m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
    if m:
        channel_name = m.group(1)

    # 2. Look for title tag (strip " - YouTube")
    if not channel_name:
        m = re.search(r'<title>([^<]+)</title>', html)
        if m:
            title_text = m.group(1).strip()
            if title_text.endswith(" - YouTube"):
                title_text = title_text[:-10]
            channel_name = title_text

    # 3. Look for name metadata
    if not channel_name:
        m = re.search(r'<meta[^>]*itemprop="name"[^>]*content="([^"]+)"', html)
        if m:
            channel_name = m.group(1)

    if not channel_name:
        channel_name = "Extracted Channel"

    return {
        "name": channel_name,
        "channel_id": channel_id
    }

@app.route("/api/sources/youtube/extract", methods=["POST"])
def api_extract_channel():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Missing URL"}), 400
        
    try:
        info = extract_youtube_channel_info(url)
        return jsonify({
            "success": True,
            "name": info["name"],
            "channel_id": info["channel_id"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

def _get_sources_path():
    """Return the canonical sources file path for both reads and writes."""
    return paths.get_sources_file()


def _load_existing_sources():
    src_file = _get_sources_path()
    return load_sources(src_file)


def _write_sources(sources):
    dest = _get_sources_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sources, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=dest.parent, prefix=f".{dest.name}.",
        suffix=".tmp", delete=False,
    ) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(dest)


def _bounded_int(value, default: int, minimum: int = 1, maximum: int = 50) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def compute_state_key(source):
    stype = source.get("type", "youtube")
    if stype == "youtube":
        cid = source.get("channel_id")
        if not cid:
            name = source.get("name", "")
            hash_digest = hashlib.sha256(name.encode()).hexdigest()[:12]
            return f"youtube:unknown-{hash_digest}"
        return f"youtube:{cid}"
    elif stype in ("rss", "webpage"):
        url = source.get("url", "")
        if not url:
            name = source.get("name", "")
            hash_digest = hashlib.sha256(name.encode()).hexdigest()[:12]
            return f"{stype}:unknown-{hash_digest}"
        hash_digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        return f"{stype}:{hash_digest}"
    
    name = source.get("name", "") or str(source)
    hash_digest = hashlib.sha256(name.encode()).hexdigest()[:12]
    return f"unknown:{hash_digest}"


def _enrich_sources_with_state_keys(sources):
    enriched = []
    for s in sources:
        item = copy.deepcopy(s)
        item["state_key"] = compute_state_key(item)
        enriched.append(item)
    return enriched


@app.route("/api/sources", methods=["GET", "POST"])
def api_sources():
    if request.method == "POST":
        data = request.json or {}
        source_type = data.get("type", "youtube")
        name = data.get("name", "").strip()

        if not name:
            return jsonify({"error": "Missing name"}), 400

        category = data.get("category", "tech").strip()
        valid_categories = {"health", "tech", "deep_explainer", "news_feed"}
        if category not in valid_categories:
            return jsonify({"error": f"Unknown category: {category}"}), 400

        if source_type == "youtube":
            channel_id = data.get("channel_id", "").strip()
            if not channel_id:
                return jsonify({"error": "Missing channel_id"}), 400
            entry = {
                "name": name,
                "type": "youtube",
                "channel_id": channel_id,
                "category": category,
                "generate_cinematic_video": bool(
                    data.get("generate_cinematic_video", False)
                ),
            }
        elif source_type == "rss":
            url = data.get("url", "").strip()
            if not _valid_http_url(url):
                return jsonify({"error": "A valid http(s) URL is required"}), 400
            entry = {
                "name": name, "type": "rss", "url": url,
                "force_text_extraction": data.get("force_text_extraction", False),
                "max_items": _bounded_int(data.get("max_items"), 15),
                "category": category,
                "generate_cinematic_video": bool(
                    data.get("generate_cinematic_video", False)
                ),
            }
        elif source_type == "webpage":
            url = data.get("url", "").strip()
            if not _valid_http_url(url):
                return jsonify({"error": "A valid http(s) URL is required"}), 400
            entry = {
                "name": name, "type": "webpage", "url": url,
                "is_index_page": data.get("is_index_page", False),
                "link_selector": data.get("link_selector", ""),
                "max_items": _bounded_int(data.get("max_items"), 10),
                "category": category,
                "generate_cinematic_video": bool(
                    data.get("generate_cinematic_video", False)
                ),
            }
        else:
            return jsonify({"error": f"Unknown source type: {source_type}"}), 400

        sources = _load_existing_sources()

        # Duplicate check
        if source_type == "youtube":
            if any(s.get("channel_id") == channel_id for s in sources):
                return jsonify({"error": "Channel ID already exists"}), 400
        else:
            source_url = entry.get("url", "")
            if any(s.get("url") == source_url for s in sources):
                return jsonify({"error": "URL already exists"}), 400

        sources.append(entry)
        _write_sources(sources)
        return jsonify({"success": True, "sources": _enrich_sources_with_state_keys(sources)})
    else:
        sources = _load_existing_sources()
        return jsonify(_enrich_sources_with_state_keys(sources))


@app.route("/api/sources/cinematic", methods=["POST"])
def api_update_source_cinematic():
    data = request.json or {}
    identifier = data.get("identifier", "")
    enabled = data.get("enabled")
    if not identifier or not isinstance(enabled, bool):
        return jsonify({"error": "identifier and boolean enabled are required"}), 400

    sources = _load_existing_sources()
    source = next(
        (
            item
            for item in sources
            if item.get("channel_id") == identifier or item.get("url") == identifier
        ),
        None,
    )
    if source is None:
        return jsonify({"error": "Source not found"}), 404
    source["generate_cinematic_video"] = enabled
    _write_sources(sources)
    return jsonify({"success": True, "enabled": enabled})


def _find_and_remove_source(sources, identifier):
    """Find and remove a source by channel_id, url, or index.

    Returns:
        (found, updated_sources_list)
    """
    updated = []
    found = False
    for s in sources:
        if s.get("channel_id") == identifier or s.get("url") == identifier:
            found = True
        else:
            updated.append(s)

    if not found:
        try:
            idx = int(identifier)
            if 0 <= idx < len(sources):
                updated = [s for j, s in enumerate(sources) if j != idx]
                found = True
        except ValueError:
            pass

    return found, updated


@app.route("/api/sources/<identifier>", methods=["DELETE"])
def api_delete_source(identifier):
    sources = _load_existing_sources()
    if not sources:
        return jsonify({"error": "No sources found"}), 404

    found, updated = _find_and_remove_source(sources, identifier)
    if not found:
        return jsonify({"error": "Source not found"}), 404
    _write_sources(updated)
    return jsonify({"success": True, "sources": updated})


@app.route("/api/sources/delete", methods=["POST"])
def api_delete_source_post():
    data = request.json or {}
    identifier = data.get("identifier")
    if not identifier:
        return jsonify({"error": "Missing identifier"}), 400

    sources = _load_existing_sources()
    if not sources:
        return jsonify({"error": "No sources found"}), 404

    found, updated = _find_and_remove_source(sources, identifier)
    if not found:
        return jsonify({"error": "Source not found"}), 404
    _write_sources(updated)
    return jsonify({"success": True, "sources": updated})


@app.route("/api/sources/validate", methods=["POST"])
def api_validate_source():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Missing url"}), 400

    # Check for YouTube
    if "youtube.com" in url or "youtu.be" in url:
        try:
            info = extract_youtube_channel_info(url)
            return jsonify({"type": "youtube", "name": info["name"], "channel_id": info["channel_id"]})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # Try feedparser for RSS
    try:
        feed = feedparser.parse(url)
        if feed.entries and not (feed.bozo and not feed.entries):
            return jsonify({
                "type": "rss",
                "name": getattr(feed.feed, "title", ""),
                "entry_count": len(feed.entries),
            })
    except Exception:
        pass

    # Try trafilatura for webpage
    try:
        from source_handlers.extractor import extract_metadata
        meta = extract_metadata(url)
        if meta.get("title"):
            return jsonify({
                "type": "webpage",
                "name": meta["title"],
                "author": meta.get("author", ""),
            })
    except Exception:
        pass

    return jsonify({"type": "webpage", "name": ""})


# Legacy channel endpoint alias
@app.route("/api/state")
def api_get_state():
    state = {"last_run_time": None, "channels": {}}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return jsonify(state)

@app.route("/api/state/channel", methods=["POST"])
def api_update_channel_state():
    data = request.json or {}
    state_key = data.get("state_key")
    channel_id = data.get("channel_id")
    timestamp = data.get("timestamp")  # ISO format UTC string or None/"Never"

    if not state_key and channel_id:
        if ":" in channel_id:
            state_key = channel_id
        else:
            state_key = f"youtube:{channel_id}"

    if not state_key:
        return jsonify({"error": "Missing state_key or channel_id"}), 400

    state = {"last_run_time": None, "sources": {}}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    if "sources" not in state or not isinstance(state["sources"], dict):
        state["sources"] = {}
    state.pop("channels", None)

    if timestamp == "Never" or not timestamp:
        if state_key in state["sources"]:
            del state["sources"][state_key]
    else:
        # Validate timestamp format
        try:
            from datetime import datetime
            ts_to_parse = timestamp.replace("Z", "+00:00")
            datetime.fromisoformat(ts_to_parse)
            state["sources"][state_key] = timestamp

        except ValueError:
            return jsonify({"error": "Invalid timestamp format. Must be ISO8601."}), 400

    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return jsonify({"success": True, "state": state})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        updates = request.json or {}
        try:
            write_env_file(updates)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        config = read_env_file()
        # Never send stored credentials back to the browser.
        clean_config = config.copy()
        for secret_key in ("SMTP_PASSWORD", "YOUTUBE_API_KEY"):
            if clean_config.get(secret_key):
                clean_config[secret_key] = "********"
        return jsonify(clean_config)

@app.route("/api/prompts", methods=["GET", "POST"])
def api_prompts():
    """Category-based prompt management.

    GET  ?category=health&type=summary  → returns prompt text for that category/type
    GET  (no params)                    → returns all categories with their prompts
    POST {category, type, text}         → saves prompt text for that category/type

    """
    valid_categories = ["health", "tech", "deep_explainer", "news_feed"]
    valid_types = ["summary", "podcast"]
    bundled_prompts_dir = paths.get_prompts_dir()
    user_prompts_dir = paths.get_user_prompts_dir()

    if request.method == "POST":
        data = request.json or {}
        category = data.get("category", "").strip()
        prompt_type = data.get("type", "").strip()
        text = data.get("text", "").strip()

        if category not in valid_categories:
            return jsonify({"error": f"Invalid category: {category}"}), 400
        if prompt_type not in valid_types:
            return jsonify({"error": f"Invalid type: {prompt_type}"}), 400

        try:
            target_path = user_prompts_dir / prompt_type / f"{category}.md"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(text, encoding="utf-8")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        # Return all category prompts
        result = {"categories": valid_categories, "types": valid_types, "prompts": {}}
        for cat in valid_categories:
            result["prompts"][cat] = {}
            for pt in valid_types:
                user_path = user_prompts_dir / pt / f"{cat}.md"
                bundled_path = bundled_prompts_dir / pt / f"{cat}.md"
                prompt_path = user_path if user_path.exists() else bundled_path
                result["prompts"][cat][pt] = (
                    prompt_path.read_text(encoding="utf-8").strip()
                    if prompt_path.exists() else ""
                )

        return jsonify(result)


@app.route("/api/scheduler/toggle", methods=["POST"])
@app.route("/api/systemd/toggle", methods=["POST"])
def api_scheduler_toggle():
    _invalidate_runtime_caches()
    try:
        if sys.platform == "win32":
            active = toggle_windows_scheduler()
            return jsonify({"success": True, "timer_active": active})
        elif sys.platform == "darwin":
            active = toggle_macos_scheduler()
            return jsonify({"success": True, "timer_active": active})
        else:
            status = get_systemd_status()
            if not status["installed"]:
                return jsonify({"error": "Systemd unit files are not installed."}), 400
                
            action = "disable" if status["timer_active"] else "enable"
            cmd = ["systemctl", "--user", f"{action}", "--now", "tubelm-sync.timer"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return jsonify({"success": True, "timer_active": not status["timer_active"]})
            return jsonify({"error": res.stderr.strip()}), 500
    except Exception as e:
        logger.exception("Failed to toggle scheduler")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scheduler/setup", methods=["POST"])
@app.route("/api/systemd/setup", methods=["POST"])
def api_scheduler_setup():
    _invalidate_runtime_caches()
    day = "Sat"
    time_str = "08:00"
    if request.is_json:
        req_data = request.json or {}
        day = req_data.get("day_of_week", "Sat")
        time_str = req_data.get("time", "08:00")

    valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    if day not in valid_days or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_str):
        return jsonify({"error": "Invalid schedule day or time."}), 400
        
    try:
        if sys.platform == "win32":
            setup_windows_scheduler(day, time_str)
            return jsonify({"success": True})
        elif sys.platform == "darwin":
            setup_macos_scheduler(day, time_str)
            return jsonify({"success": True})
        else:
            timer_dir = Path("~/.config/systemd/user").expanduser()
            timer_dir.mkdir(parents=True, exist_ok=True)
            
            service_path = timer_dir / "tubelm-sync.service"
            timer_path = timer_dir / "tubelm-sync.timer"
            resume_service_path = timer_dir / "tubelm-resume.service"
            
            script_path = paths.get_data_dir() / "run_weekly.sh"
            
            if paths.is_frozen():
                exec_cmd = f'"{sys.executable}" --sync'
            else:
                venv_python = PROJECT_DIR.parent / ".venv" / "bin" / "python"
                python_bin = str(venv_python) if venv_python.exists() else sys.executable
                main_script = str(PROJECT_DIR / "main.py")
                exec_cmd = f'"{python_bin}" "{main_script}"'

            script_content = f"""#!/usr/bin/env bash
# Auto-generated by TubeLM GUI. DO NOT EDIT MANUALLY.
set -euo pipefail

LOG_DIR="{paths.get_data_dir()}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_run_$(date +%Y-%m-%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== TubeLM Weekly Sync: $(date) ==="
echo "Log file: $LOG_FILE"

# Wait for network (max 60s)
echo "Checking network connectivity..."
for i in $(seq 1 12); do
    if ping -c 1 -W 3 google.com &>/dev/null; then
        echo "Network available."
        break
    fi
    echo "Waiting for network... ($i/12)"
    sleep 5
done

# Run sync pipeline
echo "Starting sync pipeline..."
set +e
{exec_cmd} --scheduled
EXIT_CODE=$?
set -e

echo "=== Run complete: $(date) | Exit code: $EXIT_CODE ==="
find "$LOG_DIR" -name "weekly_run_*.log" -mtime +84 -delete 2>/dev/null || true
exit $EXIT_CODE
"""
            script_path.write_text(script_content, encoding="utf-8")
            
            service_content = f"""[Unit]
Description=TubeLM Weekly Briefing Sync Service
After=network-online.target

[Service]
Type=oneshot
ExecStart={script_path}
Restart=on-failure
RestartSec=30min
StandardOutput=journal
StandardError=journal
"""
            
            timer_content = f"""[Unit]
Description=Run TubeLM Weekly Sync

[Timer]
OnCalendar={day} *-*-* {time_str}:00
Persistent=true

[Install]
WantedBy=timers.target
"""

            resume_service_content = f"""[Unit]
Description=Resume an interrupted TubeLM pipeline
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=oneshot
ExecStart={exec_cmd} --resume
Restart=on-failure
RestartSec=15min
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""
            
            service_path.write_text(service_content, encoding="utf-8")
            timer_path.write_text(timer_content, encoding="utf-8")
            resume_service_path.write_text(resume_service_content, encoding="utf-8")
            
            try:
                import os
                os.chmod(str(script_path), 0o755)
            except Exception:
                pass
                
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=True)
            subprocess.run(["systemctl", "--user", "import-environment", "DBUS_SESSION_BUS_ADDRESS", "DISPLAY"], capture_output=True)
            try:
                subprocess.run(["loginctl", "enable-linger"], capture_output=True)
            except Exception as linger_err:
                logger.warning("Could not enable loginctl user lingering: %s", linger_err)
            subprocess.run(["systemctl", "--user", "enable", "--now", "tubelm-sync.timer"], capture_output=True, check=True)
            subprocess.run(["systemctl", "--user", "enable", "tubelm-resume.service"], capture_output=True, check=True)
            
            return jsonify({"success": True})
    except Exception as e:
        logger.exception("Failed to setup scheduler")
        return jsonify({"error": str(e)}), 500

def get_notebooklm_bin():
    return paths.get_notebooklm_bin()

@app.route("/api/auth/status")
def api_auth_status():
    force = request.args.get("refresh") == "1"
    now = time.monotonic()
    with _runtime_cache_lock:
        cached = _auth_cache["value"]
        if not force and cached is not None and now < _auth_cache["expires"]:
            return jsonify(copy.deepcopy(cached))

    try:
        from notebooklm import NotebookLMClient
        import asyncio

        async def _check():
            async with NotebookLMClient.from_storage(keepalive=15) as client:
                await client.notebooks.list()
            return True

        loop = asyncio.new_event_loop()
        try:
            authenticated = loop.run_until_complete(_check())
            output = "Authentication check passed. Session is active."
        finally:
            loop.close()
        payload = {
            "authenticated": authenticated,
            "output": output
        }
    except Exception as e:
        detail = str(e).splitlines()[0][:500]
        payload = {
            "authenticated": False,
            "output": f"Authentication check failed: {detail}"
        }

    with _runtime_cache_lock:
        _auth_cache.update(value=copy.deepcopy(payload), expires=now + 60)
    return jsonify(payload)

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    _invalidate_runtime_caches()
    try:
        browser = os.getenv("NOTEBOOKLM_BROWSER", "chrome")
        from notebooklm.paths import get_storage_path
        from notebooklm.cli.services.login.refresh import _login_with_browser_cookies
        import io
        from contextlib import redirect_stdout, redirect_stderr

        storage_path = get_storage_path()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        success = False
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                _login_with_browser_cookies(storage_path, browser)
            success = True
        except SystemExit as e:
            success = (e.code == 0 or e.code is None)
        except Exception as e:
            stderr_buf.write(f"\nException: {e}")

        output = stdout_buf.getvalue() + "\n" + stderr_buf.getvalue()
        return jsonify({
            "success": success,
            "output": output.strip()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

_DIGEST_NOTEBOOK_TITLE_RE = re.compile(
    r"^(?P<source>.+) Digest — (?P<date>\d{4}-\d{2}-\d{2})$"
)


def _notebook_created_timestamp(notebook) -> float:
    created_at = getattr(notebook, "created_at", None)
    if not created_at:
        return 0.0
    try:
        return created_at.timestamp()
    except (AttributeError, OSError, OverflowError, ValueError):
        return 0.0


def _latest_notebook_links(notebook_list) -> dict[str, str]:
    """Return the newest, most complete digest workspace for each source."""
    latest = {}
    for notebook in notebook_list:
        match = _DIGEST_NOTEBOOK_TITLE_RE.fullmatch((notebook.title or "").strip())
        if not match:
            continue
        source_name = match.group("source").strip()
        rank = (
            match.group("date"),
            int(getattr(notebook, "sources_count", 0) or 0),
            _notebook_created_timestamp(notebook),
        )
        current = latest.get(source_name)
        if current is None or rank > current[0]:
            latest[source_name] = (
                rank,
                f"https://notebooklm.google.com/notebook/{notebook.id}",
            )

    return {
        source_name: latest[source_name][1]
        for source_name in sorted(latest, key=str.casefold)
    }


def _fetch_real_notebooks():
    from notebooklm import NotebookLMClient
    import asyncio

    async def fetch_real():
        async with NotebookLMClient.from_storage(keepalive=30) as client:
            return await client.notebooks.list()

    return asyncio.run(fetch_real())


def _notebook_links_from_local_digests() -> dict[str, str]:
    """Best-effort fallback for an unavailable NotebookLM session."""
    notebooks = {}
    if not SUMMARIES_DIR.exists():
        return notebooks
        
    channel_header_re = re.compile(r'^##\s+(.+)$', re.MULTILINE)
    notebook_link_re = re.compile(
        r'📒\s+\[Open in NotebookLM\]\((https?://notebooklm\.google\.com/notebook/[a-zA-Z0-9_-]+)\)',
        re.IGNORECASE
    )
    
    files = sorted(SUMMARIES_DIR.glob("*_digest.md"))
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            parts = channel_header_re.split(content)
            for i in range(1, len(parts), 2):
                ch_name = parts[i].strip()
                ch_text = parts[i+1]
                m = notebook_link_re.search(ch_text)
                if m:
                    url = m.group(1).strip()
                    notebooks[ch_name] = url
        except Exception as e:
            logger.error("Error parsing digest %s for notebook URLs: %s", f.name, e)

    return notebooks


def _save_notebook_links_cache(notebooks: dict[str, str]) -> None:
    cache_path = paths.get_notebook_links_cache_file()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "version": 1,
            "updated_at": datetime.now().astimezone().isoformat(),
            "notebooks": notebooks,
        },
        indent=2,
    )
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=cache_path.parent,
        prefix=f".{cache_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(cache_path)


def _load_notebook_links_cache() -> dict[str, str] | None:
    try:
        data = json.loads(
            paths.get_notebook_links_cache_file().read_text(encoding="utf-8")
        )
        notebooks = data.get("notebooks")
        if not isinstance(notebooks, dict):
            return None
        if not all(isinstance(name, str) and isinstance(url, str) for name, url in notebooks.items()):
            return None
        return notebooks
    except (OSError, AttributeError, json.JSONDecodeError):
        return None


def _notebook_state_mtime_ns() -> int | None:
    try:
        return STATE_FILE.stat().st_mtime_ns
    except OSError:
        return None


def _cached_notebook_links(now: float, state_mtime_ns: int | None):
    with _runtime_cache_lock:
        if (
            _notebooks_cache["value"] is not None
            and now < _notebooks_cache["expires"]
            and state_mtime_ns == _notebooks_cache["state_mtime_ns"]
        ):
            return copy.deepcopy(_notebooks_cache["value"])
    return None


@app.route("/api/notebooks")
def api_notebooks():
    state_mtime_ns = _notebook_state_mtime_ns()
    now = time.monotonic()
    cached = _cached_notebook_links(now, state_mtime_ns)
    if cached is not None:
        return jsonify(cached)

    # The dashboard loads this endpoint from two views at startup. Coalesce
    # simultaneous cache misses so they produce one NotebookLM request.
    with _notebooks_fetch_lock:
        state_mtime_ns = _notebook_state_mtime_ns()
        now = time.monotonic()
        cached = _cached_notebook_links(now, state_mtime_ns)
        if cached is not None:
            return jsonify(cached)

        try:
            notebooks = _latest_notebook_links(_fetch_real_notebooks())
            _save_notebook_links_cache(notebooks)
            cache_seconds = 90
        except Exception as exc:
            logger.warning(
                "Could not refresh NotebookLM workspaces (%s); using the last successful index.",
                type(exc).__name__,
            )
            notebooks = _load_notebook_links_cache()
            if notebooks is None:
                notebooks = _notebook_links_from_local_digests()
            cache_seconds = 30

        with _runtime_cache_lock:
            _notebooks_cache.update(
                value=copy.deepcopy(notebooks),
                state_mtime_ns=state_mtime_ns,
                expires=now + cache_seconds,
            )
    return jsonify(notebooks)

@app.route("/api/notebooks/real")
def api_notebooks_real():
    try:
        nb_list = _fetch_real_notebooks()
            
        serialized = []
        for nb in nb_list:
            share_url = f"https://notebooklm.google.com/notebook/{nb.id}"
            serialized.append({
                "id": nb.id,
                "title": nb.title,
                "created_at": nb.created_at.isoformat() if nb.created_at else None,
                "sources_count": nb.sources_count,
                "is_owner": nb.is_owner,
                "url": share_url
            })
        return jsonify({"success": True, "notebooks": serialized})
    except Exception as e:
        logger.exception("Failed to fetch real notebooks list")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/notebooks/real/<notebook_id>", methods=["DELETE"])
def api_delete_notebook(notebook_id):
    try:
        from notebooklm import NotebookLMClient
        import asyncio
        
        async def do_delete():
            async with NotebookLMClient.from_storage(keepalive=30) as client:
                return await client.notebooks.delete(notebook_id)
                
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(do_delete())
        finally:
            loop.close()
            
        if success:
            _invalidate_runtime_caches()
        return jsonify({"success": success})
    except Exception as e:
        logger.exception("Failed to delete notebook %s", notebook_id)
        return jsonify({"error": str(e)}), 500

@app.route("/api/digests")
def api_digests():
    # 1. Load channels to get name -> safe_name mapping
    channels = _load_existing_sources()

    # Build safe_name to real_name mapping
    safe_to_real = {}
    for ch in channels:
        name = ch.get("name", "")
        safe = paths.safe_channel_name(name)
        safe_to_real[safe] = name

    artifacts = []
    if SUMMARIES_DIR.exists():
        for f in SUMMARIES_DIR.iterdir():
            if not f.is_file():
                continue
            name = f.name
            
            # Pattern 1: YYYY-MM-DD_digest.md (Global digest)
            md_match = re.match(r'^(\d{4}-\d{2}-\d{2})_digest\.md$', name)
            if md_match:
                date_str = md_match.group(1)
                artifacts.append({
                    "filename": name,
                    "date": date_str,
                    "type": "md",
                    "channel_safe": "global",
                    "channel_name": "Global Briefings",
                    "size": f.stat().st_size
                })
                continue

            # Pattern 2: YYYY-MM-DD_{safe_name}_digest.html (Cinematic Newsletter)
            html_match = re.match(r'^(\d{4}-\d{2}-\d{2})_(.+)_digest\.html$', name)
            if html_match:
                date_str = html_match.group(1)
                safe_name = html_match.group(2)
                real_name = safe_to_real.get(safe_name, safe_name.replace("_", " "))
                artifacts.append({
                    "filename": name,
                    "date": date_str,
                    "type": "html",
                    "channel_safe": safe_name,
                    "channel_name": real_name,
                    "size": f.stat().st_size
                })
                continue

            # Pattern 3: YYYY-MM-DD_{safe_name}_infographic.{png|jpg|jpeg|gif} (Visual Infographic)
            img_match = re.match(r'^(\d{4}-\d{2}-\d{2})_(.+)_infographic\.(png|jpg|jpeg|gif)$', name, re.IGNORECASE)
            if img_match:
                date_str = img_match.group(1)
                safe_name = img_match.group(2)
                real_name = safe_to_real.get(safe_name, safe_name.replace("_", " "))
                artifacts.append({
                    "filename": name,
                    "date": date_str,
                    "type": "png",
                    "channel_safe": safe_name,
                    "channel_name": real_name,
                    "size": f.stat().st_size
                })
                continue

            # Pattern 4: YYYY-MM-DD_{safe_name}_podcast.{mp3|wav|ogg} (Audio Overview)
            audio_match = re.match(r'^(\d{4}-\d{2}-\d{2})_(.+)_podcast\.(mp3|wav|ogg)$', name, re.IGNORECASE)
            if audio_match:
                date_str = audio_match.group(1)
                safe_name = audio_match.group(2)
                real_name = safe_to_real.get(safe_name, safe_name.replace("_", " "))
                artifacts.append({
                    "filename": name,
                    "date": date_str,
                    "type": "audio",
                    "channel_safe": safe_name,
                    "channel_name": real_name,
                    "size": f.stat().st_size
                })
                continue

            # Pattern 5: YYYY-MM-DD_{safe_name}_podcast.{mp4|webm} (Video briefing)
            video_match = re.match(r'^(\d{4}-\d{2}-\d{2})_(.+)_podcast\.(mp4|webm)$', name, re.IGNORECASE)
            if video_match:
                date_str = video_match.group(1)
                safe_name = video_match.group(2)
                real_name = safe_to_real.get(safe_name, safe_name.replace("_", " "))
                artifacts.append({
                    "filename": name,
                    "date": date_str,
                    "type": "video",
                    "channel_safe": safe_name,
                    "channel_name": real_name,
                    "size": f.stat().st_size
                })
                continue

    # Sort descending by date, then type priority (md: 0, html: 1, png: 2, audio: 3, video: 4)
    type_priority = {"md": 0, "html": 1, "png": 2, "audio": 3, "video": 4}
    artifacts.sort(key=lambda x: (x["date"], type_priority.get(x["type"], 99)), reverse=True)
    return jsonify({
        "channels": channels,
        "artifacts": artifacts
    })

@app.route("/api/digests/<filename>")
def api_get_digest(filename):
    try:
        filepath = (SUMMARIES_DIR / filename).resolve()
    except Exception:
        return jsonify({"error": "Digest file not found"}), 404

    try:
        filepath.relative_to(SUMMARIES_DIR.resolve())
        is_safe = True
    except ValueError:
        is_safe = False

    if not filepath.is_file() or not is_safe:
        return jsonify({"error": "Digest file not found"}), 404
    try:
        content = filepath.read_text(encoding="utf-8")
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/run", methods=["POST"])
def api_trigger_run():
    data = request.json or {}
    dry_run = data.get("dry_run", False)
    skip_email = data.get("skip_email", False)
    shutdown_after_run = data.get("shutdown_after_run", False)
    channels = data.get("channels", [])
    
    args = []
    if dry_run:
        args.append("--dry-run")
    if skip_email:
        args.append("--skip-email")
    if shutdown_after_run:
        args.append("--shutdown-after-run")
    if channels:
        args.append("--channels")
        args.append(",".join(channels))
        
    started, msg = runner.start(args)
    if started:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400

@app.route("/api/run/stream")
def api_stream_logs():
    return Response(runner.stream_logs(), mimetype="text/event-stream")

# ── Runner ────────────────────────────────────────────────────────────────────

def install_playwright_browsers_silently():
    """Checks if Playwright's Chromium browser is installed, and installs it silently if missing."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                logger.info("Playwright Chromium browser is already installed.")
                return
            except Exception:
                logger.info("Playwright Chromium browser not found. Installing silently...")
    except ImportError:
        logger.warning("Playwright package is not installed.")
        return

    try:
        import subprocess, sys
        # Use the venv's playwright binary so the correct browser cache path is used
        playwright_bin = str(Path(sys.executable).parent / "playwright")
        cmd = [playwright_bin, "install", "chromium"]
        logger.info("Running background playwright installation: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logger.info("Playwright Chromium browser installed successfully.")
        else:
            logger.warning("Playwright install exited with code %d: %s", result.returncode, result.stderr[:500])
    except Exception as e:
        logger.warning("Could not automatically install Playwright Chromium: %s", e)


@app.route('/api/system/requirements')
def api_system_requirements():
    """Check post-install runtime requirements and return status.

    Returns a list of requirements with status so the frontend can
    show a dismissible first-launch banner until all are met.

    Requirements checked:
      1. Playwright Chromium browser (headless, for NotebookLM automation)
      2. Google Chrome or Chromium (for rookiepy cookie extraction)
    """
    now = time.monotonic()
    with _runtime_cache_lock:
        cached = _requirements_cache["value"]
        if cached is not None and now < _requirements_cache["expires"]:
            return jsonify(copy.deepcopy(cached))

    import shutil as _shutil
    import sys
    requirements = []

    # ── 1. Playwright Chromium browser (headless automation engine) ──────────
    playwright_ok = False
    playwright_detail = ""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                playwright_ok = True
                playwright_detail = "Headless Chromium is installed and working."
            except Exception as e:
                # Extract just the first line (the actual error), strip Playwright's box-art
                raw = str(e)
                first_line = raw.split("\n")[0].strip()
                playwright_detail = first_line
    except ImportError:
        playwright_detail = (
            "Playwright package is not installed. "
            "This should not happen — please reinstall TubeLM."
        )

    playwright_bin = str(Path(sys.executable).parent / "playwright")
    # Playwright Chromium is only needed for the interactive browser-login flow.
    # TubeLM uses --browser-cookies (rookiepy) by default, so this is OPTIONAL.
    # On Ubuntu 26.04 Playwright 1.60 cannot install; treat as optional/informational.
    requirements.append({
        "name": "Playwright Chromium  —  Optional (Alternative Login Only)",
        "description": (
            "This is NOT your regular Chrome browser. "
            "Playwright Chromium is a separate headless engine used only for the "
            "interactive browser-login flow. TubeLM uses your Chrome cookies instead "
            "(rookiepy), so this dependency is OPTIONAL \u2014 you don\u2019t need it."
        ),
        "ok": True,  # Always treat as OK \u2014 TubeLM doesn't require this for normal operation
        "detail": (
            "Headless Chromium is installed and working." if playwright_ok
            else (
                f"Not installed ({playwright_detail}). "
                "This is fine \u2014 TubeLM uses your Chrome browser cookies instead."
            )
        ),
        "how_to_fix": (
            "No action required. TubeLM works without this.\n\n"
            "If you want it anyway (e.g., for interactive login):\n"
            f"  {playwright_bin} install chromium"
        ),
    })

    # ── 2. Google Chrome / Chromium (for rookiepy cookie extraction) ─────────
    chrome_path = (
        _shutil.which("google-chrome")
        or _shutil.which("google-chrome-stable")
        or _shutil.which("chromium-browser")
        or _shutil.which("chromium")
    )
    chrome_ok = chrome_path is not None
    requirements.append({
        "name": "Google Chrome  —  Cookie Source Browser",
        "description": (
            "Your regular Chrome browser (the one you use to browse). "
            "TubeLM reads your NotebookLM login cookies from it to authenticate — "
            "no password is ever stored."
        ),
        "ok": chrome_ok,
        "detail": (
            f"Found at: {chrome_path}" if chrome_ok
            else "Chrome not found in PATH. Make sure it is installed."
        ),
        "how_to_fix": (
            "1. Install Google Chrome if you haven't already:\n"
            "   sudo apt install google-chrome-stable\n\n"
            "2. Open Chrome and sign in to notebooklm.google.com\n\n"
            "3. Come back here and click 'Refresh Cookie Cache' on the Dashboard."
        ),
    })

    payload = {
        "all_ok": all(r["ok"] for r in requirements),
        "requirements": requirements,
    }
    with _runtime_cache_lock:
        _requirements_cache.update(value=copy.deepcopy(payload), expires=now + 300)
    return jsonify(payload)



def find_available_port(start_port=5000, max_port=6000):
    """Dynamically scan for a free local TCP port."""
    for p in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"Could not find an available port in range {start_port}-{max_port}")

def run_gui(port=5000):
    # Ensure summaries dir exists
    SUMMARIES_DIR.mkdir(exist_ok=True)
    
    # Start silent background playwright installation
    threading.Thread(target=install_playwright_browsers_silently, daemon=True).start()
    
    # Auto-launch browser
    def open_browser():
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception as e:
            logger.warning("Could not auto-launch browser: %s", e)
            
    Timer(1.0, open_browser).start()
    
    # Start flask app
    logger.info("TubeLM GUI Server starting on http://127.0.0.1:%d", port)
    app.run(host="127.0.0.1", port=port, debug=False)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TubeLM GUI Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the GUI server on")
    args = parser.parse_args()
    run_gui(port=args.port)
