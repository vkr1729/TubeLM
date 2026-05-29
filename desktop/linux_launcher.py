"""
linux_launcher.py — Linux System Tray Status Wrapper for TubeLM.

Runs Flask in a background daemon thread and places a premium native icon
in the Linux Desktop Panel System Tray to Open Dashboard, trigger Sync pipelines, or Exit.
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

# ── GUI / System Tray Mode ───────────────────────────────────────────────────

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

logger = logging.getLogger("TubeLM-LinuxLauncher")

try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image
except ImportError:
    logger.critical("pystray or Pillow library is not installed. Please install them with: pip install pystray pillow")
    sys.exit(1)

try:
    from gui import run_gui, find_available_port
except ImportError as e:
    logger.critical("Could not import TubeLM GUI module: %s", e)
    sys.exit(1)

# Global port state and variables
PORT = 5000
icon = None
PROJECT_DIR = paths.get_bundle_dir()

def open_dashboard(icon, item):
    webbrowser.open(f"http://127.0.0.1:{PORT}")

def trigger_sync(icon, item):
    if paths.is_frozen():
        cmd = [sys.executable, "--sync"]
    else:
        # Dev venv python fallback
        venv_python = PROJECT_DIR.parent / ".venv" / "bin" / "python"
        python_bin = str(venv_python) if venv_python.exists() else sys.executable
        main_script = str(PROJECT_DIR / "main.py")
        cmd = [python_bin, main_script]
        
    logger.info("Triggering background sync run from System Tray...")
    subprocess.Popen(cmd, cwd=str(PROJECT_DIR))
    
    # Send desktop notification on Linux via pystray native notify
    try:
        icon.notify(
            "Weekly sync pipeline has been triggered in the background.",
            title="TubeLM Sync"
        )
    except Exception as e:
        logger.warning("Failed to trigger Linux notification: %s", e)

def exit_app(icon, item):
    logger.info("Exiting TubeLM Application...")
    icon.stop()
    os._exit(0)

def main():
    global PORT, icon
    
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
    
    logger.info("Starting native Linux System Tray Icon on port %d...", PORT)
    
    # Load tray icon image from bundle or dev assets
    logo_path = paths.get_assets_dir() / "logo.png"
    if logo_path.exists():
        image = Image.open(logo_path)
    else:
        image = Image.new('RGB', (64, 64), color=(33, 150, 243))
        
    menu = Menu(
        MenuItem('Open Dashboard', open_dashboard, default=True),
        MenuItem('Sync Weekly Run Now', trigger_sync),
        MenuItem('Exit', exit_app)
    )
    
    icon = Icon("TubeLM", image, "TubeLM Dashboard", menu)
    icon.run()

if __name__ == "__main__":
    main()
