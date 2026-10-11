# Frontier Requirements Review — TubeLM Video-Level Audio Summaries & Playlist Queues

Source: `.workflow/REQUIREMENTS.md` (§1–§5, video-level audio + playlist queues rewrite)
Date: 2026-10-11
Reviewer: Muse Spark (verified against `desktop/web_reader.py`, `desktop/tts_service.py`,
`desktop/audio_storage.py`, `desktop/paths.py`, `desktop/templates/reader.html`,
`ios/Sources/TubeLMApp/Views/RootTabView.swift`, `ios/Sources/TubeLMApp/Audio/AudioPlayerManager.swift`,
`sources.json`)

> Note: the prior review in this file (2026-09-24, Top-N canonical count / interim
> removal / audio-join / UAT gates) is superseded by the REQUIREMENTS rewrite and
> preserved in git history. This review covers only the new scope (§2 A–D + §5).
> The plan-level findings in `.workflow/FRONTIER_PLAN_REVIEW.md` still stand where
> they do not conflict.

## Target User Scale Anchor

**Single-Person Personal Use Exclusively** (§1) — hard constraint carried through every
recommendation:

- Reject enterprise complexity: no auth frameworks, no microservices, no distributed
  DBs, no maintained backend logic, no new dependencies for a one-user weekly job.
- Hosts: GitHub Pages static site + Cloudflare Worker/R2 (already deployed) +
  sideloaded `.ipa` in LiveContainer on iOS. ~37 sources (`sources.json`), 2-week
  rolling retention, weekly overnight pipeline.
- Every Q below is answered with the cheapest pipeline-local or client-local fix;
  anything requiring per-user ops, server state changes, or background daemons is
  flagged as anchor-violating.

---

## Q1 — §2.A: What is the per-video synthesis unit, and what happens when synthesis yields nothing?

**Ambiguity:** §2.A mandates "audio summaries for each individual video across all
channels" with script `"<Title>, by <Channel>. <Summary>"`, but never defines the
text source per video, the RSS-article inclusion rule, or the missing-audio UI.
"Every Top 20 video will reference its corresponding video-level audio without
duplicate synthesis" assumes a join that does not yet exist.

**Code-verified edge cases / failure modes:**
- Text source is undefined at video granularity. Today's TTS input is channel-level
  only: `web_reader.py:1118` synthesizes from `summary_text / full_summary_html /
  summary_preview`, and `tts_service.py:220-275` (`_backfill_week_async`,
  concurrency 3) walks channel digests to `summary_{run_date}_{safe}.mp3`. No
  per-video text extraction, chunking, or timeout scaling exists yet.
- Silent-skip guard: `_generate_audio_async` returns `False` when cleaned text is
  `< 20 chars` (`tts_service.py:121-123`). Shorts / title-only videos will
  produce no file with no error — currently indistinguishable from "not yet run".
- RSS inclusion unclear: `sources.json` has 1 RSS source (MIT Technology Review)
  with no `video_id`. "Every individual video" either silently excludes RSS (then
  §2.C site-wide "remaining channel videos" double-counts them) or includes
  articles (then the `"<Title>, by <Channel>"` script and `safe_id = video_id or
  sanitized URL slug` naming need an article rule).
- `safe_id` collision risk: `paths.safe_channel_name` (`paths.py:225`) maps
  `[^a-zA-Z0-9_\-]` → `_`, so distinct URLs can slug to the same `safe_id`
  (`Foo?x=1` vs `Foo-x-1`); YouTube `video_id` is 11-char allowlisted
  (`web_reader.py:40,81-89`, garbage → `""`), so any LLM/feed-malformed id falls
  back to slug and may collide or orphan.
- Scale: ~37 channels × ~5 videos ≈ 150–200 TTS calls/week. At edge-tts
  ~20–40s each with concurrency 3, that is ~20–40 min of pipeline time, all
  inside the Friday-overnight window. Failure degrades to `False` (TTS never
  breaks the run by design, `tts_service.py:1-6`), so partial-audio weeks are the
  normal case, not the exception — yet §2.B demands the old channel-audio
  fallback be "eliminated", leaving missing-audio rendering unspecified.

**Recommended approach:**
- Define the unit pipeline-local: per-video TTS input = `"<Title>, by <Channel>. "`
  `+ clean_text_for_speech(video summary_html → text)`, synthesized only when
  cleaned body ≥ 20 chars; otherwise emit no file and set `audio_url = ""`
  (renders no `🎧 Listen` button — never a dead button, never channel-audio
  fallback).
- Include RSS articles as TTS units with `safe_id = sha256(url)[:12]` (not raw
  slug) and script `"by <Feed Name>"`; YouTube units use raw `video_id` when it
  passes `_VIDEO_ID_RE`, else the same hashed-slug rule. One function, tested
  with a `youtu.be` vs `youtube.com/watch?v=` pair plus an RSS URL pair.
- Keep `force=False` idempotency (skip-if-exists) and concurrency 3; log a
  per-run `{scanned, generated, skipped, failed}` count so a partial week is
  visible without new infra.
- Anchor-fit: pure pipeline + template conditional, no new services or deps.

**Alternatives:**
- Synthesize Top-20-only first, channels later — halves week-one cost but
  contradicts the decision log (Q1: "Generate per video across all channels");
  rejected unless pipeline runtime proves unacceptable.
- Fall back to channel audio when per-video is missing — preserves listenability
  on partial weeks but reinstates exactly the fallback §2.B bans and mislabels
  channel audio as video audio; rejected.
- Concatenate-then-split channel TTS to fabricate per-video files — zero extra
  synthesis cost but wrong timestamps and no per-video scrubbing; rejected.

**Decision needed:** Confirm per-video text source (summary_html → text), the
≥20-char skip rule with hidden-button rendering, RSS inclusion with hashed
`safe_id`, and `video_id`-first / hash-second naming.

## Q2 — §2.A + §2.D: How do naming, retention, R2, and Pages deploy interact at ~200 files/week?

**Ambiguity:** §2.A fixes naming `summary_video_{run_date}_{safe_id}.mp3` in
`~/.tubelm/audio/` → `site/audio/` → R2 `tubelm/audio/{run_date}/…`, while §2.D
leaves historical weeks as-is with no backfill. Nothing reconciles the new
prefix with retention, the 5 MB deploy gate, or per-file R2 latency.

**Code-verified edge cases / failure modes:**
- Retention regex misses the new prefix: `_AUDIO_DATE_RE =
  r"^(?:summary_)?(\d{4}-\d{2}-\d{2})_"` (`web_reader.py:38`) matches `summary_…`
  and bare `…` but **not** `summary_video_…`. `purge_old_digests_and_audio`
  (`web_reader.py:121`) will therefore never purge per-video local files —
  unbounded growth in `~/.tubelm/audio/` and `site/audio/`. R2 purge is safe
  (it matches `/YYYY-MM-DD/` in the key, `audio_storage.py:75`), but local/site
  are not.
- Deploy gate is per-file, not total: `deploy_to_gh_pages` refuses any file
  > 5 MB (`web_reader.py:1319-1323`), and the R2-active path deletes large
  `site/audio` files post-build (`:1302-1306`). Per-video TTS files are small
  (~50–300 KB), so the gate passes — but only if R2 upload actually happened.
  With R2 unconfigured, `site/audio/` holds ~200 files/week × 2 weeks ≈ 400
  files (~50–100 MB total); one stray NotebookLM `.m4a` > 5 MB still fails the
  whole deploy with no specified recovery order.
- R2 N+1 latency: `upload_audio` is idempotent via `head_object`
  (`audio_storage.py:50-54`) — correct, but 200 `head_object` + conditional
  `upload_file` calls per build in a tight loop adds minutes with no
  concurrency and no per-run summary.
- Deprecation gap: channel TTS generation lives in two places — standalone
  `backfill_week` (`tts_service.py:278`) and build-time backfill
  (`web_reader.py:1111-1131`, writing `summary_{date}_{ch}.mp3` +
  `summary_audio_url`). §2.A "deprecate monolithic channel TTS" names no files;
  leaving either path live silently re-creates the deprecated artifacts.
- Historical weeks (§2.D) will have channel `summary_audio_url` / NotebookLM
  `audio_url` but zero per-video files. The new `🎧 Play Summaries` channel
  button and per-card `🎧 Listen` buttons have no specified historical behavior
  — empty queue, hidden buttons, or legacy-monolithic fallback are all plausible
  readings.

**Recommended approach:**
- Extend `_AUDIO_DATE_RE` to `^(?:summary_(?:video_)?)?(\d{4}-\d{2}-\d{2})_`
  (one-line fix) so retention covers the new prefix; no migration, no new job.
- Keep R2-first ordering (audio → R2, `data.json` last, single push) with a
  pre-deploy 5 MB scan as an explicit gate message, not a surprise refusal.
- Deprecation checklist (deletion-only): disable channel-TTS synthesis in both
  `backfill_week` and the `web_reader.py:1111-1131` block; keep reading existing
  `summary_{date}_{ch}.mp3` / `summary_audio_url` for historical weeks only
  (tolerant-read, never write). NotebookLM `audio_url` deep-dives untouched.
- Historical-week UI rule: when a week has zero per-video tracks, hide the new
  queue buttons and keep the legacy channel audio button (week-scoped
  conditional, no backfill).
- Anchor-fit: regex + checklist + template conditional; no new storage or CI.

**Alternatives:**
- Mass-backfill current week during `--build-only` — fills the gap fastest but
  contradicts the decision log (Q6: "No mass backfill") and burns edge-tts time
  inside a build command; rejected.
- Delete all channel `summary_*.mp3` artifacts now — cleanest steady state but
  breaks historical-week listening the decision log preserves; rejected.
- Vendor per-video audio into the git repo / Pages without R2 — works for one
  user with R2 down but balloons the orphan `gh-pages` force-push; keep as
  degraded fallback, not primary.

**Decision needed:** Confirm the retention-regex extension, the two-site
deprecation checklist with historical tolerant-read, R2-first deploy ordering,
and the hide-buttons-on-audioless-weeks rule.

## Q3 — §2.B: What is the canonical Top-20 ↔ channel-video join key when ids are missing or URL forms differ?

**Ambiguity:** §2.B maps each Top-20 `audio_url` "from video ID / URL match" and
requires `_normalize_mobile_item()` / `_normalize_mobile_video()` to attach
video-level `audio_url`. Neither the key priority nor normalization is defined,
and the current code joins on channel name — not video identity.

**Code-verified edge cases / failure modes:**
- Today's join is channel-level: `week_audio_map` keyed by normalized channel
  name/id (`web_reader.py:1171-1178`) fills Top-20 `audio_url` by `source_name`
  (`:1188-1191`), and the mobile export repeats it (`:1248-1266`). The
  normalization (`_normalize_channel_key`, `:364-366`, lowercase + strip
  punctuation) papers over `Peter Attia, MD` vs `Peter Attia MD` but cannot
  address video identity at all — every Top-20 card currently points at channel
  audio by construction.
- Video identity is lossy at three boundaries: `_clean_video_id` allowlists
  11-char ids (else `""`, `:81-89`); `extract_youtube_video_id` (`:200`) must
  handle `watch?v=`, `youtu.be/`, `shorts/`, `embed/`, and bare ids or the same
  video yields two keys; `_make_item_id` (`:92-113`) falls back from
  `video_id` → URL (≤200 chars) → title-hash, so a Top-20 item with `video_id`
  and a channel video with only URL get *different* synthetic ids and never
  join.
- Dedup scope: Top-20 items are deduped by `video_id or url or title-lower`
  (`:1161-1168`) but channel videos are not cross-deduped against Top-20, so a
  "no duplicate synthesis" claim needs a shared synthesis map keyed the same
  way or Top-20 re-synthesis happens under a different key.
- iOS has its own second-chance join: `resolveAudioUrl` falls back to channel
  audio by case-insensitive name/id (`RootTabView.swift:530-544`), and
  `mergeFeedAudio` re-applies channel audio to audioless videos (`:563-594`).
  If the pipeline stops emitting channel fallback but iOS keeps applying it,
  the banned fallback survives on-device.

**Recommended approach:**
- Canonical video key (pipeline-local, one helper): normalized YouTube id when
  `extract_youtube_video_id(url) or video_id` yields an 11-char id (lowercased?
  No — YouTube ids are case-sensitive; compare exact), else normalized URL
  (strip tracking params, `youtu.be` → `youtube.com/watch?v=` canonical form),
  else `sha256(title-lower)[:16]`. Synthesis map, Top-20 wiring, and both
  `_normalize_*` callers all use this helper; channel-name fallback deleted
  from both the `weeks` wiring (`:1188-1191`) and the mobile export
  (`:1265-1266`).
- `audio_url = ""` when unjoined (no channel fallback); template/iOS hide the
  per-card button on empty. iOS `resolveAudioUrl` keeps direct-hit only; delete
  the channel-fallback branch and the `mergeFeedAudio` video backfill (keep
  channel objects' own `summaryAudioUrl` for historical weeks).
- Anchor-fit: one helper + call-site swaps + template/iOS conditionals; no new
  identity service.

**Alternatives:**
- Keep channel-audio fallback until per-video coverage is complete — kindest to
  partial weeks but directly violates the "eliminates the old fallback"
  requirement; rejected except as a week-scoped historical rule (see Q2).
- Fuzzy title matching for join misses — rescues LLM-mangled ids but
  reintroduces false-positive audio (wrong video's summary plays); rejected in
  favor of honest empty state.
- Treat Top-20 sidecar audio as authoritative and copy it onto channel videos
  (reverse join) — fixes Top-20 display but leaves channel cards silent;
  rejected; the synthesis map is the single source.

**Decision needed:** Confirm the id → canonical-URL → title-hash key priority,
URL canonicalization rule, deletion of both pipeline and iOS channel fallbacks,
and empty-`audio_url` = hidden-button semantics.

## Q4 — §2.C: Where does heard ↔ watched coupling live, and what are its trigger semantics?

**Ambiguity:** §2.C stores heard tracks in `localStorage` under
`tubelm_heard:{src}`, skips heard tracks "during forward progression", and
auto-marks the card `Watched ✓` / `Read ✓` at "90%+ playback (or ends)". The
key scheme, the src→card mapping, and the exact trigger are all unspecified —
and the two halves live in different subsystems today.

**Code-verified edge cases / failure modes:**
- Key is URL, not content: `heardKey(src) = 'tubelm_heard:' + src`
  (`reader.html:3038`), `isHeard`/`markHeard` (`:3039-3047`). The same audio
  served as `audio/…mp3` vs `https://…r2…/…mp3` yields two keys; a re-synthesized
  week yields a third. Keys accumulate unbounded in `localStorage` (no purge,
  unlike `read_ids` capped at 5000 in `web_reader.py:117-118`), and heard state
  never enters cross-device sync (sync payload is `read_ids`; heard is
  local-only).
- Trigger exists but coupling does not: `timeupdate` marks heard at
  `currentTime / duration >= 0.9` (`reader.html:3582-3591`) and `onended`
  advances the queue (`:3604-3609`), but `markHeard` only sets the flag and
  re-renders the sidebar — it never calls `markVideoWatchedState`
  (`:2270-2284`) or `recordItemState`. The §2.C "automatically marked as
  Watched" path is unwritten.
- Gaming / misfire modes: seeking to 95% then pausing marks heard without
  listening; saved-position restore (`tubelm_pos:` + `loadedmetadata`,
  `:3242-3249`, `:3548-3555`) jumping past 90% marks heard on load; sub-10s
  TTS clips hit 90% in seconds; `duration = NaN/Infinity` (metadata not yet
  loaded, live edge) guards correctly today (`d && isFinite(d) && d > 0`) but
  any rewrite must preserve the guard. `queueNext` (`:3273-3284`) skips heard
  forward but `queuePrev` (`:3285-3287`) does not skip back — correct but
  unstated, and "during forward progression" needs exactly this закрепление.
- iOS divergence: `playItemAudio` calls `markItemRead` on play *start*
  (`RootTabView.swift:546-550`), not at 90%. Web-at-90% vs iOS-at-start will
  permanently disagree on watched state across devices for the same video.

**Recommended approach:**
- Key heard by canonical video key (Q3), not `src`: `tubelm_heard:{week}:{key}`,
  with `src` retained as a secondary alias written at mark time (covers the
  R2-vs-relative duality without double entries). Cap stored keys (e.g. prune
  to latest 1000 on write, mirroring `MAX_READ_IDS`).
- Trigger (client-local, web): keep `timeupdate ≥ 0.9 AND isFinite(duration)`
  OR `ended` as the single mark path; on mark, call both `markHeard(key)` and
  `markVideoWatchedState(videoId, url, true)` via a src→`{videoId, url}`
  lookup carried on the queue track (new track shape, see Q5). Seek-gaming
  accepted for a one-user player (no fraud model); saved-pos restore past 90%
  explicitly counts as heard (document it, don't special-case it).
- Forward-skip = `queueNext` only; `queuePrev` never skips; `playAllUnheard`
  builds `unheardOnly` with fallback to full queue when empty (existing
  `:3288-3295` behavior, preserved).
- iOS: keep mark-on-start (LiveContainer background-audio reality) but record
  the same canonical key into synced `readIDs` so web 90% and iOS start converge
  on the shared watched bit even though heard bits stay device-local.
- Anchor-fit: localStorage-only + existing `readIDs` sync; no server, no auth.

**Alternatives:**
- Sync heard state across devices via the worker — true parity but elevates a
  playback-progress hint to synced CRDT state for one user; rejected.
- Require `ended` only (drop 90%) — precise but punishes podcast-style early
  exits and breaks the decision log (Q3: "90%+"); rejected.
- Separate heard from watched (revert coupling) — simplest code but contradicts
  the decision log (Q3: "Auto-mark"); rejected.

**Decision needed:** Confirm canonical-key (not src) heard keys with alias +
  prune cap, the 90%-or-ended single mark path with src→card lookup, forward-
  only skip semantics, and iOS-converges-via-`readIDs` parity rule.

## Q5 — §2.C + §5: What is the queue construction contract for Top-20-first site-wide ordering with dedupe?

**Ambiguity:** §2.C orders the site-wide queue "Top 20 first (#1–#20), followed
by remaining channel videos by category" with per-scope Play buttons, and §5
pins the mini-player title to `"${Channel} · ${Video Title}"`. The track shape,
dedupe rule, within-category sort, and empty-queue behavior are undefined — and
the current player is channel-level only.

**Code-verified edge cases / failure modes:**
- Today's queue is channel-tracks: `buildQueue` filters channels with
  `has_audio/audio_url or summary_audio_url` (`reader.html:3199-3202`), sorts by
  `CATEGORY_ORDER = ['tech','deep_explainer','health','news_feed']` then channel
  name (`:3214-3221`), and stores `{chId, weekKey, src, title, category,
  summary}` (`:3222-3229`). There is no per-video track, no Top-20 segment, no
  rank, no `videoId`. `playChannelAudio` (`:3296-3324`) and `playAudioDirect`
  (`:3339+`) splice monolithic tracks; `toggleAudio` (`:3544-3568`) bypasses the
  queue entirely. All four paths need consolidation or the new buttons will
  fight the old ones.
- Top-20/channel overlap: Top-20 items are drawn from channel videos (§2.A), so
  "Top 20 first, followed by remaining" without dedupe plays ~20 videos twice
  in the site-wide queue. "Remaining" must mean set-minus on the Q3 canonical
  key, but no requirement states it.
- Within-category sort unspecified: channel-name sort (today) vs published-date
  vs Top-20-rank (for the first segment) produce audibly different commutes.
  RSS items have no `duration`/`video_id`; unknown categories sort as `99`
  (today) — silent bucketing.
- Persistence + scale: `savePlayer`/`loadPlayer` persist the full queue
  (`tubelm_player`, `:3177-3194`). A 150-track site-wide queue of `{src, title}`
  pairs is fine (~50 KB), but stale `src` URLs from a purged week (see Q2) will
  404 on restore with only a console warning (`playIndex` catch, `:3259-3266`).
- Scope gaps: Brief mode (`renderBriefView`, `:3063-3104`) has its own `🔊
  Listen` (channel summary, `:3089`) outside the queue; RSS `feed.xml` encloses
  no per-video audio; email digest links to text only. None is in §2.C scope,
  but each will look broken next to per-card `🎧 Listen` buttons if left
  untouched.

**Recommended approach:**
- New track shape (client-local): `{key (Q3 canonical), videoId, url, src,
  title, channelName, channelId, category, rank?, weekKey}`; display title
  always `` `${channelName} · ${title}` `` (§5). Three constructors share one
  `buildVideoQueue(tracks)` primitive: Top-20 scope (rank order 1→20, skip
  `audio_url == ""` with a count note "N of 20 have audio"), channel scope
  (channel's videos in digest order), site-wide (Top-20 segment + set-minus
  remainder sorted by `CATEGORY_ORDER` then channel name then digest order).
- Route all new buttons (`🎧 Play All Top 20`, `🎧 Play Summaries`,
  `► Play Summaries`, per-card `🎧 Listen` via `playAudioDirect`-replacement)
  through `playIndex`/`queueNext`; leave `toggleAudio` for historical-week
  monolithic playback only (week-scoped branch, deleted when retention ages
  those weeks out).
- Restore hardening: on `loadPlayer`, drop tracks whose `weekKey` is not
  `current/prev` and whose `src` fails a `HEAD`-less `canplay` timeout —
  surface "Queued track unavailable (week purged)" in the mini-player instead
  of a console-only warning.
- Out-of-scope freeze: Brief mode, RSS enclosures, and email keep current
  behavior; note as non-goals so they are not filed as regressions.
- Anchor-fit: template-local queue rewrite, no new player library, no service
  worker, no background sync.

**Alternatives:**
- Unified always-mixed queue (podcasts + summaries + per-video) — simplest
  `buildQueue` but destroys the deliberate NotebookLM-vs-TTS separation
  (`reader.html:3163` comment, prior review Q4) and doubles commute length;
  rejected; keep per-scope queues with per-channel NotebookLM-first rule where
  a deep-dive exists.
- Server-side (build-time) playlist files (`.m3u` per scope) — shareable and
  testable but adds three artifacts per week for one listener's ephemeral
  heard-skipping queue; rejected.
- Cap site-wide queue at Top-20 only — sidesteps the 150-track restore and
  sort debates but abandons the "followed by remaining" decision (Q5:
  "Confirmed: Top 20 first, followed by remaining"); rejected.

**Decision needed:** Confirm the track shape with canonical `key`, Top-20-rank
then category/channel/digest ordering, set-minus dedupe for the remainder
segment, `loadPlayer` purge rule, and Brief/RSS/email as explicit non-goals.
