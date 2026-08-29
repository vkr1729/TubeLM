#!/usr/bin/env python3
"""
test_gui_e2e.py — Comprehensive End-to-End GUI & API Test Suite for TubeLM.
Launches the Flask Web Dashboard, queries all active API endpoints, drives the browser
via Playwright utilizing native Chrome, and validates both dashboard themes.
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
REPORT_DIR = Path(
    os.environ.get(
        "TUBELM_E2E_REPORT_DIR",
        str(ROOT_DIR / "summaries" / "test_report"),
    )
).resolve()

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

venv_python = ROOT_DIR / ".venv" / "bin" / "python"
python_bin = str(venv_python) if venv_python.exists() else sys.executable
server_process = subprocess.Popen(
    [python_bin, str(PROJECT_DIR / "gui.py"), "--port", str(PORT)],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=str(PROJECT_DIR),
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

    # B. Audit /api/sources (GET)
    print(" -> GET /api/sources ... ", end="")
    resp = requests.get(f"{BASE_URL}/api/sources", timeout=5)
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
    # New category-based structure
    assert "categories" in prompts
    assert "prompts" in prompts
    assert "tech" in prompts["prompts"]
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

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            color_scheme="dark",
        )
        page = context.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        # Navigate to Dashboard
        print(f"[*] Navigating to Dashboard: {BASE_URL}")
        navigation = page.goto(BASE_URL)
        assert navigation and navigation.ok
        page.wait_for_timeout(2000)

        # Capture Homepage Dashboard Screenshot
        homepage_shot = REPORT_DIR / "01_dashboard.png"
        page.screenshot(path=str(homepage_shot))
        print(f"✅ Saved homepage screenshot: {homepage_shot}")

        # Validate the overview and every primary navigation destination.
        assert page.locator("html").get_attribute("data-theme") == "dark"
        assert page.locator("#dashboard h1").inner_text() == "Briefings, under control."
        assert page.locator(".metric-card").count() == 4
        expected_tabs = {
            "sources": "Content Sources",
            "settings": "Settings",
            "run": "Run Pipeline",
            "digests": "Digests Library",
        }

        # The theme switch must update immediately and survive navigation/reload.
        page.locator("#theme-toggle").click()
        assert page.locator("html").get_attribute("data-theme") == "light"
        assert page.locator("#theme-toggle-label").inner_text() == "Dark mode"
        page.wait_for_timeout(250)  # Allow the surface-color transition to settle.
        for tab_id, heading in expected_tabs.items():
            page.locator(f'.nav-item[data-tab="{tab_id}"] button').click()
            assert page.locator(f"#{tab_id} h1").inner_text() == heading
        page.locator('.nav-item[data-tab="dashboard"] button').click()
        page.reload()
        page.wait_for_timeout(300)
        assert page.locator("html").get_attribute("data-theme") == "light"
        page.locator("#theme-toggle").click()
        assert page.locator("html").get_attribute("data-theme") == "dark"

        for tab_id, heading in expected_tabs.items():
            page.locator(f'.nav-item[data-tab="{tab_id}"] button').click()
            assert page.locator(f"#{tab_id}").is_visible()
            assert page.locator(f"#{tab_id} h1").inner_text() == heading

        page.set_viewport_size({"width": 1280, "height": 800})
        page.locator('.nav-item[data-tab="sources"] button').click()
        page.locator("#channels-table-body tr").first.wait_for()
        page.locator(".content-area").evaluate(
            "el => { el.scrollTop = document.querySelectorAll('#sources .glass-card')[1].offsetTop - 24; }"
        )
        page.mouse.move(1240, 40)
        page.wait_for_timeout(400)
        sources_shot = REPORT_DIR / "02_sources.png"
        page.screenshot(path=str(sources_shot))

        page.locator('.nav-item[data-tab="run"] button').click()
        page.locator(".content-area").evaluate("el => { el.scrollTop = 0; }")
        page.mouse.move(1240, 40)
        page.wait_for_timeout(400)
        run_shot = REPORT_DIR / "03_run_console.png"
        page.screenshot(path=str(run_shot))

        page.locator('.nav-item[data-tab="dashboard"] button').click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(250)
        mobile_shot = REPORT_DIR / "04_mobile_dashboard.png"
        page.screenshot(path=str(mobile_shot), full_page=True)
        assert page.locator(".sidebar").is_visible()
        assert not page.locator(".brand").is_visible()
        assert not page_errors, f"Browser JavaScript errors: {page_errors}"
        print("✅ Both themes, navigation, responsive layout, and JavaScript console validated.")

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
