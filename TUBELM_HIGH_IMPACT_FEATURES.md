# TubeLM — High-Impact Feature Proposals & Turnkey Agent Prompts

Target: iPhone 16, iOS 26+, standalone PWA at `https://vkr1729.github.io/TubeLM/`, built by `desktop/web_reader.py` from `desktop/templates/reader.html`. All features keep the $0 budget and the flat architecture. Every prompt assumes `TUBELM_REVIEW_AND_FIX_PLAN.md` Steps 1–8 are merged: audio on R2 (not git), the audio manifest, JSON sidecars, inline utility CSS (no Tailwind CDN), the `esc()` helper, the state-driven audio controller with `loadedmetadata`-based resume, and the single-active-player rule.

| # | Feature | Why it matters on the phone | Effort |
| --- | --- | --- | --- |
| 1 | Background audio playlist with lock-screen MediaSession controls | Turns nine 40-minute overviews into one commute-length podcast you control from the lock screen and AirPods. | M |
| 2 | Reading-time budget + "5-minute Brief" mode | Tells you what the week costs before you start, and gives a one-screen version when you have no time. | S |
| 3 | Direct 1-tap YouTube app playback with inline iframe fallback | Deep-links straight into YouTube Premium for ad-free, lock-screen background playback; falls back to inline iframe when app is absent. | S |
| 4 | Dynamic "Unread-First" sinking/sorting for channels & Top 20 | Unread items stay at the top under your thumb; finished items sink to the bottom so you never scroll past already-watched content. | S |
| 5 | Commute Font Size Stepper (`Aa`) | Instant 3-step text scale (13px / 15px / 17px) to read comfortably on a vibrating MRT without eye fatigue. | XS |
| 6 | Option C Neural Summary TTS (`edge-tts`) | Studio-quality AI narration of channel summaries that plays in the background with the screen locked via the mini-player. | S |

Build order: 1 → 2 → 3 → 4 (Complete) → 5 → 6. All features preserve the flat "boring code" architecture and $0 infrastructure budget.

---

## Feature 1 — Background audio playlist + lock-screen MediaSession

**What it is.** A persistent mini-player bar at the bottom of the reader (safe-area aware) that owns the single `<audio>` element. "▶ Play all unheard" builds a queue of every channel with audio in the selected week, ordered by category then channel, skipping tracks marked heard. The `MediaSession` API publishes title/artist/artwork (`TubeLM` icon) and handlers for play/pause/next/previous/seek/seekto so the lock screen, Control Center, AirPods and CarPlay controls work. Per-track position is persisted (`tubelm_pos:<url>`), a track is marked heard at 90 %, and the queue auto-advances. Speed is global and persisted.

**Why high leverage.** Audio is the most expensive artifact the pipeline produces and today it needs the screen on, the app in front, and a tap per channel.

**iOS notes encoded in the prompt.** Playback must be started from a user gesture; subsequent `play()` calls for the *same element* after a track change are allowed once the element has been activated. Standalone PWAs on iOS 17+ continue audio in the background when the element is playing; MediaSession metadata must be set *after* `play()` resolves or on `playing`. `setPositionState` must be called on `loadedmetadata`, `ratechange`, and after seeks.

### Turnkey prompt (Antigravity · Gemini 3.8 Flash (high))

```text
ROLE: Repository vkr1729/TubeLM. The reader is a single Jinja2 template desktop/templates/reader.html rendered by desktop/web_reader.py into ~/.tubelm/site/index.html and deployed to gh-pages. Flat "boring code" architecture: no frameworks, no bundlers, no external JS. SITE_DATA is embedded JSON: `weeks.{current|prev}.channels[]` with fields id, name, category, has_audio, audio_url (absolute R2 URL or relative), videos[], run_date.

PRECONDITIONS (verify, do not re-implement): the audio controller already uses `globalAudio` (`#global-audio-element`), `toggleAudio(src, btn)`, `updatePlayIcon()`, `cycleAudioSpeed()`, `formatTime()`, a progress watchdog + `loadedmetadata`-based resume, and per-track position persistence under localStorage `tubelm_pos:<src>`.

GOAL: A playlist-capable background audio player with lock-screen controls.

PART A — QUEUE MODEL (reader.html, script block)
- `const player = { queue: [], index: -1, speed: 1.0 }` persisted to localStorage `tubelm_player` (queue as array of `{chId, weekKey, src, title, category}`; index; speed). Restore on load; do not auto-play on load (iOS forbids), just show the bar in paused state at the restored track/position.
- `buildQueue(weekKey, {unheardOnly=true})`: channels with `has_audio && audio_url`, filtered by current category pill (`currentCategoryId`), ordered by category order ['tech','deep_explainer','health','news_feed'] then name; skip tracks with `tubelm_heard:<src> === '1'` when unheardOnly.
- `playIndex(i)`: set `globalAudio.src`, restore position from `tubelm_pos:<src>` in `loadedmetadata`, `playbackRate = player.speed`, `play()`; update MediaSession metadata; update the mini-bar; `selectChannel(chId)` ONLY if the reading pane is not currently showing a different channel the user scrolled into (never yank the reading view mid-scroll: if `selectedItemId !== chId`, just update the bar).
- `next()/prev()`: bounds-checked; at the end of the queue, stop and mark the queue done; if `unheardOnly`, tracks marked heard while playing are removed from the *remaining* queue.
- Heard: on `timeupdate`, when `currentTime/duration >= 0.9` set `tubelm_heard:<src>=1` once and add a `♪ heard` badge to the channel's sidebar item (render-time check in `renderSidebar`).
- `ended` → `next()`.

PART B — MINI-PLAYER BAR (HTML + CSS)
- `#miniPlayer`: fixed bottom, full width, height 56 px + `env(safe-area-inset-bottom)` padding, background `var(--sidebar-bg)`, top border `var(--border-color)`, z-index 30, hidden until a queue exists. Contents left→right: 36 px artwork (the TL logo div), title (channel name, single line, ellipsis) with a sub-line `category · m:ss / m:ss`, buttons ⏮ ⏯ ⏭, a speed button (cycles 1/1.25/1.5/1.75/2, persisted), and a 3 px progress line along the top edge of the bar (`width` in %). Tapping the title opens the channel (selectChannel). Reading pane and sidebar get `padding-bottom: 72px` while the bar is visible (toggle a class on body).
- Add a "▶ Play all unheard" button to the sidebar header (next to the unread count) and a per-channel "▶ Add to queue" affordance inside the audio card (renders only if the channel is not already in the queue).
- The existing per-channel audio card's play button must route through the queue: if the channel is in the queue, jump to it; else insert it at `index+1` and play it.

PART C — MEDIASESSION
- On each `playIndex`, after `play()` resolves OR on the first `playing` event: `navigator.mediaSession.metadata = new MediaMetadata({title: ch.name, artist: 'TubeLM · ' + category label, album: 'Week of ' + run_date, artwork: [{src: 'icon-512.png', sizes:'512x512', type:'image/png'}, {src:'icon-192.png', sizes:'192x192', type:'image/png'}]})`.
- Action handlers: play, pause, previoustrack, nexttrack, seekbackward (15 s), seekforward (30 s), seekto (`details.seekTime`, respect `fastSeek` if provided), stop. Wrap each `setActionHandler` in try/catch (unsupported actions throw).
- `updatePositionState()`: `navigator.mediaSession.setPositionState({duration, playbackRate, position})` guarded by `isFinite(duration)`; call on loadedmetadata, ratechange, seeked, play, pause, and every 5 s while playing. Set `navigator.mediaSession.playbackState` to 'playing'/'paused'.
- Wake Lock is NOT needed for audio; do not request it.

PART D — iOS ACTIVATION RULES
- The first `play()` must occur inside a click/touch handler. `buildQueue` + `playIndex(0)` are called directly from the button's handler; no awaits before `play()`.
- Track changes triggered by `ended` or MediaSession handlers call `play()` without a gesture; that is allowed on iOS for an element that has already played via a gesture — keep exactly one `<audio>` element for the app's lifetime; never recreate it.
- Never use `autoplay` attribute. Never call `load()` between tracks except inside the recovery path already present.

CONSTRAINTS
- No external libraries. All CSS inline in the existing style block (Tailwind CDN is banned).
- Do not re-render the reading pane when tracks change; update only `#miniPlayer` and, if visible, the channel's audio card icon/progress (use `[data-audio-src]` lookups).
- Escape all interpolated strings with the existing `esc()`.

VERIFICATION
- Extend desktop/scripts/run_browser_uat.py (Playwright, Chromium with `--autoplay-policy=no-user-gesture-required`) using a generated fixture site (two channels with tiny generated MP3s via ffmpeg `-f lavfi -i sine=frequency=440:duration=3`): (a) "Play all unheard" starts track 1 (`globalAudio.src` endswith the first channel file, `paused === false`); (b) track 1 `ended` → track 2 plays; (c) after track 2 passes 90 % the sidebar item shows the heard badge and localStorage has `tubelm_heard:<src>`; (d) reload → mini-bar is visible, paused, showing track 2 and its stored position; (e) `navigator.mediaSession.metadata.title` equals the channel name after play; (f) pressing the speed button cycles and persists.
- Unit test in desktop/tests/unit/test_rendering.py that the template still renders with `has_audio` channels present and absent (no JS errors is checked in the Playwright script with `page.on('pageerror')`).
- Report changes, new localStorage keys, and test output. Include a 6-line manual iOS checklist (install to Home Screen → play → lock screen shows title/controls → next from lock screen works → AirPods double-tap skips).
```

---

## Feature 2 — Reading-time budget + "5-minute Brief" mode

**What it is.** Every channel shows `~4 min` (words ÷ 230 wpm, computed at build time from `summary_text` and stored in the sidecar JSON, plus audio length if present). The sidebar header shows the total unread cost: `Unread: 14 channels · 48 min read · 3 h 20 audio`. A **Brief** toggle renders one continuous page: for each unread channel in the current category, the channel name, the first paragraph of each item's summary (build-time `brief` field: first 60 words of each item), and a "Read full ↓" link that expands in place. Marking read from Brief mode uses the same `toggleRead`.

**Why high leverage.** The reader today presents 18–22 channels as equal weight; the decision "what do I read in the next 5 minutes" has no data.

### Turnkey prompt (Antigravity · Gemini 3.8 Flash (high))

```text
ROLE: Repository vkr1729/TubeLM. Files: desktop/web_reader.py (site builder; reads per-channel JSON sidecars `{run_date}_{safe_name}_digest.json` first, HTML fallback second), desktop/templates/reader.html, desktop/tests/unit/test_web_reader.py. No frameworks.

PART A — BUILD-TIME METRICS (web_reader.py)
- In the function that produces each channel dict (JSON path and HTML fallback path), add:
  `word_count`: words in the plain-text summary (strip HTML/markdown; `re.findall(r"\w+")`).
  `read_minutes`: `max(1, round(word_count / 230))`.
  `audio_seconds`: if `audio_path` exists locally, read MP3 duration with `mutagen` if importable; otherwise estimate from file size at 128 kbps for uncompressed / 64 kbps if `COMPRESS_AUDIO` (document the estimate). Do not add a hard dependency; `mutagen` is optional (try/except ImportError).
  `brief`: list of `{title, url, video_id, lead}` where `lead` = first 60 words of that item's summary text (plain text, no markdown), ending with "…" if truncated. For channels whose summary could not be split per item, `lead` of the first paragraph of the whole summary.
- Add per-week aggregates to `site_data.weeks[week]`: `total_read_minutes`, `total_audio_seconds`, `channel_count`.
- Keep `parse_channel_digest` backwards compatible; tests for both paths.

PART B — READER UI (reader.html)
- Sidebar item meta line: `~{read_minutes} min` and, when audio exists, `· {mm}m audio`.
- Sidebar header line under "Sources (n)": `Unread · {n} channels · {sum read} min · {sum audio} audio` computed from unread channels in the current category filter; update on every renderSidebar.
- Category pills get a count badge of unread minutes (e.g. `Tech 21m`).
- New toggle in the category bar: `Brief` (id `mode-brief`). When active: `renderActiveView()` renders `#briefView` instead of the selected channel: for each unread channel matching the filter, a section with the channel name (tap → selectChannel), read time, then each item's `title` (link, `esc()`), `lead`, and a "Read full ↓" button that expands that item's `summary_html` in place (lazy: insert on first expand). A sticky footer button "Mark all above as read" marks every channel currently rendered in the Brief as read via `toggleRead` (only for those not yet read) and re-renders.
- Brief mode persists in localStorage `tubelm_mode`. Selecting a channel from the sidebar exits Brief mode.
- Also show a small "This week: {total_read_minutes} min · {audio} audio" line under the "Editorial Picks" heading.

CONSTRAINTS
- All strings through `esc()`; `summary_html` is trusted build output (own markdown renderer, html=False).
- No new network requests; everything comes from SITE_DATA.
- Do not change the read-state key format.

VERIFICATION
- test_web_reader.py: build a fixture sidecar with 460 words → `read_minutes == 2`; `brief[0].lead` has ≤ 60 words and ends with "…"; aggregates sum correctly across two channels; HTML-fallback path yields the same fields.
- Playwright script (desktop/scripts/run_browser_uat.py): with two unread channels (2 min + 3 min), the header shows "5 min"; enabling Brief renders two sections; "Read full ↓" expands one item's HTML; "Mark all above as read" makes both channels read and the header shows "0 min".
- Report changes and test output.
```

---

## Feature 3 — Direct 1-Tap YouTube App Playback with Inline Fallback

**What it is.** Clicking play on any YouTube video card or editorial pick launches playback immediately. On mobile (iPhone), it defaults to deep-linking directly into the native YouTube app (`youtube://watch?v={id}`), delivering zero-ad YouTube Premium playback, seamless lock-screen and background audio on MRT/bus commutes, and zero feed contamination when using a secondary YouTube profile. If the YouTube app is not installed (or on desktop browsers), it falls back seamlessly within 500ms to the in-app modal/inline player. A dedicated affordance or settings toggle allows switching between "App" and "Inline" modes.

**Why high leverage.** Solves three real-world commute frictions in a single stroke: (1) eliminates the awkward iOS two-tap iframe mounting ritual, (2) leverages existing YouTube Premium for ad-free viewing, and (3) unlocks native lock-screen background audio for commutes.

**iOS notes encoded in the prompt.** Standalone PWAs on iOS can deep-link to custom URL schemes (`youtube://`) synchronously during a tap event. To avoid stuck states when the native app is missing, use a navigation watcher: set a timeout (500–600ms) with `blur` and `pagehide` listeners. If the app opens, iOS blurs/hides the PWA and the timeout is disarmed. If the PWA remains focused, the timeout triggers and opens the fallback modal iframe.

### Turnkey prompt (Antigravity · Gemini 3.8 Flash (high))

```text
ROLE: Repository vkr1729/TubeLM. File: desktop/templates/reader.html. Flat architecture: no external libraries, vanilla JS and CSS.

GOAL: Instant 1-tap playback for YouTube videos defaulting to native YouTube app on mobile (iPhone 16) with inline iframe fallback for desktop or when the native app is absent.

PART A — DIRECT PLAY DISPATCHER (reader.html)
- Replace direct `openVideoModal(...)` and `toggleVideoPlayer(...)` click bindings with a unified dispatcher:
  `playVideo(videoId, title, {preferInline=false})`
- Preference Storage:
  Store preferred player mode in localStorage `tubelm_player_pref`: `'app'` (default on mobile) or `'inline'` (default on desktop).
  Provide a small quick-toggle icon/chip in the reading pane header or video card (e.g. `📺 App` vs `🔲 Inline`) to let the user switch modes anytime.

PART B — DEEP LINK & FALLBACK LOGIC
- When playing in `'app'` mode on a mobile device:
  1. Register one-time `blur` and `pagehide` event listeners on `window` to detect when the OS successfully switches away to the YouTube native app:
     ```javascript
     let appOpened = false;
     const onDeactivate = () => {
       appOpened = true;
       window.removeEventListener('pagehide', onDeactivate);
       window.removeEventListener('blur', onDeactivate);
     };
     window.addEventListener('pagehide', onDeactivate);
     window.addEventListener('blur', onDeactivate);
     ```
  2. Initiate deep link synchronously inside the click handler:
     `window.location.href = `youtube://watch?v=${encodeURIComponent(videoId)}``
  3. Fallback timer (600ms):
     If after 600ms `document.visibilityState === 'visible'` and `!appOpened`, the native app is not installed. Disarm listeners and fall back to opening `openVideoModal(videoId, title)`.
- When playing in `'inline'` mode or on desktop:
  Directly invoke `openVideoModal(videoId, title)`.

PART C — MODAL & IN-APP ENHANCEMENTS
- Inside the video modal header:
  Add an explicit `Open in YouTube ↗` button linking to `https://www.youtube.com/watch?v=${videoId}` (`target="_blank" rel="noopener"`), allowing the user to pop out to the native app at any point.
- Ensure active audio overview pauses automatically whenever a video is launched via `playVideo` to prevent audio clashes.

CONSTRAINTS
- All titles and URLs must be escaped with `esc()`.
- The deep link call must be completely synchronous within the touch/click handler to satisfy iOS Safari user-activation rules.
- Do not introduce external dependencies.

VERIFICATION
- Unit/Browser check in Playwright:
  (a) On desktop user agent, clicking play immediately mounts the inline modal player.
  (b) The "Open in YouTube ↗" button in the modal links to `https://www.youtube.com/watch?v=...`.
  (c) Toggling the player preference to 'inline' forces modal player on mobile; setting to 'app' invokes deep-link dispatcher.
  (d) Report changes, localStorage keys, and manual verification instructions on iOS Safari / Home Screen PWA.
```

---

## Feature 4 — Dynamic "Unread-First" Sinking/Sorting (Sidebar & Top 20)

**What it is.** 
1. **Sidebar Channels:** When a channel is marked as read, it automatically sinks to the bottom of the channel list. Unread channels remain anchored at the very top of the sidebar under your thumb. Once all channels in a category are read, they remain visible at the bottom with their `✓` indicator.
2. **Top 20 Editorial Picks:** Eliminates the rigid "Top 10 vs Next 10" split in favor of an inbox-style list where watched/read videos automatically sink to the bottom (with a muted style and `✓ Seen` tag) while unread picks float to the top. Each card gains a quick "✓ Mark Seen" toggle, and launching a video automatically marks it as seen.

**Why high leverage.** Solves daily screen fatigue: on mobile, you can only see 4–5 items on screen at once. Without this, once you finish the first 4–5 items on Monday, you have to scroll past them every single time you open the app on Tuesday through Sunday.

### Turnkey prompt (Antigravity · Gemini 3.8 Flash (high))

```text
ROLE: Repository vkr1729/TubeLM. File: desktop/templates/reader.html. Flat architecture, vanilla JS and CSS.

GOAL: Dynamic "unread-first" sorting for both sidebar channels and Top 20 editorial picks so unread content stays at the top and completed content sinks to the bottom.

PART A — SIDEBAR "UNREAD-FIRST" SORTING (reader.html)
- In `renderSidebar()`:
  Before iterating through filtered channels, partition and sort them stably:
  ```javascript
  const unreadChannels = filtered.filter(ch => !isChannelRead(ch.id));
  const readChannels = filtered.filter(ch => isChannelRead(ch.id));
  const sortedChannels = [...unreadChannels, ...readChannels];
  ```
  Iterate over `sortedChannels` to construct sidebar buttons.
- In `toggleRead(chId)`:
  After saving read state, re-render sidebar (`renderSidebar()`) so the newly read channel smoothly moves to the bottom of the list.

PART B — TOP 20 ITEM READ STATE & UNIFIED SINKING (reader.html)
- Top 20 Read State Storage:
  Store read item IDs in localStorage `tubelm_top20_read` (JSON array of video URLs or IDs).
  Helper functions:
  - `isTopItemRead(id)`: checks Set initialized from localStorage.
  - `toggleTopItemRead(id)`: toggles in Set, persists to localStorage, and re-renders active view if `selectedItemId === 'top20'`.
- Unified 20-Item View:
  - Unify the Top 20 view from the arbitrary Top 10 cards + Next 10 table into a cohesive 20-item layout.
  - Preserve original rank badges (`#01`, `#02` ... `#20`) prominently on each item.
  - Partition items:
    ```javascript
    const unreadPicks = items.filter(it => !isTopItemRead(it.video_id || it.url));
    const readPicks = items.filter(it => isTopItemRead(it.video_id || it.url));
    const sortedPicks = [...unreadPicks, ...readPicks];
    ```
  - Read items render with dimmed opacity (`opacity-60`), a muted background, and a "✓ Seen" badge.
  - Each item card has a quick "Mark as Seen" / "Seen ✓" toggle button.
  - When `playVideo(...)` is triggered on any Top 20 item, automatically mark it as seen so it sinks on next render.
  - Provide a small "Show Watched ({n})" collapsible toggle if the user wants to collapse seen videos completely.

CONSTRAINTS
- Zero server/pipeline changes. Everything is stored client-side in localStorage.
- Retain the exact original rank numbers on badges (`#01`, `#14`) so editorial rank is never lost even when items reorder.

VERIFICATION
- In Playwright:
  (a) Marking channel 1 as read moves it below unread channels in the sidebar DOM.
  (b) Clicking "Mark as Seen" on Top 20 item #01 moves it below unread picks while keeping its "#01" badge intact.
  (c) Reloading the page retains the unread-first ordering from localStorage.
```

---

## Feature 5 — Commute Font Size Stepper (`Aa`)

**What it is.** An instant, 3-level text scale toggle (`Aa` button in the top header) cycling between:
- **Small (13px):** Compact, high-density desktop reading.
- **Medium (15px):** Comfortable mobile default with `1.65` line height.
- **Large (17px):** High-legibility mode designed specifically for tired eyes on a moving, vibrating MRT commute.
Persists across sessions in `localStorage['tubelm_font_size']` and controls CSS variables without causing layout shifts or wrapping in the navigation bars.

---

## Feature 6 — Option C Neural Summary TTS via `edge-tts`

**What it is.** A 1-to-2 minute spoken audio edition of each channel's written executive briefing, synthesized using Microsoft's free `edge-tts` engine (`en-US-ChristopherNeural` / `en-US-JennyNeural`). 
Because it outputs a true `.mp3` file:
- It routes directly into the Feature 1 Mini-Player.
- It continues playing seamlessly **in the background when the phone screen is locked or turned off in your pocket**.
- It integrates with the iOS lock screen (artwork, scrub bar) and AirPods gestures (double-tap to pause/resume).
- It provides audio for 100% of channels, including single-video digests and RSS feeds that don't receive NotebookLM 2-host podcast deep dives.

---

## Archived / Future Roadmap Features (Deferred)

The following features have been archived and are excluded from the active build:

* **Archived — Cross-device read & listen state via Cloudflare Worker + KV:**
  * Requires deploying Worker code in a separate repository (`Instagram_digest`), provisioning Cloudflare KV bindings, and managing distributed delta conflicts. Deferred to preserve pipeline stability.
* **Archived — Export to Obsidian / Apple Notes / Markdown:**
  * Dropped to focus on mobile reading, playback, and commuting UX.
* **Archived — Offline week pack (Service Worker Range synthesis):**
  * Dropped because R2 streaming + inlined CSS already provides instant cold starts and sub-second load times.
