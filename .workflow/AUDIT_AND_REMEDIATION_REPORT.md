# Audit & Remediation Report — TubeLM iOS vs `.workflow/REQUIREMENTS.md`

Date: 2026-09-19 · Scope: personal-use scale only (no enterprise patterns introduced).
Baseline: `swift test` (TubeLMCore) could not run out-of-the-box — the toolchain's
`swift-test` requires `libxml2.so.2` while the host provides `.so.16`; tests were
executed with a compat symlink (`LD_LIBRARY_PATH=/tmp/llxml`). Python baseline:
244 unit tests passing, ruff clean, `node --check worker/worker.js` clean.

Final verification: **250 Python tests passing, ruff clean, 7/7 Swift tests
passing, worker syntax clean, CI YAML valid, Info.plist parses.**

---

## A. Sync protocol mismatch (critical — cross-device sync was fully broken)

The iOS `CloudflareSyncClient` spoke a protocol the worker does not implement:
payload `{"client_id", "item_states": {id: {read, timestamp}}}` vs the worker's
`{"read_ids", "top20_read", "item_states": {id: signed_ts}}`; response decoder
expected `merged_item_states` which the worker never returns — **every** GET and
POST decode threw, so sync silently never worked in either direction.

- **Fix** (`ios/Sources/TubeLMCore/Sync/CloudflareSyncClient.swift`): rewrote
  `SyncPayload`/`SyncResponse` to the worker's exact keys; `item_states` values
  are signed `Double` timestamps (positive = read, negative = unread tombstone),
  matching the web reader's LWW scheme. Added typed `SyncError`
  (unauthorized / rate-limited / too-large / server) instead of one opaque
  `URLError`. `fetchRemoteState`/`pushLocalMutations` return `nil` when unpaired
  (empty key) rather than a fake `"skipped"` payload. 15 s request timeouts.
- **Fix** (`RootTabView.swift`): added the missing pairing surface — a sync
  settings sheet (worker URL + passphrase persisted to `UserDefaults`), a
  toolbar button to open it, pull-on-launch, and **debounced background push**
  (1.5 s coalescing `Task`, cancels superseded pushes) on *every* mutation:
  watched, queued, and bookmarked — per §2 "Auto-syncs in the background on
  every state mutation… No manual sync required."
- **Tests** (`TubeLMCoreTests.testSyncPayloadMatchesWorkerContract`): asserts
  encoded keys are exactly `read_ids`/`top20_read`/`item_states` (no `client_id`,
  no `merged_item_states`) and that real worker GET shapes decode, including the
  empty-state shape.

## B. Feed refresh: unconditional GET, no ETag, no foreground revalidation

`refreshFeedIfNeeded` did a plain `data(from:)` on every launch — no
`If-None-Match`/`If-Modified-Since`, no 304 handling, no single-flight guard,
no foreground-transition hook, despite §2 mandating "silent, single-flight
ETag / If-Modified-Since check" on "every app launch or foreground transition".
Concurrent launches could also interleave full re-downloads.

- **Fix** (`RootTabView.swift`): single-flight guard (`isRefreshing`), conditional
  GET with stored ETag/Last-Modified, 304 → touch `lastChecked` only, 2xx →
  decode + atomic cache replace + meta update, offline → silently keep cache.
  `scenePhase == .active` observer triggers revalidation on foregrounding.

## C. Read state: append-only, wrong eviction, unsafe writes

- `ContentStore.markItemRead` had **no unmark path** — `toggleRead` in
  `RootTabView` removed the id from the in-memory set but re-persisted it via
  `markItemRead`, so unmarking never survived a relaunch. Added
  `unmarkItemRead` writing a negative tombstone.
- `loadReadIDs` used `Set(ids.prefix(5000))` — `Set` has no order, so the "LRU"
  cap evicted **arbitrary** ids. Rewrote around `loadReadIDsOrdered()` with
  dedup + most-recent-first ordering; cap now evicts the genuinely stalest.
- `atomicWrite` did remove-then-move (a crash window with **no file at all**)
  and never created parent dirs. Now `Data.write(.atomic)` + parent-dir creation.
- No local `item_states` store existed, so tombstones could never be pushed or
  merged. Added capped (5000, largest-|ts| kept) finite-only store plus
  `applyRemoteStates` (most-recent-intent-wins merge, prunes/adds read ids).
- Non-finite `Double` (NaN/Inf) timestamps are rejected at the boundary.
- **Spec correction**: removed the 200-bookmark cap (`maxPinnedBookmarks`) —
  §2 requires *unlimited* text bookmarks (~2 KB each).

## D. Queue reorder crash + dead modifier + missing reorder UI

`CommuteQueueModel.move(fromOffsets:toOffset:)` subscripted `items[$0]` with no
bounds check — an out-of-range `IndexSet` (stale drag state) crashed. Now
filters to valid indices and no-ops when empty. `PlayerDeckSheet` used `.onMove`
inside a `VStack` where it never fires (List-only API); replaced with working
drag-and-drop reorder via a `QueueDropDelegate` driving the (now safe) model
`move`, satisfying §2's "full re-orderable Up Next queue".

## E. Audio engine crashes & false states

- `setupTimeObserver` was never called when the player already existed
  (`replaceCurrentItem` path) — elapsed time froze on track 2+; double-called it
  would leak observers. Now guarded, and duration only adopts finite positive
  values (`CMTime.indefinite` → NaN previously poisoned `duration`, the
  scrubber range, and `skip`).
- `seek`/`skip`/`formatTime` now clamp non-finite and negative inputs; `seek`
  clamps against `max(duration, 0)`.
- `playTrack` used `URL(string:)` — pipeline `audio_url`s are **relative**
  (`audio/…`) and silently failed to `nil`, landing in a "simulated playback"
  branch that set `isPlaying = true` with no audio. Now resolves against the
  Pages base URL, requires http(s), trims/ignores empty strings, and reports
  honest idle state when nothing is playable.
- Added end-of-track observer (play/pause icon + Now Playing no longer stick on
  "playing" after the audio ends) with correct observer-token cleanup
  (previously `removeObserver(self)` could not remove the block-based token).
- Channel "Listen" fallback now skips empty/whitespace audio strings instead of
  letting `""` shadow a real `channel.audioUrl`.
- 56 pt touch targets (§2): main play button is 62 pt; skip/speed are 44 pt —
  kept (44 pt is the platform minimum and the compact layout is spec-locked).

## F. Markdown rendering: injection, entities, lists

`MarkdownView` interpolated raw summary text into `LocalizedStringKey` — any
`\(…)`-like or `%`-style sequence in pipeline content could misrender or
resolve against the bundle, and `**bold**` markers leaked literally. Rewrote:
plain `Text` composition with manual `**bold**` runs, HTML-entity decoding
(`&amp;`/`&lt;`/`&gt;`/`&quot;`/`&#39;`/`&nbsp;`), `<br>/<li>/<ul>/<ol>/<b>/<em>`
normalization, numbered-list (`1.`/`1)`) blocks, tag stripping for headers —
covering the "rich formatted Markdown… proper paragraphs, bold keywords,
formatted bullet points" requirement for real pipeline HTML.

## G. Pipeline export (`desktop/web_reader.py`) — crashes, bloat, key divergence

- `parse_top20_digest` contained a **duplicated extraction block** (source-type/
  video-id computed twice) and referenced `rank_num`/`why_it_matters`/
  `source_name`/`published` correctly only by accident of ordering. Removed the
  duplicate; kept the single dedup + rank-fallback path.
- `extract_youtube_video_id` accepted 5+-char fragments via a "mock" fallback —
  LLM/feed garbage that collides as identity keys. Now strict 11-char only.
- Four unguarded `int(…)` conversions (malformed `duration_seconds`,
  `read_minutes`, `audio_seconds`) crashed the weekly build on dirty input.
  Added `_safe_int_seconds` / `_safe_channel_int`, applied at all sites.
- `_make_item_id` hashed every URL to 16 hex chars, diverging from the web
  reader's watch-state keys (raw `video_id`/URL), so cross-device read matching
  between laptop and phone missed. Now: raw `video_id` → raw URL (≤200 chars,
  sha256 only for over-long) → title hash. Documented convergence in docstring.
- `data.json` passed through producer keys (`candidate_id`, `summary`,
  `video_id`, `published`, `brief`, `word_count`, `audio_path`, …) the iOS
  models never read, and dropped `why_it_matters` when the Top-20 sidecar was
  the source (sidecar key is `summary`). Added `_normalize_mobile_item/_video/
  _channel` projecting exactly the §2/plan schema, with `summary→why_it_matters`
  backfill — smaller weekly payload, guaranteed-decodable.
- Duration cross-fill mutated shared dicts in place; now merges without
  clobbering existing values. `run_date` can no longer leak the literal string
  `"None"` into `data.json` (validated `YYYY-MM-DD`, else `""`).
- `hashlib` import moved to module top (was mid-file).
- Verified end-to-end with a synthetic pipeline run: relative audio URLs,
  `**bold**` + `&amp;` summaries, and RSS (URL-keyed) items all export to
  contract shape with stable ids.
- `audio_storage.bucket()` default was the legacy `"instagram-digest"` bucket
  while `wrangler.toml` binds `tubelm` — uploads and the worker CDN could target
  different buckets. Default is now `"tubelm"`; docstring updated.

## H. UI-spec alignment (Mock 1 lock)

- Channel header completed text is now exactly **"✓ Channel Completed"** (§2).
- Raw pipeline categories (`tech`, `deep_explainer`, `news_feed`, …) rendered
  uppercased verbatim; added `Channel.categoryLabel` mapping to the spec pills
  (**Tech & AI**, **Health & Bio**, **Science & Deep**, + News) with title-case
  fallback, rendered as a proper pill.
- Fabricated durations removed: `"14m"`/`"12m"` placeholders and
  `totalCount * 10` queue math replaced with real `durationSeconds` sums
  (falling back to `read_minutes`, then hiding the separator when unknown);
  player defaults changed from fake "Weekly Briefing Audio / 14:48" to honest
  idle state.
- Tactile haptics (§1) were entirely absent: added `Haptics` helper and wired
  light taps (queue, unmark, tab-level actions) and success confirmations
  (mark read, bookmark) into the central handlers.
- Serif headlines (§3: New York for headlines): `AppTheme.title` is now serif.
  (Neon `#d9ff63` badge kept — brand identity shared with PWA icons, AAA
  contrast intact.)
- Link opening in all three tabs now validates `http/https` before
  `UIApplication.shared.open` (pipeline URLs are untrusted input).
- Briefing shows a real empty state (first-run offline) instead of a blank
  feed; queue subtitle hides the `·` separator when duration is unknown.

## I. Packaging, CI, hygiene

- `.github/workflows/build-ios.yml`: added empty-IPA guard — the old script
  `zip`ped a binary-less `Payload` and uploaded it as a green artifact when both
  `cp` branches missed. Now fails loudly.
- `ios/TubeLM/Info.plist`: added `ITSAppUsesNonExemptEncryption = false`
  (avoids App Store / sideload compliance prompts for a no-encryption app).
- `.gitignore`: added `ios/.build/`, `.ruff_cache/`, `worker/.wrangler/`
  (the latter contains a real Cloudflare **account id** currently sitting
  untracked in the tree — never commit it).

## J. Adversarial findings checked and deliberately NOT changed

- `worker/worker.js`: audited line-by-line — merge math, DO serialization,
  header-only auth, per-IP + per-key rate limits, id caps, CORS scoping, Range
  handling are correct. **No changes.**
- `purge_old_digests_and_audio` 14-day retention, TTS backfill guards,
  R2-vs-local audio routing, RSS generation: correct. **No changes.**
- Web-reader `CANONICAL_KEY_RE` vs new URL-style synthetic ids: the reader's
  keys are date-scoped, the app's are id-scoped — convergence holds at the
  `video_id`/URL level where cross-device matching actually happens; the
  template's tombstone/merge logic already handles the rest. Reader template
  untouched (shipped Pages surface — out of scope for blind edits).
- `.workflow/mocks/build_mock1_full.py` has a **pre-existing** f-string
  `SyntaxError` (JS `===` ternaries inside an f-string literal); all 12 other
  mock scripts compile. Design-time mock tooling only — flagged, not fixed
  (untracked scratch content, not a shipped path).
- 120 Hz ProMotion: nothing to fix — standard SwiftUI `ScrollView`/`LazyVStack`
  inherits ProMotion; no custom timers or `drawingGroup` hazards present.
- LiveContainer packaging stays unsigned-zip (correct for the JIT container);
  no entitlements beyond `audio` background mode were added.

## K. Tests added

- Swift (+2 new, 7 total): worker-contract payload/response, out-of-bounds
  queue moves, tombstone unmark + remote merge, non-finite timestamp rejection,
  category-pill mapping, empty-audio fallback.
- Python (+6 new, 250 total in `tests/unit/`): id/URL convergence, safe-int
  coercion, producer-key stripping, `summary→why_it_matters` mapping,
  `run_date != "None"`.
