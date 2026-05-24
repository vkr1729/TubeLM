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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("TubeLM-LinuxLauncher")

try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image
except ImportError:
    logger.critical("pystray or Pillow library is not installed. Please install them with: pip install pystray pillow")
    sys.exit(1)

# Import the GUI server parts
PROJECT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))

try:
    from gui import run_gui, find_available_port
except ImportError as e:
    logger.critical("Could not import TubeLM GUI module: %s", e)
    sys.exit(1)

# Global port state
PORT = 5000
icon = None

def open_dashboard(icon, item):
    webbrowser.open(f"http://127.0.0.1:{PORT}")

def trigger_sync(icon, item):
    # Spawns main.py script asynchronously
    venv_python = PROJECT_DIR / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable
    main_script = str(PROJECT_DIR / "main.py")
    
    logger.info("Triggering background sync run from System Tray...")
    subprocess.Popen([python_bin, main_script], cwd=str(PROJECT_DIR))

def exit_app(icon, item):
    logger.info("Exiting TubeLM Application...")
    icon.stop()
    os._exit(0)

def main():
    global PORT, icon
    try:
        PORT = find_available_port(5000)
    except Exception as e:
        logger.critical("Could not find any available port: %s", e)
        sys.exit(1)
        
    # Start Flask app in a background daemon thread
    server_thread = threading.Thread(target=run_gui, args=(PORT,), daemon=True)
    server_thread.start()
    
    logger.info("Starting native Linux System Tray Icon on port %d...", PORT)
    
    # Load tray icon image
    logo_path = PROJECT_DIR / "assets" / "logo.png"
    if logo_path.exists():
        image = Image.open(logo_path)
    else:
        # Fallback to an empty 64x64 blue block if the image doesn't exist
        image = Image.new('RGB', (64, 64), color=(33, 150, 243))
        
    menu = Menu(
        MenuItem('Open Dashboard', open_dashboard),
        MenuItem('Sync Weekly Run Now', trigger_sync),
        MenuItem('Exit', exit_app)
    )
    
    icon = Icon("TubeLM", image, "TubeLM Dashboard", menu)
    icon.run()

if __name__ == "__main__":
    main()
