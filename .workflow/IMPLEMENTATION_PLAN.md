# Implementation Plan: TubeLM iOS Native App (LiveContainer)

## 1. Architectural Strategy & Constraints Anchor
- **Persona & Scale:** Single-user personal app exclusively. No multi-tenant auth, no cloud database setup, no complex migrations.
- **Target Platform:** iOS 26 baseline on iPhone 16 inside LiveContainer (unsigned JIT sideloading).
- **Design Archetype:** Mock 1 Clean Minimalist Briefing (Light mode default + Dark mode, 3 tabs: Briefing [continuous 20 items], Channels [compact proportional 'Listen' button], Bookmarks [clean saved library], and Player Deck Sheet with Commute Queue).
- **Typography:** Unified Apple system typography (SF Pro / SF Pro Text for body and UI controls, New York for serif headlines, system `.monospaced` for ranks/durations). Zero third-party font bloat.
- **Audio Engine:** `AVPlayer` streaming engine with transparent local caching (not local-only `AVAudioPlayer`).
- **Sync & Refresh:** Foreground single-flight revalidation (`data.json`) + debounced background sync to Cloudflare Worker (`GET/POST /` with `Authorization: Bearer <key>`) reusing existing LWW CRDT state.

---

## 2. Canonical Data Contract & Storage Architecture

### Canonical Data Schema (`data.json` & `schema_version: 1`)
Flat, mobile-optimized schema emitted by pipeline:
```json
{
  "schema_version": 1,
  "built_at": "ISO-8601",
  "run_date": "YYYY-MM-DD",
  "top20": {
    "items": [
      {
        "id": "synthetic_unique_id",
        "rank": 1,
        "title": "...",
        "source_name": "...",
        "source_type": "youtube | rss | newsletter",
        "duration": "14m",
        "why_it_matters": "...",
        "url": "https://...",
        "audio_url": "https://..."
      }
    ]
  },
  "channels": [
    {
      "id": "channel_id",
      "name": "...",
      "category": "tech | health | science",
      "read_minutes": 4,
      "summary_text": "...",
      "videos": [
        {
          "id": "synthetic_unique_id",
          "title": "...",
          "duration": "12m",
          "summary_html": "...",
          "url": "https://...",
          "audio_url": "https://...",
          "source_type": "youtube | rss"
        }
      ]
    }
  ]
}
```

### Synthetic Identity Key (Crucial Fix for RSS items)
- RSS/article items often lack YouTube `video_id`.
- Every item is assigned a stable synthetic ID: `sha256(canonical_url)[:16]` (or channel_slug + index fallback).
- Used uniformly across `AppState`, `read_ids` (capped at 5,000 LRU), `CommuteQueue`, and `Bookmarks`.

### Two-Tier Local Storage Hierarchy
1. `Documents/cache/`: Rolling current-week content, overwritten atomically on weekly refresh.
2. `Documents/pinned/`: User bookmarks and saved text digests. **Pin-exempt from 14-day rolling purge** (capped at 200 items / ~1 MB).

---

## 3. Modular Swift Package Structure (`ios/`)

To guarantee testability on Linux while supporting native iOS UI:
```text
ios/
├── Package.swift               # Dual-target SPM manifest
├── Sources/
│   ├── TubeLMCore/             # Pure Swift 6 (Compiles & tests on Linux!)
│   │   ├── Models/             # DigestFeed, TopItem, Channel, VideoItem
│   │   ├── Storage/            # ContentStore (atomic write, ETag, pin-exempt)
│   │   ├── Sync/               # CloudflareSync (GET/POST / root CRDT merge)
│   │   └── Queue/              # QueueMath & unwatched filtering
│   └── TubeLMApp/              # iOS Target (macOS/Xcode only)
│       ├── Audio/              # AVPlayer engine, MPRemoteCommandCenter
│       ├── Views/              # SwiftUI views (Mock 1 Clean Minimalist)
│       └── App.swift           # @main entrypoint
└── Tests/
    └── TubeLMCoreTests/        # 100% Linux-executable unit test suite
```

---

## 4. Implementation Phases

### Phase 1: Pipeline JSON Export Hook (Python)
- **Target:** `desktop/web_reader.py` (inside `build_reader_site`)
- **Actions:**
  - Assign stable synthetic ID to every video/article item.
  - Export `data.json` directly to `paths.get_site_dir() / "data.json"` with `schema_version: 1`.
  - Regenerate `.workflow/mocks/mock_data.json` from the real pipeline output.
- **Verification:**
  ```bash
  python3 -c "from desktop.web_reader import build_reader_site; from desktop import paths; import json; assert (paths.get_site_dir() / 'data.json').exists()"
  ```

### Phase 2: Swift 6 `TubeLMCore` Library (Linux-Testable)
- **Target:** `ios/Sources/TubeLMCore/` & `ios/Tests/TubeLMCoreTests/`
- **Actions:**
  - Define `Codable` models with tolerant decoding (`decodeIfPresent`, safe defaults).
  - Implement `ContentStore` with atomic file swapping and 5,000 LRU `read_ids` cap.
  - Implement `CloudflareSyncClient` calling `GET /` and `POST /` with `X-Sync-Key` / `Bearer` matching `worker/worker.js`.
  - Implement `CommuteQueue` model with synthetic IDs and dynamic "Listen Unwatched" filtering.
- **Verification (on Linux):**
  ```bash
  swift test --package-path ios
  ```

### Phase 3: Audio Engine (`TubeLMApp/Audio`)
- **Target:** `ios/Sources/TubeLMApp/Audio/`
- **Actions:**
  - `AVPlayer`-based `AudioService` supporting remote CDN URLs and local cached files.
  - Lockscreen / Headphone remote commands (`MPRemoteCommandCenter`, 15s skip, play/pause).
  - `MPNowPlayingInfoCenter` track title and progress updates.
  - Dynamic unwatched channel playlist generation.

### Phase 4: SwiftUI Native Views (Mock 1 Clean Minimalist Spec)
- **Target:** `ios/Sources/TubeLMApp/Views/`
- **Actions:**
  - `RootTabView`: 3-tab layout (`Briefing`, `Channels`, `Bookmarks`) with floating mini-player.
  - `BriefingView`: Continuous feed of 20 items (ranks `#1` to `#20`, zero section dividers, "Why It Matters", `Play`, concise `Watch`/`Read`, `+ Queue`, Bookmark).
  - `ChannelsView`: Clean search, channel list, compact proportional `Listen` pill button (not an oversized bar), expandable markdown disclosures.
  - `BookmarksView`: Clean saved articles library (text-only, swipe-to-delete).
  - `PlayerDeckSheet`: Slide-up sheet with scrubber, 15s skip, 1.25x speed toggle, and re-orderable `Up Next` queue.

### Phase 5: LiveContainer Packaging & CI Pipeline
- **Target:** `ios/` & `.github/workflows/build-ios.yml`
- **Actions:**
  - Author `Info.plist` with `UIBackgroundModes: [audio]` and LiveContainer configurations.
  - Author `scripts/package_ipa.sh` to package `.app` bundle into unsigned `.ipa`.
  - Author `.github/workflows/build-ios.yml` to compile on `macos-latest` and publish `.ipa` artifacts on GitHub Releases.

### Phase 6: App Icon & Launch Crash Defect Resolution (LiveContainer Hardening)
- **Target:** `ios/TubeLM/`, `ios/Sources/`, `scripts/package_ipa.sh`, `.github/workflows/build-ios.yml`
- **Actions:**
  1. **App Icon Assets & Declaration:**
     - Generate crisp production PNG icons (`AppIcon60x60@2x.png` [120x120], `AppIcon60x60@3x.png` [180x180], `AppIcon76x76@2x.png` [152x152], `AppIcon83.5x83.5@2x.png` [167x167], `AppIcon.png` [1024x1024]) in `ios/TubeLM/`.
     - Update `ios/TubeLM/Info.plist` with `CFBundleIcons`, `CFBundleIcons~ipad`, `CFBundleIconFiles`, `CFBundleIconFile`, `CFBundleSupportedPlatforms` (`iPhoneOS`), `MinimumOSVersion` (`17.0`), `CFBundlePackageType` (`APPL`), `CFBundleSignature` (`????`).
  2. **Launch Path Crash Elimination:**
     - In `ContentStore.swift`: Remove `Bundle.module` runtime reliance (which invokes `Swift.fatalError` when not running in Swift PM test harnesses). Safely load from `Bundle.main.url(forResource: "data", withExtension: "json")` or sandbox documents, with never-throw fallback to staged empty state.
     - In `AudioPlayerManager.swift`: Remove eager `setActive(true)` during `init()`. Defer audio session activation to `play()` and `playTrack()` so app launch never conflicts with LiveContainer host audio session.
  3. **Packaging & Ad-Hoc Code Signing:**
     - Update `scripts/package_ipa.sh` to stage all `AppIcon*.png` files into `Payload/TubeLM.app/`.
     - Ensure ad-hoc code signing (`codesign -s - --force --deep "$APP_DIR"` or `ldid -S`) is executed so the Mach-O binary and bundle contain valid `LC_CODE_SIGNATURE` load command, preventing iOS AMFI from killing the app upon launch.
     - Add post-packaging validation assertions: assert all 5 icon PNGs exist in `Payload/TubeLM.app/`, assert `Info.plist` contains icon keys and `CFBundleSupportedPlatforms`, assert Mach-O binary is non-empty and signed.
  4. **CI Workflow Alignment:**
     - Update `.github/workflows/build-ios.yml` to copy `AppIcon*.png` and perform ad-hoc code signing during device IPA packaging, matching the simulator packaging.

