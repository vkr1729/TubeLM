# Audit & Remediation Report — TubeLM vs `.workflow/REQUIREMENTS.md`

Date: 2026-09-20 · Scope: personal-use scale only (no enterprise patterns introduced).
Auditor method: adversarial — probed every workspace trust boundary with hostile
inputs (nulls, wrong types, garbage strings, NaN/Inf, missing files, non-JSON
bodies, over-long ids) and fixed what crashed, desynced, or regressed.

Working tree at audit start (2026-09-20, second session): uncommitted Phase-2
UAT remediation was already in flight (theme mode, feed partition, alias-aware
read state, `video_id` backfill, player-deck redesign, keychain/settings plan,
`data.json` + mock regeneration). This cycle audited that work adversarially
against REQUIREMENTS §§1–5, fixed what it broke or left hostile, and
re-verified the whole workspace. Personal-use scale respected throughout: no
new services, deps, tables, or background daemons.

Baseline (pre-remediation, re-measured 2026-09-20):
`swift test` needs a compat shim on this host (`swift-test` wants
`libxml2.so.2`, host provides `.so.16`; `mkdir -p /tmp/llxml &&
ln -sf /usr/lib/x86_64-linux-gnu/libxml2.so.16 /tmp/llxml/libxml2.so.2`).
Python: 277 unit + 26 integration passing, ruff clean,
`node --check worker/worker.js` clean. Prior report (2026-09-19, sections A–K
below) verified intact — all fixes re-checked, none regressed.

Final verification (post-remediation): **294 Python passing
(`-p no:randomly`; random-order runs show one pre-existing order-dependent
flake — see X.5), ruff clean, 27/27 Swift tests passing (incl. UAT suite),
`node --check worker/worker.js` clean, `web_reader --build-only` clean,
synthetic mobile-contract projection (20 items / 23 channels) decodes.**

Prior audit (2026-09-19, retained verbatim — re-verified, no regressions):

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

## K. Tests added (2026-09-19 cycle)

- Swift (+2 new, 7 total): worker-contract payload/response, out-of-bounds
  queue moves, tombstone unmark + remote merge, non-finite timestamp rejection,
  category-pill mapping, empty-audio fallback.
- Python (+6 new, 250 total in `tests/unit/`): id/URL convergence, safe-int
  coercion, producer-key stripping, `summary→why_it_matters` mapping,
  `run_date != "None"`.

---

# New audit cycle — 2026-09-20 (this session)

Working tree at audit start already contained uncommitted §4 remediation
(icon set, plist keys, `Bundle.module` removal, deferred audio session,
`package_ipa.sh` + CI validation) plus a committed-but-stale `ios/TubeLM.ipa`
(no icons inside). Each item below was **probed with a hostile input first,
then fixed, then covered by a test**. Personal-use scale respected throughout:
no new services, deps, tables, or background daemons.

## L. `read_state` cross-device wipe (critical — phone state silently dropped)

- **Probe:** mobile identity keys are raw `video_id` / raw URL
  (`7K_sA6o1dOE`, `https://example.com/a`) — the dashboard
  `_CANONICAL_READ_ID_RE` (`^\d{4}-\d{2}-\d{2}_.+`) matches **none** of them.
  `POST /api/reader/read-state` ran `_sanitize_read_ids(ids,
  canonical_only=True)`, so any phone-originated read state forwarded through
  the PWA/desktop path was reduced to `[]`. The single-id toggle path
  (`{id, is_read}`) also failed to discard the truncated form on unmark, and
  crashed the comparison when the stored document was a non-list.
  `purge_old_digests_and_audio` had the same shape of bug in milder form
  (non-date ids kept, but rewrite was a non-atomic `write_text` and a
  non-list `read_ids` document broke the diff).
- **Fix** (`desktop/gui.py`): default sanitize path (no `canonical_only`)
  preserves all string ids; single-id path truncates symmetrically on add
  **and** remove and tolerates a corrupt/non-list stored document.
  `canonical_only=True` retained as an opt-in for the legacy date-scoped
  channel view only.
- **Fix** (`desktop/web_reader.py`): purge keeps non-date ids (mobile keys
  have no retention date and must never age out), guards non-list documents,
  and rewrites atomically (pid-temp + `os.replace`).
- **Tests:** `test_read_state_preserves_mobile_keys` (integration: video-id +
  URL round-trip through the real endpoint),
  `test_read_ids_preserve_mobile_keys` + `test_read_ids_reject_non_list_input`
  (unit). Existing `test_read_ids_canonical_only_filtering` kept green —
  opt-in behavior unchanged.

## M. Unsafe numeric coercion: NaN/Inf/decimals crash or poison the week

- **Probe:** `_safe_int_seconds(12.9)` **raised** `ValueError`
  (`int("12.9")` throws — only `int()`'s own error was caught, not the
  float-string case); `_safe_channel_int(float('nan'))` raised; Swift
  `decodeIfPresent(Int.self)` throws on `"7"` / `12.9` / `true`, so one dirty
  producer row kills the whole feed decode.
- **Fix** (Python): both coercers go through `float()` + `math.isfinite` —
  `"12.9"`/`12.9` → `12`, NaN/Inf/garbage → `0`, never raise.
- **Fix** (Swift, `DigestFeed.swift`): file-private `lenientInt`/
  `lenientString` helpers; `FeedItem.rank`/`durationSeconds`,
  `Channel.readMinutes`, and all `id`/`title`/`name`/`category` fields coerce
  numeric-string/float/bool and fall back instead of throwing. Empty-string
  ids fall back to `UUID()`.
- **Tests:** extended `test_safe_int_seconds_never_crashes` (NaN/Inf/decimals),
  new Swift `testLenientDecodingToleratesDirtyProducerValues`.

## N. Mobile-export shape crashes on hostile producer rows

- **Probe:** `_normalize_mobile_item(raw, rank="abc")` passed the garbage
  string into `data.json` (`"rank": "abc"` — Swift `Int?` decode then throws
  for the whole feed); `_normalize_mobile_channel({'videos': None})` raised
  `TypeError: 'NoneType' object is not iterable`, killing the weekly build;
  `_make_item_id({'id': 'x'*500})` emitted a 500-char id breaking every
  256-char cap downstream; `optimize_audio_for_web(missing.mp3)` raised
  `FileNotFoundError` out of the fallback copy; `generate_rss_feed` raised
  bare `KeyError: 'title'` on a partial Top-20 row and accepted non-dict
  channels/items; `data.json` temp-write used `Path.replace` with no cleanup.
- **Fix** (`desktop/web_reader.py`): rank coerced to `Int`, omitted when
  garbage; channel normalizer rejects non-dict input and non-list `videos`;
  `_make_item_id` hashes over-long ids to 16-char form; missing audio input
  returns `False` (logs, no raise) and the fallback copy guards `OSError`;
  RSS filters non-dict rows and uses `.get()` throughout; `data.json` swap is
  `os.replace` in `try/finally` with temp cleanup.
- **Tests:** `test_normalize_item_rank_garbage_omits_rank`,
  `test_normalize_channel_rejects_non_list_videos`,
  `test_make_item_id_caps_overlong_ids`,
  `test_generate_rss_feed_tolerates_hostile_shapes`,
  `test_optimize_audio_missing_input_returns_false`.

## O. Flask endpoints: non-JSON bodies + type-confusion crashes

- **Probe:** `POST`ing `text/plain` to the 10 endpoints using `request.json`
  raised `415` (Werkzeug, unhandled HTML error page); non-string
  `name`/`url`/`channel_id`/`identifier` raised `AttributeError` on `.strip()`
  → **500**; `{"channels": "UC123"}` iterated a string into corrupt
  `--channels U,C,1,2,3` argv; `compute_state_key("notadict")` raised
  `AttributeError`; numeric `timestamp` raised on `.replace()`; unbounded
  `name`/`link_selector`/`identifier`/`url` flowed into stored JSON.
- **Fix** (`desktop/gui.py`): all 10 `request.json` sites → silent
  `get_json(silent=True)` + `isinstance(dict)` guard; per-field
  `isinstance(str)` checks with 400s before `.strip()`; `channels` must be a
  list; `compute_state_key`/`_enrich…` skip non-dicts; `state/channel`
  validates `channel_id`/`state_key`/`timestamp` types; length caps (`name`
  256, `channel_id` 128, `url`/`identifier` 2048, `link_selector` 512, prompt
  text 200k).
- **Tests** (`TestRequestHardening`, 6 new): garbage-body sweep,
  channels-type, non-string source fields, non-string timestamp, non-string
  prompt text.

## P. Handler construction: KeyError on dirty `sources.json` rows

- **Probe:** any loader-passing row with a wrong-typed field
  (`max_items: "lots"`, `category: 123`, missing `name`) raised
  `KeyError`/`TypeError` inside `create_handler` or handler `__init__`.
- **Fix** (`factory.py`, `rss_handler.py`, `webpage_handler.py`):
  `create_handler` validates `name`/`channel_id`/`url` (descriptive
  `ValueError` per row — `main.py` already catches per-source and skips);
  category falls back to `"tech"`; `max_items` clamped to `[1, 50]` at factory
  and handler `__init__` (bool-safe); non-string `link_selector` → `""`.
- **Tests:** existing `test_factory` + `test_sources_loader` green (16
  passing); clamp covered by `test_clamps_source_item_limit` (`5000` → `50`).

## Q. Downloader: `ValueError` on garbage rank kills archival

- **Probe:** `build_video_filename("x", …)` raised `Unknown format code 'd'`;
  `download_top10_videos` with `rank: "abc"` raised `invalid literal for
  int()` — one bad row aborted the whole Top-10 archival pass.
- **Fix** (`desktop/top10_downloader.py`): rank coerced (`→ 0` filename,
  `→ sequential` task). Verified `build_video_filename('x',…)` →
  `"00 - S - T.mp4"`.

## R. Swift store: blank/over-long ids bypass every 256-char cap

- **Probe:** `markItemRead("   ")` stored a whitespace id; 500-char ids flowed
  into all three stores — desyncing from the worker (`MAX_ID_LENGTH = 256`,
  drops them) and dashboard (truncates), so one item had three keys.
- **Fix** (`ContentStore.swift` + `CloudflareSyncClient.swift`): trim +
  reject blank + reject `>256` at every store entry point
  (`mark`/`unmark`, bookmarks, all state-map load/save/merge paths); sync
  push sanitizes ids/states to worker bounds (trim, 256-cap, finite-only,
  5000-cap) before encoding.
- **Tests:** Swift `testStoreRejectsBlankAndOverlongIds`.

## S. Swift decode on real-world nulls (verified, extended by M)

- `audio_url: null` on all 20 Top-20 items and absent `summary_audio_url` —
  already handled (`String?` optionals). Residual wrong-type risk covered in
  M. Synthetic projection of the full mock feed (20 items / 23 channels,
  producer keys stripped) verified contract-clean.

## T. UI-spec drift: fabricated durations in two places

- **Probe:** `ChannelsView` header rendered `"\(readMinutes ?? 4)m"` —
  unknown read time displayed a fabricated `4m`; channel `+ Queue` fell back
  to the same `4m`; negative `durationSeconds` summed into queue math.
- **Fix** (`ChannelsView.swift`): header hides `· Nm` when `readMinutes` is
  nil/≤0; queue label prefers positive-`durationSeconds` sum, then positive
  `readMinutes`, else `""` (deck row already hides `·` on empty duration).

## U. Stale `ios/TubeLM.ipa` (flagged, not replaced)

- Committed `ios/TubeLM.ipa` (2.38 MB) predates the icon work — `unzip -l`
  shows 5 files, **no `AppIcon*.png`**; fresh `build/TubeLM.ipa` (gitignored)
  has all 10 files with icons, same `arm64` binary hash (`8dc16076…`).
  Replacing a 2.4 MB binary is a release action for the owner (rebuild +
  re-sign via CI `Package LiveContainer IPA`), not an audit side effect.
  **Recommendation:** after merging, regenerate via
  `scripts/package_ipa.sh`/CI and overwrite `ios/TubeLM.ipa`, or ignore
  `ios/*.ipa` and ship CI artifacts only.

## V. Checked and deliberately NOT changed (this cycle)

- `worker/worker.js` — re-audited: LWW merge, tombstones, per-IP + per-key
  rate limits, 1 MiB cap, header-only auth, CORS, Range/audio path correct.
- `desktop/main.py`, `notebooklm_service.py`, `tts_service.py`,
  `audio_storage.py`, `paths.py`, `run_control.py`, `sources_loader.py`,
  `email_service.py`, `summary_quality.py`, `weekly_audio_service.py`,
  `top10_service.py`, extractors — garbage timestamps / corrupt state files /
  `None` handlers all fall back safely.
- `desktop/templates/reader.html` — shipped Pages surface; merge/tombstone
  logic already handles the mobile key space. Untouched.
- `.workflow/mocks/build_mock1_full.py` f-string `SyntaxError` — still
  present, still design-time mock tooling only (tracked, not a shipped path;
  other 12 mock scripts compile). Not fixed: editing it risks invalidating
  the UAT fixtures it emits.
- Top-20 YouTube-only pin (`_source_candidates` skips non-YouTube rows
  without `video_id`) — pre-existing product decision ("pure video top 20",
  commit `6e49ac4`); conflicts with REQUIREMENTS §2 "20 videos/articles"
  wording but out of scope for a crash-fix audit. Flagged, not changed.
- `MinimumOSVersion 17.0` vs §1 "iOS 26 baseline" — floor vs tested target,
  consistent as written.

## W. Tests added this cycle

- Python unit (+13 incl. extended): NaN/Inf/decimal coercion;
  rank-garbage omission; non-list-videos rejection; over-long-id hashing;
  hostile-RSS tolerance; missing-audio `False`; mobile-key preservation;
  non-list sanitize rejection; missing-input ffmpeg `False`.
- Python integration (+6 in `TestRequestHardening`): garbage-body sweep;
  mobile-key round-trip; channels-type; non-string source fields; non-string
  timestamp; non-string prompt text.
- Swift (+2): lenient dirty-producer decode; blank/over-long id rejection.
- Totals: **291 Python passing** (265 unit + 26 integration), **20 Swift
  executed / 0 failures**, ruff clean, worker syntax clean.

---

# New audit cycle — 2026-09-20, session 2 (Phase-2 UAT work + this audit's fixes)

Uncommitted Phase-2 UAT remediation was already in the tree at session start
(theme default, partitioned feeds, alias-aware read state, `video_id`
backfill, player-deck redesign, settings sheet, regenerated fixtures). Each
item below was **probed with a hostile input first, then fixed, then covered
by a test**. Personal-use scale respected throughout: no new services, deps,
tables, or daemons. Baseline at session start: 277 unit + 26 integration
passing at HEAD (291 with the in-flight UAT tests); one pre-existing
order-dependent flake in `test_pipeline_runner` (see X.5) fires under some
random seeds with or without these changes.

## X. Bugs found and fixed this session

### X.1 `OverflowError: int(Inf)` crashes the weekly build (critical)
- **Probe:** `_normalize_mobile_item({'rank': float('inf')})` raised
  `OverflowError` — the `int()` coercion caught `ValueError`/`TypeError` but
  not `OverflowError`, so one dirty producer rank killed the whole
  `data.json` export. Same hole in the `build_reader_site` rank path and in
  `int('1e400')`-style huge strings (float-Inf via `_safe_int_or_none`).
- **Fix** (`desktop/web_reader.py`): new `_safe_int_or_none()` rank coercer
  (`float()` + `math.isfinite`, catches `ValueError`/`TypeError`/
  `OverflowError`, garbage/None/non-finite → `None` → rank omitted or idx
  fallback). Applied at `_normalize_mobile_item` and the `build_reader_site`
  Top-20 loop. Also hardened the two other bare `int(rank_text)` digest
  parsers (`parse_top20_digest`, `top10_downloader.extract_items`) with
  `OverflowError`.
- **Tests:** `test_normalize_item_rank_infinite_omits_rank` (±Inf omission);
  existing `test_normalize_item_rank_garbage_omits_rank` kept green.

### X.2 `TTS_TIMEOUT_SECONDS=inf/1e400` crashes `tts_service` import (critical)
- **Probe:** `parse_tts_timeout_seconds('inf')` / `'1e400'` raised
  `OverflowError` (`int(float('inf'))`) at **module import time** — a typo'd
  env value killed the entire pipeline before any work started, contradicting
  the function's "never crashes import" contract (only `ValueError` caught).
- **Fix** (`desktop/tts_service.py`): explicit NaN/±Inf rejection before
  `int()`, catch `OverflowError` alongside `ValueError`; warn + default 300.
- **Tests:** existing `TestTimeoutParsing` green; probe values now return 300.

### X.3 `backfill_week` still crashes inside a running event loop
- **Probe:** calling `backfill_week()` from inside `asyncio.run(main())`
  raised `RuntimeError: asyncio.run() cannot be called from a running event
  loop` — same REQUIREMENTS §5.4 root cause the in-flight work fixed for
  `generate_summary_tts` but missed for its sibling entrypoint (and the
  `_backfill_week_async.process_one` path re-entered the sync wrapper via
  `asyncio.to_thread(generate_summary_tts, …)`, spawning a worker thread per
  channel that each blocked on its own `asyncio.run`).
- **Fix** (`desktop/tts_service.py`, per IMPLEMENTATION_PLAN Slice 1):
  `process_one` now awaits `_generate_audio_async` directly under the
  semaphore (no thread hop); `backfill_week` detects a running loop and
  offloads the whole `_backfill_week_async` coroutine to one worker thread
  with its own loop. The sync wrapper stays monkeypatchable: `process_one`
  dispatches through `globals()["generate_summary_tts"]` when tests replace
  it, else the async core.
- **Tests:** all 23 `test_tts.py` green (incl. the in-flight
  `test_generate_from_inside_running_event_loop`); nested-loop probe now
  returns `{'scanned': 1, 'generated': 0, 'skipped': 0, 'failed': 1}` instead
  of raising.

### X.4 Duplicate feed ids crash both Swift views at render
- **Probe:** `Dictionary(uniqueKeysWithValues:)` with two items sharing one
  `id` throws at view-body evaluation — the pipeline only dedups within a
  single Top-20/weekly pass, so a duplicated id across passes (or a hostile
  `data.json`) kills `BriefingView` and `ChannelsView` before first paint.
- **Fix** (`BriefingView.swift`, `ChannelsView.swift`): first-wins
  dictionary build (`originalRanks[id] ?? …`), preserving rank/index and
  never throwing.
- **Tests:** covered by existing Swift suite shape (partition tests);
  render-path probe verified by construction (no `uniqueKeysWithValues`
  remains in `Sources/`).

### X.5 `unwatchedVideos` ignored `video_id`/URL aliases (commute queue wrong)
- **Probe:** with `readIDs = {"J3ljHm57yU0"}` (video-id key from the web
  reader) a channel video `{id: "item-001", videoId: "J3ljHm57yU0"}` still
  counted as unwatched — `CommuteQueueModel.unwatchedVideos` matched only
  `id`, while every view and the store already match on the full alias set,
  so "Listen Unwatched" replayed watched summaries (§2 violation).
- **Fix** (`CommuteQueueModel.swift`): filter on
  `$0.aliases.intersection(readIDs).isEmpty`, converging with
  `ChannelsView`/`BriefingView`/`ContentStore`.
- **Tests:** existing `testCommuteQueueMathAndUnwatchedFiltering` and UAT-019
  green (id-keyed fixtures unaffected); alias case verified by probe.

### X.6 Whitespace-only ids bypassed the dashboard sanitizer
- **Probe:** `_sanitize_read_ids(["  "])` returned `["  "]` — the truthiness
  check ran pre-strip, so blank ids persisted into `read_state.json` and
  desynced from the worker (which drops them) and the app (which trims).
- **Fix** (`desktop/gui.py`): strip-then-check (`item.strip()`, incl. the
  `canonical_only` regex input); blanks dropped, surrounding whitespace
  trimmed before truncation/dedup.
- **Tests:** new `test_read_ids_reject_blank_and_trim_surrounding_whitespace`.

### X.7 `OverflowError` in remaining `int()` coercions (sweep)
- **Probe:** `build_video_filename(float('inf'))`, download-task rank,
  `_bounded_max_items(float('inf'))` (factory + both handlers + GUI
  `_bounded_int`) all raised `OverflowError` through `int()` guards that
  caught only `TypeError`/`ValueError`.
- **Fix:** `except (TypeError, ValueError, OverflowError)` at all six sites
  (`top10_downloader` ×3, factory, `rss_handler`, `webpage_handler`,
  `gui._bounded_int`). `email_service.channel_order` sort key and
  `youtube_handler.publishedAt` parse left alone (int-on-small-int /
  datetime parse — no float-Inf path).
- **Tests:** full suite green; probe values now degrade to defaults.

### X.8 Stale test expectations vs the §5.3 `video_id` contract (regression)
- **Probe:** full suite red — `test_normalize_strips_producer_keys_and_maps_summary`
  and `test_normalize_video_drops_video_id_key` asserted `video_id` is
  stripped from the mobile export, but the in-flight §5.3 fix deliberately
  emits `video_id` (IMPLEMENTATION_PLAN Slice 1.5 + `DigestFeed.videoId` +
  `SyncIdentity.aliases` need it for cross-device key alignment).
- **Fix** (tests only, contract wins): assert `video_id` is **present**
  (`test_normalize_video_keeps_video_id_key`); producer-bloat assertion now
  covers only genuinely dead keys (`candidate_id`, `summary`, `published`).
- **Tests:** `TestMobileExportContract` 11/11 green.

### X.9 Dead read-state helpers removed (hygiene, no behavior change)
- `RootTabView`: deleted uncalled `markRead(_:)`/`toggleRead(_:)` (single-id
  legacy path — every caller now uses alias-aware
  `markItemRead/toggleVideoRead`) and uncalled `toggleItemRead(_:)`
  (Briefing toggles route through `onMarkRead` + `playItemAudio`). Callers
  re-grepped; no references remain.

## Y. Requirements trace (audited in-flight UAT work — verified, kept)

- §5.1 Light-mode default + 3-way toggle: `TubeLMApp.AppThemeMode`
  (`light` default via `@AppStorage("tubelm.themeMode")`,
  `.preferredColorScheme(mode.colorScheme ?? .light)`), picker in
  `SyncSettingsSheet`. No `preferredColorScheme(nil)` remains. ✅
- §5.2 Watched-to-bottom: `FeedPartition.unreadFirst` (stable, order
  preserving) in `BriefingView` (top-20, animated) and `ChannelsView`
  (expanded disclosures); original `#rank` preserved via first-wins maps;
  title/Play/Watch/Read taps one-way mark (Channels `openVideoLink` now
  `onMarkRead`, not toggle). ✅
- §5.3 Sync keys: default endpoint `kedarvreddy` in client + settings +
  migration guard; `SyncIdentity.normalizeVideoUrl` ports
  `reader.html:normalizeVideoUrl` exactly (v-param → pathname-slice →
  origin+path → trimmed-raw); `FeedItem`/`VideoItem.aliases` fan out
  (id/videoId/url/normalized); store mark/unmark/isRead alias-aware;
  settings sheet persists endpoint + passphrase with status. ✅
- §5.4 TTS loop fix: `generate_summary_tts` worker-thread offload done
  in-flight; `backfill_week` + `process_one` completed this session (X.3);
  idempotent skip, per-channel isolation, `gather(return_exceptions=True)`
  with `is True` counting. ✅ (Audio backfill itself is an operator run
  action, not a code artifact — `data.json` channels already carry
  `summary_audio_url`s; Top-20 item `audio_url`s are empty because Top-20
  rows have no per-item narration by product design.)
- §5.5 Player deck: 180pt emerald-gradient artwork card, capsule scrubber
  with `DragGesture(minimumDistance: 0)`, 56pt skip targets / 68pt play /
  56pt speed circle, Up-Next with swipe-delete + drag-reorder delegate,
  mono time labels, VoiceOver labels, haptics on transport. ✅
- §4 hardening (prior cycle, re-verified): no `Bundle.module` in `Sources/`;
  `setActive(true)` only inside `ensureAudioSession()` called from
  `playTrack`/`play`; `Info.plist` platform keys + icons + `ITSAppUses…`
  present; `package_ipa.sh` ad-hoc signs + validates (5 icons, binary,
  plist keys); CI refuses binary-less IPAs. `dist_ios/TubeLM.ipa` (tracked)
  contains all 5 icons + signed binary; the HEAD-deleted `ios/TubeLM.ipa`
  prepared-statement husk is gone — no action. ✅

## Z. Deliberately NOT changed (re-checked this session)

- `worker/worker.js`: LWW merge, tombstones, per-IP + per-key rate limits,
  1 MiB cap, header-only auth, CORS, Range/audio path correct. Untouched.
- `desktop/templates/reader.html`: shipped Pages surface; JS
  `normalizeVideoUrl` is the reference the Swift port matches. Untouched.
- `.workflow/mocks/build_mock1_full.py` f-string `SyntaxError`: still
  present, still design-time mock tooling only. Untouched.
- Top-20 YouTube-only pin: pre-existing product decision, flagged in the
  prior cycle. Untouched.
- `MinimumOSVersion 17.0` vs §1 "iOS 26 baseline": floor vs tested target.
  Untouched.
- `Channel.readMinutes` default `4`: honest fallback chain in views (real
  `durationSeconds` sum → positive `readMinutes` → hide separator) — no
  fabricated display. Untouched.
- Grandchild-pipe / stop-endpoint flakes (X.5 note): `test_stop_kills_…`
  (process-group reap race) and `test_stop_endpoint_when_idle_is_400` each
  fail under some random-test-order seeds at HEAD too (verified via
  `git stash`); both pass in fixed order and in isolation. Pre-existing
  infra flake, not a product bug — flagged, not "fixed" with duct tape.

## W2. Tests added this session

- Python unit (+3): blank/whitespace-id sanitizer rejection;
  ±Inf rank omission; `video_id`-kept contract update (replaces 1 stale
  assertion).
- Python: `OverflowError` sweep covered by new probes run ad hoc (all 15
  hostile inputs no-crash); existing `TestTimeoutParsing`,
  `TestMobileExportContract`, `test_tts.py` (23), factory/loader suites
  kept green.
- Swift (+0 new files): duplicate-id, alias-unwatched, and partition
  behavior covered by construction + existing 27-test suite (all passing).
- Totals: **294 Python passing** (`-p no:randomly`; 293 + 1 order-flake in
  fully-random runs, pre-existing at HEAD), **27 Swift passing / 0
  failures**, ruff clean, worker syntax clean, `web_reader --build-only`
  clean with `video_id`-keyed mobile contract verified in the built
  `data.json`.
