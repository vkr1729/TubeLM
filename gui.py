"""
gui.py — TubeLM Local Web Dashboard GUI Backend

Serves API endpoints and streams live logs from the weekly sync execution.
Optionally launched via python main.py --gui or python gui.py.
"""

import os
import sys
import json
import re
import queue
import logging
import threading
import subprocess
import webbrowser
import requests
from datetime import datetime
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, request, Response, send_from_directory, render_template_string

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("TubeLM-GUI")

app = Flask(__name__)

# Base paths
PROJECT_DIR = Path(__file__).parent.resolve()
ENV_FILE = PROJECT_DIR / ".env"
CHANNELS_FILE = PROJECT_DIR / "channels.json"
STATE_FILE = PROJECT_DIR / "state.json"
SUMMARIES_DIR = PROJECT_DIR / "summaries"

# Global pipeline runner instance
class PipelineRunner:
    def __init__(self):
        self.process = None
        self.log_queue = queue.Queue(maxsize=2000)
        self.is_running = False
        self.lock = threading.Lock()
        self.output_log = []

    def start(self, args_list):
        with self.lock:
            if self.is_running:
                return False, "Pipeline is already running."
            
            self.is_running = True
            self.output_log = []
            # Clear queue
            while not self.log_queue.empty():
                try:
                    self.log_queue.get_nowait()
                except queue.Empty:
                    break

            threading.Thread(target=self._run, args=(args_list,), daemon=True).start()
            return True, "Pipeline started."

    def _run(self, args_list):
        # Locate python binary from current venv or fallback to sys.executable
        venv_python = PROJECT_DIR / ".venv" / "bin" / "python"
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
                self.output_log.append(line)
                try:
                    self.log_queue.put(line, timeout=0.1)
                except queue.Full:
                    pass # Don't block background thread if queue filled
                    
            self.process.wait()
            exit_code = self.process.returncode
            end_msg = f"\n--- Pipeline finished with exit code {exit_code} ---\n"
            self.output_log.append(end_msg)
            self.log_queue.put(end_msg)
        except Exception as e:
            err_msg = f"\n--- Pipeline execution error: {e} ---\n"
            self.output_log.append(err_msg)
            self.log_queue.put(err_msg)
        finally:
            self.is_running = False

    def stream_logs(self):
        # Stream already accumulated logs
        for line in self.output_log:
            yield f"data: {line.rstrip()}\n\n"
            
        # Stream new logs
        while self.is_running or not self.log_queue.empty():
            try:
                line = self.log_queue.get(timeout=1.0)
                yield f"data: {line.rstrip()}\n\n"
            except queue.Empty:
                continue

runner = PipelineRunner()

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
    if not ENV_FILE.exists():
        # Create from example if possible
        example = PROJECT_DIR / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, ENV_FILE)
            
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        existing_lines = f.readlines()

    lines = []
    keys_to_update = updates.copy()
    
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

# ── Systemd Helpers ───────────────────────────────────────────────────────────

def get_systemd_status():
    status = {
        "timer_active": False,
        "timer_enabled": False,
        "next_run": "Not Scheduled",
        "service_running": False,
        "service_status": "Unknown",
        "installed": False
    }
    
    timer_path = Path("~/.config/systemd/user/youtube-digest.timer").expanduser()
    service_path = Path("~/.config/systemd/user/youtube-digest.service").expanduser()
    if not timer_path.exists() and not service_path.exists():
        return status
        
    status["installed"] = True
    
    # Check timer active
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", "youtube-digest.timer"],
            capture_output=True, text=True, timeout=5
        )
        status["timer_active"] = res.stdout.strip() == "active"
    except Exception:
        pass

    # Check timer enabled
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", "youtube-digest.timer"],
            capture_output=True, text=True, timeout=5
        )
        status["timer_enabled"] = res.stdout.strip() == "enabled"
    except Exception:
        pass

    # Check next run
    try:
        res = subprocess.run(
            ["systemctl", "--user", "list-timers", "youtube-digest.timer"],
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

    # Check service status
    try:
        res = subprocess.run(
            ["systemctl", "--user", "show", "youtube-digest.service", "--property=ActiveState,SubState"],
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
    return send_from_directory(str(SUMMARIES_DIR), filename)

@app.route("/assets/<path:filename>")
def serve_asset_file(filename):
    return send_from_directory(str(PROJECT_DIR / "assets"), filename)

@app.route("/api/status")
def api_status():
    # Monitored channels count
    channel_count = 0
    if CHANNELS_FILE.exists():
        try:
            channels = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
            channel_count = len(channels)
        except Exception:
            pass

    # Last run time
    last_run = "Never"
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            last_run = state.get("last_run_time", "Never")
        except Exception:
            pass

    systemd_info = get_systemd_status()

    return jsonify({
        "channel_count": channel_count,
        "last_run": last_run,
        "systemd": systemd_info,
        "pipeline_running": runner.is_running
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

@app.route("/api/channels/extract", methods=["POST"])
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

@app.route("/api/channels", methods=["GET", "POST"])
def api_channels():
    if request.method == "POST":
        data = request.json
        name = data.get("name", "").strip()
        channel_id = data.get("channel_id", "").strip()
        
        if not name or not channel_id:
            return jsonify({"error": "Missing name or channel_id"}), 400

        channels = []
        if CHANNELS_FILE.exists():
            try:
                channels = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        # Check if ID already exists
        if any(c.get("channel_id") == channel_id for c in channels):
            return jsonify({"error": "Channel ID already exists"}), 400

        channels.append({"name": name, "channel_id": channel_id})
        CHANNELS_FILE.write_text(json.dumps(channels, indent=2), encoding="utf-8")
        return jsonify({"success": True, "channels": channels})

    else:
        channels = []
        if CHANNELS_FILE.exists():
            try:
                channels = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return jsonify(channels)

@app.route("/api/channels/<channel_id>", methods=["DELETE"])
def api_delete_channel(channel_id):
    if not CHANNELS_FILE.exists():
        return jsonify({"error": "No channels file"}), 404
        
    try:
        channels = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        updated = [c for c in channels if c.get("channel_id") != channel_id]
        if len(updated) == len(channels):
            return jsonify({"error": "Channel not found"}), 404
            
        CHANNELS_FILE.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        return jsonify({"success": True, "channels": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    data = request.json
    channel_id = data.get("channel_id")
    timestamp = data.get("timestamp")  # ISO format UTC string or None/"Never"
    
    state = {"last_run_time": None, "channels": {}}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    if "channels" not in state or not isinstance(state["channels"], dict):
        state["channels"] = {}
        
    if not channel_id:
        return jsonify({"error": "Missing channel_id"}), 400
        
    if timestamp == "Never" or not timestamp:
        if channel_id in state["channels"]:
            del state["channels"][channel_id]
    else:
        # Validate timestamp format
        try:
            from datetime import datetime
            ts_to_parse = timestamp.replace("Z", "+00:00")
            datetime.fromisoformat(ts_to_parse)
            state["channels"][channel_id] = timestamp
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
        updates = request.json
        try:
            write_env_file(updates)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        config = read_env_file()
        # Hide actual password in response for safety
        clean_config = config.copy()
        if "SMTP_PASSWORD" in clean_config and clean_config["SMTP_PASSWORD"]:
            clean_config["SMTP_PASSWORD"] = "********"
        return jsonify(clean_config)

@app.route("/api/prompts", methods=["GET", "POST"])
def api_prompts():
    summary_path = PROJECT_DIR / "Summary_Prompt.md"
    podcast_path = PROJECT_DIR / "Podcast_Prompt.md"
    
    if request.method == "POST":
        data = request.json
        summary_text = data.get("summary_prompt", "").strip()
        podcast_text = data.get("podcast_prompt", "").strip()
        
        try:
            summary_path.write_text(summary_text, encoding="utf-8")
            podcast_path.write_text(podcast_text, encoding="utf-8")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        summary_text = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
        podcast_text = podcast_path.read_text(encoding="utf-8").strip() if podcast_path.exists() else ""
        return jsonify({
            "summary_prompt": summary_text,
            "podcast_prompt": podcast_text
        })

@app.route("/api/systemd/toggle", methods=["POST"])
def api_systemd_toggle():
    status = get_systemd_status()
    if not status["installed"]:
        return jsonify({"error": "Systemd unit files are not installed."}), 400
        
    action = "disable" if status["timer_active"] else "enable"
    cmd = ["systemctl", "--user", f"{action}", "--now", "youtube-digest.timer"]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return jsonify({"success": True, "timer_active": not status["timer_active"]})
        return jsonify({"error": res.stderr.strip()}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/auth/status")
def api_auth_status():
    venv_notebooklm = PROJECT_DIR / ".venv" / "bin" / "notebooklm"
    notebooklm_bin = str(venv_notebooklm) if venv_notebooklm.exists() else "notebooklm"
    
    try:
        res = subprocess.run(
            [notebooklm_bin, "auth", "check", "--test"],
            capture_output=True, text=True, timeout=15
        )
        return jsonify({
            "authenticated": res.returncode == 0,
            "output": res.stdout.strip() + "\n" + res.stderr.strip()
        })
    except Exception as e:
        return jsonify({"authenticated": False, "error": str(e)})

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    venv_notebooklm = PROJECT_DIR / ".venv" / "bin" / "notebooklm"
    notebooklm_bin = str(venv_notebooklm) if venv_notebooklm.exists() else "notebooklm"
    
    try:
        res = subprocess.run(
            [notebooklm_bin, "login", "--browser-cookies", "chrome"],
            capture_output=True, text=True, timeout=30
        )
        return jsonify({
            "success": res.returncode == 0,
            "output": res.stdout.strip() + "\n" + res.stderr.strip()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/notebooks")
def api_notebooks():
    notebooks = {}
    if not SUMMARIES_DIR.exists():
        return jsonify(notebooks)
        
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
            
    return jsonify(notebooks)

@app.route("/api/notebooks/real")
def api_notebooks_real():
    try:
        from notebooklm import NotebookLMClient
        import asyncio
        
        async def fetch_real():
            client = await NotebookLMClient.from_storage(keepalive=30)
            async with client:
                return await client.notebooks.list()
                
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            nb_list = loop.run_until_complete(fetch_real())
        finally:
            loop.close()
            
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
            client = await NotebookLMClient.from_storage(keepalive=30)
            async with client:
                return await client.notebooks.delete(notebook_id)
                
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(do_delete())
        finally:
            loop.close()
            
        return jsonify({"success": success})
    except Exception as e:
        logger.exception("Failed to delete notebook %s", notebook_id)
        return jsonify({"error": str(e)}), 500

@app.route("/api/digests")
def api_digests():
    digests = []
    if SUMMARIES_DIR.exists():
        for f in SUMMARIES_DIR.glob("*_digest.md"):
            digests.append({
                "filename": f.name,
                "date": f.name.split("_")[0],
                "size": f.stat().st_size
            })
    # Sort descending by date
    digests.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(digests)

@app.route("/api/digests/<filename>")
def api_get_digest(filename):
    filepath = SUMMARIES_DIR / filename
    if not filepath.exists() or not filepath.is_relative_to(SUMMARIES_DIR):
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
    channels = data.get("channels", [])
    
    args = []
    if dry_run:
        args.append("--dry-run")
    if skip_email:
        args.append("--skip-email")
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

def run_gui(port=5000):
    # Ensure summaries dir exists
    SUMMARIES_DIR.mkdir(exist_ok=True)
    
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
    run_gui()
