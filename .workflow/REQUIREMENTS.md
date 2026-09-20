# Requirements Specification: TubeLM iOS (LiveContainer Native)

## 1. Project Overview & Target User Anchor
- **Project Name:** TubeLM iOS (Native Reader for LiveContainer)
- **Target User & Scale:** **Single-Person Personal Use Exclusively**.
  - *Hard Constraint:* Strictly reject enterprise complexity, multi-tenant databases, user authentication frameworks, or remote cloud server maintenance.
  - *Host Environment:* Installed and executed inside **LiveContainer** on iOS (JIT / unsigned side-loading container).
  - *Target Platform:* **iOS 26 baseline** running on **iPhone 16** (solid, vetted API surface avoiding bleeding-edge iOS 27 day-1 instability).
  - *User Usage Profile:* Opened **7–8 times weekly** during commute (Singapore network / transit). Snappy streaming + local offline caching when in transit dead zones.
- **Primary Objective:** Deliver a native, fluid, high-signal mobile reader for the weekly TubeLM digest, replacing the PWA with instantaneous cold starts, native 120Hz ProMotion scrolling, lockscreen & headphone audio controls (`AVAudioPlayer` + `MPNowPlayingInfoCenter`), tactile haptics, and zero-touch weekly content refresh.

---

## 2. Functional Requirements (Scope Matrix)
- **Inputs & Data Sources:**
  - Automated ingestion of `site_data` / `data.json` (`schema_version: 1`) published weekly to GitHub Pages (`https://vkr1729.github.io/TubeLM/`).
  - Audio files hosted on Cloudflare R2 / Audio CDN (`/tubelm/audio/...`) or GitHub Pages (`/audio/...`).
- **Core Transformations & Workflows:**
  - **Zero-Input Auto-Refresh (Stale-While-Revalidate):** On every app launch or foreground transition, the app performs a silent, single-flight `ETag` / `If-Modified-Since` check against the remote `data.json`. If a new weekly digest is published, the app atomically updates the local cache without interrupting the user.
  - **Fast Streaming & Transparent Caching:** Leveraging high-speed Singapore connectivity for instant streaming playback with transparent local disk caching so subway tunnels are protected.
  - **Granular Watch/Read Interactions:**
    - Clean concise action buttons: **"Watch"** for YouTube videos, **"Read"** for articles and newsletters.
    - Direct tap: Tapping any item title immediately opens the target link (YouTube app or Safari) and **automatically marks the item as watched/read**.
    - When all items in a channel are completed, the channel header automatically switches to **"✓ Channel Completed"**.
  - **Channel Multi-Item Breakdown (Tab 2):**
    - Expandable channel view disclosing every individual video/article (e.g. all 6 items in MIT Tech Review or IBM Technology).
    - Rich formatted Markdown rendering for all summaries (proper paragraphs, bold keywords, formatted bullet points).
    - **Smart Unwatched Audio Playback:** Tapping "Listen Unwatched" dynamically filters playback to *only* narrate the remaining unwatched summaries, skipping already watched ones.
  - **Commute Queue Integrated into Player Deck:**
    - Dropped from separate tab; anchored directly to the Player (like Spotify & Castro).
    - Tapping the sticky Mini-Player slides up the **Commute Deck & Queue Sheet** modal with Now Playing controls (56pt touch targets, scrubber, 15s skip, 1.25x speed) and the full **"Up Next in Commute Queue"** list.
    - Explicit `+ Queue` buttons on all Briefing and Channel items.
  - **Unlimited Text Bookmarks (Tab 3):**
    - Dedicated tab for permanent saved articles & digests.
    - Pure text summaries with negligible footprint (~2 KB each). Audio caching for bookmarks dropped entirely, enabling **unlimited bookmarks**.
  - **Event-Driven Cloudflare Worker Sync:**
    - Connects to `tubelm-sync.<subdomain>.workers.dev` (`worker/worker.js`) using `Authorization: Bearer <passphrase>` or `X-Sync-Key`.
    - Auto-syncs in the background on every state mutation (item watched, channel completed, item queued, or bookmarked). No manual sync required.
- **Outputs & Deliverables:**
  - Complete iOS application package (`.ipa` / `.app` bundle) ready for one-tap import into LiveContainer.
  - Static `data.json` export hook in `desktop/web_reader.py` ensuring the iOS app can cleanly consume pure JSON without parsing HTML.
- **State & Persistence:**
  - Local JSON / SQLite cache within the LiveContainer app sandbox (`Documents/` container).
  - `read_state` persisted locally with automatic background sync to Cloudflare Worker.

---

## 3. UI Specification & Design Lock (Mock 1: Clean Minimalist Briefing)
- **Selected Archetype:** **Mock 1: The Executive Briefing** (Artifact & Apple News inspired, clean minimalist).
- **Theme Support:** **Light Mode Default** with high-contrast palette, plus full Dark Mode toggle.
- **Typography & Font Consistency:** Unified Apple typography hierarchy across the entire app (SF Pro / SF Pro Text for clean, legible body and UI controls; New York / Apple Serif for dignified headlines; monospace for timestamps/numbers). Consistent typographic rhythm and weights throughout.
- **Strict Visual Hygiene:** All floating commentary, dev notes, section dividers, and instructional helper text eliminated. Pure signal only.
- **Three Core Tabs:**
  1. **Briefing Tab:** Continuous, uninterrupted feed of all **20 videos/articles** (clean `#1` to `#20` rank badges, no "Top 10" or "Next 10" splits, no section dividers), prominent "Why It Matters" callouts, Play Audio buttons, 1-tap `+ Queue` buttons, and clean `Watch` / `Read` actions.
  2. **Channels Tab:** Searchable directory of 23 curated sources with category pills (`Tech & AI`, `Health & Bio`, `Science & Deep`), channel avatars, video counts, expandable disclosures revealing each video's rich markdown summary, direct links. Clean, compact **"Listen"** button (proportional pill, not an oversized stretched bar) alongside `+ Queue`.
  3. **Bookmarks Tab:** Dedicated permanent library of saved text articles (unlimited, zero audio bloat, clean card list).
- **Persistent Mini-Player & Commute Queue Drawer:**
  - Floats above bottom tab bar with track title and queue count badge (`3 in Queue`).
  - Tapping opens the native iOS **Now Playing & Commute Deck Sheet** with scrubber, 15s skip, 1.25x speed, and the full re-orderable "Up Next" queue.

---

## 4. Defect Resolution & LiveContainer Hardening (Phase 1 Incident)

### 4.1 Missing App Icon
- **Problem:** App displays blank/default placeholder icon in LiveContainer and iOS home screen.
- **Requirement:**
  - Generate full set of production iOS PNG icons (`AppIcon60x60@2x.png` [120x120], `AppIcon60x60@3x.png` [180x180], `AppIcon76x76@2x.png` [152x152], `AppIcon.png` [512x512 / 1024x1024]) adhering to the Executive Briefing design system (emerald background `#15803d`, lime-accented "TL" monogram).
  - Configure `Info.plist` with `CFBundleIcons`, `CFBundleIcons~ipad`, `CFBundleIconFiles`, and `CFBundleIconFile` referencing the icon assets.
  - Package all icon PNGs directly into the root of `TubeLM.app` within the IPA payload.

### 4.2 Immediate Crash on App Launch
- **Problem:** App crashes immediately upon launch before rendering the first screen.
- **Root Causes & Requirements:**
  1. **SPM Bundle.module fatalError Trap:** `ContentStore.loadCachedFeed()` called `Bundle.module` which throws `fatalError` when run outside Swift PM test builds. Requirement: Eliminate `Bundle.module` dependency for runtime bundle loading; safely query `Bundle.main.url(forResource: "data", withExtension: "json")` and fallback to sandbox documents with zero crash risk.
  2. **Eager Audio Session Activation:** `AudioPlayerManager.init()` eagerly activated `AVAudioSession.sharedInstance().setActive(true)` during app launch, causing launch conflicts under LiveContainer's host audio session. Requirement: Defer `setActive(true)` until explicit user playback starts (`play()` / `playTrack()`).
  3. **Missing Info.plist Platform Keys:** Missing `CFBundleSupportedPlatforms` (`iPhoneOS`), `MinimumOSVersion` (`17.0`), `CFBundlePackageType` (`APPL`), `CFBundleSignature` (`????`), and launch screen declarations. Requirement: Complete `Info.plist` according to Apple and LiveContainer specifications.
  4. **Unsigned Mach-O Binary (AMFI Rejection):** Packaging script produced Mach-O binary without `LC_CODE_SIGNATURE`, causing iOS AMFI to kill the process on launch. Requirement: Ensure ad-hoc code signing (`codesign -s - --force --deep` or `ldid -S`) is executed during packaging.

---

## 5. UAT Remediation Requirements (Phase 2 Feedback)

### 5.1 Light Mode Default & Polish (Issue 1)
- **Problem:** App rendered in dark mode by default because `.preferredColorScheme(nil)` adopted the device/LiveContainer system dark theme.
- **Requirement:**
  - Enforce **Light Mode Default** across all views (`.preferredColorScheme(.light)`).
  - Add user theme selection (Light / Dark / System) in Settings, defaulting to Light.
  - Ensure high-contrast typography, clean off-white card backgrounds, and crisp borders in Light Mode.

### 5.2 Dynamic Feed Sorting: Watched Items to Bottom (Issue 2)
- **Problem:** When a video or article is played or marked watched, it remained at the top in place.
- **Requirement:**
  - Align with Web/PWA behavior: In `BriefingView` and `ChannelsView`, sort unread/unwatched items first, and push watched/read items to the bottom.
  - Preserve original item rank badges (`#1`, `#2`, etc.) regardless of position.
  - Automatically mark item watched when tapping "Play", "Watch", "Read", or the item title.
  - Animate item transitions smoothly so the next unwatched video immediately occupies the top slot.

### 5.3 Cloudflare Sync Fix & Key Alignment (Issue 3)
- **Problem:** Watched state sync failed between iOS app and web reader; worker URL was hardcoded to outdated `vkr1729.workers.dev`; article IDs differed between web and app.
- **Requirement:**
  - Update default worker endpoint to `https://tubelm-sync.kedarvreddy.workers.dev`.
  - In `ContentStore` and sync payload, sync and match both `video_id`, article `url`, and normalized URL keys bidirectionally.
  - Provide a clear, persistent sync passphrase input with visual connection status (Synced ✓, Connecting..., or Error).

### 5.4 Audio Summaries Investigation & Pipeline Fix (Issue 4)
- **Problem:** App and web reader have no audio summaries for the 2026-09-18 weekly digest.
- **Root Cause:** `desktop/tts_service.py` called `asyncio.run()` while inside an already running asyncio event loop in `main.py` and `web_reader.py`, throwing `RuntimeError: asyncio.run() cannot be called from a running event loop` for all channels.
- **Requirement:**
  - Fix event loop handling in `tts_service.py` to safely execute in both sync and async contexts.
  - Backfill TTS audio summaries for the 2026-09-18 digest.
  - Update `data.json` with generated audio URLs and verify audio playback in both the app and web reader.

### 5.5 Player Deck Sheet Redesign (Issue 5)
- **Problem:** The Now Playing modal appears awkward with an oversized neon yellow square ("TL"), standard slider, and unbalanced controls.
- **Requirement:**
  - Redesign `PlayerDeckSheet` to match modern Apple Podcasts / Castro design standards:
    - Elegant artwork card with refined proportions, rounded corners, soft shadow, and dynamic channel badge.
    - Custom scrubber bar with smooth drag and mono time labels.
    - Balanced media controls: proportional 15s skip buttons, emerald accent play/pause button, and clean speed pill.
    - Clean "Up Next" queue section with reordering and swipe-to-delete.


