# TubeLM v4.0 — High-Signal Web Reader, 2-Week Rolling Purge & Lean Delivery
## (plus v4.0 hardening patch: bounded waits, atomic state, fetch guards, offline SW)

## Outcome
Upgrade TubeLM to handle 37+ sources seamlessly by replacing per-channel email clutter with a fast, mobile-friendly static Web Reader deployed to GitHub Pages (and mirrored locally). Enforces a strict 2-week rolling retention window across NotebookLM and local storage, presents a tiered Top 20 executive briefing, and makes notebooks public for zero-friction audio playback.

The v4.0 hardening patch closes the five P1 findings from the architecture audit
(timeouts, atomicity, SSRF, library `sys.exit`) and the offline-PWA gap, with
18 new regression tests (194 total, all passing). Rationale for each fix is in
the Hardening patch section below; no pipeline behavior or config schema changed.

## Scope
- **Current module (v4.0 Core):**
  1. **Lean Email Policy:** Disable individual channel emails by default (zero spam for 37 channels); deliver only one consolidated weekly Executive Briefing (Top 20 + link to Web Reader).
  2. **Static Web Reader (`desktop/web_reader.py` + `desktop/templates/reader.html`):** Compiles the 2-week rolling digests into an editorial, dark-mode, mobile-responsive HTML reader and `feed.xml` RSS feed, automatically pushed to the `gh-pages` branch and served locally at `/reader`.
  3. **2-Week Automated Purge:** Automatically prune NotebookLM notebooks older than 2 weeks (`NOTEBOOKS_RETENTION_LIMIT=2`) and purge local digests/artifacts older than 14 days.
  4. **Frictionless Audio & Public Sharing:** Automatically enable public link sharing on generated NotebookLM notebooks and download audio overviews into the web reader for native in-browser playback.
  5. **Tiered Top 20 Display:** Structure the cross-source rankings into "Top 10 Must-Watch Editor's Picks" and "Next 10 Notable".
- **Later modules:**
  - Automated weekly cron triggering via systemd user timer.
  - Offline PWA service worker caching for airplane reading.
- **Not included:**
  - Complex multi-user auth, databases, or third-party SaaS hosting (pure static GitHub Pages + local Flask).
  - Heavy JS frontend frameworks (no React/Next.js overhead; lightweight semantic HTML + CSS tokens + vanilla JS).

## Architecture and why
- **Design:** Single-pass static site generator module (`desktop/web_reader.py`) invoked after all source handlers and Top 20 rankings complete. Uses Jinja2 (`desktop/templates/reader.html`) styled with `/ui-ux-pro-max` editorial guidelines (Inter typography, CSS variables, WCAG AAA dark/light mode, mobile-first responsive cards). Pushes the build to an orphan `gh-pages` git branch using standard git commands.
- **Why it fits:** Operates entirely within the existing Python virtual environment and git repository without adding external runtime dependencies, cloud databases, or build steps.
- **Tradeoff:** GitHub Pages build push takes 3-5 seconds over git, but gives the user access to all digests on mobile devices anywhere without running a public web server.
- **Rejected alternative:** Deploying a dynamic Next.js / Vercel full-stack application. Rejected because it introduces unnecessary cloud maintenance, node build toolchains, API routes, and database costs for a personal weekly reading workflow.

## How it works
1. **Source Processing:** Sources are fetched, summarized via NotebookLM, and notebooks are made public via `client.sharing.set_public(notebook_id, public=True)`.
2. **Local Digest Save:** Individual channel HTML digests are written to `~/.tubelm/summaries/`. Individual emails are skipped.
3. **Cross-Source Ranking:** `top10_service.py` ranks the Top 20 items (split into Top 10 Must-Watch and Next 10 Notable).
4. **Site Build & Retention:**
   - `web_reader.py` scans the latest 2 weeks of digests from `~/.tubelm/summaries/` and copies downloaded audio overviews.
   - Deletes any local HTML digests older than 14 days.
   - Renders `index.html` and `feed.xml`.
   - Pushes build artifacts to `gh-pages`.
5. **Lean Notification:** If email is configured, sends a single executive email with the Top 20 highlights and a button to open the live GitHub Pages reader.

## File map
| Path | What it contains | Why it exists / connects to |
| --- | --- | --- |
| `desktop/web_reader.py` | Static site builder, RSS feed generator, and git `gh-pages` deployment runner. | Core module for reading solution. Connects `main.py` and `gui.py` to GitHub Pages. |
| `desktop/templates/reader.html` | Editorial web reader template adhering to `/ui-ux-pro-max` (dark/light mode, fuzzy search, category filter, read tracker). | Presentation layer for the Web Reader and local `/reader` dashboard route. |
| `desktop/config.py` | Updated defaults: `NOTEBOOKS_RETENTION_LIMIT=2`, `channel_emails_enabled=False`, `gh_pages_deploy=True`. | Configuration central hub. |
| `desktop/main.py` | Channel loop skip-channel-email logic, post-batch web reader build trigger, and purge execution. | Pipeline orchestrator. |
| `desktop/notebooklm_service.py` | Default `set_public(notebook_id, True)` and automated 2-week notebook pruning. | NotebookLM integration. |
| `desktop/gui.py` | Added `/reader` route and `/api/reader/data` to mirror the web reader locally in desktop GUI. | Local dashboard integration. |
| `desktop/tests/unit/test_web_reader.py` | Unit tests for site rendering, 2-week pruning, and RSS generation. | Verifies reader generation and cleanup without hitting git remote. |

## Implementation Steps
1. **Configuration & Retention Defaults (`desktop/config.py`, `desktop/notebooklm_service.py`):**
   - Set `NOTEBOOKS_RETENTION_LIMIT = 2` as the standard default.
   - Add `channel_emails_enabled = False` and `deploy_to_gh_pages = True`.
   - Ensure notebook creation automatically sets `public=True` via `client.sharing.set_public`.
2. **Web Reader Generator & Template (`desktop/web_reader.py`, `desktop/templates/reader.html`):**
   - Implement `build_reader_site(summaries_dir, top10_batch, audio_batches)` generating `index.html` and `feed.xml`.
   - Implement `deploy_to_gh_pages()` using local git commands.
   - Design `reader.html` with category filters (`tech`, `health`, `deep_explainer`), fuzzy search, audio player, and LocalStorage read tracker.
3. **Pipeline Hook & Local Dashboard Integration (`desktop/main.py`, `desktop/gui.py`):**
   - Skip individual channel emails by default while ensuring the Top 20 Executive Briefing email sends.
   - Trigger `build_reader_site()` and `deploy_to_gh_pages()` at pipeline finish.
   - Add a "Reader" tab in the desktop GUI linking to the local `/reader` route.
4. **Verification & Tests (`desktop/tests/unit/test_web_reader.py`):**
   - Test 2-week rolling window pruning (verifying files older than 14 days are removed).
   - Test HTML rendering and tiered Top 20 format.

## Hardening patch (audit P1/P2 fixes) — what changed and why
1. **Bounded `edge-tts` (`desktop/tts_service.py`, `TTS_TIMEOUT_SECONDS=90`).**
   Why: synthesis ran with no timeout inside the sequential per-channel loop, so
   one hung websocket stalled every later channel. Now `asyncio.wait_for` fails
   the single narration to `False` (TTS never breaks a run by contract) and the
   pipeline moves on.
2. **Bounded `ffmpeg` (`desktop/web_reader.py`, `FFMPEG_TIMEOUT_SECONDS=120`).**
   Why: `optimize_audio_for_web` could hang the whole site build on one corrupt
   file. Timeout falls back to a plain copy, preserving the existing guarantee.
3. **Atomic GUI state writes (`desktop/gui.py`, `_atomic_write_json_file`).**
   Why: `/api/state/channel` and `/api/reader/read-state` used direct
   `write_text`, so SIGKILL mid-write truncated `state.json`, and concurrent
   pipeline writes could interleave. Both endpoints now use pid-temp +
   `os.replace`, matching the pipeline's `_write_state_file` pattern.
4. **Read-state bounds (`MAX_READ_IDS=5000`, string-only).** Why: the endpoint
   accepted unbounded arbitrary JSON, letting one browser grow
   `read_state.json` without limit. Now sanitized, de-duplicated, capped.
5. **SSRF fetch guard (`_ensure_safe_fetch_url`).** Why: `/api/sources/validate`
   and channel extraction fetched arbitrary user URLs server-side with no
   private-IP check (cloud metadata, intranet). Now blocks non-http(s) schemes
   and hosts resolving to loopback/private/link-local/reserved/multicast
   addresses; RSS validation additionally fetches with a 15s timeout before
   parsing bytes, and trafilatura runs under a 30s pool timeout so a slow host
   cannot hang a Flask worker.
6. **No `sys.exit` in library code (`NotebookLMAuthExpiredError`).** Why:
   `notebooklm_service.process_source_items` called `sys.exit(2)` on unrecoverable
   auth failure, killing testability and skipping cleanup. It now raises; the
   CLI orchestrator (`main.py`) prints `AUTH_REQUIRED` and exits(2) once.
7. **Offline service worker (`sw.js`, generated by `generate_pwa_assets`,
   registered in `reader.html`).** Why: the PWA had manifest/icons but no worker
   (`/sw.js` 404d), so no offline reading. Cache-first for immutable
   date-prefixed audio, stale-while-revalidate for documents — no framework, no
   build step, versioned `tubelm-v1` cache with old-cache purge on activate.
8. **Pipeline cancellation (`PipelineRunner.stop` + `POST /api/run/stop`).**
   Why: a started GUI pipeline was unkillable except by killing the server, and
   `_run` kept a stale `process` handle. `stop()` terminates the subprocess;
   `_run` clears the handle on exit.
9. **Dead-code prune (`notebooklm_service.py`, `gui.py`, `main.py`).** Why:
   pruned video/infographic subsystems left shadowing params (`video_instructions`,
   `generate_cinematic_video`, `generate_infographics`), stub queues, and stale
   docstrings implying features that no longer exist. Removed; kept the two
   compat stubs (`resume_deferred_artifacts`, `generate_artifacts_after_delivery`)
   and the per-source `generate_cinematic_video` metadata field because committed
   tests pin them. Dropped the write-only `GENERATE_INFOGRAPHICS` env key from the
   GUI allowlist.

## Proof checks
1. `.venv/bin/python -m pytest desktop/tests -q` — 194 passed (176 existing + 18 new in `desktop/tests/unit/test_hardening_fixes.py`).
2. `python desktop/web_reader.py --build-only` — builds the site locally into `.tubelm/site` and verifies `index.html`, `feed.xml`, and `sw.js` exist and render cleanly.
3. Live dashboard test: open `http://127.0.0.1:5000/reader` in browser and verify search, filter, audio player, and dark mode toggles.
4. Hardening browser/API sweep: `HOME=/tmp/tubelmtest .venv/bin/python /tmp/tubelmtest/stage_site.py`, start `desktop/gui.py --port 5057` with that HOME, then `.venv/bin/python /tmp/tubelmtest/verify_browser.py` — 20/21 checks pass (reader/sw/manifest routes, read-state cap+sanitize roundtrip, SSRF 400s, run-stop wiring, config masking). The 21st (live Chromium render) is environment-blocked in sandbox-only runners: all local Chromium binaries die with SIGTRAP at startup; re-run `verify_browser.py` on any host where Chromium launches. `node --check` on the generated `sw.js` and tag-balance parse of `index.html` pass as substitute static evidence.

## Run and limitations
- **Run:** Triggered automatically at the end of every weekly TubeLM sync, or manually via `python desktop/web_reader.py`.
- **Limitations:** Automated GitHub Pages push requires git push permissions for the repository. Works offline locally via the desktop dashboard at all times.
