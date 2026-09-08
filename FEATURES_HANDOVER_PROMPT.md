# TubeLM — High-Impact Features Handover Prompt for Muse Spark 1.3

You are tasked with developing and integrating high-impact mobile UX and playback features into TubeLM in a single, clean execution pass, based on the specifications in [TUBELM_HIGH_IMPACT_FEATURES.md](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/TUBELM_HIGH_IMPACT_FEATURES.md).

---

## 1. Operating Mandate & Engineering Rules

1. **Flat "Boring Code" Architecture**:
   - No npm, no node bundlers, no external client frameworks.
   - The reader is a single Jinja2 template at [desktop/templates/reader.html](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/templates/reader.html) rendered by [desktop/web_reader.py](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/web_reader.py) into `~/.tubelm/site/index.html`.
   - All styles must be inline CSS in the existing `<style>` block (Tailwind CDN is strictly banned).
   - All interpolated user/channel strings in HTML must use the existing `esc()` helper.
2. **Preserve Existing Functionality**:
   - All 151 automated tests currently pass (`151 passed in 32s`). You must NOT break existing tests.
3. **Environment & Tooling**:
   - Python venv: `/home/kedarnath-reddy-vallaboina/youtube-project-2/.venv/bin/python`
   - Pytest: `/home/kedarnath-reddy-vallaboina/youtube-project-2/.venv/bin/pytest`
4. **Zero Cloud Infrastructure Dependencies**:
   - All 4 features are strictly self-contained within `reader.html` and `web_reader.py`. Do not introduce external APIs, Cloudflare Worker dependencies, or database bindings.

---

## 2. Features to Implement in a Single Go

### Feature 1: Background Audio Playlist + Lock-Screen MediaSession
*Turns weekly overviews into a commute-length continuous podcast with lock screen and headphone controls.*

1. **Persistent Mini-Player Bar (`reader.html`)**:
   - `#miniPlayer`: fixed at bottom, full width, height `56px + env(safe-area-inset-bottom)` padding, background `var(--sidebar-bg)`, top border `var(--border-color)`, z-index 30.
   - Display: TL logo artwork, current track channel name (truncated with ellipsis), sub-line with category and time `m:ss / m:ss`, controls (⏮ Previous, ⏯ Play/Pause, ⏭ Next), a speed button (cycles 1x / 1.25x / 1.5x / 1.75x / 2x, persisted in localStorage), and a 3px progress line along the top edge.
   - When the bar is visible, add `padding-bottom: 72px` to the reading pane and sidebar.
2. **Queue Management & Play All Unheard**:
   - Add a `▶ Play all unheard` button to the sidebar header next to the unread count.
   - `buildQueue(weekKey, { unheardOnly: true })`: collects channels in the active week with `has_audio && audio_url`, filtered by current category, sorted by category then name, skipping tracks with `tubelm_heard:<src> === '1'`.
   - Store queue state in `localStorage` (`tubelm_player`). On page load, restore queue and track/position in paused state (do not auto-play on load).
   - Existing per-channel audio card's play button routes through the queue: if channel is in the queue, jump to it; otherwise insert at `index+1` and play.
   - Track auto-advancement: on `ended` event, advance to `next()`. When `currentTime / duration >= 0.9`, set `tubelm_heard:<src> = 1` and reflect with a `♪ heard` badge in the sidebar.
3. **MediaSession Integration**:
   - When a track starts:
     ```javascript
     if ('mediaSession' in navigator) {
       navigator.mediaSession.metadata = new MediaMetadata({
         title: ch.name,
         artist: 'TubeLM · ' + ch.category,
         album: 'Week of ' + run_date,
         artwork: [
           { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
           { src: 'icon-192.png', sizes: '192x192', type: 'image/png' }
         ]
       });
     }
     ```
   - Wire action handlers: `play`, `pause`, `previoustrack`, `nexttrack`, `seekbackward` (15s), `seekforward` (30s), `seekto`.
   - Call `navigator.mediaSession.setPositionState({ duration, playbackRate, position })` on `loadedmetadata`, `ratechange`, `seeked`, and every 5s while playing.
4. **iOS Single-Element Activation**:
   - The first `play()` must be triggered directly inside a user touch/click handler.
   - Keep the single `globalAudio` element alive for the entire session; never recreate it. Subsequent track changes initiated by `ended` or MediaSession call `play()` on the existing activated audio element.

---

### Feature 2: Reading-Time Budget + "5-Minute Brief" Mode
*Gives an upfront time cost for the week and a fast, one-screen reading mode.*

1. **Build-Time Metrics (`desktop/web_reader.py`)**:
   - In `parse_channel_digest_json()` and `parse_channel_digest()`:
     - `word_count`: count words in summary text (`re.findall(r"\w+", summary_text)`).
     - `read_minutes`: `max(1, round(word_count / 230))`.
     - `audio_seconds`: if `audio_path` exists, estimate duration (file size at 64 kbps mono / 128 kbps) or read via mutagen if present.
     - `brief`: list of `{title, url, video_id, lead}` where `lead` is the first 60 words of that item's summary text ending in `…`.
   - In `site_data.weeks[week]`, add aggregates: `total_read_minutes`, `total_audio_seconds`, `channel_count`.
2. **Reader UI (`reader.html`)**:
   - In sidebar channel meta line: display `~{read_minutes} min` (and `· {mm}m audio` if audio exists).
   - In sidebar header under "Sources": display `Unread: {n} channels · {sum read} min · {sum audio} audio` for channels matching the current category.
   - In category navigation bar, add a `Brief` toggle button (`#mode-brief`).
   - When `Brief` is active, `renderActiveView()` renders `#briefView`: a single continuous page of all unread channels in the current category with channel names, read times, item titles, and 60-word `lead` paragraphs with a "Read full ↓" expander.
   - Provide a sticky "Mark all above as read" button at the bottom of the Brief view.

---

### Feature 3: Direct 1-Tap YouTube App Playback with Inline Fallback
*Target: iPhone 16 with YouTube Premium & secondary channel profile.*

1. **Unified Play Dispatcher (`reader.html`)**:
   - Replace raw modal opening with a unified `playVideo(videoId, title, options = {})` dispatcher.
   - Store player preference in `localStorage.getItem('tubelm_player_pref')`: default `'app'` on mobile devices (`/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)`), `'inline'` on desktop.
   - Add a subtle toggle affordance in the reading pane header or video card (e.g. `📺 App` vs `🔲 Inline`) to allow toggling this preference anytime.
2. **Deep-Link & Fallback Mechanism**:
   - When playing in `'app'` mode on a mobile device:
     - Register one-time `pagehide` and `blur` listeners on `window` to detect when the OS successfully switches away to the native YouTube app.
     - Synchronously execute deep-link: `window.location.href = `youtube://watch?v=${encodeURIComponent(videoId)}``.
     - Start a 600ms fallback timer: if `document.visibilityState === 'visible'` after 600ms (indicating the native YouTube app is not installed or didn't take over), clean up listeners and fall back to opening the in-app modal (`openVideoModal(videoId, title)`).
   - When playing in `'inline'` mode or on desktop:
     - Directly invoke `openVideoModal(videoId, title)`.
3. **Modal Enhancement**:
   - In `openVideoModal()`, add a clear `Open in YouTube ↗` button in the header linking to `https://www.youtube.com/watch?v=${videoId}` (`target="_blank" rel="noopener"`).
   - Automatically pause any active audio overview when a video is launched.

---

### Feature 4: Dynamic "Unread-First" Sinking for Channels & Top 20 Videos
*Keeps unread items anchored at the top under your thumb; sinks completed items to the bottom.*

1. **Sidebar Channels Unread-First Sorting (`reader.html`)**:
   - In `renderSidebar()`:
     Before creating the channel list DOM, stably sort channels so all unread channels appear at the top, and all read channels sink to the bottom:
     ```javascript
     const unreadChannels = filtered.filter(ch => !isChannelRead(ch.id));
     const readChannels = filtered.filter(ch => isChannelRead(ch.id));
     const sortedChannels = [...unreadChannels, ...readChannels];
     ```
   - When `toggleRead(chId)` is clicked, immediately call `renderSidebar()` to smoothly move the newly read channel to the bottom.
2. **Top 20 Unified Inbox Sinking (`reader.html`)**:
   - Unify the Top 20 editorial picks into a single responsive list (removing the arbitrary Top 10 vs Next 10 wall) while keeping each item's prominent rank badge (`#01`, `#02` ... `#20`).
   - Store watched/read status for Top 20 video IDs or URLs in localStorage `tubelm_top20_read`.
   - Helpers:
     - `isTopItemRead(id)`: checks Set from localStorage.
     - `toggleTopItemRead(id)`: toggles in Set, persists to localStorage, and re-renders view.
   - Sort items dynamically on render:
     ```javascript
     const unreadPicks = items.filter(it => !isTopItemRead(it.video_id || it.url));
     const readPicks = items.filter(it => isTopItemRead(it.video_id || it.url));
     const sortedPicks = [...unreadPicks, ...readPicks];
     ```
   - Unread items stay prominently at the top with full contrast.
   - Seen/read items sink to the bottom with dimmed styling (`opacity-60`), muted background, and a `✓ Seen` tag.
   - Add a fast "✓ Mark Seen" / "Seen ✓" toggle button on each pick card.
   - When a video is launched via `playVideo(...)`, automatically mark that item as seen in `tubelm_top20_read`.
   - Add an optional "Hide Seen ({n})" toggle button at the top of the picks view to collapse completed videos entirely.

---

## 3. Verification Protocol

1. **Compilation Check**:
   ```bash
   .venv/bin/python -m py_compile desktop/*.py
   ```
2. **Full Automated Test Suite**:
   ```bash
   .venv/bin/pytest desktop/tests -v
   ```
   All 151 existing tests must pass, plus any new unit tests for reading metrics and dispatching.
3. **Dry Run**:
   ```bash
   .venv/bin/python desktop/main.py --dry-run
   ```
   Must exit with code 0.
4. **Summary Report**:
   Provide a concise list of modified files, new localStorage keys, and confirmation that all tests pass.
