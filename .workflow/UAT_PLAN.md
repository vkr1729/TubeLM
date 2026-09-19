# UAT Plan — TubeLM iOS (LiveContainer Native)

Date: 2026-09-19 · Status: ready for independent execution
References: `.workflow/REQUIREMENTS.md`, `.workflow/AUDIT_AND_REMEDIATION_REPORT.md`,
`.workflow/IMPLEMENTATION_PLAN.md`, `worker/worker.js`, `ios/` (TubeLMCore + TubeLMApp)

## 0. Independence & purpose

This is a **black-box acceptance plan**. The tester verifies **observable behavior
on the device** against REQUIREMENTS, not implementation. The audit report is used
only for **traceability** (every remediated defect gets at least one UAT case) —
the tester must not need to read Swift/Python source to execute or judge a case.

**Accept =** the app is shippable for single-person personal commute use
(iPhone 16, iOS 26, LiveContainer). Any P0 failure rejects the build.

## 1. Scope

**In scope:** install into LiveContainer, all three tabs, mini-player + Commute
Deck sheet, audio (streaming, lockscreen, headphones, background), zero-input
weekly refresh, offline commute behavior, local persistence, Cloudflare Worker
sync, `data.json` contract as consumed by the app, Mock-1 visual lock (light +
dark), typography, haptics, touch targets, input hardening.

**Out of scope:** weekly pipeline content quality (LLM summaries), PWA/web
reader, R2 upload tooling, Xcode build internals, unit-test suites (already
green: 250 Python + 7 Swift per audit §K). Those are regression safety nets,
not acceptance evidence.

## 2. Test environment

### 2.1 Device & host

- iPhone 16, **iOS 26** baseline, portrait. LiveContainer installed (JIT /
  unsigned sideload path). One build under test, recorded by version +
  IPA sha256.
- No other TubeLM installs. System Light **and** Dark appearance both tested.
- Headphones (Bluetooth) + lockscreen available for audio-remote cases.

### 2.2 Backends (record actual values on the run sheet)

- Feed: `https://vkr1729.github.io/TubeLM/data.json` (`schema_version: 1`).
- Audio: Cloudflare R2 `/tubelm/audio/...` or Pages `/audio/...`; relative
  `audio/…` URLs resolve against `https://vkr1729.github.io/TubeLM/`.
- Sync: `tubelm-sync.<subdomain>.workers.dev` (`worker/worker.js`),
  `Authorization: Bearer <passphrase>` / `X-Sync-Key`. Passphrase ≥ 16 chars.
- Control a **second sync peer** (curl or a second install with the same key)
  for cross-device cases in S6.

### 2.3 Fixtures & network profiles

- **Fresh week feed:** current published `data.json` (≈20 top items, ≈23
  channels). Record `run_date`, item count, channel count.
- **Synthetic edge feed** (serve locally or stage on Pages for S10): items with
  `**bold**` + `&amp;` summaries, `<ul>/<li>/<br>/<b>` HTML, numbered lists,
  relative `audio/…` URLs, empty/whitespace `audio_url`, non-http(s) `url`
  values, RSS items keyed by raw URL, strict-11-char vs garbage YouTube ids.
- **Network profiles:** (a) fast Wi-Fi, (b) offline / Airplane mode,
  (c) flaky tunnel (offline 60–120 s mid-stream), (d) conditional-GET observable
  via proxy or response headers (`ETag`, `Last-Modified`, 304).
- **Clean slate:** delete app sandbox (`Documents/cache`, `Documents/pinned`)
  + clear sync pairing before S0/S5/S7 runs.

### 2.4 Entry criteria

IPA installs one-tap into LiveContainer; feed reachable (or staged offline
cache present); sync worker reachable; tester has pairing passphrase.

### 2.5 Exit / acceptance criteria

- **All P0 cases pass.** No more than 2 P1 failures, each with a logged defect
  and workaround; **zero P2-only rejection** (P2s advisory).
- No crash, no data loss, no stuck "playing with no sound", no empty IPA,
  no sync-direction silent breakage, no fabricated durations, no spec-string
  drift (`✓ Channel Completed`, category pills, `N in Queue`).
- Sign-off table (§8) completed with build hash + device + iOS version.

## 3. Conventions

- Verdicts: **PASS / FAIL / BLOCKED / N/A**. FAIL requires a defect entry (§9).
- Priority: **P0** ship-blocker · **P1** must-fix-or-waive · **P2** polish.
- Requirement tags: `R2-*` = REQUIREMENTS §2 workflow, `R3-*` = §3 UI lock.
  Audit tags: `A`–`K` per audit report sections.
- Time-boxes: sync push is debounced ~1.5 s — wait **≥ 5 s** after a mutation
  before asserting remote state. Feed refresh timeout ~20 s, sync ~15 s.

---

## S0. Install & packaging [P0]

### UAT-001 One-tap LiveContainer install [P0] (R2-outputs, I)
Pre: clean device, IPA from CI release artifact.
Steps: 1. Import IPA into LiveContainer. 2. Launch.
Expect: installs without signing/entitlement prompts; app icon + name TubeLM;
cold start lands on Briefing tab, no crash.
Pass if: one-tap install, first launch renders Briefing (feed or honest
`No Briefing Yet` offline empty state).

### UAT-002 IPA is not empty [P0] (R2-outputs, I)
Pre: IPA file on host.
Steps: 1. `unzip -l TubeLM.ipa` shows `Payload/TubeLM.app/TubeLM` binary
(non-trivial size) + `Info.plist`. 2. Confirm CI would have failed loudly
without the binary (no silent green empty artifact).
Expect: binary present + executable bit; no binary → packaging step exits
non-zero, no artifact shipped.
Pass if: binary present in the tested IPA.

### UAT-003 Info.plist contract [P0] (I)
Steps: 1. Inspect `Payload/TubeLM.app/Info.plist`.
Expect: `CFBundleIdentifier com.vkr1729.tubelm`; `UIBackgroundModes` contains
`audio`; `ITSAppUsesNonExemptEncryption = false` (no compliance prompt);
portrait orientation; `LSRequiresIPhoneOS`, `arm64`.
Pass if: all keys exact; background audio mode present.

### UAT-004 Unsigned-zip is LiveContainer-correct, no extra entitlements [P1] (J)
Steps: 1. Install unsigned IPA. 2. Background the app mid-playback.
Expect: installs unsigned; audio continues in background (audio mode only,
no extra entitlements required).
Pass if: background playback works with audio-only background mode.

## S1. Briefing tab (Tab 1)

### UAT-005 Continuous #1–#20 feed, no splits/dividers [P0] (R3-Briefing, H)
Steps: 1. Launch with fresh feed. 2. Scroll entire Briefing.
Expect: all 20 items in one uninterrupted list, rank badges `#1`…`#20`
monospace; no "Top 10 / Next 10" split, no section dividers, no dev notes.
Pass if: count = feed `top20.items` (20 on a normal week), order = rank order.

### UAT-006 Why-It-Matters callouts [P0] (R3-Briefing)
Steps: 1. Inspect every card with `why_it_matters`.
Expect: prominent callout block (`WHY IT MATTERS`) on cards that have it;
no `**` markers leaking literally; HTML entities decoded.
Pass if: callouts render as formatted text, never raw markup.

### UAT-007 Watch vs Read labels [P0] (R2-actions)
Steps: 1. Find a YouTube item and an article/newsletter (`rss`/`newsletter`).
Expect: YouTube shows **Watch**, article/newsletter shows **Read** with
matching icon (`play.rectangle` vs `doc.text`).
Pass if: every card's action label matches its `source_type`.

### UAT-008 Title tap opens link AND auto-marks watched [P0] (R2-actions)
Steps: 1. Note an unread item. 2. Tap its title. 3. Return to app.
Expect: system opens YouTube app / Safari; card dims (≈0.45 opacity) as read.
Pass if: external open + read state set on a single tap.

### UAT-009 Watch/Read button = same as title tap [P0] (R2-actions)
Steps: 1. Tap the `Watch`/`Read` button on an unread item.
Expect: same as UAT-008 (opens + marks read).
Pass if: identical behavior.

### UAT-010 Play + Queue + Bookmark on every Briefing card [P0] (R2-queue, R3)
Steps: 1. On one card tap `Play`, then `+ Queue`, then bookmark icon.
Expect: `Play` starts that item's audio; `+ Queue` toasts `Added to Queue`
and bumps mini-player `N in Queue`; bookmark fills + appears in Tab 3.
Pass if: all three act on the correct item; duplicate `+ Queue` does not
duplicate the entry.

### UAT-011 First-run offline empty state [P1] (H)
Pre: fresh install, Airplane mode, no cache.
Steps: 1. Launch offline.
Expect: `No Briefing Yet` + `Connect to refresh the weekly digest…`, not a
blank feed; state preserved; no crash.
Pass if: honest empty state, recovers on reconnect (see S5).

### UAT-012 Link validation — no crash on bad URLs [P0] (H)
Pre: edge feed with `ftp:`, `javascript:`, empty, garbage `url` values.
Steps: 1. Tap each bad-URL title/button.
Expect: no external-open attempt, no crash; item still marks read where the
tap rule applies; valid items unaffected.
Pass if: only `http/https` opens; nothing crashes.

## S2. Channels tab (Tab 2)

### UAT-013 Searchable 23-source directory [P0] (R3-Channels)
Steps: 1. Open Channels. 2. Type a channel name fragment, then a category
fragment. 3. Clear.
Expect: list filters by name or category (case-insensitive); clearing
restores full directory; counts/avatars visible.
Pass if: search works both ways, empty query = full list.

### UAT-014 Category pills are spec-locked [P0] (R3-Channels, H)
Steps: 1. Scroll all channels.
Expect: pills read **Tech & AI**, **Health & Bio**, **Science & Deep**, or
**News**; raw pipeline values (`tech`, `deep_explainer`, `news_feed`) never
render uppercased verbatim; unknown categories title-case gracefully.
Pass if: zero verbatim raw-category strings on screen.

### UAT-015 Expandable multi-item breakdown [P0] (R2-channels)
Steps: 1. Expand a multi-item channel (e.g. 6-item MIT/IBM style).
Expect: disclosure reveals **every** video/article with numbered titles,
duration badge, rich markdown summary, direct `Watch`/`Read` link, per-item
`+ Queue` and bookmark.
Pass if: expanded count = channel `videos` count; nothing truncated.

### UAT-016 Rich markdown rendering [P0] (R2-channels, F)
Pre: edge feed (bold, entities, `<br>/<li>/<ul>/<ol>/<b>/<em>`, numbered lists,
headers).
Steps: 1. Expand an item with each construct.
Expect: paragraphs + bold keywords + bullets + numbered lists render
formatted; `&amp;→&`, `&lt;→<`, `&gt;→>`, `&quot;→"`, `&#39;/&apos;→'`,
`&nbsp;→space`; no raw tags, no `**` leakage, no `\(…)` misrender.
Pass if: all constructs legible; literal markup nowhere.

### UAT-017 Channel completion header — exact string [P0] (R2-actions, H)
Steps: 1. In one channel, mark every video read (checkboxes or title taps).
Expect: header flips to exactly **`✓ Channel Completed`** (accent color).
2. Unmark one item.
Expect: header reverts to `k/n Completed`.
Pass if: string byte-exact including `✓` + single space.

### UAT-018 Compact Listen pill, not a stretched bar [P1] (R3-Channels, H)
Steps: 1. Inspect channel action bar.
Expect: proportional `Listen` pill + separate `+ Queue`; Listen does not
span the card width.
Pass if: compact pill layout on all channels.

### UAT-019 Smart Unwatched playback [P0] (R2-channels, E)
Steps: 1. Mark 2 of 5 videos in a channel read. 2. Tap channel `Listen`.
Expect: playback targets **only unwatched** summaries
(`Unwatched Summaries (3)`); skipped items' audio never queued/played.
3. Mark all read → tap `Listen`.
Expect: falls back to `Channel Overview` audio.
Pass if: unwatched filtering exact; empty/whitespace per-item `audio_url`
never shadows a real `channel.audioUrl` fallback.

### UAT-020 Per-video checkbox toggles read both ways [P0] (R2-actions, C)
Steps: 1. Check an unread video → uncheck it → relaunch.
Expect: persists both directions (unmark survives relaunch via tombstone);
header counts follow.
Pass if: toggle is durable, not append-only.

### UAT-021 Real durations, no fabrications [P0] (H)
Steps: 1. Compare channel/queue duration labels against feed
`durationSeconds`/`read_minutes`.
Expect: labels derive from real values; unknown durations hide the `·`
separator (no `14m`/`12m` placeholders, no `totalCount × 10` math).
Pass if: no placeholder durations anywhere.

## S3. Bookmarks tab (Tab 3)

### UAT-022 Save + remove + persist [P0] (R2-bookmarks)
Steps: 1. Bookmark 3 items (Briefing + expanded channel). 2. Open Tab 3.
3. Remove one. 4. Relaunch.
Expect: Tab 3 lists saved text articles as clean cards; removal sticks;
survives relaunch (pinned store, purge-exempt).
Pass if: add/remove/durable, order most-recent-first.

### UAT-023 Unlimited text bookmarks, zero audio bloat [P0] (R2-bookmarks, C)
Steps: 1. Bookmark **≥ 250 items** (repeat-tap across weeks or script the
pinned store via UI).
Expect: all retained — no 200-item cap, no eviction, no error; each ≈ 2 KB
text; no audio cached for bookmarks.
Pass if: count > 200 persists after relaunch; disk growth is text-scale.

### UAT-024 Bookmark cards are clean + linkable [P1] (R3-Bookmarks)
Steps: 1. Inspect cards.
Expect: source eyebrow, serif title, 2-line summary, `Watch`/`Read` link,
`Remove`; no audio widgets, no helper clutter.
Pass if: text-only library look; `Remove` is clearly destructive-safe
(single item only).

### UAT-025 Empty bookmarks state [P2] (R3)
Pre: zero bookmarks.
Steps: 1. Open Tab 3.
Expect: `No Bookmarks Yet` + guidance, not blank.
Pass if: honest empty state.

## S4. Mini-player, Commute Deck, queue, audio engine

### UAT-026 Mini-player always visible with queue badge [P0] (R3-player, R2)
Steps: 1. Enqueue 3 items from different tabs.
Expect: sticky mini-player floats above tab bar on all tabs showing track
title + **`3 in Queue`** badge; survives tab switches.
Pass if: badge count exact; tapping bar opens the Deck sheet.

### UAT-027 Commute Deck sheet controls [P0] (R2-player)
Steps: 1. Open Deck. 2. Operate scrubber, −15 s, +15 s, speed button,
play/pause, close.
Expect: scrubber seeks with `mm:ss / mm:ss` monospace labels; skips move
±15 s clamped to `[0, duration]`; speed cycles `1.0 → 1.25 → 1.5 → 2.0`;
default speed **1.25x**; close returns to prior tab.
Pass if: every control responds within 1 s; no stuck states.

### UAT-028 Touch targets [P0] (R2-player, E)
Steps: 1. (By inspection or accessibility inspector) measure main play
(≥ 56 pt — actually 62 pt) and skip/speed (≥ 44 pt platform minimum).
Expect: main play ≥ 56 pt; all Deck controls ≥ 44 pt; no overlap/mis-tap.
Pass if: main play ≥ 56 pt, others ≥ 44 pt.

### UAT-029 Up-Next queue: add, dedupe, remove, reorder [P0] (R2-queue, D)
Steps: 1. Add items from Briefing **and** channel subcards. 2. Re-add a
duplicate. 3. Remove one via ×. 4. Drag-reorder Up Next.
Expect: single combined queue, no duplicates, removal instant, drag-drop
reorders and persists for the session; stale/out-of-range drag never crashes.
Pass if: order after drag = dropped order; no crash on rapid drags.

### UAT-030 No separate queue tab [P1] (R2-queue)
Steps: 1. Count tabs. 2. Confirm queue only via mini-player → Deck sheet.
Expect: exactly 3 tabs (Briefing / Channels / Bookmarks); queue anchored to
Player Spotify/Castro-style.
Pass if: 3 tabs; no orphan queue tab.

### UAT-031 Streaming starts fast on good network [P0] (R1-profile, R2-cache)
Pre: fast Wi-Fi, uncached episode.
Steps: 1. Tap `Play`. 2. Time to audible sound.
Expect: snappy start (< ~3 s on fast Singapore-grade link); title/source
update immediately.
Pass if: audible quickly; no indefinite spinner.

### UAT-032 Relative audio URLs resolve [P0] (E, G)
Pre: feed with relative `audio/…` item URLs.
Steps: 1. Play such an item.
Expect: resolves against Pages base to `https://…`, plays over http(s).
Pass if: relative-URL items play; absolute URLs unaffected.

### UAT-033 Honest idle — no fake playback [P0] (E, H)
Steps: 1. Play an item with empty/missing `audio_url`.
Expect: **no** stuck `playing` indicator: `isPlaying = false`, time resets,
idle title (`Nothing Playing` / `Pick an episode`) — never fake `14:48`-style
defaults.
Pass if: unplayable item surfaces idle, never phantom playback.

### UAT-034 Track advance / end-of-track resets UI [P0] (E)
Steps: 1. Play a short clip to completion. 2. Play track 2+ in a row.
Expect: at end, play/pause icon + Now Playing flip to paused; elapsed time
does **not** freeze on track 2+ (time observer follows replacement items).
Pass if: end state honest; multi-track timing live.

### UAT-035 Seek/skip/time hardening [P1] (E)
Steps: 1. During playback: skip forward past end, backward past 0, scrub to
extremes rapidly.
Expect: clamps to `[0, duration]`; `mm:ss` never shows `NaN`/negative;
`CMTime.indefinite` never poisons scrubber range.
Pass if: no NaN, no negative, no scrubber blowout.

### UAT-036 Lockscreen + headphone remotes [P0] (R1-objective)
Steps: 1. Play. 2. Lock phone: check Now Playing (title/artist/elapsed).
3. Use headphone play/pause, ±15 s (where exposed), Control Center.
Expect: metadata + progress live; remotes toggle/skip correctly.
Pass if: lockscreen + headphones fully drive playback.

### UAT-037 Background audio + interruption [P0] (R1, I)
Steps: 1. Play, background the app (LiveContainer + home). 2. Take a short
call / Siri interruption.
Expect: audio continues backgrounded; interruption pauses and (per-OS) state
stays consistent; foreground return needs no restart.
Pass if: background + interruption handled, no silence-with-playing-icon.

### UAT-038 Tunnel / flaky-network playback [P1] (R1-profile, R2-cache)
Steps: 1. Start streaming, cut network 60–120 s, restore.
Expect: transparent local caching covers the dead zone where buffered; app
never crashes; playback resumes or holds position honestly.
Pass if: no crash, no phantom progress during outage.

## S5. Zero-input refresh, caching, offline commute

### UAT-039 Launch performs silent conditional refresh [P0] (R2-refresh, B)
Pre: instrumented proxy **or** observe `lastChecked` behavior across a staged
feed bump.
Steps: 1. Launch (or foreground) with unchanged feed. 2. Launch after
publishing a new weekly digest.
Expect: (1) silent `If-None-Match` / `If-Modified-Since`; 304 keeps cache
untouched, no UI flash. (2) New week atomically replaces cache without
interrupting playback/reading.
Pass if: no full re-download when unmodified; atomic swap when modified.

### UAT-040 Foreground revalidation [P0] (R2-refresh, B)
Steps: 1. Background app. 2. Publish feed bump. 3. Foreground.
Expect: refresh triggers on `scenePhase == .active` without any manual pull.
Pass if: new content appears after foreground, zero taps.

### UAT-041 Single-flight — no duplicate downloads [P1] (B)
Steps: 1. Cold-launch + rapid foreground/background × 5.
Expect: one refresh in flight; no interleaved full re-downloads, no
corrupted/partial feed, no crash.
Pass if: feed intact, network shows coalesced conditional GETs.

### UAT-042 Offline launch serves cache silently [P0] (R2-refresh, B)
Pre: cached feed present, then Airplane mode.
Steps: 1. Relaunch offline. 2. Browse all tabs, play cached audio.
Expect: full local experience, no error modal, no blank feed; refresh fails
silent.
Pass if: offline = fully usable from cache.

### UAT-043 Request timeouts never hang UI [P1] (A, B)
Steps: 1. Blackhole feed + sync hosts (no response). 2. Launch, tap around.
Expect: feed gives up ≈ 20 s, sync ≈ 15 s; UI stays responsive throughout.
Pass if: no spinner > timeout + 5 s; cache still served.

## S6. Cloudflare Worker sync (event-driven, LWW)

### UAT-044 Pairing surface exists and persists [P0] (R2-sync, A)
Steps: 1. Tap toolbar sync icon (accessibility `Sync settings`). 2. Enter
Worker URL + ≥ 16-char passphrase, Save. 3. Relaunch, reopen sheet.
Expect: sheet shows persisted URL + key; pull-on-launch + save triggers
immediate pull then push.
Pass if: pairing survives relaunch; Save visibly syncs.

### UAT-045 Unpaired = honest local-only [P0] (A)
Pre: empty passphrase.
Steps: 1. Mark items, queue, bookmark with network on.
Expect: everything works locally; **no** fake `skipped` sync, no error
popup; client makes no authed sync calls.
Pass if: local-only, silent, fully functional.

### UAT-046 Every mutation auto-pushes, debounced, no manual sync [P0] (R2-sync, A)
Steps: 1. Paired. 2. Separately: mark read, unmark, enqueue, bookmark.
After each, wait ≥ 5 s and `GET /` the worker with the same key (curl).
Expect: each mutation lands server-side within seconds, coalesced (≈ 1.5 s
debounce — rapid taps = one request); **no manual sync button exists or is
needed**.
Pass if: 4/4 mutation classes propagate; no manual step.

### UAT-047 Exact worker contract keys [P0] (A)
Steps: 1. Capture a POST body (proxy) or decode via test peer.
Expect: keys exactly `read_ids` / `top20_read` / `item_states` — no
`client_id`, response never requires `merged_item_states`; `item_states`
values are signed ms timestamps (positive = read, negative = unread
tombstone).
Pass if: contract byte-exact; empty-state GET decodes.

### UAT-048 Cross-device convergence both directions [P0] (R2-sync, A, C)
Steps: 1. Peer B marks item X read. 2. On device A: background → foreground
(pull). 3. On A unmark Y; check peer B after push.
Expect: A gains X; B reflects Y's tombstone; read-id sets converge.
Pass if: bidirectional sync works — the pre-fix "silently never worked"
failure is gone.

### UAT-049 Unmark is a tombstone, survives relaunch + sync [P0] (C)
Steps: 1. Paired. Mark X, wait push. 2. Unmark X. 3. Relaunch. 4. Check peer.
Expect: X stays unread locally after relaunch; negative tombstone present
server-side; peer drops X.
Pass if: unmark durable locally **and** remotely (append-only bug gone).

### UAT-050 Most-recent-intent-wins on conflict [P1] (C, J)
Steps: 1. Peer sets X read with old ts. 2. Device sets X unread newer.
3. Sync both.
Expect: newer absolute-timestamp intent wins regardless of direction.
Pass if: conflict resolves to latest intent, both peers agree.

### UAT-051 Auth failures are typed and silent-safe [P1] (A, J)
Steps: 1. Pair with wrong/short key. 2. Mutate. 3. Fix key, mutate again.
Expect: 401 unauthorized → local stays authoritative, no crash/popup loop;
recovery on correct key. 429 → silent, next mutation retries with
`Retry-After` respected. 413 → silent, local intact.
Pass if: failures never interrupt reading; recovery automatic.

### UAT-052 Header-only auth, key never in URL [P1] (J)
Steps: 1. Capture sync traffic.
Expect: key only in `Authorization: Bearer` / `X-Sync-Key` headers; never in
query string, logs, or pasted URLs.
Pass if: header-only/password-manager-safe.

## S7. Persistence & storage

### UAT-053 Read state LRU keeps the genuinely recent [P1] (C)
Pre: read-state store near cap (or simulate 5000+ marks over weeks).
Steps: 1. Mark a fresh item. 2. Relaunch.
Expect: newest marks survive; genuinely stalest evicted (most-recent-first
ordering — never arbitrary `Set.prefix` eviction).
Pass if: fresh marks durable at cap pressure.

### UAT-054 Non-finite timestamps rejected [P1] (C)
Pre: edge sync payload containing `NaN`/`Infinity` `item_states` values.
Steps: 1. Push/merge payload. 2. Relaunch.
Expect: values dropped at boundary; store stays valid; no crash.
Pass if: state intact, bad timestamps gone.

### UAT-055 Atomic writes survive crash/kill [P0] (C, B)
Steps: 1. Mark + bookmark + queue. 2. Immediately force-kill mid-write
(repeat × 3). 3. Relaunch.
Expect: files valid JSON, never missing/empty; at worst last mutation lost,
never whole-store loss (no remove-then-move window).
Pass if: 3/3 kills recover with intact stores.

### UAT-056 Bookmarks exempt from rolling purge [P1] (C, J)
Steps: 1. Bookmark items from an old week. 2. Advance feed 2+ weeks (or run
14-day retention rollover).
Expect: current-week cache rolls; `pinned/` bookmarks untouched.
Pass if: bookmarks survive purges indefinitely.

## S8. Pipeline `data.json` contract (as the app consumes it)

Run with `curl`/`python3 -c` against the live feed **plus** in-app confirmation
(the app must render the same file without parsing HTML).

### UAT-057 Schema shape + tolerant decode [P0] (R2-inputs, G)
Steps: 1. Fetch `data.json`; assert `schema_version == 1`, `run_date` matches
`YYYY-MM-DD` (never literal `"None"`), `top20.items[]` + `channels[].videos[]`
carry `id/title/url/audio_url/source_type`. 2. Open the same file in-app.
Expect: contract keys present; app decodes without error; `summary →
why_it_matters` backfilled where the Top-20 sidecar used `summary`.
Pass if: curl-clean **and** app-renders.

### UAT-058 Stable identity keys match web reader [P0] (G)
Steps: 1. Compare `data.json` ids against web-reader watch-state keys.
Expect: YouTube items use raw `video_id`; URL items raw URL (≤ 200 chars,
sha256 only when over-long); title-hash fallback otherwise. Marking read on
phone converges with laptop state for the same video/URL.
Pass if: cross-device read matching hits on `video_id`/URL.

### UAT-059 Strict YouTube ids + safe ints — dirty input never breaks the week [P0] (G)
Pre: synthetic producer row with 5-char `video_id`, `duration_seconds:
"twelve"`, `read_minutes: null`, `audio_seconds: "NaN"`.
Steps: 1. Run export. 2. Load output in-app.
Expect: garbage ids rejected (strict 11-char only, no mock-fallback
collisions); malformed ints coerced safely; weekly build + app decode succeed.
Pass if: no crash, no phantom identity collisions.

### UAT-060 Payload is mobile-projected, durations honest [P1] (G, H)
Steps: 1. Inspect `data.json` keys + size.
Expect: exactly the mobile schema (no producer leakage: `candidate_id`,
`summary`, `video_id`, `published`, `brief`, `word_count`, `audio_path`);
duration cross-fill merges without clobbering; payload weekly-sized.
Pass if: lean, decodable, no key drift.

### UAT-061 Audio bucket alignment [P1] (G)
Steps: 1. Play R2-hosted audio end-to-end (Range seeks included).
Expect: uploads land in the bound `tubelm` bucket (not legacy
`instagram-digest`); CDN streams + seeks succeed.
Pass if: audio URLs in `data.json` actually play.

## S9. Visual lock, theme, typography, hygiene, a11y

### UAT-062 Mock-1 minimalist lock, pure signal [P0] (R3-hygiene, H)
Steps: 1. Walk all tabs + Deck in Light and Dark.
Expect: Executive-Briefing minimalism; zero floating commentary, dev notes,
section dividers, instructional helper text (empty states excepted).
Pass if: pure-signal screens; nothing scaffold-like visible.

### UAT-063 Light default + Dark mode [P0] (R3-theme)
Steps: 1. Fresh install → Light. 2. Switch system to Dark.
Expect: Light default high-contrast; Dark fully legible (cards, pills,
`Why It Matters`, Deck, mini-player); neon `#d9ff63` rank badge keeps AAA
contrast both modes.
Pass if: both modes AAA-legible, no invisible text.

### UAT-064 Typography hierarchy [P1] (R3-type, H)
Steps: 1. Inspect headlines (serif New York), body/controls (SF Pro),
ranks/durations (monospace).
Expect: consistent rhythm/weights app-wide; headlines serif, timestamps
monospace.
Pass if: hierarchy uniform; no third-party-font look.

### UAT-065 Haptics present [P1] (R1-objective, H)
Steps (on device, haptics on): 1. Mark read (success thump). 2. Bookmark
(success). 3. `+ Queue` / unmark / tab actions (light tap).
Expect: tactile confirmation on success paths, light taps elsewhere.
Pass if: haptics felt where specified; none blocks interaction.

### UAT-066 ProMotion-smooth scrolling [P1] (J)
Steps: 1. Fling-scroll Briefing + expanded Channels on iPhone 16.
Expect: 120 Hz-smooth standard SwiftUI lists; no jank, no custom-timer
stutter.
Pass if: butter-smooth, no frame drops visible.

## S10. Resilience & adversarial inputs

### UAT-067 Queue reorder abuse never crashes [P0] (D)
Steps: 1. Rapid/out-of-order drags, drag onto itself, drag with 1-item and
empty queue.
Expect: no crash; no-op or correct move; model filters invalid indices.
Pass if: 10 hostile drags, zero crashes.

### UAT-068 Sync payload hardening [P1] (J, C)
Pre: craft POSTs with > 5000 ids, > 256-char ids, control chars, `NaN`
timestamps, > 1 MiB body, malformed JSON.
Steps: 1. Push each at the worker (curl). 2. Confirm app still syncs after.
Expect: worker sanitizes/caps (429/413/400 where specified), merges stay
correct; app never bricks.
Pass if: worker correct per case; app recovers.

### UAT-069 Markdown injection inert [P1] (F)
Pre: summaries containing `\(…)`-like sequences, `%`-style tokens,
`<script>`, unclosed tags.
Steps: 1. Render in expanded channel.
Expect: plain-text composition; no bundle-string resolution, no markup
execution, no crash; `**bold**` still bolds.
Pass if: hostile summaries render as inert text.

### UAT-070 Audio edge inputs [P1] (E)
Steps: 1. Items with `audio_url`: `""`, whitespace, relative path, `ftp:`,
> 2 KB garbage, missing key.
Expect: playable ones play; rest → honest idle; never fake playing, never
crash.
Pass if: 6/6 handled per rule.

### UAT-071 Rapid-tap / double-tap storm [P1] (D, B, A)
Steps: 1. Double-tap Play, `+ Queue`, bookmark, checkboxes, Listen × 10 fast.
Expect: single coherent outcome each (debounced sync = one push); no stuck
toggles, no duplicate queue rows, no crash.
Pass if: UI converges; sync coalesces.

### UAT-072 Rotation / multitasking / low-storage [P2] (I)
Steps: 1. Portrait lock respected. 2. Split/slide-over (where LiveContainer
allows). 3. Near-full disk: mark + bookmark + queue.
Expect: portrait holds; writes fail safe (atomic) with data intact.
Pass if: no layout break, no store corruption.

## S11. Commute performance acceptance

### UAT-073 Cold start snappy [P0] (R1-objective)
Pre: cached feed, fast link.
Steps: 1. Force-quit, relaunch, time to interactive Briefing.
Expect: instantaneous feel (cached render first, silent revalidate after —
never blocked on network).
Pass if: interactive from cache in ≤ ~2 s; refresh silent.

### UAT-074 Week-over-week refresh is zero-touch [P0] (R1-objective, R2-refresh)
Steps: 1. Use normally across a Thursday→Friday publish boundary (or staged
bump): launch × 3 over the week.
Expect: new digest appears with zero settings/URL/paste steps; old read
state carries; bookmarks intact.
Pass if: tester performs zero maintenance actions.

### UAT-075 7–8×/week commute loop [P1] (R1-profile)
Steps: 1. Simulate a week: 8 sessions mixing streaming + tunnel-offline +
queue + bookmarks + sync peer checks.
Expect: every session starts fast, works offline, converges sync.
Pass if: 8/8 sessions usable; end-of-week state matches peer.

---

## 6. Traceability matrix

| Requirement / Audit | UAT cases |
|---|---|
| R1 personal-scale, iOS 26 / iPhone 16 / LiveContainer, commute profile | 001, 004, 031, 038, 073–075 |
| R2 feed input + `data.json` schema | 039–042, 057–060 |
| R2 zero-input SWR refresh (ETag/IMS, single-flight, foreground) | 039, 040, 041, 074 |
| R2 streaming + transparent caching | 031, 032, 038, 061 |
| R2 Watch/Read + tap-to-open + auto-mark | 007, 008, 009, 012 |
| R2 channel completion `✓ Channel Completed` | 017, 020 |
| R2 channel breakdown + markdown + Listen Unwatched | 015, 016, 019 |
| R2 commute queue in Player Deck (no separate tab) | 026, 027, 029, 030 |
| R2 unlimited text bookmarks | 022, 023, 056 |
| R2 worker sync every mutation, no manual sync | 044–048, 051, 052 |
| R2 outputs: IPA + `data.json` hook | 001–003, 057–061 |
| R2 persistence Documents/ + bg sync | 042, 053–056 |
| R3 Mock-1, Light/Dark, hygiene | 005, 062, 063 |
| R3 typography (SF Pro / NY serif / mono) | 064 |
| R3 3 tabs exact | 005, 013, 022, 030 |
| R3 mini-player + Deck + `N in Queue` + 56 pt / scrubber / 15 s / 1.25x | 026, 027, 028 |
| Audit A sync protocol + pairing + debounce | 043–048, 051, 052, 071 |
| Audit B refresh ETag/foreground/single-flight | 039, 040, 041, 043 |
| Audit C read-state/tombstones/LRU/atomic/unlimited | 020, 049, 050, 053, 054, 055, 023 |
| Audit D queue crash + reorder UI | 029, 067, 071 |
| Audit E audio engine + honest idle + remotes | 027, 031–038, 070 |
| Audit F markdown/entities/lists | 006, 016, 069 |
| Audit G pipeline export + ids + bucket | 057–061 |
| Audit H UI-spec strings/pills/durations/haptics/links/empty states | 011, 012, 014, 017–019, 021, 025, 033, 062, 064, 065 |
| Audit I packaging/CI/plist/gitignore | 001–004 |
| Audit J deliberately-unchanged (worker math, purge, 120 Hz, unsigned) | 050, 052, 056, 066, 068 |
| Audit K automated suites green (precondition, not acceptance) | entry criteria |

## 7. Execution runbook

1. Record build: version, IPA sha256, feed `run_date`, worker URL, device/iOS.
2. Execute S0 → S11 in order; S6 needs the second peer ready before S6.
3. Offline cases (011, 038, 042) run with Airplane mode **after** a cached
   baseline exists — except 011 which mandates no-cache first.
4. For sync assertions use `GET /` with the same passphrase:
   `curl -s -H "Authorization: Bearer <key>" https://<worker>/ | python3 -m json.tool`
   and compare `read_ids` / `top20_read` / `item_states` signs.
5. Any FAIL → file defect (§9) with steps + expected/actual + build + feed
   `run_date`; continue the suite unless blocked.
6. Re-test fixes on a fresh build; never flip a verdict without re-execution.

## 8. Sign-off

| Role | Name | Build (sha256, 12 chars) | Device / iOS | Date | Verdict |
|---|---|---|---|---|---|
| Automated iOS Simulator UAT | GitHub Actions (Run 35427394154) | `539da4f98e6d` | iPhone 16 Pro Simulator (iOS 18.5) / macOS-15 (Xcode 16.2) | 2026-09-19 | **PASS** (17/17 Swift acceptance + unit tests green; Live install & launch PID 20105 verified with screenshot) |
| CI Builder & Packager | GitHub Actions (Run 35427394154) | `539da4f98e6d` | macOS-15 (Xcode 16.2 / Swift 6.0.3) | 2026-09-19 | **PASS** (UAT-001..004 binary & plist verified; Mach-O 64-bit arm64 PIE) |
| Core Test Runner | pytest + swift-test | Git commit `9d62b1f` | Ubuntu 26.04 LTS | 2026-09-19 | **PASS** (276 Python + 17 Swift tests green) |
| Owner | Kedarnath Reddy Vallaboina | `539da4f98e6d` | iPhone 16 / iOS 26 (LiveContainer) | 2026-09-19 | **Ready for Device Acceptance** |

Accepted only when §2.5 holds. Dissenting notes go here, not in chat threads.

## 9. Defect log template

| ID | UAT case | Severity (P0/P1/P2) | Steps | Expected | Actual | Build | Feed `run_date` | Status |
|---|---|---|---|---|---|---|---|---|
| DEF-001 | UAT-0xx | P0 | … | … | … | … | … | open/fixed/verified |
