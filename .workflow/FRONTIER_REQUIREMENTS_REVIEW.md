# Frontier Requirements Review — TubeLM iOS UAT Remediation (§5)

Source: `.workflow/REQUIREMENTS.md` §5 (diff vs `main`: +44 lines, uncommitted)
Date: 2026-09-20
Reviewer: Muse Spark (code-verified against `ios/Sources`, `desktop/tts_service.py`, `desktop/main.py`, `desktop/web_reader.py`, `desktop/templates/reader.html`, `worker/worker.js`)

## Target User Scale Anchor

**Single-Person Personal Use Exclusively** (§1) — hard constraint carried through every recommendation:

- Reject enterprise complexity: no multi-tenant DB, no auth framework, no maintained backend.
- Host: sideloaded `.ipa` inside **LiveContainer** on iOS (JIT, unsigned, no reliable background daemons/push).
- Baseline: **iOS 26 on iPhone 16**; usage 7–8 opens/week on Singapore commute with tunnel dead zones.
- Every Q below is answered with the cheapest local-first fix that keeps the commute triage snappy; anything requiring per-user ops, server state, or background daemons is flagged as anchor-violating.

Prior review of §4 (icon / launch crash / signing) stands — this review covers only the new §5 UAT items. Code status: **none of §5.1–5.5 is implemented** (verified below).

---

## Q1 — §5.1: What does "Light Mode Default + toggle" concretely mean in code?

**Ambiguity:** §5.1 requires enforcing Light default (`.preferredColorScheme(.light)`) *and* adding Light/Dark/System selection defaulting to Light. No storage, scope, or palette contract is specified.

**Code-verified edge cases / failure modes:**
- `ios/Sources/TubeLMApp/TubeLMApp.swift:11` is still `.preferredColorScheme(nil)` — current behavior is system-following, the exact bug §5.1 reports.
- `AppTheme` (`ios/Sources/TubeLMApp/Views/Theme/Typography.swift`) uses semantic `Color(uiColor: .systemBackground / .secondarySystemBackground / .separator)` — these auto-adapt to the system theme. Forcing `.light` at the root changes what they resolve to, but any view relying on raw `.primary/.secondary` or hard-coded dark-tuned values has unverified contrast; "high-contrast typography, off-white cards, crisp borders" has no measurable definition.
- No Settings view, no `@AppStorage` theme key, no `ThemeMode` enum exists anywhere in `ios/Sources`.
- LiveContainer host in dark mode + forced-light app risks a dark→light flash on launch and a mismatched keyboard/alert appearance.

**Recommended approach:**
- Single `@AppStorage("tubelm.themeMode")` (`light` default) + root `.preferredColorScheme(mappedOrNil)` on `RootTabView`; Settings segmented control (Light / Dark / System). Audit `AppTheme` once: keep semantic backgrounds (they resolve correctly under forced light) and spot-check `accent #15803d` on off-white cards for contrast; fix only failing pairs.
- Anchor-fit: one local default, zero server, zero migration.

**Alternatives:**
- Hard-force `.light` everywhere with no toggle — smallest diff, but directly violates the "user theme selection" clause; rejected.
- Custom in-app theme engine (own color tokens per mode) — full control, but over-engineered for a 1-user app when SwiftUI already handles it; rejected.
- Keep `.preferredColorScheme(nil)` and call it "System" — reproduces the reported bug; rejected.

**Decision needed:** Confirm AppStorage-backed Light-default + 3-way toggle as the contract, and define "polish" as a contrast spot-check rather than a full redesign.

## Q2 — §5.2: How does "watched to bottom" sort without breaking rank, order, or animation?

**Ambiguity:** §5.2 says sort unread-first in `BriefingView` and `ChannelsView`, preserve `#1–#20` badges, auto-mark on Play/Watch/Read/title-tap, animate transitions. Unspecified: sort key stability, whether *channels* reorder or only *videos within* a channel, and when the mark fires relative to URL-open success.

**Code-verified edge cases / failure modes:**
- `BriefingView.swift:52` renders `ForEach(Array(items.prefix(20).enumerated()))` with `rank = index + 1` — rank is **position-derived**, so any reorder shifts badges unless the view switches to the model's stable `FeedItem.rank`. `FeedItem.rank` exists (`DigestFeed.swift:73`) but is unused in both views.
- No sorting exists today: neither `BriefingView` nor `ChannelsView` partitions by `readIDs`. Web/PWA reference behavior is richer than the spec states: `reader.html:2717-2723` partitions into normal-unread / deferred-unread / read (plus a `hideSeen` toggle at `:2721`), and channel videos sort `[...normalUnread, ...deferredUnread, ...readVideos]` (`:2868`) — none of which exists on iOS. Blindly copying index-based rank breaks the badge guarantee on day one.
- Auto-mark on title-tap: if the YouTube/Safari open fails (no network, LiveContainer URL-scheme block), the item is already marked read with no undo path specified. Queue/bookmark lists referencing original order go stale after a mid-scroll re-sort; rapid successive taps can thrash `LazyVStack` animation and yank scroll.

**Recommended approach:**
- Stable partition, not a re-sort: `unread (original feed order) + read (original feed order)` computed at render time in both views (and inside each expanded channel's video list; channel *directory* order stays alphabetical/searchable). Badge shows `item.rank ?? originalIndex+1`. Wrap the mutation in `withAnimation` and mark-read immediately on user intent (tap/Play), matching spec wording.
- Anchor-fit: pure client-side array partition, no persistence or server change.

**Alternatives:**
- Hide watched items entirely (web `hideSeen` toggle) — cleaner triage, but spec explicitly says "push to bottom," not hide; rejected as default (optional toggle later).
- Re-sort channels themselves by completion — breaks directory findability for 23 sources; rejected.
- Mark-read only after confirmed URL-open/playback-start — more "correct," but delays the triage feedback the spec wants and complicates every tap handler; rejected.

**Decision needed:** Confirm partition-not-sort + stable-rank-badge + immediate-mark semantics; confirm channels directory order is out of scope.

## Q3 — §5.3: What is the canonical cross-device identity key, and what ships the endpoint migration?

**Ambiguity:** §5.3 requires changing the default worker endpoint to `kedarvreddy`, syncing/matching `video_id` + `url` + normalized URL keys bidirectionally, and adding persistent passphrase input with status. No canonical key, no migration path, no status state machine.

**Code-verified edge cases / failure modes:**
- Both iOS defaults still point at the old host: `CloudflareSyncClient.swift:101` and `RootTabView.swift:8` hardcode `tubelm-sync.vkr1729.workers.dev`. Changing the default orphans state stored under the old Worker's Durable Object unless migration is defined.
- Key asymmetry is the real bug, not just the URL: iOS writes a **single** key per mutation (`ContentStore.markItemRead` → `SyncPayload.itemStates[item.id]`), while web fans out **three** keys per action (`reader.html:2270-2285` `markVideoWatchedState` writes `vid`, `url`, and `normalizeVideoUrl(...)`). The worker (`worker.js:239-291` `mergeSyncState`) and iOS (`ContentStore.applyRemoteStates`) merge on **exact-string LWW** with no normalization — so an iOS `video_id`-keyed mark never matches a web `url`-keyed lookup and vice versa. RSS/article items have empty `video_id` (`data.json:104` `"video_id": ""`), falling back to URL/title-hash keys (`web_reader.py:79-100` `_make_item_id`) where trailing-slash/query/case differences silently fork identity. iOS `FeedItem/VideoItem` decoders mint a random `UUID` when `id` is missing (`DigestFeed.swift:122-128, 280-286`) — unstable across weekly feeds.
- No connection-status UI exists: only a transient `syncToastText` (`RootTabView.swift:99`) and a `SyncSettingsSheet` whose helper text already says "leave empty to stay local-only" (`:445`). Passphrase persists in `UserDefaults` plaintext (`SyncDefaults.keyKey`), never Keychain.

**Recommended approach:**
- Lock the canonical key to the pipeline's `_make_item_id` output (11-char `video_id` when present, else raw URL ≤200 chars, else hash) and make iOS fan out the same alias set web writes (`id` + `video_id`/`url` + normalized URL) on every mark, matching on *any* alias on read. Single shared helper on iOS; no worker logic change (keeps zero-maintenance infra). Ship endpoint change with one-time fallback (try new, on network-error try old once, then persist working value) so existing state isn't stranded. Passphrase in Keychain; Settings shows persistent `Synced ✓ / Connecting… / Error <reason>` driven by last push/fetch outcome.
- Anchor-fit: local-first stays authoritative; sync remains best-effort and optional.

**Alternatives:**
- Normalize server-side in the worker — fixes future matches but leaves offline iOS lookups broken and adds maintained server logic; rejected.
- URL-only or id-only keys — each breaks one content class (YouTube ids vs RSS URLs); rejected.
- Force state reset/re-pair on migration — simplest code, destroys commute triage history for the one user who matters; rejected.

**Decision needed:** Confirm alias-fan-out + `_make_item_id` canonical contract, old→new endpoint fallback, Keychain storage, and the 3-state status row as §5.3 exit criteria.

## Q4 — §5.4: Which execution contexts must the TTS fix cover, and what bounds the backfill?

**Ambiguity:** §5.4 correctly diagnoses `asyncio.run()` inside a running loop and requires a fix + backfill of the 2026-09-18 digest + `data.json` update. Unspecified: the full caller set that must keep working, backfill idempotency/scope, and which audio-URL field is canonical.

**Code-verified edge cases / failure modes:**
- Two `asyncio.run` entry points: `tts_service.py:166` (`generate_summary_tts`) and `:265` (`backfill_week`). The crash path is `main.py:723-725`: `generate_summary_tts` called from inside `async_main` (async context) → `RuntimeError`. `web_reader.py:1081-1085` calls it from sync `build_reader_site` (safe today) — so "fails in both" is really "fails wherever the caller is async," and any fix must be loop-agnostic, not just moved.
- `_backfill_week_async:224-229` wraps the *sync* `generate_summary_tts` in `asyncio.to_thread` (thread without a loop, so it accidentally works) instead of awaiting the async core directly — wasteful and masks the real layering bug. A naive "detect running loop and create a new one in the same thread" fix re-raises; a naive "always new thread" fix hides errors and complicates cancellation.
- Backfill scope is unbounded as specified: no idempotency rule (re-synthesizing existing non-empty MP3s wastes edge-tts time/money), no per-channel failure isolation (today one channel's exception is caught at call site, but a backfill crash aborts the week), and two competing URL fields (`summary_audio_url` vs `audio_url` on `Channel`, `web_reader.py:1091/1102`) with no statement of which the app plays when both exist.

**Recommended approach:**
- Split layers: keep `_generate_audio_async` as the single async core; make `generate_summary_tts` a loop-agnostic sync wrapper (if a loop is running in this thread, execute the coroutine on a dedicated short-lived thread with its own loop; else `asyncio.run` inline). Make `_backfill_week_async` call the async core directly with its semaphore, per-channel try/except + `{scanned, generated, skipped, failed}` stats. Backfill is idempotent (skip non-empty MP3 unless `--force`), then rewrite `data.json` audio URLs and play-verify one item per surface.
- Anchor-fit: pipeline-only change, no app or infra change, bounded cost.

**Alternatives:**
- Always run TTS on a fresh thread — works in both contexts but adds thread-hopping to the hot sync path and obscures tracebacks; rejected as the primary pattern.
- Make all callers async — correct long-term, but forces `build_reader_site` and pipeline finalization into async for a one-user weekly job; rejected for this fix.
- Fix forward only, skip the 2026-09-18 backfill — violates the explicit requirement and leaves the current digest silent; rejected.

**Decision needed:** Confirm loop-agnostic wrapper + direct-async backfill + idempotent scope, and declare the canonical audio-URL field the app reads.

## Q5 — §5.5: What are the measurable acceptance bars for the Player Deck redesign?

**Ambiguity:** §5.5 mandates "Apple Podcasts / Castro standards" with artwork card, custom scrubber, balanced controls, and re-orderable Up Next — all subjective with no sizes, gestures, or accessibility floor.

**Code-verified edge cases / failure modes:**
- Current sheet (`PlayerDeckSheet.swift:50-58`) is the reported bug verbatim: 100×100 `accentBadge` square with `"TL"`, standard `Slider` (`:76-80`), skip buttons 44×44 (`:97`), play 62×62 (`:104`), speed as a 44×44 circle (`:121-125`). §2 separately requires **56pt touch targets** — the redesign must satisfy both "balanced proportions" and the 56pt floor; 44pt skips fail it today.
- Queue reorder uses desktop drag idiom (`:179-180` `.onDrag`/`.onDrop` with `NSItemProvider` + `UTType.text` + `QueueDropDelegate`), which is unreliable as the primary iOS-touch reorder path inside a LiveContainer sheet; only removal affordance is a small `xmark` (`:167-174`), no swipe-to-delete. No channel badge, no artwork asset, mono time labels exist (`:87`) but the scrubber hit area is the stock slider's.
- Custom scrubber drag inside a scrollable sheet fights the sheet's own pan gesture; without `minimumDistance`/hit-area rules, scrub attempts scroll the queue instead. No VoiceOver labels on transport controls.

**Recommended approach:**
- Set numeric bars: artwork card ~180–200pt, 24pt radius, soft shadow, channel-badge overlay (keep refined TL monogram — no new asset pipeline); custom capsule scrubber with ≥24pt hit height + drag gesture that claims the touch, mono time labels retained; transport row at ≥56pt targets (emerald play ~64pt, 15s skips 56pt, speed pill); Up Next with native `EditMode` reorder + swipe-to-delete (keep xmark as fallback), replacing drag-drop as primary.
- Anchor-fit: pure SwiftUI, no new dependencies, no artwork downloads (tunnel-safe).

**Alternatives:**
- Restyle the stock `Slider` — least code, but keeps the exact control the feedback calls out and the gesture conflict; rejected.
- Remote artwork images per episode — prettier, but adds a network dependency into the tunnel use case and an asset pipeline for one user; rejected.
- Third-party audio-UI kit — faster polish, but a new dependency for a single sheet; rejected.

**Decision needed:** Lock the numeric bars (artwork size, 56pt floor, scrubber hit area, native reorder + swipe-delete) as the §5.5 acceptance test.
