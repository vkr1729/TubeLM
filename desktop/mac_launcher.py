"""
mac_launcher.py — macOS Menu Bar Status Bar Wrapper for TubeLM.

Runs Flask in a background daemon thread and places a premium native '📺'
icon in the macOS Menu Bar to Open Dashboard, trigger Sync pipelines, or Quit.
"""

import sys
import os
import threading
import webbrowser
import subprocess
import logging
from pathlib import Path

# Add project directory to path and import paths.py utility
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

# ── Handle background sync trigger (Frozen CLI Mode) ──────────────────────────
if "--sync" in sys.argv:
    import asyncio
    from main import async_main
    paths.ensure_data_dir()
    
    log_dir = paths.get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "weekly_run.log"
    
    handlers = [logging.FileHandler(log_file, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers,
    )
    logger = logging.getLogger("TubeLM-SyncCLI")
    logger.info("Executing tray-triggered sync run...")
    
    dry_run = "--dry-run" in sys.argv
    skip_email = "--skip-email" in sys.argv
    
    channels_filter = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--channels" and idx + 1 < len(sys.argv):
            channels_filter = sys.argv[idx + 1]
            break
            
    logger.info("Executing background sync run (dry_run=%s, skip_email=%s, channels=%s)...",
                dry_run, skip_email, channels_filter)
    try:
        asyncio.run(async_main(dry_run=dry_run, skip_email=skip_email, channels_filter=channels_filter))
        logger.info("Background sync run complete.")
        sys.exit(0)
    except Exception as e:
        logger.critical("Background sync run failed: %s", e)
        sys.exit(1)

# ── GUI / Menu Bar Mode ──────────────────────────────────────────────────────

# Setup logging to both stdout and ~/.tubelm/tubelm.log
log_dir = paths.get_data_dir()
try:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tubelm.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8")
        ]
    )
except Exception as log_err:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    print(f"Warning: Could not configure file logging: {log_err}", file=sys.stderr)

logger = logging.getLogger("TubeLM-MacLauncher")

try:
    import rumps
except ImportError:
    logger.critical("rumps library is not installed. Please install it with: pip install rumps")
    sys.exit(1)

try:
    from gui import run_gui, find_available_port
except ImportError as e:
    logger.critical("Could not import TubeLM GUI module: %s", e)
    sys.exit(1)

# Global port state and variables
PORT = 5000
PROJECT_DIR = paths.get_bundle_dir()

class TubeLMApp(rumps.App):
    def __init__(self, port):
        super(TubeLMApp, self).__init__("📺", template=True)
        self.port = port
        self.menu = [
            rumps.MenuItem("Open Dashboard", callback=self.open_dashboard),
            rumps.MenuItem("Sync Weekly Run Now", callback=self.trigger_sync),
            None, # Separator
        ]
        
    def open_dashboard(self, _):
        webbrowser.open(f"http://127.0.0.1:{self.port}")
        
    def trigger_sync(self, _):
        if paths.is_frozen():
            cmd = [sys.executable, "--sync"]
        else:
            # Dev venv python fallback
            venv_python = PROJECT_DIR.parent / ".venv" / "bin" / "python"
            python_bin = str(venv_python) if venv_python.exists() else sys.executable
            main_script = str(PROJECT_DIR / "main.py")
            cmd = [python_bin, main_script]
            
        logger.info("Triggering background sync run from Menu Bar...")
        subprocess.Popen(cmd, cwd=str(PROJECT_DIR))
        rumps.notification(
            title="TubeLM Sync",
            subtitle="Pipeline Started",
            message="TubeLM weekly sync has been triggered in the background."
        )

def main():
    global PORT
    
    start_port = 5000
    for idx, arg in enumerate(sys.argv):
        if arg == "--port" and idx + 1 < len(sys.argv):
            try:
                start_port = int(sys.argv[idx + 1])
            except ValueError:
                pass
                
    try:
        PORT = find_available_port(start_port)
    except Exception as e:
        logger.critical("Could not find any available port: %s", e)
        sys.exit(1)
        
    server_thread = threading.Thread(target=run_gui, args=(PORT,), daemon=True)
    server_thread.start()
    
    logger.info("Starting native macOS Menu Bar Status Item on port %d...", PORT)
    
    app = TubeLMApp(PORT)
    app.run()

if __name__ == "__main__":
    main()
