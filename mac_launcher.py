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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("TubeLM-MacLauncher")

try:
    import rumps
except ImportError:
    logger.critical("rumps library is not installed. Please install it with: pip install rumps")
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
        # Spawns main.py script asynchronously so it doesn't freeze the Menu Bar UI
        venv_python = PROJECT_DIR / ".venv" / "bin" / "python"
        python_bin = str(venv_python) if venv_python.exists() else sys.executable
        main_script = str(PROJECT_DIR / "main.py")
        
        logger.info("Triggering background sync run from Menu Bar...")
        subprocess.Popen([python_bin, main_script], cwd=str(PROJECT_DIR))
        rumps.notification(
            title="TubeLM Sync",
            subtitle="Pipeline Started",
            message="TubeLM weekly sync has been triggered in the background."
        )

def main():
    global PORT
    try:
        PORT = find_available_port(5000)
    except Exception as e:
        logger.critical("Could not find any available port: %s", e)
        sys.exit(1)
        
    # Start Flask app in a background daemon thread
    server_thread = threading.Thread(target=run_gui, args=(PORT,), daemon=True)
    server_thread.start()
    
    logger.info("Starting native macOS Menu Bar Status Item on port %d...", PORT)
    
    # Initialize and run Menu Bar status item loop
    app = TubeLMApp(PORT)
    app.run()

if __name__ == "__main__":
    main()
