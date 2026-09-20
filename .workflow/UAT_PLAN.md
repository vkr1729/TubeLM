# UAT Plan — TubeLM iOS (LiveContainer Native)

Date: 2026-09-20 · Status: ready for independent execution ·
References: `.workflow/REQUIREMENTS.md` (§§1–5), `.workflow/AUDIT_AND_REMEDIATION_REPORT.md` (§§A–Z, X.1–X.9),
`.workflow/IMPLEMENTATION_PLAN.md` (Slices 1–5), `scripts/package_ipa.sh`
Supersedes: `.workflow/UAT_PLAN.md` dated 2026-09-20 (Section-4 gate). That gate is preserved verbatim
as Suite SEC below and is now the front gate of this full plan.

## 0. Independence & purpose

This is a **black-box acceptance plan**. The tester verifies **observable behavior on device and host**
against REQUIREMENTS. No Swift/Python source reading is required or allowed for verdicts.

- The audit report is used **only for traceability** — every §4 defect and every §5 remediation maps to ≥1 case.
- Verdicts come from: what the eye sees on device, what `unzip`/`plutil`/`codesign`/`file`/`otool` print on host,
  what LiveContainer reports, whether another app's audio keeps playing, and what `curl` against the sync
  worker returns.
- **Accept =** shippable for single-person personal commute use (iPhone 16, iOS 26 baseline, LiveContainer).
  **Any P0 failure rejects the build, regardless of automated-suite results.**
- Automated evidence (`swift test`, pytest, CI simulator UAT) is a **precondition, not acceptance**.
  Acceptance is granted only by executing this plan against the exact IPA under test.

## 1. Scope

**In scope:** REQUIREMENTS §§1–5 in full —
§1 user profile & platform qualities, §2 workflows (refresh, streaming/cache, Watch/Read, channels,
queue+deck, bookmarks, sync, outputs, persistence), §3 Mock-1 visual lock, §4 hardening chain,
§5 UAT remediations (theme, sorting, sync keys, TTS audio, deck redesign).

**Out of scope:** weekly pipeline content quality (ranking relevance, summary prose), PWA/web-reader UI,
R2 tooling internals, Xcode internals, unit suites.

## 2. Build under test — read this first

The repo has contained a known-stale artifact (committed `ios/TubeLM.ipa` predating the icon work —
`unzip -l` showed no `AppIcon*.png`, audit §U). **Never accept against an IPA you have not fingerprinted.**

- Build under test MUST be the fresh CI artifact (via `scripts/package_ipa.sh` / `Package LiveContainer IPA`
  workflow) or a locally rebuilt IPA from the same script.
- Record on the run sheet: IPA path, `shasum -a 256`, `unzip -l` output, feed `run_date`, worker URL,
  device model + iOS version, LiveContainer version.
- If `unzip -l <IPA>` shows anything other than **exactly the 5 icons in SEC-01**, stop — the build is stale.

## 3. Test environment

### 3.1 Device & host

- iPhone 16, **iOS 26** baseline, portrait, LiveContainer installed (JIT / unsigned sideload path).
- Host (macOS or Linux) with: `unzip`, `plutil` (or `python3 -c plistlib`), `file`, `shasum`,
  plus **one** of `codesign` (macOS) / `ldid` / `otool` for signature checks. PNG dimension check via
  PIL, `sips -g pixelWidth -g pixelHeight` (macOS), or `file`. `curl` + `python3`/`jq` for sync + `data.json` checks.
- Reference audio source for the deferred-audio cases: any continuously playing app (Music/Podcasts/Safari).
- Headphones + lockscreen available for the audio-confirmation cases.
- Second sync peer for Suite SY: `curl` against the worker, or the web reader with the same passphrase.

### 3.2 Clean-slate rule

Before the SEC gate: delete any prior TubeLM install from LiveContainer, clear sandbox state where
accessible, and start each launch-crash case from force-quit. Do not carry state between SEC-06–SEC-11
except where the case explicitly chains. Suites BR→PF run on a fresh install unless a case chains state.

### 3.3 Entry criteria

1. Fresh IPA built by `scripts/package_ipa.sh` (CI log shows all icon assets verified in bundle).
2. `unzip -l` lists a non-empty `Payload/TubeLM.app/TubeLM` binary + `Info.plist`.
3. Feed reachable **or** bundled `data.json` seed present (either is fine — fallback is under test).
4. Tester holds no signing certificates (ad-hoc path is the correct path; do not re-sign with a team identity).

### 3.4 Exit / acceptance criteria

- **All P0 cases pass.** Any P0 FAIL = build rejected, file defect (§10), stop the run.
- At most 1 P1 failure, each with logged defect + workaround; zero P2-only rejection.
- Sign-off table (§9) completed with build hash + device + iOS version.

## 4. Conventions

- Verdicts: **PASS / FAIL / BLOCKED / N/A**. Every FAIL needs a defect entry (§10).
- Priority: **P0** ship-blocker · **P1** must-fix-or-waive · **P2** polish.
- Tags: `R1..R5` = REQUIREMENTS §§1–5 items. `A..Z/X` = audit sections. `U` = stale-IPA lesson.
- Time-boxes: launch verdicts need **≥10 s** foreground observation (AMFI kills are immediate but
  audio-session conflicts can lag). Force-quit between launch cases. After any sync mutation, wait **≥5 s**
  before checking the peer (1.5 s debounce + network).

---

## Suite SEC — Section 4 gate (run first; P0 FAIL stops the run)

### Group A — App icons: 5 assets declared and packaged (R4.1)

Canonical set (from `scripts/generate_icons.py` + `scripts/package_ipa.sh` validation loop).
Any deviation in name, count, or size is a FAIL:

| File (bundle root) | Expected px | Role |
|---|---|---|
| `AppIcon.png` | 1024×1024 | Master / LiveContainer high-res |
| `AppIcon60x60@2x.png` | 120×120 | iPhone 60pt @2x |
| `AppIcon60x60@3x.png` | 180×180 | iPhone 60pt @3x |
| `AppIcon76x76@2x.png` | 152×152 | iPad 76pt @2x |
| `AppIcon83.5x83.5@2x.png` | 167×167 | iPad Pro 83.5pt @2x |

Design lock: emerald gradient (`#15803d`→dark), lime `#d9ff63` "TL" monogram — eye-check only.

#### SEC-01 Five icons inside the IPA, correct sizes [P0] (R4.1, U)
Type: host-only. Pre: IPA file on host.
Steps: 1. `unzip -l <IPA> | grep -E "AppIcon.*\.png"` — expect exactly the 5 rows above, under
`Payload/TubeLM.app/`. 2. Unzip to a temp dir; verify each PNG's dimensions and that each file is a
non-empty RGB PNG. 3. If any of the 5 is missing → build predates icon work → FAIL, do not install.
Pass if: `unzip -l` lists 5/5 AND dimension check is 5/5 exact.

#### SEC-02 Info.plist declares the icon set [P0] (R4.1)
Type: host-only. Pre: same temp-dir bundle from SEC-01.
Steps: 1. `plutil -p Payload/TubeLM.app/Info.plist` and check: `CFBundleIcons.CFBundlePrimaryIcon`
(`CFBundleIconFiles` contains `AppIcon60x60`, `CFBundleIconName` = `AppIcon`);
`CFBundleIcons~ipad.CFBundlePrimaryIcon` lists `AppIcon60x60`, `AppIcon76x76`, `AppIcon83.5x83.5`;
top-level `CFBundleIconFile` = `AppIcon` and `CFBundleIconFiles` covers the stems. 2. Cross-check: every
stem resolves to at least one PNG from SEC-01.
Pass if: declarations exact AND every stem resolves to a packaged PNG.

#### SEC-03 Icon renders on device — no placeholder [P0] (R4.1)
Type: device. Pre: SEC-01+SEC-02 PASS; clean LiveContainer.
Steps: 1. Import IPA one-tap. 2. Inspect icon in LiveContainer list + (where visible) home screen /
app library. 3. Compare against design lock (green + "TL").
Pass if: real icon visible post-install AND after first launch AND after LiveContainer restart; never
the blank/white-grid placeholder, never stretched/letterboxed.

### Group B — No launch crash (R4.2, whole chain)

#### SEC-04 Cold launch reaches Briefing, stays alive [P0] (R4.2)
Type: device. Pre: fresh install, network ON, force-quit.
Steps: 1. Tap icon. 2. Observe 10 s without touching. 3. Note first screen.
Pass if: Briefing tab renders (feed cards) or honest `No Briefing Yet` empty state if offline — either is
a pass; first screen renders within ~5 s on cache/seed AND process survives 10 s. Never black screen,
never instant return to LiveContainer list (AMFI-kill signature), never a crash alert.

#### SEC-05 Relaunch storm — 5 consecutive force-quit launches [P0] (R4.2)
Type: device. Pre: SEC-04 PASS.
Steps: force-quit → launch → wait to Briefing → force-quit, ×5.
Pass if: 5/5 reach Briefing, no cumulative failure.

#### SEC-06 Info.plist platform keys present [P0] (R4.2-3)
Type: host-only.
Steps: in the same `plutil -p` output verify: `CFBundleSupportedPlatforms = ["iPhoneOS"]`,
`MinimumOSVersion = "17.0"`, `CFBundlePackageType = "APPL"`, `CFBundleSignature = "????"`,
`LSRequiresIPhoneOS = true`, `UIRequiredDeviceCapabilities` contains `arm64`,
`UILaunchScreen` dict present (may be empty), `UIBackgroundModes` contains `audio`,
`CFBundleIdentifier = com.vkr1729.tubelm`, `CFBundleExecutable = TubeLM`.
Pass if: every key above present and byte-exact. (`MinimumOSVersion` 17.0 is a floor against the
§1 iOS-26 test target — that combination is correct, not a mismatch.)

### Group C — Non-throwing cache fallback (R4.2-1)

Principle: cache loading must **never crash the UI** — corrupt/missing cache degrades to the bundled
seed or an honest empty state. The tester proves this by deleting/corrupting the cache.

#### SEC-07 First launch with empty cache falls back to seed [P0] (R4.2-1)
Type: device. Pre: fresh install (no `Documents/cache/feed.json`), network OFF (Airplane) to force the local path.
Steps: 1. Airplane ON. 2. Launch.
Pass if: Briefing renders from bundled seed OR honest `No Briefing Yet` — either acceptable; crash /
blank / spinner-forever are FAIL. Usable with zero taps, no crash.

#### SEC-08 Corrupt cache is quarantined, app heals [P0] (R4.2-1)
Type: device (+ host where sandbox is reachable; otherwise simulator/CI log).
Steps: 1. Plant a corrupt cache file: write garbage bytes to `Documents/cache/feed.json` (on LiveContainer
use its file browser if exposed; on simulator use `xcrun simctl get_app_container`). 2. Force-quit →
relaunch (record network ON/OFF). 3. After launch, list `Documents/cache/` for a quarantined sibling.
Pass if: no crash AND (quarantine file exists OR fresh valid `feed.json` rewritten) AND Briefing usable;
corrupt bytes never left as the live `feed.json`.

#### SEC-09 Missing seed → honest empty, recovers [P1] (R4.2-1)
Type: device/simulator. Pre: repacked copy of the IPA without `Payload/TubeLM.app/data.json` (re-zip,
reinstall to a scratch slot where allowed; otherwise simulator).
Steps: 1. Launch offline with no cache and no bundle seed.
Pass if: honest `No Briefing Yet` empty state; recovers to full feed when network returns. No crash on
the hardest fallback path. (Waivable with defect.)

### Group D — Deferred audio session activation (R4.2-2)

Principle: the audio session must activate only on explicit Play, never at launch.
Black-box proxy: **another app's audio must survive our launch and navigation**.

#### SEC-10 Launch does not steal background audio [P0] (R4.2-2)
Type: device. Pre: start Music/Podcasts playback, keep it audible.
Steps: 1. While external audio plays, cold-launch TubeLM. 2. Navigate all 3 tabs + open/close the Deck
sheet — press NO Play button. 3. Listen throughout.
Pass if: external audio plays uninterrupted; no ducking, no pause, no TubeLM Now-Playing takeover.
FAIL pattern (old bug): external audio ducks/stops the moment TubeLM launches.

#### SEC-11 Session activates only on explicit Play [P0] (R4.2-2)
Type: device. Pre: SEC-10 PASS, external audio still playing (or restart it).
Steps: 1. In TubeLM tap a real episode `Play`. 2. Observe.
Pass if: takeover happens exactly at the Play tap — pre-Play silence from TubeLM + post-Play proper
takeover with live lockscreen metadata (title/source/elapsed). Not before.

#### SEC-12 Unplayable item never activates session or fakes playback [P0] (R4.2-2)
Type: device. Pre: feed row with empty/missing `audio_url` (edge feed or airplane-blocked stream).
Steps: 1. Tap `Play` on the unplayable item.
Pass if: honest idle — `Nothing Playing`/`Pick an episode` equivalent, play icon stays "play", no phantom
progress; external audio (if any) NOT stolen; no crash.

#### SEC-13 Lockscreen/headphone remotes still work after deferral [P1] (R4.2-2 + R1)
Type: device. Pre: playing a real episode.
Steps: 1. Lock phone → check Now Playing metadata/progress. 2. Headphone play/pause + Control Center.
Pass if: lockscreen + headphones fully drive playback. (Waivable with defect.)

### Group E — Ad-hoc code signature (R4.2-4)

#### SEC-14 Mach-O carries LC_CODE_SIGNATURE, ad-hoc [P0] (R4.2-4)
Type: host-only. Pre: extracted `Payload/TubeLM.app/TubeLM` from SEC-01.
Steps: 1. `file Payload/TubeLM.app/TubeLM` → arch must be arm64. 2. `otool -l … | grep -A3
LC_CODE_SIGNATURE` (macOS; on Linux `llvm-readobj` or the CI log line `Applying ad-hoc code signature`
is acceptable proxy). 3. macOS only: `codesign -dv --verbose=4` → ad-hoc identity.
Pass if: arch=arm64 AND signature evidence present AND binary non-trivial size.

#### SEC-15 Device install proves AMFI acceptance [P0] (R4.2-4)
Type: device. Pre: SEC-14 PASS.
Steps: 1. Import unsigned IPA one-tap into LiveContainer (no certs, no prompts expected). 2. Launch,
keep foreground 10 s. 3. Background mid-playback, foreground again.
Pass if: installs without signing/entitlement prompts; zero SIGKILLs; background audio continues.

#### SEC-16 Packaging script validation is enforced, not decorative [P1] (harness)
Type: host (negative control). Pre: a scratch copy of a valid `.app` dir.
Steps: 1. Delete one icon from the scratch copy, run `scripts/package_ipa.sh <scratch.app> /tmp/neg-test.ipa`
→ expect non-zero exit naming the missing icon. 2. Restore icons, delete the `TubeLM` binary, re-run →
expect missing-binary non-zero exit.
Pass if: both negative runs exit non-zero with the naming error. (Waivable with defect.)

---

## Suite BR — Briefing tab (R2, R3, R5.2)

#### BR-01 Continuous #1–#20 feed, no splits or dividers [P0] (R3)
Pre: fresh install, network ON, weekly feed loaded.
Steps: 1. Open Briefing tab. 2. Scroll top to bottom counting rank badges.
Pass if: exactly one continuous list with `#1`→`#20` badges in order; no "Top 10"/"Next 10" split headers,
no section dividers, no instructional helper text anywhere.

#### BR-02 "Why It Matters" callouts on every item [P0] (R3)
Steps: 1. Scan all 20 cards.
Pass if: each card shows a prominent callout block (accent label + summary body); no empty callout shells.

#### BR-03 Watch vs Read buttons correct per item [P0] (R2)
Steps: 1. Confirm video items show **Watch** (+ play icon) and article/newsletter items show **Read**
(+ doc icon). 2. Tap each on 2 videos + 2 articles.
Pass if: labels match content type; taps open YouTube app (videos) or Safari (articles) via valid
http(s) links only.

#### BR-04 Title tap opens link AND marks watched [P0] (R2, R5.2)
Steps: 1. Fresh state, tap an unwatched item's title (not the button).
Pass if: target opens AND the item flips to watched styling (dimmed + `✓ Watched`) without a second tap.

#### BR-05 Watched items sink to bottom, ranks preserved [P0] (R5.2)
Steps: 1. Note `#1` at top. 2. Tap Play (or Watch) on `#1`. 3. Watch the list.
Pass if: `#1` animates to the bottom marked watched, `#2` occupies the top slot, and every badge keeps
its original number (`#1` still reads `#1` at the bottom). Repeat for 2 more items — unread always first,
order stable within each group.

#### BR-06 Play marks watched; channel Listen does NOT mass-mark [P0] (R5.2, plan Slice 3)
Steps: 1. Tap `Play` on a Briefing item → verify it marks watched. 2. Go to Channels, tap `Listen` on a
fresh channel → verify its videos stay unwatched.
Pass if: item-level Play marks; channel-level Listen never mass-marks (commute queue stays intact).

#### BR-07 +Queue on every Briefing item [P0] (R2)
Steps: 1. Tap `+ Queue` on 3 Briefing items. 2. Check mini-player badge.
Pass if: toast confirms each add, badge reads `3 in Queue`, duplicates are ignored (re-tap adds nothing).

#### BR-08 Bookmark toggle from Briefing [P0] (R2)
Steps: 1. Bookmark 2 Briefing items. 2. Open Bookmarks tab.
Pass if: both appear as text cards; un-bookmarking from Briefing removes them there too.

#### BR-09 Empty feed is honest, not blank [P1] (R2, H)
Steps: 1. Fresh install, Airplane ON, no cache/seed (or SEC-09 build).
Pass if: `No Briefing Yet`-style empty state with a recovery hint; recovers on reconnect. Never a blank
screen or eternal spinner.

---

## Suite CH — Channels tab (R2, R3, R5.2)

#### CH-01 Directory: 23 sources, searchable, pill labels exact [P0] (R3)
Steps: 1. Open Channels. 2. Count entries (expect 23 on the reference week). 3. Type 3 queries in search
(name + category). 4. Read every category pill.
Pass if: search filters by name AND category; pills read exactly `Tech & AI`, `Health & Bio`,
`Science & Deep` (or News) — never raw `tech`/`deep_explainer`/`news_feed` verbatim, never uppercased slugs.

#### CH-02 Expandable breakdown shows every item [P0] (R2)
Steps: 1. Expand a multi-item channel (e.g. 6-item MIT/IBM-style channel on the reference week).
Pass if: every video/article disclosed with title, markdown summary, duration, and Watch/Read + `+ Queue`
actions; collapse/expand is instant.

#### CH-03 Markdown renders rich, no leak [P0] (R2, F)
Steps: 1. Read 5 expanded summaries containing bold/bullets/entities.
Pass if: bold keywords bold (no literal `**`), real bullet/numbered lists, `&amp;`/`&lt;` decoded —
no raw HTML tags, no `\(…)` artifacts.

#### CH-04 Title tap one-way marks; checkbox toggles [P0] (R5.2)
Steps: 1. Tap a video title → verify watched (one-way: stays watched). 2. Tap its checkbox → unwatched.
3. Tap checkbox again → watched.
Pass if: title tap never unmarks; checkbox toggles both ways with animation; watched videos sink within
the expanded list with original numbering intact.

#### CH-05 Channel completion header exact [P0] (R2)
Steps: 1. Mark every video in one channel watched.
Pass if: header flips to exactly `✓ Channel Completed`; unmarking one video flips it back to `n/m Completed`.

#### CH-06 Listen pill proportional + Queue [P0] (R2, R3)
Steps: 1. Inspect the action bar on 3 channels. 2. Tap `Listen` then `+ Queue`.
Pass if: `Listen` is a proportional pill (not a full-width stretched bar) beside `+ Queue`; both respond;
`+ Queue` enqueues the channel mix without marking videos read (see BR-06).

#### CH-07 "Listen Unwatched" skips watched [P0] (R2, X.5)
Steps: 1. Mark half a channel's videos watched. 2. Tap `Listen` (unwatched playback).
Pass if: playback covers only the remaining unwatched summaries — watched ones are skipped, including
items marked watched from the web reader (video-id/URL alias match, not just in-app ids).

#### CH-08 No fabricated durations [P1] (R2, H/T)
Steps: 1. Find a channel with unknown read time and a queue label with unknown duration.
Pass if: no invented `4m`/`14m`-style values — unknown times hide the `· Nm` separator (or show honest
totals from real `durationSeconds`); never a hard-coded placeholder.

---

## Suite BK — Bookmarks tab (R2)

#### BK-01 Save / remove round-trip [P0] (R2)
Steps: 1. Bookmark items from Briefing AND Channels. 2. Remove one from the Bookmarks tab.
Pass if: saves appear instantly as clean text cards; removal is instant in both directions.

#### BK-02 Unlimited, text-only, no audio bloat [P0] (R2, C)
Steps: 1. Bookmark 10+ items (past any historical cap). 2. Confirm each card is text summary only.
Pass if: all retained (no eviction at any small cap); no audio players/download weight on bookmark cards;
list stays snappy.

#### BK-03 Bookmarks survive relaunch + sync [P0] (R2)
Steps: 1. Bookmark 2 items. 2. Force-quit → relaunch. 3. (If paired) check the second peer.
Pass if: bookmarks persist locally and propagate to the peer; removals propagate too.

#### BK-04 Empty state honest [P2] (R3)
Steps: 1. Fresh install → open Bookmarks.
Pass if: friendly empty card, no dead controls.

---

## Suite PD — Player deck, queue & audio engine (R1, R2, R3, R5.5)

#### PD-01 Mini-player floats with live badge [P0] (R3)
Steps: 1. Enqueue 3 items. 2. Switch across all 3 tabs.
Pass if: mini-player floats above the tab bar on every tab showing track title + `3 in Queue` badge;
tap slides up the Commute Deck & Queue sheet.

#### PD-02 Deck artwork + scrubber match the redesign [P0] (R5.5)
Steps: 1. Open the Deck. 2. Inspect artwork, scrubber, time labels.
Pass if: refined ~180pt artwork card (rounded, shadow, gradient — NOT an oversized neon square);
custom capsule scrubber with smooth drag and mono `MM:SS / MM:SS` labels; no standard-slider look.

#### PD-03 Transport: 15 s skip, play, speed [P0] (R2, R5.5)
Steps: 1. Play a real episode. 2. Tap −15 s / +15 s, pause/resume, cycle speed (expect 1.0×→1.25×→…).
Pass if: skips jump ±15 s, play/pause is instant on a large central target, speed pill cycles including
1.25×; all targets thumb-comfortable (56pt floor) with no mis-taps; VoiceOver labels present.

#### PD-04 Up Next: reorder + swipe-delete + empty state [P0] (R2, R5.5, D)
Steps: 1. Queue 4 items, open Deck. 2. Drag-reorder middle → top. 3. Swipe-delete one. 4. Remove all.
Pass if: reorder sticks with no crash (incl. rapid drags); swipe-delete removes exactly one; empty queue
shows the honest empty card; count badge tracks throughout. (Old bug: reorder crashed on stale indices.)

#### PD-05 Streaming starts fast on good network [P0] (R1, R2)
Steps: 1. On Wi-Fi/good cellular, tap Play on a channel summary.
Pass if: audio starts within ~2–3 s; scrubber/duration populate with real values (never a fake
`14:48`-style default, never `Weekly Briefing Audio` placeholder title).

#### PD-06 Relative audio URLs play [P0] (R2, E)
Steps: 1. Play an item whose `audio_url` is relative (`audio/…`, per the Pages layout).
Pass if: resolves and plays over http(s); never silent-fake-playing. Host cross-check: `data.json`
audio fields that are relative must all resolve under the Pages base.

#### PD-07 Track end is honest [P1] (R2, E)
Steps: 1. Play a short clip to completion.
Pass if: play/pause icon + Now Playing flip to paused/idle at end; no stuck "playing" with silence.

#### PD-08 Seek/skip clamp, no poison [P1] (E)
Steps: 1. During early buffering (unknown duration), drag scrubber to both ends + hammer ±15 s.
Pass if: no crash, no NaN time labels, position clamps sanely; recovers when duration lands.

#### PD-09 Haptics present [P1] (R1)
Steps: 1. Mark read, bookmark, queue, transport taps.
Pass if: light taps on actions, success confirmation on mark/bookmark. (Feel, not sight.)

#### PD-10 Background + tunnel behavior [P0] (R1)
Steps: 1. Play, background the app (audio continues). 2. Airplane ON mid-play (cached portion continues).
Pass if: background audio persists via the audio entitlement; dead zones degrade to cached audio, never a
crash; foregrounding revalidates (see RF).

---

## Suite RF — Zero-input refresh & caching (R2)

#### RF-01 Launch auto-refreshes silently [P0] (R2)
Steps: 1. Publish/await a new weekly digest remotely. 2. Launch (or foreground) the app, touch nothing.
Pass if: new week appears atomically with no manual pull, no full-screen loader blocking the old feed,
no interruption of what the user was reading.

#### RF-02 Foreground revalidates [P0] (R2)
Steps: 1. Background the app. 2. Publish a digest change. 3. Foreground.
Pass if: refresh triggers on foreground transition (same silent single-flight behavior as launch).

#### RF-03 Offline keeps serving cache silently [P0] (R2, B)
Steps: 1. Load feed online. 2. Airplane ON. 3. Force-quit → launch, navigate all tabs.
Pass if: full local feed usable, zero error popups; sync failures equally silent (no blocking alerts).

#### RF-04 Rapid launches don't stampede [P1] (R2, B)
Steps: 1. Kill + launch 3× in quick succession on a slow network.
Pass if: one effective fetch (no duplicated spinners, no interleaved/corrupt feed, no crash).

---

## Suite SY — Cloudflare sync (R2, R5.3)

Pre: Settings sheet open. Default endpoint must read `https://tubelm-sync.kedarvreddy.workers.dev`
(old `vkr1729.workers.dev` must be gone). After every mutation wait ≥5 s before checking the peer.

#### SY-01 Pairing surface: endpoint + passphrase + status [P0] (R5.3)
Steps: 1. Open Settings (toolbar sync button). 2. Inspect fields with empty vs filled passphrase.
Pass if: persistent worker-URL + passphrase inputs; visual status reads `Synced ✓` / `Connecting…` /
error, or a clear local-only mode when the passphrase is empty. Settings persist across relaunch.

#### SY-02 Watched state syncs phone → peer [P0] (R2, R5.3)
Steps: 1. Pair both peers. 2. Mark 2 items watched on the phone. 3. Check the peer.
Pass if: peer shows both watched within seconds; HTTP 200s on the wire; no manual sync button needed.

#### SY-03 Cross-key matching: video_id / URL / normalized [P0] (R5.3, X.5)
Steps: 1. On the peer, mark a YouTube video watched via its `watch?v=` URL form. 2. Check the phone's
Briefing + expanded channel row for the same video (different id shape: raw `video_id` vs URL).
Pass if: phone shows it watched — matching works across `video_id`, raw URL, and normalized URL forms
in both directions (also covers CH-07's alias case).

#### SY-04 Unmark tombstones sync and survive relaunch [P0] (C)
Steps: 1. Unmark a watched item on the phone. 2. Force-quit → relaunch. 3. Check the peer.
Pass if: item stays unwatched after relaunch AND peer shows unwatched (negative tombstone won —
unmark is not re-persisted as read).

#### SY-05 Queue + bookmark mutations auto-push [P0] (R2)
Steps: 1. Queue an item + bookmark an item on the phone. 2. Check the peer (where the peer models them).
Pass if: both propagate in the background with no manual action; failures never interrupt the user.

#### SY-06 Unpaired / wrong key degrades to local [P1] (R2, A)
Steps: 1. Clear the passphrase (or enter a wrong one). 2. Mark items, queue, bookmark.
Pass if: everything works locally; status shows local-only/error; re-pairing re-converges without loss.

#### SY-07 Conflict converges, newest intent wins [P1] (C, J)
Steps: 1. Mark item X watched on phone, unwatched on peer (near-simultaneous). 2. Let both settle.
Pass if: both peers converge to the same (most-recent) state; no flapping, no duplicates.

---

## Suite TH — Theme & visual lock (R3, R5.1)

#### TH-01 Light Mode default, crisp out of the box [P0] (R5.1)
Steps: 1. Fresh install, launch.
Pass if: Light Mode active immediately (off-white cards, high-contrast text, crisp borders) — never
dark-by-default from the system theme.

#### TH-02 Three-way toggle Light / Dark / System [P0] (R5.1)
Steps: 1. Settings → cycle Light → Dark → System.
Pass if: each applies instantly across all tabs + Deck; Dark is fully legible; System follows the device;
choice persists across relaunch; default is Light.

#### TH-03 Typography hierarchy consistent [P1] (R3)
Steps: 1. Scan headlines, body, controls, timestamps across all tabs + Deck.
Pass if: serif headlines (New York), clean sans body/controls (SF Pro), monospace time/numbers; one
rhythm, no mixed-system-font drift.

#### TH-04 Strict visual hygiene [P1] (R3)
Steps: 1. Slow-scroll every tab + Deck top to bottom.
Pass if: pure signal only — no floating dev commentary, no section dividers in Briefing, no instructional
helper text, no oversized neon placeholder blocks.

---

## Suite DT — data.json contract (R2, host + device)

Run on host against the built `site/data.json` (or the fetched Pages `data.json`), then confirm on device.

#### DT-01 Schema, ids, ints [P0] (R2, G/M/N/X)
Steps (host): 1. `schema_version == 1`. 2. Every item id non-empty, ≤256 chars, unique. 3. Every
`rank`/`duration_seconds`/`read_minutes` decodes as an int (no `"abc"`, no `Inf`/`NaN`). 4. No producer
bloat keys (`candidate_id`, `summary`, `published`, bare `brief`) on mobile items; `why_it_matters`
populated; `video_id` present where the source is YouTube.
Pass if: all hold on the real file; device renders the same file with no blank cards and no whole-feed
failure from one dirty row.

#### DT-02 Audio URLs present and playable [P0] (R5.4)
Steps (host): 1. Channel `summary_audio_url`s populated for the backfilled week. 2. Each URL HEAD/GETs
200 (or resolves relatively under Pages/R2). Steps (device): 3. Play 3 channel summaries in-app.
Pass if: host URLs resolve AND all 3 play real audio (this is the §5.4 backfill proof).

---

## Suite RB — Adversarial robustness, black-box (A–X)

These replay the audit's hostile probes without reading code — via edge-fixture feeds (side-loaded
`data.json` variants or a local HTTP stub serving `data.json` shapes) where noted.

#### RB-01 Duplicate ids can't kill render [P0] (X.4)
Steps: 1. Serve a `data.json` with two items sharing one id. 2. Launch, open Briefing + Channels.
Pass if: feed renders (first-wins, rank stable); no crash, no blank tab.

#### RB-02 Dirty producer values degrade, never kill the feed [P0] (M/N/X.1)
Steps: 1. Serve rows with `rank: "abc"/Inf`, `duration_seconds: "x"/NaN`, wrong-typed
`title`/`category`, `videos: null`, 500-char ids, `audio_url: null`.
Pass if: feed renders; garbage ranks omitted (badges fall back to position), dirty numbers coerce to
sane defaults, over-long ids still match/sync or are ignored consistently — one dirty row never kills
the week, never crashes the build.

#### RB-03 Blank/whitespace sync ids rejected consistently [P1] (R/X.6)
Steps: 1. Mark/unmark normally, then attempt sync round-trips. 2. Inspect `read_state` (peer/`curl`) for
blank or whitespace-only ids.
Pass if: no blank ids persist anywhere; phone, worker (256-cap), and peer agree on key shape.

#### RB-04 Non-JSON / garbage sync bodies don't corrupt state [P1] (O)
Steps: 1. `curl` text/plain + wrong-typed fields at the worker/sync surface. 2. Re-check phone state.
Pass if: 4xx (never 500), phone state untouched, next legitimate sync succeeds.

#### RB-05 Tap-storm + rotation stability [P1] (D/E)
Steps: 1. Rapid-fire Play/queue/bookmark on several rows; rotate (where supported); background/foreground
mid-burst.
Pass if: no crash, no stuck "playing with no sound", counts and badges settle to truth.

---

## Suite PF — Commute performance & weekly loop (R1)

#### PF-01 Cold start snappy [P0] (R1)
Steps: 1. Force-quit → launch on cache, time to interactive Briefing.
Pass if: first paint ~≤2 s on warm cache, interactive promptly; scrolling immediately at 120 Hz-smooth
ProMotion with no jank on iPhone 16 (no custom-spinner stalls).

#### PF-02 Zero-touch weekly refresh [P0] (R1, R2)
Steps: 1. With a new digest published, launch with zero taps.
Pass if: week updates by itself (RF-01) — the 7–8×/week commuter never touches settings, refresh, or sync.

#### PF-03 8-session commute loop [P1] (R1)
Steps: 1. Across repeated launch→play→background→tunnel(Airplane)→foreground cycles (≥8), vary
watched/queue/bookmark state.
Pass if: zero crashes, zero state loss, zero resync-from-scratch; cache + tombstones + queue converge
every time.

---

## 5. Comprehensive test matrix

Run in order: SEC gate → BR/CH/BK → PD → RF → SY → TH → DT → RB → PF.
`SEC` steps are fully specified above; all other rows point at their case section.

| # | Case | Pri | Requirement / Audit | Type | Gate? |
|---|---|---|---|---|---|
| SEC-01 | 5 icons in IPA, exact px | P0 | R4.1, U | host | YES — stop if FAIL |
| SEC-02 | plist icon declarations resolve | P0 | R4.1 | host | YES |
| SEC-03 | Icon renders, no placeholder | P0 | R4.1 | device | YES |
| SEC-04 | Cold launch → Briefing, 10 s alive | P0 | R4.2 | device | YES |
| SEC-05 | 5× relaunch storm | P0 | R4.2 | device | YES |
| SEC-06 | plist platform keys exact | P0 | R4.2-3 | host | YES |
| SEC-07 | Empty cache → seed fallback | P0 | R4.2-1 | device | YES |
| SEC-08 | Corrupt cache quarantined + heals | P0 | R4.2-1 | device | YES |
| SEC-09 | Missing seed → honest empty, recovers | P1 | R4.2-1 | device/sim | YES (waivable) |
| SEC-10 | Launch doesn't steal bg audio | P0 | R4.2-2 | device | YES |
| SEC-11 | Session takes over only on Play | P0 | R4.2-2 | device | YES |
| SEC-12 | Unplayable item: honest idle, no steal | P0 | R4.2-2 | device | YES |
| SEC-13 | Lockscreen/remotes intact post-deferral | P1 | R4.2-2, R1 | device | YES (waivable) |
| SEC-14 | LC_CODE_SIGNATURE ad-hoc present | P0 | R4.2-4 | host | YES |
| SEC-15 | Install proves AMFI acceptance | P0 | R4.2-4 | device | YES |
| SEC-16 | packager negative controls fail loudly | P1 | harness | host | YES (waivable) |
| BR-01 | Continuous #1–#20, no splits/dividers | P0 | R3 | device | after gate |
| BR-02 | Why-It-Matters callouts | P0 | R3 | device | after gate |
| BR-03 | Watch vs Read per type + opens | P0 | R2 | device | after gate |
| BR-04 | Title tap opens + marks | P0 | R2, R5.2 | device | after gate |
| BR-05 | Watched sinks, ranks preserved | P0 | R5.2 | device | after gate |
| BR-06 | Play marks; channel Listen doesn't | P0 | R5.2 | device | after gate |
| BR-07 | +Queue + badge | P0 | R2 | device | after gate |
| BR-08 | Bookmark toggle from Briefing | P0 | R2 | device | after gate |
| BR-09 | Honest empty feed | P1 | R2 | device | after gate |
| CH-01 | 23 sources, search, exact pills | P0 | R3 | device | after gate |
| CH-02 | Expandable full breakdown | P0 | R2 | device | after gate |
| CH-03 | Markdown rich, no leak | P0 | R2, F | device | after gate |
| CH-04 | Title one-way marks; checkbox toggles | P0 | R5.2 | device | after gate |
| CH-05 | ✓ Channel Completed exact | P0 | R2 | device | after gate |
| CH-06 | Proportional Listen pill + Queue | P0 | R2, R3 | device | after gate |
| CH-07 | Listen Unwatched skips watched | P0 | R2, X.5 | device | after gate |
| CH-08 | No fabricated durations | P1 | R2, H/T | device | after gate |
| BK-01 | Save / remove round-trip | P0 | R2 | device | after gate |
| BK-02 | Unlimited text-only bookmarks | P0 | R2, C | device | after gate |
| BK-03 | Bookmarks survive relaunch + sync | P0 | R2 | device | after gate |
| BK-04 | Honest empty bookmarks | P2 | R3 | device | after gate |
| PD-01 | Mini-player + live badge | P0 | R3 | device | after gate |
| PD-02 | Deck artwork + scrubber redesign | P0 | R5.5 | device | after gate |
| PD-03 | 15 s skip, play, speed incl. 1.25× | P0 | R2, R5.5 | device | after gate |
| PD-04 | Up Next reorder + delete + empty | P0 | R2, R5.5, D | device | after gate |
| PD-05 | Fast streaming, real metadata | P0 | R1, R2 | device | after gate |
| PD-06 | Relative audio URLs play | P0 | R2, E | device | after gate |
| PD-07 | Honest track end | P1 | R2, E | device | after gate |
| PD-08 | Seek/skip clamp, no poison | P1 | E | device | after gate |
| PD-09 | Haptics present | P1 | R1 | device | after gate |
| PD-10 | Background + tunnel behavior | P0 | R1 | device | after gate |
| RF-01 | Silent auto-refresh on launch | P0 | R2 | device | after gate |
| RF-02 | Foreground revalidates | P0 | R2 | device | after gate |
| RF-03 | Offline serves cache silently | P0 | R2, B | device | after gate |
| RF-04 | No fetch stampede | P1 | R2, B | device | after gate |
| SY-01 | Pairing surface + status | P0 | R5.3 | device | after gate |
| SY-02 | Watched syncs phone → peer | P0 | R2, R5.3 | device+peer | after gate |
| SY-03 | video_id/URL/normalized matching | P0 | R5.3, X.5 | device+peer | after gate |
| SY-04 | Unmark tombstones win + persist | P0 | C | device+peer | after gate |
| SY-05 | Queue + bookmark auto-push | P0 | R2 | device+peer | after gate |
| SY-06 | Unpaired/wrong-key local degrade | P1 | R2, A | device | after gate |
| SY-07 | Conflict converges newest-wins | P1 | C, J | device+peer | after gate |
| TH-01 | Light default out of the box | P0 | R5.1 | device | after gate |
| TH-02 | Light/Dark/System toggle + persist | P0 | R5.1 | device | after gate |
| TH-03 | Typography hierarchy | P1 | R3 | device | after gate |
| TH-04 | Visual hygiene, pure signal | P1 | R3 | device | after gate |
| DT-01 | data.json schema/ids/ints | P0 | R2, G/M/N/X | host+device | after gate |
| DT-02 | Audio URLs resolve + play (backfill proof) | P0 | R5.4 | host+device | after gate |
| RB-01 | Duplicate ids render | P0 | X.4 | device+fixture | after gate |
| RB-02 | Dirty rows degrade, feed survives | P0 | M/N/X.1 | device+fixture | after gate |
| RB-03 | Blank sync ids rejected | P1 | R/X.6 | device+peer | after gate |
| RB-04 | Garbage sync bodies are 4xx, no corruption | P1 | O | host+device | after gate |
| RB-05 | Tap-storm + rotation stability | P1 | D/E | device | after gate |
| PF-01 | Snappy cold start + 120 Hz scroll | P0 | R1 | device | after gate |
| PF-02 | Zero-touch weekly refresh | P0 | R1, R2 | device | after gate |
| PF-03 | 8-session commute loop | P1 | R1 | device | after gate |

Traceability back to §4 root causes: `Bundle.module` fatalError → SEC-04/05/07/08/09 + RB-02;
eager `setActive` → SEC-10/11/12/13; missing plist keys → SEC-02/06; unsigned Mach-O → SEC-14/15/04;
missing icons → SEC-01/02/03; stale committed IPA → §2 rule + SEC-01 step 3; packager guard → SEC-16.
Traceability to §5: theme → TH-01/02; sorting → BR-04/05/06 + CH-04; sync keys → SY-01/02/03 + CH-07;
TTS pipeline → DT-02 (+ PD-05/06 device proof); deck redesign → PD-01/02/03/04.

## 6. Execution runbook

1. Record build (§2): `shasum -a 256 <IPA>`, `unzip -l`, feed `run_date`, worker URL, device/iOS/LiveContainer.
2. Host checks first (SEC-01, 02, 06, 14, 16; DT-01/02 host halves) — cheap, no install. Any P0 FAIL → reject.
3. Device gate second (SEC-03, 04, 05, 07, 08, 10, 11, 12, 15; plus 09/13 as available).
4. Only on a green gate: BR → CH → BK → PD → RF → SY (second peer ready, ≥5 s waits) → TH → RB → PF.
5. Any FAIL → defect entry (§10) with steps + expected/actual + build + feed `run_date`; continue unless P0 blocks.
6. Never flip a verdict without re-execution on a fresh build. Note P1 waivers explicitly in sign-off.

Handy host commands (copy-paste):

```bash
unzip -l TubeLM.ipa | grep -E "AppIcon.*\.png|Payload/TubeLM.app/(TubeLM|Info.plist|data.json)"
rm -rf /tmp/tubelm-uut && mkdir -p /tmp/tubelm-uut && unzip -q TubeLM.ipa -d /tmp/tubelm-uut
python3 -c "from PIL import Image; [print(f, Image.open(f'/tmp/tubelm-uut/Payload/TubeLM.app/{f}').size) for f in ['AppIcon.png','AppIcon60x60@2x.png','AppIcon60x60@3x.png','AppIcon76x76@2x.png','AppIcon83.5x83.5@2x.png']]"
plutil -p /tmp/tubelm-uut/Payload/TubeLM.app/Info.plist  # or: python3 -c "import plistlib;print(plistlib.load(open('/tmp/tubelm-uut/Payload/TubeLM.app/Info.plist','rb')))"
file /tmp/tubelm-uut/Payload/TubeLM.app/TubeLM
codesign -dv --verbose=4 /tmp/tubelm-uut/Payload/TubeLM.app 2>&1 | head -20   # macOS
otool -l /tmp/tubelm-uut/Payload/TubeLM.app/TubeLM | grep -A3 LC_CODE_SIGNATURE  # macOS
shasum -a 256 TubeLM.ipa
python3 -c "import json;d=json.load(open('site/data.json'));print(d.get('schema_version'),d.get('run_date'),len(d.get('top20',d.get('top_20',[])) if isinstance(d.get('top20',d.get('top_20',[])),list) else []),len(d.get('channels',[])))"
curl -s -o /dev/null -w "%{http_code}\n" https://vkr1729.github.io/TubeLM/data.json
```

## 7. Sign-off

| Role | Name | Build (sha256, 12 chars) | Device / iOS | Date | Verdict |
|---|---|---|---|---|---|
| Gate tester (SEC) | | | iPhone 16 / iOS 26 (LiveContainer) | | PASS / FAIL (+ defect IDs) |
| Functional tester (BR→PF) | | | iPhone 16 / iOS 26 (LiveContainer) | | PASS / FAIL |
| Owner | Kedarnath Reddy Vallaboina | | | | Accepted only when §3.4 holds |

Dissenting notes go here, not in chat threads.

## 8. Defect log template

| ID | Case | Sev (P0/P1/P2) | Steps | Expected | Actual | Build | Feed `run_date` | Status |
|---|---|---|---|---|---|---|---|---|
| DEF-001 | SEC-0x | P0 | … | … | … | … | … | open/fixed/verified |
