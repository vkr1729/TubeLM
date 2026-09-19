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
