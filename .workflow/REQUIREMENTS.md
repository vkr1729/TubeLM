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
