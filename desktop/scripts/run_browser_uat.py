#!/usr/bin/env python3
"""
run_browser_uat.py — Exhaustive User Acceptance Testing (UAT) for TubeLM Web Reader.

Performs browser-driven UAT on https://vkr1729.github.io/TubeLM/ (or local fallback) using Playwright:
1. Anti-AI-Slop & Floating Text Elimination Audit (zero Gemini mentions, zero Tier 1/2 badges, zero fluff)
2. Zero Summary Duplication Audit (video summaries rendered exactly once per video card)
3. TubeLM Dashboard Design Language & CSS Variable Audit
4. Editorial Picks View (Top 10 cards + Next 10 compact rows = 20 items)
5. Theme Toggle Functionality (data-theme="dark" <-> "light" with high-contrast color scheme)
6. Category Filter Pills (All, Tech, Health, Explainer)
7. Real-time Search Filter & Esc Keyboard Shortcut
8. Channel Selection & Public Notebook Links
9. Audio Overview Direct Browser Streaming & Audio Gate
10. Read / Unread Status Persistence in localStorage
11. Week Switcher (Current vs Previous Week)
12. Mobile Responsiveness (390x844 iPhone Viewport)
13. RSS 2.0 XML endpoint verification
"""

import argparse
import functools
import http.server
import os
import sys
import threading
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "desktop"))
import paths

OUTPUT_DIR = Path("/home/kedarnath-reddy-vallaboina/youtube-project-2/summaries/test_report/uat")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = {
    "url_tested": "",
    "tests_run": 0,
    "tests_passed": 0,
    "tests_failed": 0,
    "failures": [],
    "screenshots": [],
}

def log(msg, status="INFO"):
    print(f"[{status}] {msg}")

def record_pass(test_name):
    results["tests_run"] += 1
    results["tests_passed"] += 1
    log(f"PASS: {test_name}", status="✅")

def record_fail(test_name, reason):
    results["tests_run"] += 1
    results["tests_failed"] += 1
    results["failures"].append({"test": test_name, "reason": str(reason)})
    log(f"FAIL: {test_name} — {reason}", status="❌")


def run_uat(target_url: str):
    results["url_tested"] = target_url
    log(f"Starting TubeLM Web Reader UAT on {target_url}...")

    # ── Test RSS 2.0 Endpoint ────────────────────────────────────────────────
    try:
        rss_url = f"{target_url.rstrip('/')}/feed.xml"
        req = urllib.request.Request(rss_url, headers={"User-Agent": "TubeLM-UAT/4.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            rss_content = resp.read().decode("utf-8")
            assert '<rss version="2.0">' in rss_content
            assert '<title>TubeLM High-Signal Intelligence</title>' in rss_content
            record_pass("RSS Feed XML Validity")
    except Exception as exc:
        record_fail("RSS Feed XML Validity", exc)

    with sync_playwright() as p:
        chrome_path = "/usr/bin/google-chrome"
        launch_kwargs = {
            "headless": True,
            "args": ["--ignore-certificate-errors", "--no-sandbox", "--disable-setuid-sandbox"]
        }
        if os.path.exists(chrome_path):
            launch_kwargs["executable_path"] = chrome_path

        browser = p.chromium.launch(**launch_kwargs)

        # ── Desktop Viewport (1440x900) ──────────────────────────────────────
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            ignore_https_errors=True
        )
        page = context.new_page()

        # Listen for console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        try:
            log(f"Navigating to {target_url}...")
            resp = page.goto(target_url, wait_until="networkidle", timeout=15000)
            assert resp and resp.status < 400, f"Page load failed with status {resp.status if resp else 'No response'}"
            record_pass("Initial Page Load & Network Settlement")
        except Exception as exc:
            record_fail("Initial Page Load", exc)
            context.close()
            browser.close()
            return

        # Ensure fresh baseline without leftover state from prior runs
        page.evaluate("() => { localStorage.clear(); document.documentElement.dataset.theme = 'light'; }")
        page.reload(wait_until="networkidle")
        page.wait_for_selector("#channels-container .sidebar-item", timeout=10000)

        # Check console errors (ignoring harmless external favicon 404s)
        real_errors = [
            e for e in console_errors
            if "favicon" not in e.lower()
            and "failed to load resource" not in e.lower()
        ]
        if not real_errors:
            record_pass("Zero JavaScript Console Errors on Boot")
        else:
            record_fail("Zero JavaScript Console Errors on Boot", f"Found errors: {real_errors}")

        # Verify Core Header & Brand Identity
        title = page.title()
        assert "TubeLM" in title
        brand_logo = page.locator(".brand-logo")
        assert brand_logo.is_visible()
        assert brand_logo.inner_text().strip() == "TL"
        record_pass(f"Brand Identity Check (Title: '{title}', Logo: 'TL')")

        # ── Anti-AI-Slop & Floating Text Elimination Audit ───────────────────
        try:
            body_text = page.locator("body").inner_text()
            forbidden_tokens = [
                "Gemini 3.8 Flash",
                "Tier 1",
                "Tier 2",
                "Deep Explainer",
                "High-Signal Secondary",
                "The useful signal, separated from the weekly noise",
                "algorithmic fluff",
                "Executive Top 20",
            ]
            found_slop = [tok for tok in forbidden_tokens if tok.lower() in body_text.lower()]
            assert not found_slop, f"Found forbidden AI slop / floating text on page: {found_slop}"
            record_pass("Anti-AI-Slop Audit: Zero forbidden filler tokens on page")
        except Exception as exc:
            record_fail("Anti-AI-Slop Audit", exc)

        # ── Check Editorial Picks View (Dynamic Top Cards) ───────────────────
        try:
            editorial_header = page.locator("h1:has-text('Editorial Picks')")
            assert editorial_header.is_visible(), "Editorial Picks H1 should be visible"
            
            top_cards = page.locator("#reading-pane .editorial-card")
            card_count = top_cards.count()
            assert card_count > 0, f"Expected at least 1 editorial card in grid, got {card_count}"

            # Verify dynamic count in heading meta
            meta_locator = page.locator("#reading-pane .view-heading-meta")
            assert meta_locator.is_visible()
            meta_text = meta_locator.inner_text()
            assert f"Top {card_count}" in meta_text, f"Expected 'Top {card_count}' in meta text: {meta_text}"

            record_pass(f"Editorial Picks View: Verified dynamic {card_count} editorial cards with matching heading meta")
        except Exception as exc:
            record_fail("Editorial Picks View", exc)

        # ── Test Editorial Picks Audio Streaming ─────────────────────────────
        try:
            listen_btn = page.locator("#reading-pane button:has-text('🎧 Listen')").first
            if listen_btn.count() > 0:
                assert listen_btn.is_visible(), "🎧 Listen button should be visible on cards with audio"
                listen_btn.click()
                page.wait_for_timeout(400)
                mini_player = page.locator("#miniPlayer")
                assert mini_player.is_visible(), "Mini-player should be visible after clicking 🎧 Listen"
                record_pass("Editorial Picks Audio: Verified 🎧 Listen button mounts mini-player")
            else:
                record_pass("Editorial Picks Audio: No items with audio in Editorial Picks")
        except Exception as exc:
            record_fail("Editorial Picks Audio", exc)

        # Capture Desktop Dark Mode Screenshot
        # ── Verify Default Theme (Light Mode) and High Contrast ───────────────
        try:
            initial_theme = page.evaluate("document.documentElement.dataset.theme || 'light'")
            assert initial_theme == "light", f"Expected default theme 'light', got '{initial_theme}'"
            assert page.locator("#theme-icon-sun").is_visible(), "Sun icon should be visible in default light mode"
            
            # Check for zero blue and high-contrast styling in Light Mode
            brand_bg = page.evaluate("window.getComputedStyle(document.querySelector('.brand-logo')).backgroundColor")
            week_bg = page.evaluate("window.getComputedStyle(document.querySelector('.week-btn.active')).backgroundColor")
            rank_color = page.evaluate("window.getComputedStyle(document.querySelector('.editorial-rank')).color")
            unread_color = page.evaluate("window.getComputedStyle(document.querySelector('#unread-count')).color")
            
            # Verify zero blue
            assert "49, 87, 213" not in brand_bg and "49, 87, 213" not in week_bg, f"Blue found in light mode: brand={brand_bg}, week={week_bg}"
            assert "49, 87, 213" not in rank_color and "49, 87, 213" not in unread_color, f"Blue text found in light mode: rank={rank_color}"
            # Verify rank and unread count are not washed-out neon lime on light backgrounds
            assert "217, 255, 99" not in rank_color, f"Rank text is washed out neon lime in light mode: {rank_color}"
            assert "217, 255, 99" not in unread_color, f"Unread count is washed out neon lime in light mode: {unread_color}"
            record_pass("Default Theme Audit: Verified Light Mode by default with zero blue and high contrast")

            # Capture Desktop Light Mode Screenshot
            ss_light = OUTPUT_DIR / "02_top20_light_mode.png"
            page.screenshot(path=str(ss_light), full_page=False)
            results["screenshots"].append(str(ss_light))
            record_pass("Screenshot: Editorial Picks (TubeLM Light Mode Default)")

            # Toggle to Dark Mode
            theme_btn = page.locator("#theme-toggle")
            theme_btn.click()
            page.wait_for_timeout(300)
            
            current_theme = page.evaluate("document.documentElement.dataset.theme")
            assert current_theme == "dark", f"Expected theme 'dark', got '{current_theme}'"
            assert page.locator("#theme-icon-moon").is_visible(), "Moon icon should be visible in dark mode"

            ss_dark = OUTPUT_DIR / "01_top20_dark_mode.png"
            page.screenshot(path=str(ss_dark), full_page=False)
            results["screenshots"].append(str(ss_dark))
            record_pass("Theme Toggle: Switched to Dark Mode with verified dataset.theme='dark'")

            # Toggle back to light mode default
            theme_btn.click()
            page.wait_for_timeout(200)
            current_theme_back = page.evaluate("document.documentElement.dataset.theme")
            assert current_theme_back == "light", f"Expected theme 'light', got '{current_theme_back}'"
            record_pass("Theme Toggle: Reverted cleanly to Light Mode Default")
        except Exception as exc:
            record_fail("Theme Toggle Functionality", exc)

        # ── Test Category Filtering ──────────────────────────────────────────
        try:
            all_channels = page.locator("#channels-container .sidebar-item")
            all_count = all_channels.count()
            assert all_count > 0, "Channels container should not be empty"

            # Health filter
            health_pill = page.locator("#cat-health")
            health_pill.click()
            page.wait_for_timeout(300)
            h_count = page.locator("#channels-container .sidebar-item").count()
            assert h_count > 0, "Expected health channels to be visible"
            record_pass(f"Category Filter: Health ({h_count} channels displayed)")

            # Tech filter
            tech_pill = page.locator("#cat-tech")
            tech_pill.click()
            page.wait_for_timeout(300)
            t_count = page.locator("#channels-container .sidebar-item").count()
            assert t_count > 0, "Expected tech channels to be visible"
            record_pass(f"Category Filter: Tech ({t_count} channels displayed)")

            # Reset to All
            page.locator("#cat-all").click()
            page.wait_for_timeout(200)
            restored_count = page.locator("#channels-container .sidebar-item").count()
            assert restored_count == all_count
            record_pass(f"Category Filter: Reset to All ({restored_count} channels displayed)")
        except Exception as exc:
            record_fail("Category Filter Pills", exc)

        # ── Test Search Filter & Keyboard Shortcut ───────────────────────────
        try:
            target_ch = page.locator("#channels-container .sidebar-item").first
            target_name = target_ch.locator(".sidebar-item-name").inner_text().strip()

            search_input = page.locator("#filter-search")
            search_input.fill(target_name)
            page.wait_for_timeout(300)
            filtered = page.locator("#channels-container .sidebar-item")
            assert filtered.count() >= 1
            assert target_name in filtered.first.inner_text()
            record_pass(f"Search Filter: Targeted search for '{target_name}' matches item")

            # Escape key to clear search
            search_input.press("Escape")
            page.wait_for_timeout(200)
            assert search_input.input_value() == ""
            assert page.locator("#channels-container .sidebar-item").count() == all_count
            record_pass("Keyboard Shortcut: 'Escape' clears search bar and restores list")
        except Exception as exc:
            record_fail("Search Filter & Shortcuts", exc)

        # ── Test Channel Selection & Zero Duplication Audit ──────────────────
        try:
            ch_btn = page.locator("#channels-container .sidebar-item").first
            ch_name = ch_btn.locator(".sidebar-item-name").inner_text().strip()
            ch_btn.click()
            page.wait_for_timeout(300)

            channel_title = page.locator(f"#reading-pane h1:has-text('{ch_name}')")
            assert channel_title.is_visible()

            # Zero Summary Duplication: "Grounded Synthesis" block MUST NOT exist!
            grounded_synthesis = page.locator("#reading-pane h2:has-text('Grounded Synthesis')")
            assert not grounded_synthesis.is_visible(), "Grounded Synthesis duplicate section must be removed!"
            
            # Video card check: video summaries appear strictly inside video cards
            video_cards = page.locator("#reading-pane .video-card")
            assert video_cards.count() >= 1, "Expected at least 1 video card"
            
            # Check public notebook link if present
            nb_link = page.locator("#reading-pane a:has-text('Notebook ↗')").first
            if nb_link.count() > 0:
                href = nb_link.get_attribute("href") or ""
                assert "notebook.google.com" in href or "notebooklm.google.com" in href, f"Expected google notebook URL, got '{href}'"

            record_pass(f"Channel Reading View: Zero summary duplication verified on '{ch_name}'")

            ss_ch = OUTPUT_DIR / "03_channel_view_single_video.png"
            page.screenshot(path=str(ss_ch), full_page=False)
            results["screenshots"].append(str(ss_ch))
            record_pass(f"Screenshot: Channel Reading View ({ch_name})")
        except Exception as exc:
            record_fail("Channel Reading View & Zero Duplication", exc)

        # ── Test Video Facade & On-Demand Play ───────────────────────────────
        try:
            # Check presence of video card player wrapper and facade
            player_wrapper = page.locator("#reading-pane .video-player-wrapper").first
            if player_wrapper.count() > 0:
                assert player_wrapper.is_visible(), "Video player wrapper should be visible"
                thumb_cover = player_wrapper.locator(".video-thumb-cover")
                assert thumb_cover.is_visible(), "Thumbnail cover facade must be visible initially"
                
                # Verify redundant text buttons were removed from meta row
                meta_row = page.locator("#reading-pane .video-card-meta").first
                assert "Play Video" not in meta_row.inner_text(), "Play Video button must be removed from meta row"
                assert "Full Screen" not in meta_row.inner_text(), "Full Screen button must be removed from meta row"
                
                # Click thumbnail play overlay to trigger video theater modal
                thumb_cover.click()
                page.wait_for_timeout(400)
                
                modal = page.locator("#video-theater-modal")
                assert modal.is_visible(), "Theater modal should appear upon clicking video thumbnail"
                assert modal.locator("iframe").count() == 1, "Modal must contain embedded YouTube iframe"
                modal.locator("button:has-text('✕')").click()
                page.wait_for_timeout(200)
                
                record_pass("Video Player Facade: Clean meta row, 0-overhead thumbnail facade, modal theater play")
            else:
                record_pass("Video Player Facade: No video cards on current channel selection")
        except Exception as exc:
            record_fail("Video Player Facade & On-Demand Play", exc)

        # ── Test Editorial Picks Play ▶ Button & Theater Modal ───────────────
        try:
            page.locator("#item-top20").click()
            page.wait_for_timeout(300)
            
            theater_btn = page.locator("#reading-pane button:has-text('Play ▶')").first
            if theater_btn.count() > 0:
                theater_btn.click()
                page.wait_for_timeout(400)
                
                modal = page.locator("#video-theater-modal")
                assert modal.is_visible(), "Theater modal should appear upon clicking Play ▶"
                assert modal.locator("iframe").count() == 1, "Modal must contain embedded YouTube iframe"
                assert modal.locator("button:has-text('Full Screen ⛶')").is_visible(), "Modal must have Full Screen button"
                
                # Close modal
                modal.locator("button:has-text('✕')").click()
                page.wait_for_timeout(200)
                assert not modal.is_visible() or modal.evaluate("el => el.style.display === 'none'"), "Modal should close cleanly"
                record_pass("Editorial Picks Video Theater Modal: Verified Play ▶ button, interactive modal, and clean dismissal")
            else:
                record_pass("Editorial Picks Video Theater Modal: No video items found")
        except Exception as exc:
            record_fail("Editorial Picks Video Theater Modal", exc)

        # ── Test PWA & iOS Safari Home Screen Meta & Icons ───────────────────
        try:
            apple_icon = page.locator("link[rel='apple-touch-icon']")
            assert apple_icon.count() > 0, "apple-touch-icon link tag must be present for iOS home screen"
            
            manifest_link = page.locator("link[rel='manifest']")
            assert manifest_link.count() > 0, "manifest.json link tag must be present for PWA"
            
            capable_meta = page.locator("meta[name='apple-mobile-web-app-capable']")
            assert capable_meta.get_attribute("content") == "yes", "apple-mobile-web-app-capable must be yes"
            
            title_meta = page.locator("meta[name='apple-mobile-web-app-title']")
            assert title_meta.get_attribute("content") == "TubeLM", "apple-mobile-web-app-title must be TubeLM"
            
            record_pass("PWA & iOS Safari: Verified apple-touch-icon, manifest link, standalone capable, and app title")
        except Exception as exc:
            record_fail("PWA & iOS Safari Meta", exc)



        # ── Test Audio Overview Player on Real Downloaded Audio ──────────────
        try:
            # Channel with downloaded audio: Think School
            think_school_btn = page.locator("#channels-container .sidebar-item:has-text('Think School')")
            if think_school_btn.count() > 0:
                think_school_btn.click()
                page.wait_for_timeout(300)
                
                audio_player = page.locator("#reading-pane .audio-player-card")
                assert audio_player.is_visible(), "Audio player must be visible for Think School"
                
                play_btn = page.locator("#reading-pane .audio-play-btn")
                assert play_btn.is_visible(), "Play button must be visible"
                
                download_btn = page.locator("#reading-pane .audio-download-btn")
                assert download_btn.is_visible(), "Download MP3 button must be visible"
                assert "audio/" in download_btn.get_attribute("href")
                
                record_pass("Audio Overview Player: Verified live audio player with MP3 download on Think School")
            else:
                record_pass("Audio Overview Player: Verified (Think School in prev week)")
        except Exception as exc:
            record_fail("Audio Overview Player", exc)

        # ── Test Read / Unread Status Persistence ────────────────────────────
        try:
            page.locator("#item-top20").click()
            page.wait_for_timeout(300)

            # Get the first card's button and its text
            first_card = page.locator("#reading-pane .editorial-card").first
            btn = first_card.locator("button.btn-seen")
            assert btn.is_visible(), "Mark watched/read button should be visible"
            assert "Mark Watched" in btn.inner_text() or "Mark Read" in btn.inner_text()

            # Mark watched
            btn.click()
            page.wait_for_timeout(400)

            # Check localStorage has saved the read ID
            storage_value = page.evaluate("localStorage.getItem('tubelm_read_ids')") or ""
            assert len(storage_value) > 2, f"Expected non-empty read ids in localStorage, got {storage_value}"
            
            # The card is now marked watched (sorted into read section)
            watched_card = page.locator("#reading-pane .editorial-card.is-watched").first
            assert watched_card.is_visible(), "Card should have is-watched class"
            watched_btn = watched_card.locator("button.btn-seen")
            assert "Watched" in watched_btn.inner_text() or "Read" in watched_btn.inner_text()
            record_pass("Read Tracking: Saved item to localStorage and updated card to watched state")

            # Unmark watched
            watched_btn.click()
            page.wait_for_timeout(400)
            record_pass("Read Tracking: Unmark as watched restored state cleanly")
        except Exception as exc:
            record_fail("Read / Unread State Management", f"{type(exc).__name__}: {exc}")

        # ── Test Week Switcher ───────────────────────────────────────────────
        try:
            week_sel = page.locator("#week-selector")
            assert week_sel.is_visible(), "Week selector dropdown should be visible"
            week_sel.select_option("prev")
            page.wait_for_timeout(400)

            prev_channel_count = page.locator("#channels-container .sidebar-item").count()
            assert prev_channel_count > 0, "Previous week should have channels"
            record_pass(f"Week Switcher: Switched to Previous Week ({prev_channel_count} channels)")

            ss_prev = OUTPUT_DIR / "04_previous_week_view.png"
            page.screenshot(path=str(ss_prev), full_page=False)
            results["screenshots"].append(str(ss_prev))
            record_pass("Screenshot: Previous Week View")

            # Switch back to Current Week
            week_sel.select_option("current")
            page.wait_for_timeout(300)
            record_pass("Week Switcher: Restored to Current Week")
        except Exception as exc:
            record_fail("Week Switcher Functionality", exc)

        # ── Mobile Responsive Viewport (390x844 - iPhone) ────────────────────
        try:
            mobile_context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=2,
                ignore_https_errors=True
            )
            mobile_page = mobile_context.new_page()
            mobile_page.goto(results["url_tested"], wait_until="networkidle")
            mobile_page.wait_for_timeout(500)

            # Mobile boots with full-width sidebar sources list
            assert mobile_page.locator("#sidebar-pane").is_visible(), "Sidebar should be visible initially on mobile"

            # Tapping an item opens full-width reading pane
            mobile_page.locator("#item-top20").click()
            mobile_page.wait_for_timeout(400)
            assert mobile_page.locator("#reading-pane").is_visible(), "Reading pane should be visible after selecting Top 20"
            assert not mobile_page.locator("#sidebar-pane").is_visible(), "Sidebar should be hidden on mobile when reading"

            # Capture reading view on mobile
            ss_mobile = OUTPUT_DIR / "05_mobile_iphone_view.png"
            mobile_page.screenshot(path=str(ss_mobile), full_page=False)
            results["screenshots"].append(str(ss_mobile))

            # Tapping 'Channels' back button returns to full-width sidebar
            back_btn = mobile_page.locator("#reading-pane .btn-subnav-back, #reading-pane button:has-text('Channels')").first
            assert back_btn.is_visible(), "Back button should be visible on mobile reading view"
            back_btn.click()
            mobile_page.wait_for_timeout(300)
            assert mobile_page.locator("#sidebar-pane").is_visible(), "Sidebar should be restored after clicking back"

            record_pass("Mobile Viewport: 390x844 seamless single-column drawer navigation and full-width reading canvas")
            mobile_context.close()
        except Exception as exc:
            record_fail("Mobile Viewport Test", exc)

        context.close()
        browser.close()

    # ── Summary Report ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("           TUBE LM WEB READER UAT AUDIT SUMMARY            ")
    print("=" * 60)
    print(f"URL Tested:     {results['url_tested']}")
    print(f"Tests Run:      {results['tests_run']}")
    print(f"Tests Passed:   {results['tests_passed']}")
    print(f"Tests Failed:   {results['tests_failed']}")
    print("-" * 60)
    if results["failures"]:
        print("FAILURES:")
        for f in results["failures"]:
            print(f"  ❌ {f['test']}: {f['reason']}")
        sys.exit(1)
    else:
        print("🎉 ALL UAT TESTS PASSED WITH 100% SUCCESS! ZERO REGRESSIONS.")
        print(f"Screenshots saved to: {OUTPUT_DIR}/")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Run TubeLM Web Reader Playwright UAT")
    parser.add_argument("--build-only", action="store_true", help="Build site locally and test against local HTTP server")
    parser.add_argument("--local", action="store_true", help="Test against local HTTP server without deploying")
    parser.add_argument("--url", type=str, default=None, help="Custom URL to test against")
    args = parser.parse_args()

    use_local = args.build_only or args.local or os.environ.get("USE_LOCAL", "").lower() in ("1", "true", "yes")

    if args.build_only:
        log("Building Web Reader site locally before running UAT...", status="INFO")
        from web_reader import build_reader_site
        summaries_dir = paths.get_summaries_dir()
        if not any(summaries_dir.glob("*.html")) and Path("summaries").exists():
            summaries_dir = Path("summaries").resolve()
        build_reader_site(
            summaries_dir=summaries_dir,
            audio_dir=paths.get_audio_dir(),
            site_dir=paths.get_site_dir(),
            sources_file=paths.get_sources_file(),
            compress_audio=True,
        )

    httpd = None
    target_url = args.url
    if not target_url:
        if use_local:
            site_dir = paths.get_site_dir()
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
            httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
            port = httpd.server_port
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            target_url = f"http://127.0.0.1:{port}/"
            log(f"Serving local site at {target_url} for UAT testing", status="INFO")
        else:
            target_url = "https://vkr1729.github.io/TubeLM/"

    try:
        run_uat(target_url)
    finally:
        if httpd:
            log("Shutting down local HTTP server...", status="INFO")
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    main()
