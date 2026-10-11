# Implementation Plan: TubeLM Video-Level Audio Summaries & Playlist Queues

## 1. Architectural Blueprint
- **Runtime & Stack:** Python 3.14 (Desktop Pipeline & Web Reader Builder), Vanilla JS + Tailwind CSS (Static Web Reader PWA), Swift 6 / SwiftUI (iOS App Core / LiveContainer).
- **Component Boundaries:**
  - `desktop/tts_service.py`: Text cleaning with strategic pausing, neural speech synthesis (`edge-tts`), video safe ID generation, and async per-video synthesis engine.
  - `desktop/main.py`: Source processing loop, sidecar text persistence, and batch audio generation hook.
  - `desktop/web_reader.py`: Video audio manifest resolution, canonical video key join (`canonical_video_key`), Top 20 audio wiring, mobile `data.json` normalization, and retention regex.
  - `desktop/templates/reader.html`: Interactive PWA UI, `tubelm_player_v2` playlist engine, per-card listen triggers, heard store with alias/cap, and auto-watched synchronization.
- **Data Flow Diagram / Pipeline:**
  ```text
  [Source Handler] -> [Channel Videos + Markdown Summary]
         |
         v
  [_split_markdown_summary_by_videos] -> Per-Video Markdown
         |
         v
  [clean_text_for_speech] (Strips #, /, \, backticks; inserts strategic pauses before whitespace collapse)
         |
         v
  [generate_video_summary_tts / _backfill_week_async] -> summary_video_{date}_{safe_id}.mp3 -> [R2 Upload]
         |
         v
  [build_reader_site] -> [canonical_video_key Join] -> Top 20 & Channel Video cards (no channel fallback)
         |
         v
  [reader.html] -> Mini-Player Queues (tubelm_player_v2: Top 20 / Channel / Site-wide)
         |
         v (90%+ played or ended)
  [markHeard(key)] + [markVideoWatchedState(videoId, url, true)]
  ```

---

## 2. Component Breakdown & Execution Order

### Slice 0: Identity Contract, URL Normalization & Retention Regex
1. **`desktop/web_reader.py`**:
   - Extend `extract_youtube_video_id(url)` to handle `shorts/` URLs in addition to `/watch?v=`, `/embed/`, `youtu.be/`, `/v/`.
   - Implement `canonical_video_key(item: dict) -> str`: Exact 11-char YouTube `video_id` (case-sensitive) -> canonical URL (`youtu.be` / `shorts/` -> `youtube.com/watch?v=`, tracking params stripped) -> `sha256(title_lower)[:16]`.
   - Update `_AUDIO_DATE_RE` to `r"^(?:summary_(?:video_)?)?(\d{4}-\d{2}-\d{2})_"` so per-video files respect rolling 2-week local retention.
2. **`desktop/tts_service.py`**:
   - Implement `clean_video_safe_id(video: dict) -> str`: Return valid 11-char YouTube `video_id`, or `sha256(url)[:12]` for RSS/articles.
   - Implement `video_summary_filename(run_date: str, safe_id: str) -> str`: `f"summary_video_{run_date}_{safe_id}.mp3"`.

### Slice 1: Speech Cleaning, Natural Pausing & Synthesis Engine
1. **`desktop/tts_service.py`**:
   - Update `clean_text_for_speech(text: str) -> str`:
     - Order-sensitive pause insertion: ensure markdown headings (e.g. `### The Hook`, `### The Mechanics & Evidence`) without terminal punctuation have `". "` appended *before* whitespace collapsing.
     - Strip markdown hashes (`#`, `##`, `###`), stray backticks (`` ` ``), backslashes (`\`, `\$` -> `$`).
     - Handle slashes: convert `and/or` to `and or`, strip isolated slashes while preserving dates (`2026/10/11`) and fractions (`1/2`).
   - Implement `generate_video_summary_tts(title: str, channel_name: str, summary_md: str, output_path: Path, ...) -> bool`:
     - Spoken script: `f"{title}, by {channel_name}. {cleaned_summary}"`.
     - Skip synthesis and return `False` if cleaned summary body is `< 20 chars`.
   - Update `_backfill_week_async`:
     - Deprecate monolithic channel TTS generation.
     - Synthesize video-level audio files using `_split_markdown_summary_by_videos()` at concurrency 3.
     - Log `{scanned, generated, skipped, failed}` statistics.

### Slice 2: Pipeline Integration & Build-Time Audio Wiring
1. **`desktop/main.py`**:
   - In source processing loop (around lines 730–736):
     - Extract per-video markdown summaries using `_split_markdown_summary_by_videos()`.
     - Save sidecar JSON with video metadata and `audio_file` references.
     - Remove monolithic channel TTS call.
2. **`desktop/web_reader.py`**:
   - In `parse_channel_digest_json()`:
     - Detect and attach video-level `audio_url` from sidecar or local audio dir (`summary_video_{run_date}_{safe_id}.mp3`).
   - In `build_reader_site()`:
     - Build `video_audio_map` keyed by `canonical_video_key`.
     - Wire Top 20 items to their specific video audio via `canonical_video_key`.
     - Remove channel-level audio fallback (`:1188-1191`) for Top 20 items: if no video audio exists, set `audio_url = ""` (renders no listen button).
     - In `_normalize_mobile_item` and `_normalize_mobile_video`: attach video-level `audio_url` and remove `fallback_audio` channel fallback (`:1265-1266`).
     - Skip `optimize_audio_for_web` for `summary_video_*.mp3` (already optimal mono MP3).

### Slice 3: Web Reader UI, Playlist Queues & Watched Sync
1. **`desktop/templates/reader.html`**:
   - **Editorial Picks (Top 20)**:
     - Add `🎧 Play All Top 20 Summaries` action button in the Top 20 header (hidden if 0 Top 20 videos have audio).
     - Each Top 20 card renders `🎧 Listen` button only when `item.audio_url` is present (playing specific video audio).
   - **Channel View**:
     - Replace header `🔊 Listen` with `🎧 Play Summaries` (hidden if 0 channel videos have audio; preserve legacy channel audio if historical week).
     - Add `🎧 Listen` button to each video card in `videosHtml` when `v.audio_url` is present.
   - **Queue Engine (`tubelm_player_v2`)**:
     - Standardized track shape: `{key, videoId, url, src, title, channelName, channelId, category, rank, weekKey}`.
     - `queueTop20(weekKey)`: Queues Top 20 tracks (#1 to #20, skipping empty audio).
     - `queueChannel(weekKey, chId)`: Queues that channel's videos in order.
     - `queueAll(weekKey)`: Queues Top 20 first (#1 to #20), followed by remaining channel videos by category with **set-minus deduplication** on `key`.
     - `queueNext()`: Automatically skips already-heard tracks forward.
     - `queuePrev()`: Does not skip backward.
     - Migrate `loadPlayer` from legacy `tubelm_player` to `tubelm_player_v2`.
   - **Heard & Watched Synchronization**:
     - In `timeupdate` (at ≥ 90% duration and finite duration) or `onended`:
       - Mark `tubelm_heard:{week}:{key}` (and `src` alias), pruned to 1000 items.
       - Automatically call `markVideoWatchedState(videoId, url, true)` to mark the card as `Watched ✓` (or `Read ✓`).
   - **Mini-Player**:
     - Displays `"${Channel Name} · ${Video Title}"` and dynamic category/rank badge.

### Slice 4: Automated Verification, CI Build & Release
1. Run local test suite: `pytest desktop/tests/unit/test_tts.py desktop/tests/unit/test_web_reader.py -v`.
2. Build static Web Reader: `.venv/bin/python desktop/web_reader.py --build-only`.
3. Commit and push changes to GitHub.
4. Monitor GitHub Actions (`build-ios.yml` / `verify.yml`) on macOS runners to compile the iOS app and execute automated simulator acceptance tests.
5. Confirm all CI checks are green before release.

---

## 3. Frontier Architectural Review & Enhancements
- **P0-1 Identity Resolution:** Unified canonical video key (`canonical_video_key`) with YouTube `shorts/` normalization and exact case-sensitive matching.
- **P0-2 Synthesis Architecture:** Retained async batch synthesis (`_backfill_week_async`) with concurrency 3, eliminating inline pipeline runtime blowup.
- **P0-3 Speech Cleaning Order:** Order-sensitive pause insertion: heading pauses appended before whitespace collapse. Enhanced slash/backslash handling (`and or`, `$`, dates preserved).
- **P1-1 Retention & R2:** Updated `_AUDIO_DATE_RE` regex, skipped redundant re-encoding on TTS MP3s, and added historical-week guards.
- **P1-2 Player Migration:** Upgraded `tubelm_player_v2`, dual-key heard lookup with prune cap, forward-only heard skipping, and 90%+ duration guard with finite check.

---

## 4. Verification & Guardrails
- **Automated Tests:**
  - `pytest desktop/tests/unit/test_tts.py -v` (Speech cleaning, pause insertion, safe ID generation, TTS synthesis)
  - `pytest desktop/tests/unit/test_web_reader.py -v` (Canonical key, Shorts URL extraction, Top 20 wiring without channel fallback, retention regex)
  - `.venv/bin/python desktop/web_reader.py --build-only` (Static build verification)
- **CI Verification:** GitHub Actions macOS runner builds iOS app and executes automated tests.
- **Circuit Breaker Rule:** If 2 consecutive failed attempts occur during implementation, invoke frontier model stuck guidance immediately (`cmd -t -p "Emergency guidance..."`).
