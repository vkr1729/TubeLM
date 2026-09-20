# Implementation Plan: TubeLM iOS UAT Remediation (Phase 2 — Final Blueprint)

## 1. Architectural Strategy & Constraints Anchor
- **Persona & Scale:** Single-user personal app exclusively. No multi-tenant auth, no cloud database setup, no complex migrations.
- **Host & Environment:** Sideloaded `.ipa` inside **LiveContainer** on iOS 26 (iPhone 16 baseline), used primarily during Singapore transit commutes with tunnel dead zones.
- **Design Alignment:** Clean Minimalist Executive Briefing archetype:
  - **Light Mode Default** with high-contrast Apple typography (SF Pro / New York serif) and a 3-way toggle (Light / Dark / System) stored via `@AppStorage("tubelm.themeMode")`.
  - **Watched-to-Bottom Feed Partition:** Unread items first, watched/read items at the bottom with original rank badges (`#1..#20`) strictly preserved. Partition logic lives in `TubeLMCore` for 100% Linux testability.
  - **Apple Podcasts-Inspired Player Deck:** Refined ~180pt artwork tile, custom capsule scrubber with dedicated drag gesture, 56pt transport controls, and polished Up Next queue.
- **Sync & Audio Engine:**
  - Event-driven sync to `https://tubelm-sync.kedarvreddy.workers.dev` with alias fan-out (`id`, `video_id`, `url`, normalized URL) and Keychain passphrase storage.
  - Loop-agnostic neural TTS synthesis in `desktop/tts_service.py` with idempotent backfill for `2026-09-18` and verified `summary_audio_url`.

---

## 2. Component Breakdown & Implementation Slices

### Slice 1: TTS Pipeline Bug Fix & Audio Backfill (`desktop/`)
- **Files:**
  - `desktop/tts_service.py`
  - `desktop/web_reader.py`
  - `desktop/tests/unit/test_tts.py`
- **Actions:**
  1. Fix event loop collision in `generate_summary_tts`:
     - Detect active loop via `asyncio.get_running_loop()`.
     - If running in an active loop, execute `_generate_audio_async` on a dedicated worker thread with its own event loop using a pooled `ThreadPoolExecutor`.
     - If no loop is active, call `asyncio.run(_generate_audio_async(...))` directly inline.
     - Never raise; degrade to `False` on error.
  2. Refactor `_backfill_week_async`:
     - Await `_generate_audio_async` directly under the concurrency semaphore (`async with sem:`).
     - Isolate per-channel exceptions with try/except so one failure does not abort the week.
     - Keep idempotent check (skip non-empty MP3s unless `force=True`).
  3. Add unit test in `desktop/tests/unit/test_tts.py`:
     - Verify `generate_summary_tts` succeeds when called from inside an active asyncio event loop (with mocked `edge_tts.Communicate.save`).
     - Verify async backfill awaits the async core directly without calling the sync wrapper.
  4. Run backfill for `2026-09-18` digest:
     ```bash
     .venv/bin/python desktop/tts_service.py --backfill --date 2026-09-18
     ```
  5. Include optional `video_id` in `web_reader.py`'s `_normalize_mobile_item` and `_normalize_mobile_video`.
  6. Rebuild reader site and `data.json`:
     ```bash
     .venv/bin/python -c "from web_reader import build_reader_site; build_reader_site()"
     ```
  7. Verify `summary_audio_url` fields in `site/data.json` are populated with valid URLs.

### Slice 2: Core Identity, Aliases & Feed Partitioning (`TubeLMCore`)
- **Files:**
  - `ios/Sources/TubeLMCore/Sync/SyncIdentity.swift` [NEW]
  - `ios/Sources/TubeLMCore/Models/DigestFeed.swift`
  - `ios/Sources/TubeLMCore/Storage/ContentStore.swift`
  - `ios/Sources/TubeLMCore/Queue/FeedPartition.swift` [NEW]
  - `ios/Sources/TubeLMCore/Sync/CloudflareSyncClient.swift`
  - `ios/Tests/TubeLMCoreTests/SyncIdentityTests.swift` [NEW]
  - `ios/Tests/TubeLMCoreTests/FeedPartitionTests.swift` [NEW]
- **Actions:**
  1. Add optional `videoId` to `FeedItem` and `VideoItem` models in `DigestFeed.swift` (lenient decoding from JSON).
  2. Create `SyncIdentity.swift`:
     - `normalizeVideoUrl(_ url: String?) -> String`: Exact port of `reader.html:normalizeVideoUrl` (extract YouTube `v` parameter or pathname, origin + pathname for articles, raw trimmed fallback).
     - `aliases(id: String, videoId: String?, url: String?) -> Set<String>`: Generates all valid keys (`id`, `videoId`, `url`, `normalizedUrl`).
  3. Update `ContentStore.swift`:
     - Alias-aware `markItemRead(aliases: Set<String>)`: Persists all aliases into `read_ids` (capped at 5,000 LRU) and `item_states` with current timestamp.
     - Alias-aware `unmarkItemRead(aliases: Set<String>)`: Tombstones all aliases in `item_states` (-timestamp) and removes from `read_ids`.
     - `isItemRead(aliases: Set<String>) -> Bool`: Checks if *any* alias exists in `readIDs`.
  4. Create `FeedPartition.swift`:
     - `unreadFirst<T: Identifiable>(items: [T], isRead: (T) -> Bool) -> [T]`: Stable partition preserving relative order of unread items, followed by read items.
     - Badge helper ensuring original rank is preserved (`item.rank ?? originalIndex + 1`).
  5. Update `CloudflareSyncClient.swift`:
     - Change default `baseURL` to `https://tubelm-sync.kedarvreddy.workers.dev`.
     - Cap synced bookmarks to most-recent 200 to protect against payload limit (413).
  6. Add comprehensive Linux-runnable tests in `TubeLMCoreTests`:
     - `SyncIdentityTests`: Vector tests matching JavaScript `normalizeVideoUrl` across YouTube watch, youtu.be, shorts, and RSS articles.
     - `FeedPartitionTests`: Order stability, rank preservation, empty/all-read edge cases.

### Slice 3: App Wiring, Keychain & Settings (`TubeLMApp`)
- **Files:**
  - `ios/Sources/TubeLMApp/TubeLMApp.swift`
  - `ios/Sources/TubeLMApp/Views/RootTabView.swift`
  - `ios/Sources/TubeLMApp/Views/Theme/Typography.swift`
- **Actions:**
  1. **Theme Management:**
     - Add `enum AppThemeMode: String, CaseIterable` (`light`, `dark`, `system`).
     - Root `@AppStorage("tubelm.themeMode")` in `TubeLMApp.swift` defaulting to `"light"`.
     - Apply `.preferredColorScheme(themeMode.colorScheme)` at `WindowGroup` root.
     - Add Theme section to `SyncSettingsSheet` with a 3-way segmented picker.
     - Contrast audit in `Typography.swift`: verify `AppTheme.accentBadgeText`, `whyBackgroundLight`, and secondary backgrounds under Light Mode.
  2. **Keychain Passphrase Storage:**
     - Add simple Keychain helper (~30 lines of `SecItemAdd` / `SecItemCopyMatching` / `SecItemUpdate`) for the sync passphrase, replacing plaintext `UserDefaults`.
  3. **Sync Status Badge & Debounce:**
     - Preserve 1.5s push debounce (`RootTabView.scheduleSyncPush`).
     - Expose 3-state sync connection indicator in `SyncSettingsSheet`: `Synced ✓`, `Connecting…`, `Needs Passphrase / Error`.
     - Add endpoint migration fallback: test new `kedarvreddy` endpoint; if offline/unreachable on first setup, allow fallback.
  4. **One-Way Mark & Scope:**
     - `playItemAudio`: Mark that item as read.
     - Channel `Listen`: Do NOT mark individual videos read (preserving unwatched commute queue).

### Slice 4: Dynamic Partitioned Views & Tap Fix (`TubeLMApp`)
- **Files:**
  - `ios/Sources/TubeLMApp/Views/BriefingView.swift`
  - `ios/Sources/TubeLMApp/Views/ChannelsView.swift`
- **Actions:**
  1. `BriefingView.swift`:
     - Compute partitioned feed: `FeedPartition.unreadFirst(items: items.prefix(20), isRead: isItemRead)`.
     - Rank badge displays `item.rank ?? (originalIndex + 1)`.
     - Wrap mark-watched actions in `withAnimation(.spring(response: 0.35, dampingFraction: 0.8))`.
     - Auto-mark watched when user taps **Play**, **Watch**, **Read**, or the item title.
  2. `ChannelsView.swift`:
     - Keep channel directory order strictly alphabetical/searchable.
     - Inside expanded channel disclosure: partition videos with `FeedPartition.unreadFirst` (non-animated to prevent scroll yank inside expanded cells).
     - **Fix bug in `openVideoLink`**: Change from `onToggleRead` to `onMarkRead` (one-way mark on title tap).

### Slice 5: Player Deck Sheet Redesign (`PlayerDeckSheet.swift`)
- **Files:**
  - `ios/Sources/TubeLMApp/Views/PlayerDeckSheet.swift`
- **Actions:**
  1. **Artwork Tile:**
     - Replace the 100×100 neon box with an elegant ~180×180pt card (24pt corner radius, gentle shadow, subtle emerald gradient `#064e3b` to `#047857`).
     - Dynamic monogram / channel initials with crisp typography and clean border.
  2. **Custom Capsule Scrubber:**
     - Sleek 4pt capsule progress bar with 24pt touch/drag hit target.
     - Dedicated `DragGesture` with `minimumDistance: 10` to prevent scroll-view pan conflicts.
     - Monospace elapsed and duration time labels (`MM:SS` / `MM:SS`).
     - VoiceOver accessibility traits (`.isAdjustable`).
  3. **Balanced Transport Controls (56pt touch target floor):**
     - Center Play/Pause: 64×64pt circular emerald button with tactile depth and shadow.
     - Skip buttons: 56×56pt circular touch targets (`gobackward.15`, `goforward.15`) with secondary background.
     - Playback speed: 56×44pt rounded pill cycling `1.0× → 1.25× → 1.5× → 2.0×`.
  4. **Commute Queue:**
     - Clean "Up Next" section with swipe-to-delete and drag-reorder affordances.
     - Clear empty state card when queue is empty.

---

## 3. Verification & Acceptance Plan

### Automated Verification Suite
1. **TTS Service Unit Tests (Python):**
   ```bash
   .venv/bin/pytest desktop/tests/unit/test_tts.py -v
   ```
2. **Swift Core Package Tests (Linux SPM):**
   ```bash
   cd ios && swift test --enable-code-coverage
   ```
3. **Automated Simulator Acceptance Suite:**
   ```bash
   cd ios && swift test --filter AutomatedSimulatorUATTests
   ```

### Manual Acceptance Verification (Checklist)
1. **Light Mode Default:** Launch app fresh; verify crisp Light Mode is active; open Settings, toggle to Dark Mode and System; verify seamless transitions.
2. **Watched Items to Bottom:** In Briefing tab, tap Play or Watch on item #1; verify item #1 animates to the bottom, marked as watched, while item #2 moves to the top; verify rank badges (`#1`, `#2`) remain intact.
3. **Cloudflare Sync:** Mark 2 items watched; verify sync push to `https://tubelm-sync.kedarvreddy.workers.dev` returns HTTP 200 with synced status; check web reader to verify items show as watched.
4. **Audio Playback:** Tap "Play" on a channel audio summary; verify audio streams smoothly and lockscreen controls respond.
5. **Player Deck Sheet:** Tap mini-player; verify refined ~180pt artwork card, sleek scrubber, 56pt buttons, and smooth commute queue interactions.
