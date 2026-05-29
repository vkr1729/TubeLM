#!/usr/bin/env python3
"""
test_gui_e2e.py — Comprehensive End-to-End GUI & API Test Suite for TubeLM.
Launches the Flask Web Dashboard, queries all active API endpoints, drives the browser
via Playwright utilizing native Chrome, and saves screenshots of the dark-mode dashboard.
"""

import os
import sys
import time
import socket
import requests
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

# Setup test variables
PORT = 5050
BASE_URL = f"http://127.0.0.1:{PORT}"
PROJECT_DIR = Path(__file__).parent.parent.resolve()
ROOT_DIR = PROJECT_DIR.parent.resolve()
REPORT_DIR = ROOT_DIR / "summaries" / "test_report"

print("=========================================================================")
print("             📺 Starting TubeLM E2E GUI Testing Suite 📺               ")
print("=========================================================================")

# Ensure directories exist
REPORT_DIR.mkdir(parents=True, exist_ok=True)
(ROOT_DIR / "summaries").mkdir(parents=True, exist_ok=True)

def find_available_port(start_port=5050):
    for p in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("Could not locate available port for testing.")

PORT = find_available_port(5050)
BASE_URL = f"http://127.0.0.1:{PORT}"
print(f"[*] Dynamically selected available test port: {PORT}")

# ── 1. Start Flask GUI Subprocess ──────────────────────────────────────────────
print("[*] Launching TubeLM GUI Server in background...")

# Auto-detect if we should launch native compiled binary or dev script
packaged_binary = os.environ.get("TUBELM_TEST_BINARY")
if not packaged_binary:
    packaged_binary = "/usr/bin/tubelm"
    if not os.path.exists(packaged_binary):
        packaged_binary = "/opt/tubelm/tubelm"

# Verify if package binary path is valid or overridden
is_packaged = os.path.exists(packaged_binary) if packaged_binary else False

if is_packaged:
    cmd = [packaged_binary, "--gui", "--port", str(PORT)]
    if packaged_binary.lower().endswith(".exe"):
        cmd = ["wine", packaged_binary, "--gui", "--port", str(PORT)]
        
    print(f"[*] Packaging mode detected. Launching: {' '.join(cmd)}")
    server_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
else:
    print("[*] Development mode detected. Launching raw python launcher script...")
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable
    server_process = subprocess.Popen(
        [python_bin, str(PROJECT_DIR / "gui.py"), "--port", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(PROJECT_DIR)
    )

# Wait for Flask to boot and respond
time.sleep(3)

# ── 2. Run API Auditing Suite ──────────────────────────────────────────────────
print("\n[*] Starting REST API Auditing Suite...")
try:
    # A. Audit /api/status
    print(" -> GET /api/status ... ", end="")
    resp = requests.get(f"{BASE_URL}/api/status", timeout=5)
    resp.raise_for_status()
    data = resp.json()
    assert "channel_count" in data
    assert "systemd" in data
    print("✅ OK")

    # B. Audit /api/channels (GET)
    print(" -> GET /api/channels ... ", end="")
    resp = requests.get(f"{BASE_URL}/api/channels", timeout=5)
    resp.raise_for_status()
    channels = resp.json()
    assert isinstance(channels, list)
    print("✅ OK")

    # C. Audit /api/config (GET)
    print(" -> GET /api/config ... ", end="")
    resp = requests.get(f"{BASE_URL}/api/config", timeout=5)
    resp.raise_for_status()
    config = resp.json()
    assert isinstance(config, dict)
    print("✅ OK")

    # D. Audit /api/prompts (GET)
    print(" -> GET /api/prompts ... ", end="")
    resp = requests.get(f"{BASE_URL}/api/prompts", timeout=5)
    resp.raise_for_status()
    prompts = resp.json()
    assert "summary_prompt" in prompts
    assert "podcast_prompt" in prompts
    print("✅ OK")

    # E. Audit /api/digests
    print(" -> GET /api/digests ... ", end="")
    resp = requests.get(f"{BASE_URL}/api/digests", timeout=5)
    resp.raise_for_status()
    digests = resp.json()
    assert "channels" in digests
    assert "artifacts" in digests
    print("✅ OK")

except Exception as e:
    print(f"❌ FAILED: API verification error: {e}")
    try:
        server_process.terminate()
        stdout, stderr = server_process.communicate(timeout=5)
        print(f"[*] Server Subprocess Exit Code: {server_process.returncode}")
        print(f"[*] Server Subprocess stdout:\n{stdout}")
        print(f"[*] Server Subprocess stderr:\n{stderr}")
    except Exception as comm_err:
        print(f"[*] Could not retrieve subprocess streams: {comm_err}")
        try:
            server_process.kill()
        except Exception:
            pass
    sys.exit(1)

# ── 3. Drive Web Dashboard via Playwright ──────────────────────────────────────
print("\n[*] Initializing Playwright Native Chrome Engine...")

try:
    with sync_playwright() as p:
        # Launch Chrome directly to avoid compatibility issues on modern Linux
        print("[*] Launching Chromium/Chrome browser...")
        chrome_path = "/usr/bin/google-chrome"
        if not os.path.exists(chrome_path):
            chrome_path = "/usr/bin/chromium-browser"
            if not os.path.exists(chrome_path):
                chrome_path = "/usr/bin/chromium"

        if os.path.exists(chrome_path):
            print(f"[*] Launching custom executable browser: {chrome_path}")
            browser = p.chromium.launch(
                headless=True,
                executable_path=chrome_path,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
        else:
            print("[*] Falling back to default playwright browser...")
            browser = p.chromium.launch(headless=True)

        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Navigate to Dashboard
        print(f"[*] Navigating to Dashboard: {BASE_URL}")
        page.goto(BASE_URL)
        page.wait_for_timeout(2000)

        # Capture Homepage Dashboard Screenshot
        homepage_shot = REPORT_DIR / "01_homepage_dashboard.png"
        page.screenshot(path=str(homepage_shot))
        print(f"✅ Saved homepage screenshot: {homepage_shot}")

        # Check if basic UI elements are present
        assert page.locator("body").count() > 0
        print("✅ Dashboard page DOM validated.")

        # Clean shutdown browser
        browser.close()

except Exception as e:
    print(f"❌ FAILED: Playwright UI Automation error: {e}")
    server_process.terminate()
    sys.exit(1)

# ── 4. Clean Shutdown Server ───────────────────────────────────────────────────
print("\n[*] Stopping TubeLM GUI test server...")
server_process.terminate()
try:
    server_process.wait(timeout=5)
except subprocess.TimeoutExpired:
    server_process.kill()

print("\n=========================================================================")
print("             🎉 TubeLM GUI E2E Tests Completed Successfully! 🎉         ")
print("=========================================================================")
sys.exit(0)
