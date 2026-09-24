# Requirements Specification: TubeLM Web & Mobile Sync

## 1. Project Overview & Target User Anchor
- **Project Name:** TubeLM (Personal YouTube & RSS Intelligence Digest)
- **Target User & Scale:** **Single-Person Personal Use Exclusively**.
  - *Hard Constraint:* Strictly reject enterprise complexity, authentication frameworks, microservices, or complex distributed databases.
  - *Web Reader:* Hosted on GitHub Pages (`https://vkr1729.github.io/TubeLM/`) with data synced via Cloudflare Worker/R2.
  - *iOS App:* Native Swift/SwiftUI application running in LiveContainer on iOS with offline caching and background Cloudflare sync.
- **Primary Objective:** Fix critical breakdown where Top 20/Top 14 digest is not formed or displayed on GitHub Pages, restore synchronization with the iOS app, streamline pipeline retries (removing preliminary digest), and fix unreliable audio summary playback.

---

## 2. Functional Requirements (Scope Matrix)

### A. Dynamic Top Digest & Pattern Matching
- **Pattern Generalization:** Generalize all Top digest detection from hardcoded `"Top_20"` / `"Top_10"` checks to robust regex pattern matching `r"^(\d{4}-\d{2}-\d{2})_(?:TubeLM_)?Top_(\d+)_digest\.(html|json)$"` (with `re.IGNORECASE`) across:
  - `desktop/paths.py` (central `is_top_digest_file` and `parse_top_digest_count` helpers).
  - `desktop/web_reader.py` (line 1061 and everywhere file matching occurs).
  - `desktop/tts_service.py` (line 255 to properly skip Top digests during channel TTS synthesis).
  - `desktop/scripts/download_top10.py` and `desktop/scripts/send_top10_from_digests.py` (preserving exclusion polarity).
  - `desktop/tests/unit/`.
- **Dynamic Count Support:** The Top digest must support any candidate count (e.g., 14, 20) without failing:
  - Web Reader reading pane header dynamically displays "Top {N} curated videos" (or honest empty state if N=0).
  - Sidebar count label displays "{N} items".
  - Never parse a Top digest as a regular channel.
  - Mobile `data.json` exports `top20.candidate_count: N` and `top20.items: [...]`.
  - iOS app `ContentStore.swift` and `BriefingView.swift` accept and render any valid feed where `channels` or `top20.items` are present (works with 14, 20, or honest empty state for N=0).

### B. Removal of Preliminary / Interim Digest & New Retry Thresholds
- **Eliminate Interim Digest:** Completely remove the interim / preliminary Top digest logic from `desktop/main.py` and `desktop/top10_service.py`:
  - No interim email is sent during pass 1.
  - No interim HTML or JSON files (`*_interim_digest.*`) are created.
  - Only a single, finalized Top digest is produced after channel iterations complete.
- **Channel Execution & Retry Thresholds:**
  - **Iteration 1 (Initial Run):** Process all sources once. If success rate is **>= 80%**, proceed immediately to digest generation and publish (skip further retries).
  - **Iteration 2 (First Retry):** If Iteration 1 < 80%, retry failed sources. If cumulative success rate reaches **>= 70%**, proceed to digest generation and publish.
  - **Iteration 3 (Final Retry):** If cumulative success rate is **< 70%** after Iteration 2, retry remaining failed sources once more. Regardless of outcome after Iteration 3 (even if < 70%), proceed to digest generation and publish.

### C. Audio Summary Playback Reliability (Web & iOS)
- **Web Reader Audio Unification:**
  - In `desktop/templates/reader.html`, support `summary_audio_url` as a first-class audio source:
    - Display the channel Audio Overview player whenever `ch.summary_audio_url` OR `ch.audio_url` is present.
    - Fix `playChannelAudio(chId)` and `enqueueChannel(chId)` to fall back to `summary_audio_url`.
    - Add an audio listen button on Editorial Picks / Top digest cards so users can listen to spoken summaries directly from the briefing.
    - Fix `buildQueue()` to include spoken summaries when NotebookLM podcasts are absent, so "Play All Unheard" works.
    - Fix `playIndex(i)` audio loading race conditions: handle asynchronous `.play()` properly, listen to `loadedmetadata` / `canplay` before playback, avoid swallowing errors silently, and keep play/pause icons synchronized with actual `HTMLAudioElement` playback state.
- **iOS App Audio Reliability:**
  - In `RootTabView.swift`, enhance `resolveAudioUrl` with fuzzy/slug normalization so channel names with punctuation or slight formatting differences (e.g. `Peter Attia MD` vs `Peter Attia, MD`, `Nutrition Made Simple!`) resolve their summary audio URL reliably.
  - In `desktop/web_reader.py`, ensure `_normalize_mobile_item` and `_normalize_mobile_video` directly embed the resolved `audio_url` from the channel's `summary_audio_url` if not already set.
  - In `AudioPlayerManager.swift`, sanitize and percent-encode URL strings if `URL(string:)` returns nil, use `player.play()` with playback rate, and observe `AVPlayerItem.status` to handle network stalls gracefully.

### D. Automated UAT & Release Automation (Stage 5)
- **Web Reader Playwright UAT:** Run Playwright browser tests against the built static site:
  - Verify Editorial Picks render correctly with dynamic counts (e.g., Top 14 or Top 20).
  - Verify channel list contains only actual channels (no `TubeLM_Top_*` as channels).
  - Verify audio playback controls and audio element loading.
  - Verify light/dark theme toggle and mobile responsiveness.
- **iOS App Automated CI Build:**
  - Push changes to GitHub.
  - Trigger and monitor GitHub Actions workflow (`.github/workflows/build-ios.yml` / `verify.yml`) on macOS runners.
  - Verify iOS tests pass and `.ipa` builds successfully.
- **Deployment:** Automatically deploy the repaired `gh-pages` branch and ensure live site `https://vkr1729.github.io/TubeLM/` is up-to-date and synced.

---

## 3. Interview Record & Decision Log
| # | Functional Question | Recommended Approach | Evaluated Alternatives | User Decision / Rationale |
|---|---------------------|----------------------|------------------------|---------------------------|
| 1 | Target Persona & Scale | Single-user personal CLI/app | Multi-tenant SaaS | Confirmed: Single-user personal use exclusively |
| 2 | Iteration 2 Retry Threshold | Publish if >= 70% after Iteration 2; Iteration 3 only if < 70% | Require >= 90% after Iteration 2 | Confirmed: Publish if >= 70% after Iter 2; Iter 3 only if < 70% (unconditional publish after Iter 3) |
| 3 | Dynamic Top Digest Count | Support dynamic counts (1 to 20+) via regex matching & dynamic UI | Force/pad exactly 20 items | Confirmed: Dynamic counts supported smoothly across web, JSON, and iOS |
| 4 | Removal of Interim Digest | Completely remove preliminary/interim digest | Keep as config flag | Confirmed: Completely remove preliminary/interim digest; single final digest only |
| 5 | Summary Audio Playback | Unify summary TTS audio in Web player and iOS with robust slug matching and error handling | Keep separate audio tracks | Confirmed: Fix hit-or-miss audio playback across Web Reader and iOS App |

---

## 4. Frontier Model Probing Insights & Scope Gaps (Resolved)

### Q1: Canonical N & Match Pattern (§2.A)
- **Canonical N:** Defined as `len(items)` after deduplication. Filename digits are informational hints.
- **Regex Pattern:** `r".*_TubeLM_Top_(\d+)_digest\.(html|json)$"` (interim-free, as interim is completely removed).
- **Match Sites Enumeration:** Centralize detection in a helper function and update:
  - `desktop/web_reader.py:1061`
  - `desktop/tts_service.py:255`
  - `desktop/scripts/download_top10.py:31`
  - `desktop/scripts/send_top10_from_digests.py:48`
- **Dynamic Caps & Display:** Replace hardcoded caps (iOS `prefix(20)`, `reader.html:2744` "Top 20", RSS `top20_items[:10]`) with dynamic count `N`.
- **Empty Digest (N=0):** Honest empty state ("No Top picks this week — 0 candidates found") instead of corrupt cache / crash path.

### Q2: Cumulative Success Rate & Partial Publish (§2.B)
- **Success Rate Formula:** Cumulative rate = `len(completed_source_keys) / total_initial_handlers`.
  - Sources with no new content count as completed/successful.
  - Failures in discovery or processing leave the source key out of `completed_source_keys`.
  - Quota-deferrals pause or exit as before without triggering phantom retries.
- **Retry Scope:** Retries (Iterations 2 & 3) strictly execute only `failed_handlers = [h for h in initial_handlers if h.source_key not in completed_source_keys]`. This prevents double-recording Top-10 candidate batches.
- **Threshold Gating:**
  - Iteration 1: If cumulative rate $\ge 80\%$ (0.80), break to digest generation & publish.
  - Iteration 2: Retry failed sources. If cumulative rate $\ge 70\%$ (0.70), break to digest generation & publish.
  - Iteration 3: Retry remaining failed sources. Proceed to digest generation & publish unconditionally.
- **Partial Publish Disclosure:** When published with $< 100\%$ source success, include a one-line notice in the digest: *"Digest compiled from X of Y channels (Z channels unavailable or deferred)."*

### Q3: Interim Removal Blast Radius (§2.B)
- **Code Surfaces to Cleanse:**
  - `desktop/main.py`: Remove `interim_top10_sent` flag, Stage 0 interim trigger block (`lines 795-815`).
  - `desktop/top10_service.py`: Remove `is_interim` argument, interim batch recording, interim skip branches, `_interim` filename suffix, and `rotate_downloads` coupling. Maintain tolerant-read compatibility for existing batch files containing legacy keys.
  - `desktop/email_service.py`: Remove "EARLY EDITION" and "FINAL EDITION" interim label logic.
- **Artifact Sweep:** One-time cleanup script/step to purge stale `*_interim_digest.*` files from `downloads/` and `site/`.

### Q4: Audio Playback Architecture & Resolution (§2.C)
- **Build-Time Normalization:** Normalize channel names and source names at build time in `desktop/web_reader.py` (lowercase, strip whitespace, strip punctuation e.g. `,`, `!`, `.`) to ensure `source_name` joined with `channel_audio_map` never misses due to punctuation discrepancies.
- **Web Queue Composition (`buildQueue`):** Channel contributions fall back to `summary_audio_url` only when `audio_url` (NotebookLM) is absent. Add `isSummary` attribute to queue items to isolate `isHeard` tracking.
- **Web Audio Lifecycle (`playIndex`):** Eliminate dual-start race conditions. Await `canplay`, execute `.play()`, and drive play/pause UI state strictly from player promise outcomes and native events. Surface playback load errors to the mini-player UI.
- **iOS Audio Handling:** In `AudioPlayerManager.swift`, sanitize and percent-encode absolute URL strings; keep `play()` + playback rate; implement item-scoped `AVPlayerItem.status` KVO observation with teardown on track replace to handle stalls.

### Q5: Runnable Exit Criteria & Release Ordering (§2.D)
- **Localhost Playwright UAT:** Serve built static site directory locally (`http://localhost:...`) rather than `file://`. Assertions:
  - Editorial Picks header reflects dynamic count.
  - Channel list contains zero `TubeLM_Top_*` digest entries.
  - Audio player controls present and audio elements load (`canplay` verified).
  - Theme toggle (`tubelm-theme`) persists in `localStorage` across reloads.
  - Responsive layouts render cleanly across viewports: 390px (mobile), 768px (tablet), 1280px (desktop).
- **iOS CI Build:** Trigger GitHub Actions `.github/workflows/build-ios.yml` on push; verify Swift tests and IPA generation pass on macOS runners.
- **Atomic Deployment:** Scan `site/` for files $> 5\text{MB}$ before push; deploy audio to R2/Worker, write `data.json` last, push `gh-pages`, verify live `https://vkr1729.github.io/TubeLM/data.json` matches local `run_date`.

