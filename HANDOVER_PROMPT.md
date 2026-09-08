# TubeLM — Architecture Refactor & Bug-Fix Handover Prompt for Muse Spark 1.3

You are tasked with executing a comprehensive architectural refactor and bug-fix sequence for TubeLM, resolving all issues identified in [TUBELM_REVIEW_AND_FIX_PLAN.md](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/TUBELM_REVIEW_AND_FIX_PLAN.md) plus specific user overrides.

---

## 1. Critical Rules & Operating Mandate

1. **No Placeholders or Stubs**: Do not write `# TODO`, `# implement later`, or mock implementations. Every fix must be complete, production-ready, and robust.
2. **Preserve Existing Functionality**: The test suite currently passes with 147 tests (`147 passed in 48s`). You must NOT break existing tests while implementing fixes.
3. **Evidence Before Assertions**: Never declare a task complete without running concrete verification commands and inspecting output.
4. **Environment & Tooling**:
   - Python Virtual Environment: `/home/kedarnath-reddy-vallaboina/youtube-project-2/.venv/bin/python`
   - Pytest Binary: `/home/kedarnath-reddy-vallaboina/youtube-project-2/.venv/bin/pytest`
   - Do NOT use the system `/usr/bin/python3` or `/usr/bin/pytest` (they point to Python 3.14 without project dependencies).
   - Package manager: use `.venv/bin/pip` for any dependency installation.
5. **Credential Security**: Never print, log, or hardcode secrets. All R2 and API secrets must be read strictly from the active environment (`os.getenv`).

---

## 2. Additional User Constraints & Context

1. **Cloudflare R2 Credentials in `.env`**:
   The `.env` file has already been populated with live R2 credentials:
   - `R2_ACCOUNT_ID`
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
   - `R2_BUCKET_NAME`
   - `R2_PUBLIC_DOMAIN`
   Use these credentials to migrate audio off GitHub Pages as specified in T1.

2. **Turn OFF Cinematic Video Generation for RSS Articles**:
   - In `desktop/top10_downloader.py`, `register_top_article_videos(selection)` was previously called unconditionally for non-YouTube items (RSS and web articles).
   - Make Cinematic Video generation for top digest articles **strictly opt-in and disabled by default**.
   - Add `generate_top_article_videos: bool = False` to `desktop/config.py` (backed by `os.getenv("GENERATE_TOP_ARTICLE_VIDEOS", "false")`).
   - Wire this flag into `desktop/top10_downloader.py:download_top10_videos(..., generate_article_videos: bool = False)` and `desktop/top10_service.py`.
   - Ensure all RSS items in `sources.json` maintain `"generate_cinematic_video": false`.

---

## 3. Execution Blueprint & Task Breakdown

Follow the ordered blueprint from Section 4 of [TUBELM_REVIEW_AND_FIX_PLAN.md](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/TUBELM_REVIEW_AND_FIX_PLAN.md):

### Phase 1: Storage, Audio & Deploys (T1, B2, T2)
1. **Audio off Git (T1, B2)**:
   - Install `boto3>=1.34` into `.venv` (`.venv/bin/pip install "boto3>=1.34"`), and add `boto3>=1.34` to `desktop/requirements.txt`.
   - Create `desktop/audio_storage.py` implementing `upload_audio(local, run_date)`, `purge_audio(max_age_days=14)`, `is_configured()`, and S3/R2 client initialization as specified in `TUBELM_REVIEW_AND_FIX_PLAN.md:41-101`.
   - Document the 5 `R2_*` environment variables in `.env.example`.
   - In `desktop/web_reader.py` (`build_reader_site`): if `audio_storage.is_configured()`, upload audio to R2 and set `ch_data["audio_url"]` to the public R2 URL. Retain local copy only as fallback for local GUI `/reader`.
   - In `desktop/web_reader.py` (`deploy_to_gh_pages`): add a hard guard rejecting deployment if any file in `site_dir` is > 5 MB (`5 * 1024 * 1024`).
   - In `desktop/config.py`: change default `compress_audio` to `True`.

2. **Audio Manifest & Exact Run-Date Join (T2)**:
   - In `desktop/notebooklm_service.py` (`process_source_items`): attach `"run_date": today` to `result`.
   - In `schedule_artifacts_after_delivery`: pass `run_date=result["run_date"]` to `register_weekly_audio`.
   - In `desktop/weekly_audio_service.py`: accept and record `run_date`, name audio files `{run_date}_{safe_name}.mp3`, and write atomic updates to `paths.get_audio_dir() / "manifest.json"`.
   - In `desktop/web_reader.py` (`parse_channel_digest`): join audio strictly using `manifest.json` (`f"{run_date}|{safe_name}"`), with legacy fallback ONLY to exact `{run_date}_{safe_name}.mp3`. **Delete the loose `*{safe_name}*.mp3` glob join completely.**

### Phase 2: Pipeline Correctness & Background Jobs (T3, T4, T12)
3. **Build Trigger Correctness (T3, T4)**:
   - In `desktop/main.py`: initialize `successful_keys: list[str] = []` before the retry loop. Change line 832 to check `if not dry_run and completed_source_keys:`.
   - In `_finish_background_artifacts`: take an audio inventory snapshot before and after polling to detect newly landed audio; return `tuple[bool, bool]` (`(ok, new_audio)`).
   - In `main.py`: in `artifacts_only` mode, if `new_audio` is `True`, invoke `_build_and_deploy_reader(cfg)`.

4. **Notebook Retention Sweep (T12)**:
   - In `desktop/notebooklm_service.py`: add `prune_stale_digest_notebooks(client, max_age_days=14)`.
   - In `desktop/main.py`: call this cleanup once after the NotebookLM authentication gate in `async_main`.

### Phase 3: Data Hand-off & Feed Validation (T6, T5)
5. **JSON Sidecar Architecture (T6)**:
   - In `desktop/main.py`: immediately after saving channel digest HTML, write structured metadata to `.json` sidecar (`html_path.with_suffix(".json")`).
   - In `desktop/top10_service.py`: write `.json` sidecar alongside the Top 20 digest HTML.
   - In `desktop/web_reader.py`: implement `parse_channel_digest_json()` using `markdown_it` directly without re-scraping rendered HTML with BeautifulSoup. Prefer `.json` sidecars in `build_reader_site()`, falling back to HTML scraping only when sidecars are missing.
   - Update `purge_old_digests_and_audio` to purge `.json` sidecars alongside HTML.

6. **Well-Formed XML Feed (T5)**:
   - In `desktop/web_reader.py` (`generate_rss_feed`): escape XML entities in `title`, `link`, `guid` using `xml.sax.saxutils.escape`. Wrap `description` in CDATA.
   - Set item `pubDate` using the actual digest `run_date` rather than runtime `now()`.

### Phase 4: Reader Hardening & PWA Polish (T7, T8, T9, T10, T11, T14, B5)
7. **Offline-Ready CSS & XSS Sanitization (T7, T8)**:
   - In `desktop/templates/reader.html`: remove `<script src="https://cdn.tailwindcss.com">`. Replace with the self-contained CSS utility block defined in Section 2 (T7) of `TUBELM_REVIEW_AND_FIX_PLAN.md`.
   - In `desktop/web_reader.py`: escape `</script>` and `<!--` when dumping `SITE_DATA` into the template (`json.dumps(...).replace("</", "<\\/").replace("<!--", "<\\!--")`).
   - In `reader.html`: add an `esc()` escaping helper and wrap interpolated channel names, video titles, and summaries in sidebar and active view rendering.

8. **Audio Controller & Single-Player Lifecycle (T9, T10, T11)**:
   - In `reader.html`: delete the buggy `stalled` audio listener. Implement stall watchdog (12s threshold) + resume on `loadedmetadata`. Persist playback positions per track in `localStorage` (`tubelm_pos:<src>`).
   - Make the audio play icon strictly state-driven.
   - In `toggleRead()`: update the button text in-place using `[data-role="read-toggle"]` instead of re-rendering the entire view and destroying active media elements.
   - Enforce single active YouTube player: cache thumbnail facade on mount, restore facade when switching videos or closing modals, and remove `autoplay=1`.

9. **Pure Build, ISO-Week Bucketing & Static Reader (T14, B5)**:
   - In `desktop/web_reader.py`: partition digests by ISO calendar week (`date.isocalendar()[:2]`), eliminating relative date-distance drift.
   - Move destructive purge calls out of `build_reader_site()` into `desktop/main.py` post-deploy.
   - In `desktop/gui.py`: update `/reader` GET endpoint to serve the static built site rather than rebuilding synchronously on every request.

10. **Linux Arg-Length Guard (T13)**:
    - In `desktop/top10_service.py`: pass candidate summaries to `agy` via stdin or temp file, and cap character budget to prevent `OSError: [Errno 7] Argument list too long`.

11. **Cinematic Video Generation for RSS / Top Digest Articles (User Requirement)**:
    - In `desktop/config.py`: add `generate_top_article_videos: bool = False` (`GENERATE_TOP_ARTICLE_VIDEOS=false`).
    - In `desktop/top10_downloader.py`: only call `register_top_article_videos(selection)` if `generate_article_videos` is explicitly enabled. Default is `False`.
    - In `desktop/top10_service.py`: pass `getattr(cfg, "generate_top_article_videos", False)` to `download_top10_videos`.

---

## 4. Verification Protocol (Mandatory Before Sign-Off)

Run the following checks and inspect the output:

1. **Lint & Syntax Validation**:
   ```bash
   .venv/bin/python -m py_compile desktop/*.py desktop/source_handlers/*.py
   ```
2. **Comprehensive Test Suite**:
   ```bash
   .venv/bin/pytest desktop/tests -v
   ```
   - Must pass all existing tests (147+) plus new tests for:
     - R2 upload guard (>5MB rejection in `deploy_to_gh_pages`).
     - Feed XML well-formedness parsed via `xml.etree.ElementTree`.
     - Exact audio manifest join & absence of glob matching.
     - Top article video registration opt-in flag.
3. **Pipeline Dry-Run**:
   ```bash
   .venv/bin/python desktop/main.py --dry-run
   ```
   - Must successfully discover sources and exit code 0 without errors.
4. **Git Workspace Cleanliness**:
   ```bash
   git status
   ```
   - Review modified and untracked files.

Submit your work only after all 4 verification gates pass with concrete proof.
