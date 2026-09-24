# Frontier Plan Review — TubeLM iOS Implementation Plan

Source: `.workflow/REQUIREMENTS.md` + `.workflow/IMPLEMENTATION_PLAN.md`
Date: 2026-09-19
Prior review: `.workflow/FRONTIER_REQUIREMENTS_REVIEW.md` (Q1–Q5 still open)

Scale anchor: single-person personal use, LiveContainer on iOS, 7–8 opens/week on
Singapore transit, 2-week rolling retention. Anything implying multi-tenant auth,
a maintained backend, or push/background daemons violates the anchor.

---

## P0-1 — Schema triple divergence (blocker, fix before any Swift)

Three shapes disagree and no `data.json` exporter exists yet:

- `IMPLEMENTATION_PLAN.md` Phase 1 proposes
  `{version, built_at, read_ids, weeks: {current: {run_date, top20: {items}, channels}}}`
  (`top20` wrapped in an object, no `prev` week).
- `desktop/web_reader.py:1003` builds in-memory `site_data` as
  `{version: "4.0.0", built_at, read_ids, weeks: {current, prev}}` with
  `top20` as a **bare object** `{items, candidate_count}` — but never writes it
  to disk. `grep data\.json desktop/` returns zero hits. Phase 1 is greenfield,
  not a hook.
- `.workflow/mocks/mock_data.json` is **flat**:
  `{run_date, channels[23], top20, ...}` — no `version`, no `weeks` wrapper.
  It is also 508 KB, which is fine for a JSON fetch but already proves
  full-HTML-per-channel payloads are heavy.
- `REQUIREMENTS.md` §2 says `schema_version: 1`; the plan says `version: 4.0.0`.
  Pick one field name.

Consequence: Phase 2 verification ("decode `mock_data.json`") validates Swift
models against a shape the real pipeline will never emit. Any `Codable`
work done now churns.

Recommendation:
1. Lock one canonical export shape in Phase 1 first (suggest
   `{schema_version: 1, built_at, run_date, top20: {items}, channels[]}`,
   flat like the mock — the `weeks.current/prev` nesting buys nothing for a
   phone that only shows the current week; keep `prev` server-side only).
2. Regenerate `mock_data.json` from the real builder output, never by hand.
3. Only then write `DigestFeed.swift`. Tolerant reader per prior Q1
   (`decodeIfPresent` + defaults, ignore unknown keys, validate-then-atomic-swap).

## P0-2 — Sync contract mismatch + unresolved anchor conflict

- `REQUIREMENTS.md` §2 and plan Phase 2 specify
  `POST .../api/sync` with `Bearer <token>`. `worker/worker.js` exposes no
  `/api/sync` route: sync is `GET/POST /` (root) plus `/tubelm/audio/*` for
  the R2 CDN, with key derivation `sync/<sha256>.json` and a `SyncCoordinator`
  Durable Object. The plan's endpoint is wrong.
- Prior review Q4 recommends local-only + manual export/import and calls
  auto-sync anchor-violating. But the worker already exists, is deployed
  (`tubelm-sync`, R2 binding `SYNC_BUCKET`), and has passing contract tests
  (`desktop/tests/unit/test_cross_device_sync.py`, CRDT LWW merge). The plan
  ignores that decision entirely and re-specifies event-driven auto-sync on
  every mutation.

Recommendation: make an explicit decision before Phase 2 code, two options:
- (a) Adopt the existing worker as canonical: fix the plan to `GET/POST /`
  with `Authorization: Bearer` / `X-Sync-Key`, reuse the LWW `item_states`
  merge, debounce pushes (not every keystroke-mutation), and document the
  passphrase as a credential. This keeps PWA + iOS in one sync universe.
- (b) Reject it per Q4 and delete sync from the iOS v1 scope (local
  `read_state` + Share Sheet export). Then also remove sync from
  REQUIREMENTS §2 — do not ship a half-wired `SyncService.swift`.

Either is coherent; the current state (worker does CRDT, review says no
server, plan says new endpoint) is not.

## P1-1 — LiveContainer audio: pick one engine, verify background early

- REQUIREMENTS says `AVAudioPlayer`; plan Phase 3 says
  `AVPlayer` / `AVAudioPlayer`. These are not interchangeable:
  `AVAudioPlayer` is local-files-only, `AVPlayer` is the remote-streaming
  engine. For Pages/R2 URLs with transparent disk caching, it must be
  `AVPlayer` (+ `AVURLAsset` cache layer). Say so explicitly.
- `UIBackgroundModes: [audio]` + `MPRemoteCommandCenter` + lockscreen info
  inside a LiveContainer guest is unproven. LiveContainer gives no
  background-daemon or entitlement guarantees. Phase 5 (packaging/CI) is
  sequenced last — if the `.ipa` audio-background or import flow fails, all
  Phase 3–4 work is stranded.

Recommendation: move a packaging spike to Phase 0 — hand-build a minimal
audio-playing `.ipa`, import into LiveContainer on the iPhone 16 target,
confirm foreground + lockscreen/headphone controls. Only then invest in the
queue engine. Defer `BGTaskScheduler`/background prefetch entirely
(foreground single-flight refresh only, per prior Q5).

## P1-2 — `swift test` on Linux will not compile as specified

Plan Phase 2 verification runs `swift test --package-path ios` on Linux
against `Models/`, `Services/`, and by implication the whole target. There
is no `ios/` directory yet, and `Audio/` + `Views/` import `AVFoundation`,
`MediaPlayer`, `SwiftUI` — none of which exist on Linux. One target importing
those anywhere breaks `swift test` everywhere.

Recommendation: two targets from day one — `TubeLMCore` (pure `Codable`
models, `ContentStore`, queue math, merge logic; Linux-testable) and
`TubeLMApp` (SwiftUI/`AVPlayer`/`MediaPlayer`, macOS/Xcode-only). Phase 2
tests target `TubeLMCore` only. Gate Apple-only imports with
`#canImport` where shared types leak.

## P1-3 — Dependency sequencing risks

1. Phase 1 → Phase 2 is inverted in practice: Phase 2 can start file
   scaffolding but must not freeze `Codable` structs until the Phase 1 export
   lands and the mock is regenerated from it.
2. Queue identity key is undefined. `video_id` is `""` for all RSS items
   (verified in mock: MIT Tech Review entries). If `CommuteQueue` keys on
   `video_id`, RSS items collapse/dedupe to nothing. Key must be a stable
   synthetic id (`url` fallback, sanitized) shared by `AppState`,
   `read_ids`, queue, and bookmarks. Define it in Phase 2, consume in Phase 3.
3. Publish ordering is unspecified and the pipeline makes it worse:
   `build_reader_site` copies audio into `site/audio/` interleaved with HTML
   rendering, and `deploy_to_gh_pages` refuses any file > 5 MB while the
   R2-active path deletes large `site/audio` files post-build. Specify:
   audio assets first, `data.json` last, single atomic deploy; iOS treats a
   feed referencing missing audio as valid-text/degraded-audio (prior Q3),
   never a failed refresh.
4. `read_ids` bound: web caps at `MAX_READ_IDS=5000` (`web_reader.py:53`);
   the worker caps at 5000 (`worker.js:24`). The iOS plan states no cap —
   add the same 5000 LRU bound to `AppState`/`ContentStore` now, not later.

## P2 — Over-engineering cuts for a 1-user commuter app

- Typography: plan mandates JetBrains Mono for ranks/durations. A third-party
  font inside a LiveContainer bundle adds packaging/licensing weight for zero
  reader value. Use SF Mono / system `.monospaced`.
- Playback speeds 1.0/1.25/1.5/2.0 + reorderable queue + haptics + full
  search + category pills + expandable disclosures + markdown renderer +
  theme tokens is a large v1 surface for 7–8 opens/week. Suggested MVP:
  Briefing feed + Channels read-only + mini-player + `+ Queue` add/remove +
  1.0x/1.25x only (REQUIREMENTS already says 1.25x). Defer reorder,
  multi-speed, haptics to v1.1 after the LiveContainer spike proves the shell.
- `ContentStore` re-specifies atomic writes + ETag tracking from scratch;
  the proven semantics already exist (`os.replace` tmp-swap in
  `sync_audio_manifest`, SW stale-while-revalidate in generated `sw.js`).
  Reuse the pattern, don't redesign it.

## P2 — Retention/GC gap (bookmarks vs 14-day purge)

`PROJECT.md` + `purge_old_digests_and_audio` enforce a strict 14-day purge
of digests, audio, and stale `read_ids`. The iOS plan promises "unlimited"
text bookmarks and a persistent queue with no eviction rule and a single
`Documents/cache.json`. Without a pin-exempt split, the next weekly refresh
orphans queued/bookmarked Week-1 items (prior Q2).

Recommendation: `Documents/pinned/` (user-saved, exempt, capped e.g.
50 items) vs `Documents/cache/` (rolling current-week, evictable); remote
purge never deletes local pins. Add a storage-usage row when the cap exists.

## Verification commands in the plan are currently unrunnable

- `from desktop.web_reader import build_web_reader` — no such symbol; the
  function is `build_reader_site`. The assertion also checks
  `paths.get_site_dir() / "data.json"`, which nothing writes today.
- `swift test --package-path ios` — no `ios/` directory exists.
- Mock compatibility check has no runner (script or XCTest named).

Fix when implementing Phase 1/2: export-then-decode roundtrip test
(python writes `data.json` → swift `TubeLMCore` decodes the exact artifact),
not mock-only decoding.

---

## Suggested phase reorder

1. **Phase 0 (spike):** minimal `.ipa` → LiveContainer import + foreground
   audio + lockscreen controls go/no-go.
2. **Phase 1 (contract):** lock `data.json` shape, atomic write +
   publish-ordering, regenerate mock from builder output.
3. **Phase 2 (core):** `TubeLMCore` models + store + queue math + 5000-cap
   `read_ids`, Linux-tested; sync decision (a)/(b) above recorded.
4. **Phase 3–4 (app):** audio engine + SwiftUI, Xcode-only, against the
   frozen contract.
5. **Phase 5 (CI):** packaging automation only after manual import works.

## Decisions needed (blocking)

1. Canonical `data.json` shape + field name (`schema_version` vs `version`);
   flat (mock-like) vs `weeks.current` nesting.
2. Sync: adopt existing worker root-endpoint CRDT (a) or local-only v1 (b);
   fix or remove `/api/sync` + every-mutation auto-push wording.
3. Audio engine: `AVPlayer` confirmed; background-audio expectation inside
   LiveContainer confirmed or descoped.
4. Retention: pin-exempt + caps (50 items / 500 MB suggested) accepted.
5. Typographic token: system mono instead of JetBrains Mono.

---

## Phase 6 review — App Icon & Launch Crash (code-verified 2026-09-20)

Code-verified status of Phase 6 prerequisites (read against `ios/`,
`scripts/`, `.github/workflows/build-ios.yml`, not spec-read):

- Icons: DONE on disk — all 5 PNGs in `ios/TubeLM/` with correct dimensions
  (1024, 120, 180, 152, 167) and RGB, no alpha. Generator
  `scripts/generate_icons.py` is deterministic (Pillow LANCZOS from 2048 master).
- Icons: OPEN on declaration — `ios/TubeLM/Info.plist` has zero
  `CFBundleIcons*` keys; the device-IPA CI step and `scripts/package_ipa.sh`
  never stage icons. Files present + undeclared = still blank icon.
  Asset generation without plist/packaging is unverifiable alone.
- Audio: OPEN — `AudioPlayerManager.init()` still calls `setupAudioSession()`
  → `setCategory(.playback)` + `setActive(true)`; `RootTabView` instantiates
  `.shared` at view init, so eager activation fires at launch. Exactly what
  §4.2.2 bans.
- Cache: HALF-OPEN — `#if SWIFT_PACKAGE` guard + `Bundle.main` fallback exist,
  but `loadCachedFeed()` still `throws` when `feed.json` exists-but-corrupt
  (`ContentStore.swift:64-67`, throwing `Data(contentsOf:)` + `decode`).
  Caller uses `try?`, so no crash — but the result is silent blank rather
  than healed fallback. This is the residual risk Q2 flagged.
- Signing: OPEN — simulator step runs `codesign -s - --force --deep`; the
  device IPA step and `package_ipa.sh` run no signing and assert nothing.

### P6-1 — Split Phase 6 into independently verifiable slices (sequencing risk)

Phase 6 bundles four independent failure modes (undeclared icons, eager
audio, throwing cache, unsigned binary) under one heading with one exit. If
AMFI kills the binary, the icon fix cannot even be observed — slices must
order so each is verifiable before the next:

1. Plist + icon staging (no code risk; verifiable by unzip + PlistBuddy).
2. Cache never-throw (pure `TubeLMCore`, Linux-testable via `swift test`).
3. Audio defer (needs device/simulator ear-test; see P6-3).
4. Signing + CI gate last (only meaningful once 1–3 land).

Recommendation: record four sub-exits, not one Phase 6 checkbox.

### P6-2 — Icon declaration is the actual fix, not generation (pitfall)

Generation is done; the defect is declaration + staging. Concrete gaps:

- `Info.plist` needs `CFBundleIcons` (+ `CFBundleIcons~ipad`),
  `CFBundleIconFiles` (basenames without extension), plus platform keys
  `CFBundleSupportedPlatforms=[iPhoneOS]`, `MinimumOSVersion`,
  `CFBundleSignature` (`CFBundlePackageType` already present).
- Spec drift: REQUIREMENTS §4.1 names 4 PNGs, plan Phase 6 names 5 (adds
  83.5@2x). Disk has 5. Lock the plan's 5-file set as canonical and fix
  §4.1 wording.
- Staging duplication: CI's "Package LiveContainer IPA" step inlines
  `cp Info.plist` + `cp mock_data.json` + `find binary` instead of calling
  `scripts/package_ipa.sh`. Fixing the script alone leaves CI broken. Unify:
  CI calls the script (single packaging path), or both updated in lockstep.
- LiveContainer caches icons aggressively — acceptance must say delete +
  reimport, not overwrite, or a fixed build reports "still blank."

Do NOT introduce an asset catalog (`.car`) for v1 — loose PNGs + plist keys
are the correct LiveContainer packaging; `.car` is over-engineering here.

### P6-3 — Audio defer must move category too, and play() must ensure it (pitfall)

Phase 6 wording ("defer `setActive(true)` to `play()`/`playTrack()`") is
directionally right but under-specified:

- `setupRemoteCommands()` in `init()` is harmless (no session activation) —
  keep it there so lockscreen controls register at launch.
- `setCategory(.playback, …)` must move WITH `setActive(true)` into a shared
  `ensureAudioSession()` called at the top of `play()` and `playTrack()`
  (playable branch only). Deleting the init call without adding the play-time
  call silently breaks background audio instead of fixing launch.
- `play()` with `player==nil` currently sets `isPlaying=true` with nothing to
  play; after the move it should no-op or reuse `playTrack`'s honest-idle
  path — otherwise remote-command "play" at launch activates the session with
  no audio, recreating the conflict in a new shape.
- Verification needs an ear-test, not just "launches": simctl launch → tap
  play → background the app → audio continues + lockscreen title correct.
  "No crash" alone proves nothing about the audio contract.

### P6-4 — Cache path still throws on the exact tunnel case (pitfall)

A truncated download on flaky Wi-Fi poisoning the next cold start is the
field case Q2 named. Fix within `TubeLMCore` so it stays Linux-testable:

- Never-throw launch path: cache miss/corrupt → `Bundle.main` candidates →
  staged empty state. Quarantine the corrupt file
  (`feed.json.corrupt.<ts>`) instead of deleting, so the failure stays
  diagnosable.
- Validate-then-save on the seed path: a bundled seed failing
  `schema_version`/non-empty-items validation must NOT be written into
  `feed.json` (current `try? saveFeed(feed)` persists whatever decoded).
- Add a Linux regression test: garbage in `feed.json` → returns bundled
  seed (or nil), never throws. Update `RootTabView` to the non-throwing call
  and drop `try?` so a future `throws` reintroduction is a compile error,
  not a silent blank.
- "Staged empty state" wording in Phase 6 action 2 is stale — the empty
  state already exists (audit §H). Reference it; do not re-specify.

### P6-5 — Signing: pick codesign, gate it, keep ldid as footnote (over-engineering cut)

- CI runs on `macos-15` where `codesign -s - --force --deep` works — that is
  the v1 path for BOTH simulator and device steps. `ldid -S` is for
  on-device resigning workflows that do not exist in this repo; naming both
  as equals invites "either is fine" drift where the device step gets
  neither (current state). Spec: `codesign` mandatory, `ldid` footnote only.
- Proportionate gate (shell function in `package_ipa.sh`, called by CI — not
  manual): assert 5 PNGs present with size check, `PlistBuddy` print of icon
  + platform keys, `codesign -dv` success,
  `otool -l | grep LC_CODE_SIGNATURE`. Fail closed. This is NOT
  over-engineering — it is the §4 exit criteria Q1 asked for.
- Also assert the binary is the device (`arm64-apple-ios` release) build, not
  the simulator slice — a signed simulator binary in the device IPA passes a
  naive signature check and still dies on device.

### Phase 6 acceptance gates (concrete)

```bash
# 1. Icons declared + staged
/usr/libexec/PlistBuddy -c "Print :CFBundleIcons" Payload/TubeLM.app/Info.plist
unzip -l TubeLM.ipa | grep -E "AppIcon.*\.png"   # expect 5 entries
# 2. Fresh-install proof: delete + reimport into LiveContainer (icon cache), launch, no crash
# 3. Audio: tap play -> background -> audio continues, lockscreen title correct
# 4. Corrupt-cache drill: garbage into Documents/cache/feed.json -> relaunch -> seed/empty state, no crash
```

### Decisions needed (Phase 6)

1. Lock 5-icon set; correct §4.1 "4 PNGs" wording.
2. `MinimumOSVersion` value (17.0 floor per `Package.swift` `.iOS(.v17)` vs
   §1 iOS 26 baseline) — state floor + tested baseline explicitly.
3. CI calls `package_ipa.sh` (single packaging path) vs dual maintenance —
   pick single path.
4. Confirm `ensureAudioSession()`-at-play design and the background-audio
   ear-test as exit criteria.

---

## Phase 2 UAT Remediation review — current IMPLEMENTATION_PLAN.md (code-verified 2026-09-20)

Source: working-tree `REQUIREMENTS.md` §5 + `IMPLEMENTATION_PLAN.md` (Phases 1–4 + verification).
Code verified against `ios/Sources`, `ios/Package.swift`, `ios/Tests`,
`desktop/tts_service.py`, `desktop/web_reader.py`, `desktop/templates/reader.html`, `worker/worker.js`.
Status: **none of §5.1–§5.5 is implemented** (`.preferredColorScheme(nil)`,
index-derived rank, old worker host ×2, bare `asyncio.run`, 100pt deck — all confirmed below).
Prior P0-1 schema divergence is **resolved** (export exists, models match — do not re-litigate);
old Phase 6 audio/cache hardening has **landed** in tree (do not re-spec; do not regress).

Scale anchor (unchanged): single-person personal use, LiveContainer, 7–8 opens/week
on Singapore transit. Anything needing maintained server logic, new dependencies,
or background daemons violates the anchor.

### P0-1 — Phase 1 alias fan-out is under-scoped: no `video_id` in the mobile contract, 5+ call sites missed

- `FeedItem`/`VideoItem` carry **no `video_id` field** (`DigestFeed.swift:71-148, 233-305`).
  The mobile projections drop it: `_normalize_mobile_item` (`web_reader.py:340-368`)
  and `_normalize_mobile_video` (`:371-384`) emit only `id` (= `_make_item_id` output),
  `url`, `audio_url`. So `markItemRead(id:videoId:url:)` has no `videoId` to fan out
  unless (a) the pipeline adds `video_id` to the export, or (b) Swift derives the
  YouTube id from the URL. Decide before coding — Phase 1 step 2 is unimplementable as written.
- Normalization must be an **exact port** of `normalizeVideoUrl` (`reader.html:2245-2257`):
  YouTube host → `v` param else `pathname.slice(1)`; otherwise `origin + pathname`;
  catch → trimmed raw; empty → `''`. JS does NOT lowercase, trim slashes, or strip UTM —
  match it, don't "improve" it. Needs a vector test (youtube watch / youtu.be / shorts /
  RSS article / trailing-slash / query-param pairs).
- Single-key `contains` is load-bearing in **six places**, plan lists three files:
  `BriefingView.swift:54`, `ChannelsView.swift:62,177`, `RootTabView.swift:348,352`,
  `CommuteQueueModel.swift:67-68,82` (+ tests). Remote-merged keys make this worse:
  `applyRemoteStates` rebuilds `readIDs` from exact worker keys, so a web-written
  normalized key never matches `contains(item.id)`. Either expand the persisted set with
  aliases on every mark/merge (views stay `contains`-based), or replace every check with
  an any-alias helper. Pick one; do it everywhere or the UI and store diverge until relaunch.
- Recommendation: new Core `SyncIdentity.swift` (`normalize(_:)`, `aliases(id:url:)`,
  `isRead(item:readIDs:)`), alias-aware `mark/unmark/isRead` in `ContentStore`,
  wire all six call sites, unit-test on Linux. LRU amplification (3–4 keys per mark
  against the 5000 cap → ~1250 effective items) is acceptable for one user — state it,
  don't solve it. Partial alias eviction only ever fails toward "still read," never data loss.

### P0-2 — Sync hardening gaps: insecure storage wording, no migration, debounce/caps unmentioned

- "Persisted securely in `UserDefaults` / `@AppStorage`" is a contradiction:
  `UserDefaults` is plaintext (current `SyncDefaults.keyKey`, `RootTabView.swift:7`).
  The worker treats the passphrase as a credential (`worker.js:10-17`, min 16 chars).
  Use Keychain directly (~30 lines of SecItem, no new dependency) — this is the prior Q3
  decision; the plan regresses it. Fix the wording, not just the code.
- Endpoint changes in **two** places (`CloudflareSyncClient.swift:101`,
  `RootTabView.swift:8`) with no migration: the old Worker's Durable-Object namespace
  holds existing state. Ship one-time fallback (try new, on network-error try old once,
  persist the winner) so history isn't stranded.
- Confirm the split-brain before locking: worker moves `vkr1729 → kedarvreddy` but the feed
  host stays `vkr1729.github.io` (`RootTabView.swift:251`, `AudioPlayerManager.swift:80`).
  If the GitHub account migrated too, feed + audio 404 — verify, don't assume.
- "Event-driven sync on every mutation" must not kill the existing **1.5 s debounce**
  (`RootTabView.swift:305-336`): per-tap pushes hit the 60/240-per-window rate limits
  (`worker.js:29-31`). State debounce explicitly in Phase 1.
- "Unlimited bookmarks" contradicts the worker: `MAX_BOOKMARKS = 1000`, 1 MiB payload cap
  (`worker.js:23,27`), and the push encodes **all** bookmarks with no 413 handling
  (`CloudflareSyncClient.swift:190-198`). Sync most-recent ~200, keep the rest local-only
  with a Settings note; never fail the whole push on cap.

### P0-3 — Phase 3 tap semantics + testability: toggle-on-title bug, Play-mark scope, partition belongs in Core

- `ChannelsView.openVideoLink` (`:292-301`) calls `onToggleRead` — tapping an already-read
  title **unmarks** it. Must be mark-only like `BriefingView.openLink` (`:181-190`).
  Plan's "auto-mark on title tap" requires this one-line fix; without it the partition
  thrashes items back to the top.
- Scope "auto-mark on Play": item-level Play → mark that `FeedItem` (add to
  `RootTabView.playItemAudio`, `:387-389`, currently no mark). Channel Listen → mark
  **nothing** (it plays the summary; the unwatched filter depends on videos staying unread).
- Partition helper must live in **Core**, not inline in views: pure
  `FeedPartition.unreadFirst(items:isRead:)` + Linux tests (order stability, rank
  preservation, empty/all-read edges). Plan's view-local `partitionedItems` is Apple-only
  and untestable — and Phase 3 can only work if it consumes the Phase 1 any-alias `isRead`.
  Record the Phase 1 → Phase 3 dependency explicitly.

### P1-1 — TTS wrapper needs exact layering + canonical field + honest test shape

- Wrapper: `try asyncio.get_running_loop()` → `RuntimeError` means no loop → `asyncio.run`
  inline; else run the coroutine on a dedicated thread with its own loop. Close the executor
  (context manager or module-level single thread) — don't leak a thread per channel × 23.
  Never raise; pipeline degrades to `False` as today.
- `_backfill_week_async` awaiting the async core directly under the semaphore (plan step 2)
  is correct; add `return_exceptions=True` or per-channel try so one raising channel can't
  abort the week (`gather(*tasks)`, `tts_service.py:246`).
- Canonical field: channel summary audio is `summary_audio_url` (build `:1088-1097`),
  full audio is `audio_url` (`:1098-1114`); app precedence already
  `summaryAudioUrl ?? audioUrl`. Plan step 5 should say "verify `summary_audio_url`
  for 2026-09-18" — generic "`audio_url` fields" will verify the wrong key.
  Empty `FeedItem.audio_url` on top-20 items → honest idle, not a bug.
- Ordering in the plan is right (backfill CLI → rebuild `data.json`) because
  `web_reader.py:1079` skips synthesis under test env — say why so nobody "optimizes"
  the order. Idempotent backfill (skip non-empty MP3 unless `--force`) is already in
  `_generate_audio_async:116` — keep, don't re-spec.
- Tests: async-context test with mocked `edge_tts.Communicate.save` (no network);
  plus "async backfill never calls the sync wrapper" (monkeypatch `generate_summary_tts`
  to raise, await `_backfill_week_async` directly). Backfill idempotency is already covered
  (`test_tts.py:112-139`).

### P1-2 — Theme slice: single source of truth, no rename churn, measurable bars

- One `@AppStorage("tubelm.themeMode")` owner at the `TubeLMApp` root
  (currently `.preferredColorScheme(nil)`, `TubeLMApp.swift:11`); don't init two defaults
  that can diverge. Keep the `SyncSettingsSheet` name — add a Theme section instead of
  renaming to `AppSettingsSheet` (rename churn, zero behavior gain).
- Bars: spot-check accent `#15803d` body text on off-white cards, `accentBadgeText` on
  `accentBadge`, `.primary` on `whyBackgroundLight`; smoke Dark mode once (Briefing scroll
  + one expanded channel + Deck). Dark-host launch flash under LiveContainer is
  known-acceptable — note it, don't chase it.

### P1-3 — Partition details: prefix order, animation yank, directory order, queue ephemerality

- Partition the full array **then** `prefix(20)` — one line in the plan removes the ambiguity.
- Animate the mark only in Briefing (`withAnimation(.spring…)`); inner channel lists
  non-animated (avoids scroll yank inside expanded cells). Confirm channel directory order
  stays alphabetical/searchable — only videos *within* an expanded channel partition.
- Queue is **local-ephemeral**: the sync payload has no queue field
  (`SyncPayload`, `CloudflareSyncClient.swift:6-34`) — `enqueueQueueItem` triggers a push
  of read/bookmark state only. Don't imply the queue syncs; don't add queue sync (anchor).

### P1-4 — Deck slice: reorder implementation choice, a11y, ear-test regression

- `List` + `onMove` + `EditMode` restyles rows (insets/separators) inside a custom sheet.
  Either accept List styling for the Up Next section only, or keep `VStack` + xmark delete +
  explicit move controls. Pick one before coding — don't ship drag-drop *and* EditMode.
  (Current `.onDrag`/`.onDrop` + `QueueDropDelegate` is the desktop idiom; it goes either way.)
- Keep xmark delete regardless; add VoiceOver labels on play/skips/speed/scrubber
  (scrubber as adjustable). Time labels: elapsed + duration (current) is fine —
  don't churn to remaining-time unless the owner asks.
- Regression gate: background-audio ear-test after restyle (UAT SEC-10–13 already covers it;
  reference, don't duplicate). `seek(to:)` NaN-clamping is already safe
  (`AudioPlayerManager.swift:139-147`).

### P2 — Over-engineering: plan is already lean; hold the line

No `hideSeen` toggle, no channel re-sort, no server-side normalization, no remote artwork,
no custom token system, no new dependencies (Keychain = SecItem directly, scrubber = SwiftUI
gesture). Four speeds already exist — keep. Nothing to cut; the risk is scope creep
during Phase 4 polish, not the plan.

### Suggested slice order (dependency-safe)

1. **Pipeline slice (parallel day 0):** TTS wrapper fix + test → backfill 2026-09-18 →
   rebuild `data.json` → verify `summary_audio_url`. Unblocks all audio acceptance.
2. **Core slice:** `SyncIdentity` + `ContentStore` aliases + `FeedPartition` + Linux tests green.
   Decide `video_id`-in-export vs derive-only first (recommend: add optional `video_id` to
   both mobile projections — 6 lines, tolerant decode — or explicitly derive-only; either
   unblocks Phase 1 step 2).
3. **App slice A:** RootTabView wiring (endpoint + fallback, Keychain, 3-state status enum,
   mark-not-toggle, debounce intact) + theme section.
4. **App slice B:** views partition + `item.rank` badges + title-tap fix, against frozen Core.
5. **Deck slice last:** pure UI + manual acceptance + background-audio regression.
6. **Docs cleanup (non-blocking):** REQUIREMENTS §4.1 says "4 PNGs," canonical set is 5 —
   correct the wording when touching the file anyway.

### Verification additions (append to plan §3)

- Automated: normalization vector test; alias fan-out roundtrip
  (mark by `id` → read by `url`/`norm`, and reverse); partition stability test;
  LRU-with-aliases test; TTS async-context test (mocked, no network).
  Existing `cd ios && swift test` / `pytest test_tts.py` commands are valid — keep them.
- Manual (add): Keychain persistence across reinstall (passphrase survives reinstall,
  or documented otherwise); endpoint fallback (airplane-toggle drill against old host);
  413-cap behavior (badge shows Error, no push loop); title-tap on read item stays read;
  channel Listen leaves videos unread; System theme under dark host; Deck reorder +
  swipe-delete + 56pt audit + background-audio regression (link UAT SEC-10–13, don't copy).
- Negative controls already in `UAT_PLAN.md` (corrupt cache, empty cache, unplayable item) —
  link them; the plan's 5-item checklist alone is insufficient exit criteria.

### Decisions needed (blocking Phase 1/3)

1. `video_id` in mobile export (add optional field) vs derive-only in Swift.
2. Keychain (recommend) vs UserDefaults for the passphrase.
3. Endpoint fallback migration (recommend try-new-then-old-once, persist winner).
4. Bookmark sync cap (recommend most-recent ~200 synced, rest local-only + note).
5. Partition-in-Core + mark-not-toggle + channel-Play-marks-nothing (recommend all three).
6. Deck reorder primitive: `List`/`EditMode` vs move controls (recommend move controls
   unless List styling is accepted for the section).
7. Feed-host account check: is `vkr1729.github.io` staying while the worker moves?

---

## Remediation plan review — current IMPLEMENTATION_PLAN.md (code-verified 2026-09-24)

Source: working-tree `.workflow/REQUIREMENTS.md` (§§1–4) + `.workflow/IMPLEMENTATION_PLAN.md`
(Slices 1–5 + verification + contingency). Code verified against `desktop/paths.py`,
`desktop/web_reader.py`, `desktop/top10_service.py`, `desktop/main.py`,
`desktop/email_service.py`, `desktop/templates/reader.html`,
`desktop/templates/top10_digest.html`, `desktop/scripts/`, `desktop/tests/unit/`,
`ios/Sources`, `.github/workflows/`.
Prior sections of this file cover the superseded iOS-build plan; they stand except where
noted below (schema divergence is resolved — `data.json` export exists at
`web_reader.py:1209-1258` with `schema_version: 1`; do not re-litigate).

Scale anchor (unchanged): single-person personal use. No new dependencies, no server
logic changes, no background daemons.

### P0-1 — Slice 1 regex contradicts REQUIREMENTS; one call site is inverted

- REQUIREMENTS §2.A mandates `r".*_TubeLM_Top_(\d+)(?:_interim)?_digest\.(html|json)$"`;
  §4-Q1 resolves to interim-free `r".*_TubeLM_Top_(\d+)_digest\.(html|json)$"`.
  Slice 1 proposes `r"^(\d{4}-\d{2}-\d{2})_(?:TubeLM_)?Top_(\d+)_digest\.(html|json)$"`.
  These disagree on three axes: date-prefix required (plan) vs `.*` (requirements),
  `TubeLM_` optional (plan) vs mandatory (requirements), interim tolerated (§2.A) vs
  banned (§4-Q1, plan). The writer (`top10_service.py:570-573`,
  `f"{run_date}_TubeLM_Top_{item_count}{suffix}_digest.html"`) always emits
  date + `TubeLM_`, so the plan regex matches current output — but fixtures like
  `2026-09-04_Top_20_Digest.html` (`test_web_reader.py:149`, no `TubeLM_`) only match
  because of the optional group + `IGNORECASE`. Lock one canonical regex and fix §2.A
  wording to match it (recommend the plan's shape minus interim, since the writer
  guarantees the prefix — but then state that undated legacy files will NOT match).
- `send_top10_from_digests.py:47-49` uses the Top pattern as an **exclusion**
  (`if "TubeLM_Top_" in name: continue` — it collects channel digests). Slice 1 says
  "update file discovery to use `paths.is_top_digest_file`" without stating polarity.
  A literal replacement inverts the script into collecting only Top digests.
  Specify: `if paths.is_top_digest_file(p): continue` (exclusion preserved).
- `download_top10.py:31` globs `*_TubeLM_Top_*_digest.html` (requires `TubeLM_`).
  Centralizing on the optional-`TubeLM_` helper **widens** what it finds (previously
  invisible undated/non-`TubeLM_` files now match). Intended, but call it out.
- `parse_top_digest_filename() -> re.Match | None` leaks regex internals to all
  callers; nobody needs the match object. Return the count instead:
  `parse_top_digest_count(filename) -> int | None`. Smaller API, same power.
- Placement in `paths.py` is correct (all four consumers already import `paths`;
  no cycles). `str | Path` / `X | None` annotations need Python ≥ 3.10 —
  fine on 3.14, record the floor so no `from __future__` churn later.

### P0-2 — Slice 2 omits three blast-radius items REQUIREMENTS Q3 names

Verified present but absent from the plan:

1. `desktop/templates/top10_digest.html:44,60` branches on
   `selection.is_interim` / `is_final_after_interim` ("Early Edition · First Pass").
   Slice 2 lists `main.py`, `top10_service.py`, `email_service.py` only. Add the
   template (render single-edition heading unconditionally).
2. `desktop/tests/unit/test_immediate_checkpointing.py:177-189` asserts
   `is_interim True→False` sequencing. Slice 5 names only three test files and omits
   this one. Add it to the update list (or the suite stays red by design).
3. The one-time stale-artifact sweep (`*_interim_digest.*` purge, REQUIREMENTS §4-Q3
   recommendation) appears nowhere in Slice 2's actions. Add an explicit step
   (startup sweep in `main.py` or a documented one-shot script invocation that logs
   what was swept) — otherwise the interim-free regex never matches stale files and
   they linger silently.
- `rotate_downloads=True` always + tolerant-read of old batch keys: correct as
  specified (`_read_batch` uses `.get`, so old keys parse). No change needed.
- Partial-publish disclosure ("pass disclosure note if `completion_ratio < 1.0`")
  has **no integration point**: `_rank_render_and_send` takes no notice param, and
  neither `top10_digest.html` nor `email_service.py` has a slot for it. Specify:
  add `coverage_note` to the selection dict, render it in the template + email body.
  Without this the step is unimplementable as written.

### P0-3 — Verification baseline is already red; the numeric gate is false

- `pytest desktop/tests/unit --collect-only` in this tree: **190 collected, 11
  collection errors** (incl. `test_weekly_audio_service.py`). The plan's gate
  "100% tests pass (>= 262 tests)" fails on both halves: collection is broken and no
  262 tests exist to pass. Fix collection errors first (Slice 0), then gate on
  **zero failures of the collected suite**, never on an absolute count that rots
  with every added/removed test.

### P1-1 — Slices 1 and 3 both edit `web_reader.py` in overlapping regions

- Slice 1 touches line ~1061 + mobile export ~1237; Slice 3 touches
  `channel_audio_map` ~1214-1231 and `_normalize_mobile_*` (~353-419). The hunks at
  1214-1240 overlap. Do not run these slices in parallel in the same file.
  Order: lock the filename contract (Slice 1 regex + writer format) → Slice 1 read
  path → Slice 3 audio join. Slice 2 (main/top10/email/template) is file-disjoint
  and can run parallel to Slice 1.

### P1-2 — `has_audio` gate makes the Slice 3 condition change insufficient

- `has_audio` is NotebookLM-podcast-only by construction (`web_reader.py:577-593`:
  manifest hit or multi-video `{date}_{safe}.mp3`; single-video channels are
  force-`False`, asserted in `test_web_reader.py:183-251`). Summary-TTS-only channels
  have `summary_audio_url` set (lines 1101-1110) with `has_audio=False`.
- Slice 3 changes the card condition to `ch.audio_url || ch.summary_audio_url` but
  four JS gates still require `has_audio`: card render (`reader.html:2823`), badge
  (`:2600,2614`), directory audio bit (`:3044`), queue filter (`:3163`). Changing
  only `:2823` leaves summary channels out of the queue and badges. Fix all four
  gates together (or derive `has_audio ||= summary_audio_url` at build time — one
  line, fixes every gate — but that invalidates the `test_web_reader` single-video
  assertions, so update them deliberately, not accidentally).
- `buildQueue` field-name clash: the filter-stage map uses `isSummary` (plan text)
  but the queued objects use `summary` (`reader.html:3180-3187`, `summary: false`;
  `playSummaryAudio` pushes `summary: true` at `:3298`). Do NOT introduce a parallel
  `isSummary` flag — reuse the existing `summary` boolean or old persisted queues
  decode with mixed schema.

### P1-3 — SITE_DATA Top items have no audio fallback; the 🎧 button needs a rule

- The channel→item audio join exists **only** on the mobile path (`web_reader.py:1231`,
  `fallback_audio=channel_audio_map.get(...)`). SITE_DATA Top items (`:1139-1157`)
  get dedupe + `id` + duration backfill but **no** `audio_url` fallback. The Slice 3
  Editorial Picks 🎧 button ("if `item.audio_url` or channel audio is present") will
  therefore resolve nothing for web Top items unless either (a) the same fallback is
  applied to `top20_data["items"]` at build time (recommend — 3 lines, mirrors 1231),
  or (b) a JS render-time lookup `source_name → channel summary` with the same
  normalization as Python (duplicates logic in JS — avoid). Pick (a); also then the
  button rule is exact: prefer `item.audio_url`, else channel summary, else hidden.
- Normalization scope: plan populates "raw lowercase and normalized keys." Raw keys
  are redundant once both sides normalize — keep normalized-only (also cover `ch.id`,
  which derives from `name.lower().replace(" ", "_")` at `:1161` and retains
  punctuation). State the canonical rule once
  (`lower → strip [^\w\s] → collapse whitespace`) and use it for map + lookup.

### P1-4 — Retry-gating placement and precedence are unspecified

- The interim trigger being deleted sits **before** `_finish_background_artifacts`
  (`main.py:795-826`). An early `break` on `>= 80% / >= 70%` must be placed
  **after** the per-stage `_finish_background_artifacts` + checkpoint block, or a
  clean Iteration 1 skips artifact advancement. State the exact insertion point.
- Dry-run path (`:645-658`) sets `active_handlers = failed_handlers; continue` —
  gating must not fire in dry-run (no `completed_source_keys` semantics there).
- Quota-deferral (`:827-828` break; `:830-839` pause path) takes precedence over
  threshold gating, and the final Top digest at `:852-854` currently runs even when
  deferred. REQUIREMENTS Q2 says deferral "pauses/exits without phantom retries" —
  state whether a deferred run still publishes a partial digest (current behavior:
  yes) or pauses silently. Either is defensible; unspecified is not.

### P1-5 — iOS slice: fuzzy engine duplicates the build-time fix; four stale gates

- After Slice 3's normalized join + mobile `fallback_audio` embedding,
  `resolveAudioUrl` (`RootTabView.swift:530-544`, exact match only) becomes a rare
  second-chance path. Adding Swift slug-fuzzy on top (Slice 4 action 1) ships two
  normalization implementations to keep in sync per launch. Recommend: keep
  exact-match fallback, **measure** post-Slice-3 miss rate first, add fuzzy only on
  evidence (prior Q4 review reached the same conclusion; the plan regresses it
  without justification).
- `playImmediately(atRate:)` appears in REQUIREMENTS §2.C but correctly appears
  nowhere in Slice 4 (current `play()` + rate at `AudioPlayerManager.swift:113-114`
  is the right primitive for cold URL loads). Delete it from REQUIREMENTS instead
  of leaving a dangling mandate.
- URL encoding (`Slice 4 action 2`): specify encode-only-if-`URL(string:)`-returns-nil,
  never re-encode an already-encoded URL (double-encoding `%20`→`%2520` breaks R2
  links), and apply to relative `audio/...` paths too (they fail with spaces the
  same way absolute URLs do). `.urlQueryAllowed` vs `.urlPathAllowed` without a
  path/query split rule will mis-encode one side — name `URLComponents` or a single
  `addingPercentEncoding` fallback, not two character sets.
- `AVPlayerItem.status` observation needs the lifetime rule the plan omits: token
  scoped to the current item, invalidated on `replaceCurrentItem`, `.failed` →
  surface in UI, `.unknown` → stall state. Also note `@MainActor` isolation for the
  observer under Swift 6.
- N=0 consistency: Slice 4 fixes the `loadCachedFeed` quarantine gate
  (`ContentStore.swift:64-74`) but the **seed** gates (`:84-86, :99-101, :114-118`)
  still require `!top20.items.isEmpty` — an N=0 week returns `nil` (no feed at all).
  Relax all four gates together. And the honest empty state is specified only for
  web (Slice 3); `BriefingView.swift:50` (`prefix(20)` → dynamic) needs the matching
  iOS empty state, or N=0 renders an empty scroll with no copy.
- RSS `top20_items[:10]` (`web_reader.py:763`) is unmentioned. Either update to N or
  record "display all, RSS first 10" as explicit policy (prior review's suggestion) —
  don't leave the third truncation silent.

### P1-6 — UAT target and deploy ordering overstate current automation

- `run_browser_uat.py:30-32` targets the **live** URL with a `file://` fallback —
  `file://` breaks `fetch`-based `data.json` loads, live-URL testing conflates
  deploy lag with regressions. Slice 5's localhost server is the right call but
  requires rewriting `TARGET_URL`/`LOCAL_FALLBACK` + adding an `http.server`
  fixture; name the file. Also state whether the 13 existing checks are extended or
  replaced — the plan's 5 assertions alone drop anti-slop/duplication coverage.
- Deploy: R2 upload happens **during** build (`web_reader.py:1102,1113`; cleanup
  `:1263-1267`), not as a fallback after the 5 MB scan refuses (`:1280-1284`).
  Slice 5's "halt → R2 upload fallback" misdescribes the code: a refused deploy
  today requires re-running the build with R2 configured. For a user without R2
  keys, one stray MP3 = built-but-never-deployed with no documented recovery —
  record the `--compress-audio` / manual-exclusion fallback explicitly.
- `web_reader.main()` **deploys by default** (`:1353`, `if args.deploy or not
  args.build_only`). UAT must run `--build-only` first or every test build
  force-pushes the orphan `gh-pages` branch.

### P2 — Over-engineering cuts (plan is close to lean; hold these lines)

- Dual-key `channel_audio_map` (raw + normalized) → normalized-only (~half the keys,
  one code path to test).
- `parse_top_digest_filename → Match` → count-returning helper (P0-1).
- Absolute test-count gate (`>= 262`) → zero-failure gate (P0-3).
- Keep the 3-viewport Playwright matrix + `canplay`-not-audible bar — proportionate
  for a static page; the risk is Slice 5 dropping the existing 13 checks, not the
  matrix size. Keep `play()` + rate; keep `ContentStore`'s existing atomic-write /
  LRU patterns (already landed) — do not re-spec them.

### Suggested slice order (dependency-safe)

1. **Slice 0 (baseline):** fix the 11 collection errors; record collected count as
   the new gate denominator (zero-failure, not 262).
2. **Contract lock:** canonical interim-free regex (fix §2.A wording) + writer format
   (`Top_{len}_digest`) agreed; `paths.py` helpers land.
3. **Slice 1 read path** (`web_reader`, `tts_service`, `download_top10`,
   `send_top10` with exclusion polarity stated) + **Slice 2 removal** (add
   `top10_digest.html`, `test_immediate_checkpointing.py`, artifact sweep,
   `coverage_note` integration point, gating insertion point + deferral precedence)
   — file-disjoint, may parallelize.
4. **Slice 3 web audio** (all four `has_audio` gates, `summary` field reuse,
   SITE_DATA audio backfill, single-start `playIndex` with promise-driven icons,
   Editorial button resolution rule, web N=0 empty state).
5. **Slice 4 iOS** (dynamic count + iOS N=0 empty state, four-gate quarantine
   relaxation, URL-encode-only-on-nil, item-scoped status observation; fuzzy slug
   only on measured misses).
6. **Slice 5 UAT/deploy** (`run_browser_uat.py` localhost rewrite, extend — don't
   replace — the 13 checks, `--build-only` before any push, R2/compress fallback
   documented, live `run_date` smoke check with empty-`run_date` handling).

### Verification additions (append to plan §4)

- Automated: interim-free regex vector test (Top_14/20/25 + stale `_interim` file
  asserting skip-or-swept); gating boundary test (18/19 of 23 for 80%, 16/17 for
  70%); `grep -r "is_interim\|interim_sent_at\|final_after_interim" desktop/`
  expecting zero hits outside the tolerant-read shim; no-`_interim`-artifact test
  after a full run; normalization pair test (`Peter Attia, MD`, `Nutrition Made
  Simple!`); queue test asserting `summary` (not `isSummary`) flags and
  NotebookLM-first order; N=0 empty-state render test (web + `ContentStore` nil-path).
- Manual: corrupt-cache drill (garbage `feed.json` → seed/empty, no crash — already
  in `UAT_PLAN.md`, link don't duplicate); quota-deferral drill (deferred run →
  stated publish-or-pause behavior); oversize-audio drill (stray >5 MB MP3 without
  R2 → documented recovery path works).
- Negative controls already in `UAT_PLAN.md` (corrupt/empty cache, unplayable item)
  — link them; Slice 5's checklist alone is insufficient exit criteria.

### Decisions needed (blocking, remediation plan)

1. Canonical regex shape (recommend plan's dated interim-free form) + fix §2.A wording.
2. `send_top10` exclusion polarity + `download_top10` widening acknowledged.
3. Template (`top10_digest.html`), `test_immediate_checkpointing.py`, and artifact
   sweep added to Slice 2 scope.
4. `coverage_note` integration point (selection field + template + email slot).
5. Gating insertion point (after artifact advancement), dry-run exclusion, and
   deferral-publishes-partial vs pauses-silent.
6. `has_audio` strategy (rebuild all four JS gates vs build-time derive) + `summary`
   vs `isSummary` field lock.
7. SITE_DATA Top-item audio backfill at build time (recommend) vs JS lookup.
8. iOS fuzzy slug: drop until measured misses (recommend) or justify the second engine.
9. RSS `[:10]` policy: dynamic-N vs documented cap.
10. N=0 iOS empty-state copy + four-gate quarantine relaxation.
11. UAT harness rewrite scope (extend 13 checks) + `--build-only`-first rule + R2-less
   oversize recovery path.
