# Frontier Requirements Review — TubeLM iOS (LiveContainer Native)

Source: `.workflow/REQUIREMENTS.md`
Date: 2026-09-20
Reviewer: Muse Spark (code-verified against `ios/`, `worker/worker.js`, `.github/workflows/build-ios.yml`)

## Target User Scale Anchor

**Single-Person Personal Use Exclusively** (§1). Carried as hard constraint through every recommendation:

- Reject enterprise complexity: no multi-tenant DB, no auth framework, no maintained backend.
- Host: sideloaded `.ipa` inside **LiveContainer** on iOS (JIT, unsigned, no reliable background daemons/push).
- Baseline: **iOS 26 on iPhone 16**; usage 7–8 opens/week on Singapore commute with tunnel dead zones.
- Tension to watch: §2 mandates a Cloudflare Worker (`tubelm-sync.<subdomain>.workers.dev`, R2 + Durable Object `SyncCoordinator`, Bearer passphrase) that *is* a remote server. Review treats it as anchor-compliant only if it is zero-maintenance, optional, and never blocks offline use.

## Section 4 Defect Verification (code-checked, not just spec-read)

Spec §4 lists 2 incidents / 7 sub-requirements. Current code status:

- **4.1 Missing icon — still open.** No `AppIcon*.png` in repo; `ios/TubeLM/Info.plist` has no `CFBundleIcons`, `CFBundleIcons~ipad`, `CFBundleIconFiles`, `CFBundleIconFile`; `build-ios.yml` "Package LiveContainer IPA" copies only `Info.plist` + `data.json` + binary, no icons.
- **4.2.1 Bundle.module trap — mostly fixed.** `ContentStore.loadCachedFeed()` already guards `Bundle.module` behind `#if SWIFT_PACKAGE` with `Bundle.main` (`data`/`mock_data`) fallback. Residual risk is corrupt/empty fallback (see Q2).
- **4.2.2 Eager audio session — NOT fixed.** `AudioPlayerManager.init()` still calls `setupAudioSession()` → `setCategory(.playback)` + `setActive(true)` at launch, exactly what §4 bans. Must defer both to `play()`/`playTrack()`.
- **4.2.3 Missing plist keys — partially open.** Present: `CFBundlePackageType=APPL`, `UILaunchScreen`. Missing: `CFBundleSupportedPlatforms`, `MinimumOSVersion`, `CFBundleSignature`. Note version skew: §4 requires `MinimumOSVersion 17.0` while §1 declares iOS 26 baseline — floor vs. target needs a decision.
- **4.2.4 Unsigned Mach-O — open in CI.** Simulator step runs `codesign -s - --force --deep`; device IPA packaging step does not run `codesign`/`ldid` at all and never verifies `LC_CODE_SIGNATURE`.

All Qs below assume §4 must close with automated gates, not manual "it launched once" checks.

---

## Q1 — What is the acceptance proof for "icon fixed + launch-crash fixed"?

**Ambiguity:** §4 prescribes artifacts (4 PNG sizes, plist keys, `codesign -s -`) but no verification contract. "Package icons into `TubeLM.app` root" + "ensure ad-hoc signing" can silently regress — wrong dimensions, corrupt PNG, missing `~ipad` key, `codesign` pass on macOS yet AMFI kill under LiveContainer JIT, LiveContainer icon cache showing stale blank.

**Edge cases / failure modes:**
- PNG exists but wrong pixel size / wrong color profile → iOS silently falls back to blank icon, CI still green.
- `CFBundleIcons` added but `CFBundleIcons~ipad` or `CFBundleIconFiles` misspelled → iPhone OK, LiveContainer grid blank.
- `codesign -s -` runs on the simulator `.app` but device IPA ships unsigned → `unzip -l` looks fine, AMFI kills on device.
- `MinimumOSVersion 17.0` vs §1 iOS 26 baseline: building with iOS 17 SDK APIs that behave differently on 26, or vice versa.

**Recommended approach:**
- CI gate in `build-ios.yml` after packaging: assert 4 PNGs exist in `Payload/TubeLM.app/`, verify dimensions via `sips -g pixelWidth/Height` or `file`, lint plist keys with `PlistBuddy`, verify signature with `codesign -dv --verbose=4` / `otool -l | grep LC_CODE_SIGNATURE`, fail build on miss. Add LiveContainer import smoke note (install + `simctl launch` + screenshot, already partially done for sim).
- Lock semantics: `MinimumOSVersion 17.0` = floor, iOS 26 + iPhone 16 = tested baseline; state both explicitly.

**Alternatives:**
- Manual screenshot check ("looks right on my phone") — catches nothing in CI; rejected as sole gate.
- Full Apple asset catalog (`Assets.car`) instead of loose PNGs — more correct on stock iOS but heavier toolchain for LiveContainer loose-bundle packaging; defer.
- Skip verification, trust packaging script — reproduces the original incident; rejected.

**Decision needed:** Confirm CI icon+plist+signature assertions as §4 exit criteria and clarify 17.0-floor vs 26-baseline wording.

## Q2 — What renders on first launch with no cache, no bundle feed, and no network?

**Ambiguity:** §4.2.1 fixes the `fatalError` but specifies only "fallback to sandbox documents with zero crash risk." Combined with §2's stale-while-revalidate (launch → ETag check → atomic swap), the cold-start-in-tunnel path is undefined: corrupt `feed.json`, missing bundled `data.json` (CI copies `mock_data.json` today, production IPA may differ), ETag check timing out.

**Edge cases / failure modes:**
- First install opened in MRT tunnel: no `Documents/cache/feed.json`, bundled `data.json` missing/stale, network unreachable → `loadCachedFeed()` returns `nil`; does UI blank-crash, spin forever, or show readable empty state?
- Truncated download replaces good cache (header check OK, body truncated on flaky Wi-Fi) → next cold start has corrupt JSON and no fallback.
- `DigestFeed` tolerant decoding already exists (`decodeIfPresent` + defaults) but `loadCachedFeed` uses `try JSONDecoder().decode` on the cache path — a corrupt cache file *throws* instead of healing.

**Recommended approach:**
- Never-throw launch path: cache read failure → try `Bundle.main` → else render staged empty state ("No briefing yet — pull to retry"), never block on network. Download-to-temp → validate (JSON parses + `items` non-empty + `schema_version` supported) → atomic `replaceItemAt`; failed validation keeps last good cache silently.
- Make cache decode tolerant too (`try?` + fallback, or quarantining corrupt file), matching the already-tolerant `DigestFeed.init(from:)`.

**Alternatives:**
- `fatalError`/force-unwrap on missing feed — simplest, reproduces crash; rejected.
- Block cold start on network fetch for correctness — violates "instantaneous cold starts" + tunnel requirement; rejected.
- Ship large bundled seed feed to mask the case — bloats IPA, goes stale weekly; rejected as primary (small seed OK, network-independent launch required).

**Decision needed:** Confirm "offline-first empty-state + validate-then-swap" as the launch contract; fix `AudioPlayerManager` eager `setActive` in the same pass since both fire at launch.

## Q3 — Does silent refresh or auto-sync ever interrupt reading, scrolling, or playback?

**Ambiguity:** §2 demands *both* "silent single-flight ETag check on every launch/foreground, atomically updates without interrupting" *and* "auto-syncs in background on every state mutation (watched, queued, bookmarked), no manual sync." No concurrency, ordering, debounce, or conflict rule. The 120Hz triage + 56pt Commute Deck + 15s skip experience collides with mid-scroll feed swaps and tunnel-flaky POSTs.

**Edge cases / failure modes:**
- Rapid foreground/background cycling in subway → overlapping `URLSession` checks race; older response overwrites newer, or feed re-renders mid-scroll.
- Refresh lands while user reads item #7 or drags queue → force-reload yanks scroll / reorders "Up Next."
- Mutation in tunnel (mark read + queue + bookmark) with Worker unreachable → does the app retry, drop, or block UI? `CloudflareSyncClient` timeout is 15s with `unauthorized/rateLimited/payloadTooLarge` errors — no specified UX.
- ETag says modified but full `data.json` takes 30s on edge network; user already reading cached copy.

**Recommended approach:**
- Single-flight refresh with debounce (min ~60s between checks), conditional GET, 15s timeout; validate-then-stage — if user is scrolled/reading/playing, show quiet "New briefing available — tap to refresh" pill instead of force-swap; never move scroll under touch.
- Sync as best-effort background: local-first (ContentStore LWW tombstones already correct), silent retry with backoff, never block mutation UI; surface 401/429/413 only in Settings/debug, not as alerts. Leverages existing `item_states`/`bookmark_states` LWW merge in worker + client.

**Alternatives:**
- Blocking refresh on every foreground — simplest, kills snappy cold start; rejected.
- Force-reload feed on arrival — simple code, janky triage; rejected.
- Fire-and-forget sync with no retry — loses commute triage state; rejected.

**Decision needed:** Confirm single-flight + debounce + staged-apply pill + silent-retry sync as the concurrency contract.

## Q4 — Which audio URL is canonical, and what bounds the offline cache?

**Ambiguity:** §2 allows audio on R2 `/tubelm/audio/...` *or* Pages `/audio/...` with "transparent local disk caching so subway tunnels are protected," but names no canonical URL, no cache key, no storage ceiling, no cellular-vs-Wi-Fi rule. Tab 3 promises "unlimited bookmarks, audio caching dropped entirely" while the Commute Deck implies queued audio must survive tunnels.

**Edge cases / failure modes:**
- Pipeline flips R2 mid-week → same episode has two URLs; URL-keyed cache double-stores or re-downloads on cellular.
- Partial download in tunnel (stream cut mid-file) → 15s skip/scrub on truncated file, or spinner with full text available but unplayed.
- `Documents/` fills LiveContainer quota with queued audio → launch failures; no eviction or "audio unavailable offline" state specified.
- Stream-only fallback dies in tunnel with no degraded UX.

**Recommended approach:**
- Pipeline emits single canonical `audio_url` + `audio_sha`/`bytes` per item at build time; app never chooses source. Cache key = content hash, not URL, so source flips don't duplicate. Temp-download → validate → atomic swap.
- Bounded hybrid: manual "Download for commute" + auto top-N only on unmetered Wi-Fi (`allowsExpensiveNetworkAccess=false`); hard ceiling (e.g. ~1 GB) with LRU eviction, bookmarked/queued pins exempt; always show size before tap. Offline-missing audio degrades to fully readable text + inline "audio unavailable offline" instead of spinner.

**Alternatives:**
- Stream-only — fails core tunnel requirement; rejected.
- Download-everything — guarantees offline, blows LiveContainer storage + Pages bandwidth; rejected.
- Background prefetch via BGTask — unreliable in LiveContainer guest (§4 context); rejected as primary, foreground-only.

**Decision needed:** Confirm canonical-URL + hash-key + ceiling + degraded-text state; clarify bookmark-audio exclusion vs queue-audio pinning.

## Q5 — Is Worker sync required or optional, and where does the passphrase live?

**Ambiguity:** §1 anchor says "strictly reject … remote cloud server maintenance" while §2 mandates event-driven sync to `tubelm-sync.<subdomain>.workers.dev` with `Authorization: Bearer <passphrase>` on *every* mutation. Unspecified: provisioning/rotation, unconfigured state, offline behavior, and whether the app is useful with no key. `CloudflareSyncClient.isConfigured` already gates on non-empty key, but spec never says so.

**Edge cases / failure modes:**
- Fresh install with no passphrase entered opens in tunnel → every tap fires failing POSTs, 15s timeouts pile up, or errors spam the commuter.
- 401 (rotated key) / 429 (rate limit: 60/min/IP, 240/key in DO) / 413 (1 MiB cap) during commute → silent data divergence across devices with no merge UX (LWW exists server-side, client `applyRemoteStates` exists, but trigger policy undefined).
- Passphrase bundled into IPA or checked into repo → credential leak; key knowledge = read+write per worker header comment.
- Worker/R2/DO treated as "no maintenance" until custom domain, bindings, or rate tuning need changes — who owns that for a 1-user app?

**Recommended approach (anchor-compliant):**
- Local-first, sync-optional: app is fully functional with empty key (commute reading, queue, bookmarks all work offline); sync is best-effort when configured. Passphrase entered in Settings, stored in Keychain/sandbox, never bundled. Silent retry, union-merge via existing LWW; explicit "Sync status" row for 401/429/413 instead of alerts.
- Document Worker as zero-touch infra (static bindings, no per-user ops), explicitly exempted from the "no server" ban — or the ban must be reworded.

**Alternatives:**
- Hard-require sync (block usage until key valid) — bricks the tunnel use case; rejected.
- Embed key in binary/plist — leaks credential, breaks rotation; rejected.
- Drop Worker, local-only + manual export/import — purest anchor reading, but discards already-built CRDT sync; defer as fallback if Worker ops prove burdensome.

**Decision needed:** Lock v1 as local-first + optional best-effort sync; forbid bundled keys; clarify Worker exemption in §1 wording.
