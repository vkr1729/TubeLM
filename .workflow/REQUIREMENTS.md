# Requirements Specification: TubeLM Video-Level Audio Summaries & Playlist Queues

## 1. Project Overview & Target User Anchor
- **Project Name:** TubeLM (Personal YouTube & RSS Intelligence Digest)
- **Target User & Scale:** **Single-Person Personal Use Exclusively**.
  - *Hard Constraint:* Strictly reject enterprise complexity, authentication frameworks, microservices, or complex caching.
  - *Web Reader:* Hosted on GitHub Pages (`https://vkr1729.github.io/TubeLM/`) with static site data synced via Cloudflare Worker/R2.
  - *iOS App:* Native Swift/SwiftUI application running in LiveContainer on iOS with offline caching and background sync.
- **Primary Objective:** Transition from monolithic channel-level audio summaries to granular video-level audio summaries. When listening to a video card (especially in the Top 20 briefing), the player should play only that video's summary instead of reading the summaries of all videos from that channel. Provide dedicated playlist queues (Top 20, channel-level, and site-wide) that automatically track listened items, skip heard summaries, and sync watched status.

---

## 2. Functional Requirements (Scope Matrix)

### A. Video-Level Audio Synthesis & Storage
- **Per-Video Synthesis:**
  - Generate audio summaries for each individual video across all channels.
  - Because Top 20 items are drawn directly from these channel videos, every Top 20 video references its corresponding video-level audio summary without duplicate synthesis.
  - If a video's summary text is `< 20 chars`, skip synthesis and set `audio_url = ""` (renders no listen button—never a dead button).
- **Spoken Script Format & Human Pacing:**
  - Narration announces the title and channel first, followed by the video summary breakdown:
    `"<Video Title>, by <Channel Name>. <Summary Breakdown>"`
  - **Enhanced Speech Cleaning:**
    - Strip all markdown hashes (`#`, `##`, `###`), stray slashes (`/`), backslashes (`\`, `\$`), backticks (`` ` ``), and bracketed citations (`[1]`, `[2-4]`).
    - Convert slashes like `and/or` into natural words (`and or`), and strip isolated slashes so the voice never verbalizes "slash" or "hashtag".
    - Strip escaped characters like `\$` so it pronounces currency normally without saying "backslash".
  - **Strategic Natural Pauses:**
    - Insert natural punctuation pauses (`. `, `... `, or clean sentence terminations) after title/channel announcements and between major sections (`The Hook.`, `The Mechanics and Evidence.`, `The Core Principle.`).
    - Ensure section headings end with a terminal pause so headings do not run into body sentences.
- **File Naming & Cloudflare R2 Upload:**
  - Deterministic naming: `summary_video_{run_date}_{safe_id}.mp3`.
  - `safe_id` uses the exact 11-char YouTube `video_id` when valid; for non-YouTube articles or RSS items, uses `sha256(url)[:12]` to eliminate slug collisions.
  - Stored in `~/.tubelm/audio/` and synced to `site/audio/`.
  - Uploaded to Cloudflare R2 under `tubelm/audio/{run_date}/summary_video_{run_date}_{safe_id}.mp3`.
  - Extend retention regex `_AUDIO_DATE_RE` in `web_reader.py` to `r"^(?:summary_(?:video_)?)?(\d{4}-\d{2}-\d{2})_"` to automatically purge per-video files under the 2-week rolling window.
- **Deprecate Monolithic Channel TTS:**
  - Deprecate generating single monolithic channel-concatenated summary MP3s. Channel-level listening will queue the individual video summary tracks.
  - NotebookLM 2-host audio overviews (when generated) remain available as full channel deep-dives.

### B. Top 20 & Channel Video Audio Wiring
- **Canonical Join Key:**
  - Exact YouTube `video_id` -> canonical URL (`youtube.com/watch?v=...`) -> title hash.
  - Both Top 20 items and channel cards join to audio using this canonical key.
  - If no audio file exists, set `audio_url = ""` (card renders no listen button; old channel-audio fallback is eliminated).
- **Top 20 Cards:**
  - Clicking `🎧 Listen` on a Top 20 card plays only that specific video's summary audio.
- **Channel Cards:**
  - Each individual video card inside a channel view displays a `🎧 Listen` button to play that video's summary.
- **Data Contracts (`data.json` & Mobile Feed):**
  - Ensure `_normalize_mobile_item()` and `_normalize_mobile_video()` attach the video-level `audio_url` to both Top 20 items and channel video objects.

### C. Playlist Queues & Mini-Player
- **Track Data Shape:**
  - Queue items carry `{key, videoId, url, src, title, channelName, channelId, category, rank, weekKey}`.
  - Mini-player title format: `"${Channel Name} · ${Video Title}"`.
- **Top 20 Playlist Queue:**
  - Add `🎧 Play All Top 20 Summaries` button in the Editorial Picks / Top 20 header.
  - Queues all Top 20 video summary tracks in rank order (#1 through #20).
- **Channel-Level Playlist Queue:**
  - Replace old channel `🔊 Listen` with `🎧 Play Summaries`.
  - Queues all video summaries for that specific channel in digest order.
- **Site-Wide Playlist Queue:**
  - "► Play Summaries" queues Top 20 summaries first (#1 through #20), followed by remaining channel video summaries organized by category with **set-minus deduplication** (so Top 20 videos do not play twice).
- **Heard Tracking & Automatic Skipping:**
  - Key heard status by canonical key: `tubelm_heard:{week}:{key}` (with `src` alias).
  - Forward progression (`queueNext`) automatically skips already-heard tracks.
  - Backward navigation (`queuePrev`) does not skip.
- **Automatic Watched/Read Synchronization:**
  - When a video's summary audio reaches 90%+ playback (or ends), it is marked as `heard`, and the video card is automatically marked as `Watched ✓` (or `Read ✓`).

### D. Historical Runs Policy
- Historical weeks remain as-is (no retroactive mass backfill required during builds). Video-level audio is generated on pipeline runs and respected whenever present.
- If a historical week has no per-video audio, hide the new queue buttons and preserve legacy channel audio.

---

## 3. Interview Record & Decision Log

| # | Functional Question | Recommended Approach | Evaluated Alternatives | User Decision / Rationale |
|---|---------------------|----------------------|------------------------|---------------------------|
| 1 | Scope of video-level audio generation | Generate video-level audio for every individual video across all channels (naturally covering Top 20 as well). | A) Top 20 only; B) Top 20 only + deprecate channels. | **Confirmed:** Generate per video across all channels so Top 20 is automatically covered without re-synthesis. |
| 2 | Spoken audio script format | Announce title and channel first, followed by summary: `"<Title>, by <Channel Name>. <Summary>"`. | A) Direct summary text only; B) Include "Why it matters" editorial blurb. | **Confirmed:** Title & channel announcement first, followed by full video summary breakdown. |
| 3 | Auto-mark Watched on audio completion | Automatically mark video as Watched/Read once its audio summary is listened to (90%+ completed). | Keep them separate (audio heard is separate from card watched). | **Confirmed:** Auto-mark Watched/Read at 90%+ audio completion. |
| 4 | Channel-level listening architecture | Synthesize per video; channel "Play All" queues individual video tracks in the player. Deprecate monolithic concatenated channel TTS. | Keep both monolithic channel MP3 and per-video MP3s. | **Confirmed:** Deprecate monolithic channel TTS; queue individual video tracks for better scrubbing and progress. |
| 5 | Site-wide playlist ordering | Queue Top 20 summaries first (#1 to #20), followed by remaining channel videos by category. | A) Strictly by category; B) Top 20 and categories strictly separated. | **Confirmed:** Top 20 first, followed by remaining videos by category with set-minus deduplication. |
| 6 | Historical week backfill policy | No historical backfill; generate on subsequent pipeline runs and leave historical weeks as-is. | Auto-backfill current week during `--build-only`. | **Confirmed:** No mass backfill; generate on future pipeline runs. |
| 7 | Speech formatting & strategic pauses | Strip all `#`, `/`, `\`, backticks, escaped symbols; insert natural punctuation pauses between sections and announcements. | Raw text stripping only without section cadence pauses. | **Confirmed:** Enhanced text cleaning with natural human cadence pauses. |

---

## 4. Frontier Model Probing Insights & Scope Gaps
- **Q1:** Per-video text source defined as `f"{title}, by {channel}. " + clean_text_for_speech(summary)`; skip if < 20 chars; safe_id uses video_id or sha256(url)[:12].
- **Q2:** Extended `_AUDIO_DATE_RE` retention regex to `summary_video_` prefix; deprecated monolithic channel TTS generation.
- **Q3:** Canonical join key: `video_id` -> canonical URL -> title hash. Eliminated channel-level audio fallback on video cards.
- **Q4:** Coupled 90%+ audio completion to `markVideoWatchedState` and `tubelm_heard` store. Forward skip on `queueNext` only.
- **Q5:** Track shape with canonical key, set-minus deduplication in site-wide queue, and resilient player load.

---

## 5. UI Specification
- **Selected Archetype:** Existing TubeLM Modern High-Density Web Reader (`desktop/templates/reader.html`) with Neon Lime / Obsidian color palette.
- **Key View Enhancements:**
  1. *Top 20 / Editorial Picks View:* Add `🎧 Play All Top 20 Summaries` action button in the header alongside `Watch on YouTube`. Card-level `🎧 Listen` buttons now trigger individual video audio.
  2. *Channel View:* Replace channel header `🔊 Listen` with `🎧 Play Summaries` queue button. Add `🎧 Listen` buttons to each video card.
  3. *Mini-Player Drawer:* Updates track title dynamically with `"${Channel Name} · ${Video Title}"` and advances track-by-track.
