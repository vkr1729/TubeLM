# TubeLM — Features Review, Refinements & Neural Summary TTS Handover Prompt

You are tasked with reviewing, refining, and extending TubeLM's mobile UX and playback pipeline based on the initial implementation of Features 1–4. 

This prompt covers:
1. **Remediation of 3 edge-case UX/playback bugs** identified in code review.
2. **Feature 5: Commute Font Size Stepper (`Aa`)** for tired-eye MRT reading.
3. **Feature 6: Option C Neural Summary TTS (`edge-tts`)** for commute listening with the screen off and lock-screen/AirPods controls.

---

## 1. Core Operating Mandates & Environment

- **Architecture**: Flat "boring code" — vanilla JS and inline CSS in `desktop/templates/reader.html`. All interpolated variables in HTML must use `esc()`. No Tailwind CDN, no npm/webpack toolchains.
- **Python Venv**: `/home/kedarnath-reddy-vallaboina/youtube-project-2/.venv/bin/python`
- **Pytest**: `/home/kedarnath-reddy-vallaboina/youtube-project-2/.venv/bin/pytest`
- **Current Test Status**: All 162 unit/integration tests pass (`162 passed in 33s`). You must keep 100% of tests passing.

---

## 2. Bug Fixes & Refinements for Features 1–4 (`reader.html`)

### Gap 1: Brief Mode Navigation Trap (`selectTop20`)
- **File**: `desktop/templates/reader.html` (around line 1270)
- **Problem**: When `briefMode` is active and the user clicks "Editorial Picks" (`selectTop20()`), the sidebar item highlights, but the reading pane remains stuck in Brief mode because `renderActiveView()` checks `if (briefMode)` first.
- **Fix**: Inside `selectTop20()`, add:
  ```javascript
  if (briefMode) setBriefMode(false);
  ```

### Gap 2: Channel Card Audio Play/Pause Icon Mismatch
- **File**: `desktop/templates/reader.html` (around line 2046)
- **Problem**: `updatePlayIcon()` unconditionally changes `#play-icon` to ⏸ whenever `isAudioPlaying` is true, without verifying if the currently viewed channel's audio URL matches `currentAudioSrc`. If Channel A is playing in the background and the user navigates to Channel B, Channel B's card incorrectly displays a pause icon.
- **Fix**: In `updatePlayIcon()`, check if the active channel on screen matches `currentAudioSrc`:
  ```javascript
  function updatePlayIcon() {
    const icon = document.getElementById('play-icon');
    if (!icon) return;
    const activeCh = (SITE_DATA.weeks[currentWeekKey]?.channels || []).find(c => c.id === selectedItemId);
    const matchesCurrent = activeCh && activeCh.audio_url && activeCh.audio_url === currentAudioSrc;
    if (isAudioPlaying && matchesCurrent) {
      icon.innerHTML = `<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>`;
    } else {
      icon.innerHTML = `<path d="M8 5v14l11-7z"/>`;
    }
  }
  ```

### Gap 3: Resume Stutter / Stream Reload on Channel Play
- **File**: `desktop/templates/reader.html` (around line 1870)
- **Problem**: In `playChannelAudio(chId)`, if the user pauses the active track and taps play again on the same channel card to resume, `globalAudio.paused` is true, falling through to `playIndex(idx)` which re-sets `globalAudio.src` and reloads the network stream from scratch.
- **Fix**: In `playChannelAudio`, if `idx === player.index`, simply toggle play/pause without reloading:
  ```javascript
  if (idx >= 0 && idx === player.index) {
    if (globalAudio.paused) {
      globalAudio.play().catch(() => {});
      isAudioPlaying = true;
    } else {
      globalAudio.pause();
      isAudioPlaying = false;
    }
    updatePlayIcon();
    updateMiniPlayer();
    return;
  }
  ```

---

## 3. Feature 5: Commute Font Size Stepper (`Aa`)

Target: iPhone 16 on the MRT (train commute, bumpy motion, eye fatigue). Hardcoded 13px summaries require eye strain.

1. **CSS Variables & Classes (`reader.html`)**:
   - In `:root`: define `--summary-font-size: 14px;` and `--summary-line-height: 1.65;`.
   - In `.summary-content`: use `font-size: var(--summary-font-size, 14px); line-height: var(--summary-line-height, 1.65);`.
   - Also apply `--summary-font-size` to `.brief-lead` and `.editorial-quote`.
2. **Font Stepper Button (`top-header`)**:
   - Add an `Aa` button next to the theme toggle button in `.top-header`:
     ```html
     <button id="btn-font-size" onclick="cycleFontSize()" class="btn-secondary text-xs" title="Adjust text size">Aa</button>
     ```
3. **Logic & Persistence**:
   - 3 levels:
     - `small`: 13px (compact / desktop)
     - `medium`: 15px (comfortable mobile default)
     - `large`: 17px (relaxed commute reading)
   - Store in `localStorage['tubelm_font_size']`.
   - Apply `data-font="small|medium|large"` to `document.documentElement` or set CSS variables directly.
   - On load, restore the saved font size preference.

---

## 4. Feature 6: Option C Neural Summary TTS via `edge-tts`

Target: Provide a 1-to-2 minute studio-grade spoken audio version of each channel's text summary that works in the background with the screen locked, using the Feature 1 Mini-Player and AirPods controls.

### A. Dependencies & Pipeline Service
1. **Requirements**:
   - Ensure `edge-tts>=7.0.0` is in `desktop/requirements.txt` (already installed in `.venv`).
2. **TTS Module (`desktop/tts_service.py`)**:
   - Create a clean helper module:
     ```python
     import asyncio
     import logging
     import re
     from pathlib import Path
     import edge_tts

     logger = logging.getLogger(__name__)

     # High-signal, natural professional voice
     DEFAULT_VOICE = "en-US-ChristopherNeural"

     def clean_text_for_speech(text: str) -> str:
         """Strips markdown links, citations, and headers for smooth narration."""
         if not text:
             return ""
         # Remove markdown links, leave link text: [text](url) -> text
         t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
         # Remove headers #, ##, ###
         t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
         # Remove bold/italics
         t = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", t)
         # Remove raw URLs
         t = re.sub(r"https?://\S+", "", t)
         # Normalize whitespace
         return " ".join(t.split())

     async def _generate_audio_async(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> bool:
         clean = clean_text_for_speech(text)
         if not clean or len(clean) < 20:
             return False
         output_path.parent.mkdir(parents=True, exist_ok=True)
         temp_out = output_path.with_suffix(".tmp.mp3")
         try:
             communicate = edge_tts.Communicate(clean, voice)
             await communicate.save(str(temp_out))
             temp_out.replace(output_path)
             logger.info("Generated summary TTS audio: %s (%d bytes)", output_path.name, output_path.stat().st_size)
             return True
         except Exception as e:
             logger.warning("edge-tts generation failed: %s", e)
             temp_out.unlink(missing_ok=True)
             return False

     def generate_summary_tts(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> bool:
         """Synchronous entrypoint for pipeline calls."""
         if output_path.exists() and output_path.stat().st_size > 0:
             return True
         try:
             return asyncio.run(_generate_audio_async(text, output_path, voice))
         except Exception as e:
             logger.warning("Failed running async TTS: %s", e)
             return False
     ```

### B. Pipeline Integration & Immediate Backfill (`desktop/main.py` & `desktop/web_reader.py`)

1. **Automatic Build-Time Backfill for Existing Summaries (`desktop/web_reader.py`)**:
   - **CRITICAL REQUIREMENT**: TubeLM already has 18+ channel summaries generated for the current week (`2026-09-04_*_digest.html` / `.json`). We MUST synthesize TTS audio for these existing summaries so the user can listen to them immediately this week!
   - In `build_reader_site()` in `desktop/web_reader.py`:
     When looping over each channel:
     ```python
     tts_filename = f"summary_{d_str}_{ch_data['id']}.mp3"
     tts_path = audio_dir / tts_filename
     # If summary audio is missing, synthesize it immediately from existing summary text
     if not tts_path.exists() or tts_path.stat().st_size == 0:
         summary_text = ch_data.get("full_summary_html") or ch_data.get("summary_preview") or ""
         generate_summary_tts(summary_text, tts_path)
     
     if tts_path.exists() and tts_path.stat().st_size > 0:
         remote = (_audio_storage.upload_audio(tts_path, d_str) if (_audio_storage is not None and _audio_storage.is_configured()) else "")
         if remote:
             ch_data["summary_audio_url"] = remote
         else:
             dest_tts = site_audio_dir / tts_filename
             shutil.copy(tts_path, dest_tts)
             ch_data["summary_audio_url"] = f"audio/{tts_filename}"
         ch_data["summary_audio_seconds"] = _audio_seconds_for(str(tts_path))
     ```
   - Because `edge-tts` takes only ~1–2 seconds per summary, synthesizing all 18 existing channels takes **under 30 seconds total**, runs once, and is permanently cached.

2. **Standalone Backfill CLI (`desktop/tts_service.py`)**:
   - Add a `__main__` block to `desktop/tts_service.py` so running:
     ```bash
     .venv/bin/python desktop/tts_service.py --backfill
     ```
     scans `~/.tubelm/summaries/` for all `*_digest.html` and `*_digest.json` files from the current week, generates any missing `summary_{date}_{channel}.mp3` files, and prints a progress report.

3. **Ongoing Pipeline Integration (`desktop/main.py`)**:
   - In `desktop/main.py`: When future channel summaries are created during regular pipeline runs (`_process_single_source`), call `generate_summary_tts` to create the MP3 alongside the markdown/HTML digest.

### C. Reader UI Integration (`reader.html`)
1. **Affordance in Channel Header**:
   - If `ch.summary_audio_url` is present, add a sleek `🔊 Listen to Summary (~1 min)` button right below the channel title or next to the `Mark as Read` button:
     ```html
     <button onclick="playSummaryAudio('${ch.id}')" class="btn-secondary text-xs" title="Listen to spoken summary">
       🔊 Listen to Summary
     </button>
     ```
2. **Affordance in Brief Mode (`#briefView`)**:
   - In each channel's section inside the 5-Minute Brief view, include a small `🔊 Listen` button so the user can tap and listen on the go.
3. **Player Routing**:
   - Implement `playSummaryAudio(chId)`:
     - Enqueues the summary audio track `{ chId, weekKey, src: ch.summary_audio_url, title: ch.name + ' (Summary)', category: ch.category }` into `player.queue`.
     - Calls `playIndex(...)`.
     - Automatically routes through the bottom Mini-Player, setting MediaSession metadata ("Channel Name (Summary)"), enabling full lock-screen and AirPods controls on iOS!

---

## 5. Verification Protocol

1. **Compilation Check**:
   ```bash
   .venv/bin/python -m py_compile desktop/*.py
   ```
2. **Full Automated Test Suite**:
   ```bash
   .venv/bin/pytest desktop/tests -v
   ```
   All 162 existing tests must pass, plus new tests in `desktop/tests/unit/test_tts.py` verifying text cleaning, TTS file creation, and reader metadata parsing.
3. **Pipeline Dry-Run**:
   ```bash
   .venv/bin/python desktop/main.py --dry-run
   ```
   Must exit with code 0.
4. **Summary Report**:
   Provide a concise report detailing the fixed bugs, new test output, and confirmation that all tests pass.
