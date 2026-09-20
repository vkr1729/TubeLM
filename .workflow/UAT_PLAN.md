# UAT Plan — TubeLM iOS (LiveContainer Native) · Section 4 Gate

Date: 2026-09-20 · Status: ready for independent execution ·
Supersedes: UAT plan dated 2026-09-19 (that plan remains valid for regression; this plan adds a mandatory Section 4 gate in front of it)
References: `.workflow/REQUIREMENTS.md` (§1–§4), `.workflow/AUDIT_AND_REMEDIATION_REPORT.md` (§A–§W, esp. §U),
`scripts/package_ipa.sh`, `scripts/generate_icons.py`, `ios/TubeLM/Info.plist`, `.github/workflows/build-ios.yml`

## 0. Independence & purpose

This is a **black-box acceptance plan**. The tester verifies **observable behavior on device/host**
against REQUIREMENTS. No Swift/Python source reading is required or allowed for verdicts.

- The audit report is used **only for traceability** — every §4 defect gets ≥1 UAT case below.
- Verdicts come from: what the eye sees on device, what `unzip`/`plutil`/`codesign`/`otool`/`file` print on host,
  what LiveContainer/simctl report, and whether audio from another app keeps playing.
- **Accept =** shippable for single-person personal commute use (iPhone 16, iOS 26 baseline, LiveContainer).
  **Any SEC P0 failure rejects the build, regardless of regression-suite results.**

Prior automated evidence (CI simulator UAT, `swift test`, pytest) is a **precondition, not acceptance**.
Acceptance is granted only by executing this plan against the exact IPA under test.

## 1. Scope

**In scope (this gate):** REQUIREMENTS §4 in full —
§4.1 app-icon set (generate → declare → package → render) and
§4.2 launch-crash chain (Bundle fallback, deferred audio session, plist platform keys, ad-hoc signature).

**In scope (regression, condensed):** §1 profile, §2 workflows, §3 Mock-1 lock — executed **only after**
the §4 gate passes, per the 2026-09-19 plan (S0–S11, UAT-001–UAT-075). Do not re-run the full regression on a
build that fails this gate.

**Out of scope:** weekly pipeline content quality, PWA/web reader, R2 tooling, Xcode internals, unit suites.

## 2. Build under test — read this first

The repo contains a known-stale artifact: committed `ios/TubeLM.ipa` (≈2.4 MB) **predates the icon work** —
`unzip -l` shows no `AppIcon*.png` (audit §U). **Never accept against it.**

- Build under test MUST be the fresh CI artifact (`build/TubeLM.ipa` via `scripts/package_ipa.sh` /
  `Package LiveContainer IPA` workflow) or a locally rebuilt IPA from the same script.
- Record on the run sheet: IPA path, `shasum -a 256`, `unzip -l` output, feed `run_date`, worker URL,
  device model + iOS version, LiveContainer version.
- If `unzip -l <IPA>` shows anything other than **exactly the 5 icons in §5.1**, stop — the build is stale.

## 3. Test environment

### 3.1 Device & host

- iPhone 16, **iOS 26** baseline, portrait, LiveContainer installed (JIT / unsigned sideload path).
- Host (macOS or Linux) with: `unzip`, `plutil` (or `python3 -c plistlib`), `file`, `shasum`,
  plus **one** of `codesign` (macOS) / `ldid` / `otool` for signature checks. PNG dimension check via
  `python3 -c "from PIL import Image"` or `sips -g pixelWidth -g pixelHeight` (macOS) or `file`.
- Reference audio source for §5.4: any continuously playing app (Music/Podcasts/Safari audio) on the test device.
- Headphones + lockscreen available for the deferred-audio confirmation (SEC-13).

### 3.2 Clean-slate rule

Before the §4 gate: delete any prior TubeLM install from LiveContainer, clear sandbox
(`Documents/cache`, `Documents/pinned`) where accessible, and start each launch-crash case from force-quit.
Do not carry state between SEC-06–SEC-11 except where the case explicitly chains.

### 3.3 Entry criteria

1. Fresh IPA built by `scripts/package_ipa.sh` (CI log shows `✓ All 5 icon assets verified in bundle`).
2. `unzip -l` lists a non-empty `Payload/TubeLM.app/TubeLM` binary + `Info.plist`.
3. Feed reachable **or** bundled `data.json` seed present (either is fine — fallback is under test).
4. Tester holds no signing certificates (ad-hoc path is the correct path; do not re-sign with a team identity).

### 3.4 Exit / acceptance criteria

- **All SEC P0 cases pass.** Any SEC P0 FAIL = build rejected, file defect (§8), stop the run.
- At most 1 SEC P1 failure, each with logged defect + workaround; zero P2-only rejection.
- After the gate: full regression per 2026-09-19 plan meets its own §2.5 (all P0 pass).
- Sign-off table (§7) completed with build hash + device + iOS version.

## 4. Conventions

- Verdicts: **PASS / FAIL / BLOCKED / N/A**. Every FAIL needs a defect entry (§8).
- Priority: **P0** ship-blocker · **P1** must-fix-or-waive · **P2** polish.
- Tags: `R4.1` / `R4.2` = REQUIREMENTS §4 items. `U` = audit §U (stale IPA).
- IDs: `SEC-xx` = this gate (new). `UAT-xxx` = 2026-09-19 regression plan (unchanged).
- Time-boxes: launch verdict needs **≥10 s** foreground observation (AMFI kills are immediate but
  audio-session conflicts can lag). Force-quit between launch cases.

---

## 5. Section 4 gate — detailed cases

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

Design lock: emerald gradient (`#15803d`→dark), charcoal plate, lime `#d9ff63` "TL" monogram — eye-check only, no colorimeter needed.

#### SEC-01 Five icons inside the IPA, correct sizes [P0] (R4.1, U)
Type: host-only. Pre: IPA file on host.
Steps:
1. `unzip -l <IPA> | grep -E "AppIcon.*\.png"` — expect exactly the 5 rows above, under `Payload/TubeLM.app/`.
2. Unzip to a temp dir; for each PNG verify dimensions (PIL/`sips`/`file`) against the table and that each file is non-empty RGB PNG.
3. Confirm the stale-IPA signature is absent: if any of the 5 is missing → build predates icon work → FAIL, do not install.
Expect: 5/5 present, sizes exact, no `AppIcon*.png` elsewhere missing, no zero-byte file.
Pass if: `unzip -l` lists 5/5 AND dimension check is 5/5 exact.

#### SEC-02 Info.plist declares the icon set [P0] (R4.1)
Type: host-only. Pre: same temp-dir bundle from SEC-01.
Steps:
1. `plutil -p Payload/TubeLM.app/Info.plist` (or plistlib load) and check: `CFBundleIcons.CFBundlePrimaryIcon`
   (`CFBundleIconFiles` contains `AppIcon60x60`, `CFBundleIconName` = `AppIcon`);
   `CFBundleIcons~ipad.CFBundlePrimaryIcon` lists `AppIcon60x60`, `AppIcon76x76`, `AppIcon83.5x83.5`;
   top-level `CFBundleIconFile` = `AppIcon` and `CFBundleIconFiles` covers `AppIcon60x60`, `AppIcon76x76`, `AppIcon83.5x83.5`, `AppIcon`.
2. Cross-check: every `CFBundleIconFiles` stem resolves to at least one PNG from SEC-01 (iOS appends `@2x/@3x` + `.png` at runtime).
Expect: all four declaration sites present with the stems above; no typos (`Appicon`, `appIcon`), no dangling stem without a file.
Pass if: declarations exact AND every stem resolves to a packaged PNG.

#### SEC-03 Icon renders on device — no placeholder [P0] (R4.1)
Type: device. Pre: SEC-01+SEC-02 PASS; clean LiveContainer.
Steps: 1. Import IPA one-tap. 2. Inspect app icon in LiveContainer list + (where visible) iOS home screen / app library. 3. Compare against design lock (green + "TL").
Expect: crisp TubeLM icon everywhere; never the blank/white-grid iOS placeholder, never a stretched/letterboxed render.
Pass if: real icon visible post-install AND after first launch AND after reboot-of-container (LiveContainer restart).

### Group B — No launch crash (R4.2, whole chain)

#### SEC-04 Cold launch reaches Briefing, stays alive [P0] (R4.2)
Type: device. Pre: fresh install, network ON, force-quit.
Steps: 1. Tap icon. 2. Observe 10 s without touching. 3. Note first screen.
Expect: Briefing tab renders (feed cards) or honest `No Briefing Yet` empty state if offline — either is a pass;
never black screen, never instant return to LiveContainer list (AMFI-kill signature), never a crash alert.
Pass if: first screen renders within ~5 s on cache/seed AND process survives 10 s foreground.

#### SEC-05 Relaunch storm — 5 consecutive force-quit launches [P0] (R4.2)
Type: device. Pre: SEC-04 PASS.
Steps: force-quit → launch → wait to Briefing → force-quit, ×5.
Expect: 5/5 reach Briefing, no cumulative failure (catches flaky bundle-resource races the old `Bundle.module` path caused under test vs device divergence).
Pass if: 5/5 clean launches.

#### SEC-06 Info.plist platform keys present [P0] (R4.2-3)
Type: host-only.
Steps: in the same `plutil -p` output verify: `CFBundleSupportedPlatforms = ["iPhoneOS"]`,
`MinimumOSVersion = "17.0"`, `CFBundlePackageType = "APPL"`, `CFBundleSignature = "????"`,
`LSRequiresIPhoneOS = true`, `UIRequiredDeviceCapabilities` contains `arm64`,
`UILaunchScreen` dict present (may be empty), `UIBackgroundModes` contains `audio`,
`CFBundleIdentifier = com.vkr1729.tubelm`, `CFBundleExecutable = TubeLM`.
Expect: all keys exact; `MinimumOSVersion` is a floor (17.0) against the §1 iOS-26 test target — that combination is correct, not a mismatch.
Pass if: every key above present and byte-exact.

### Group C — Non-throwing cache fallback (R4.2-1)

Principle: `loadCachedFeed()` must **never throw to the UI** — corrupt/missing cache degrades to the bundled
seed or an honest empty state. The tester proves this by deleting/corrupting the cache, not by reading Swift.

#### SEC-07 First launch with empty cache falls back to seed [P0] (R4.2-1)
Type: device. Pre: fresh install (no `Documents/cache/feed.json`), network OFF (Airplane) to force the local path.
Steps: 1. Airplane ON. 2. Launch.
Expect: Briefing renders from bundled `data.json` seed (mock week: 20 items / 23 channels) OR honest `No Briefing Yet` — either acceptable; crash/blank/spinner-forever are FAIL.
Pass if: usable feed-or-empty-state with zero taps, no crash.

#### SEC-08 Corrupt cache is quarantined, app heals [P0] (R4.2-1)
Type: device (+ host where sandbox is reachable; otherwise simulator/CI log).
Steps:
1. With the app installed, plant a corrupt cache file: write garbage bytes to `Documents/cache/feed.json`
   (e.g. `CORRUPT_TRUNCATED_GARBAGE_DATA`) — on LiveContainer use its file browser if exposed; on simulator use `xcrun simctl get_app_container`.
2. Force-quit → relaunch (network ON or OFF, record which).
3. After launch, list `Documents/cache/` and look for a quarantined sibling `feed.json.corrupt.<epoch>`.
Expect: launch succeeds; feed renders from seed/network; corrupt file renamed to `*.corrupt.*` (diagnostic preserved), never left as the live `feed.json`, never a crash.
Pass if: no crash AND (quarantine file exists OR fresh valid `feed.json` rewritten) AND Briefing usable.
Note: the automated `TubeLMCoreTests.testContentStoreTwoTierAndLRUCap` covers the same path in-process; this case is its on-device twin.

#### SEC-09 Missing bundle resource still cannot crash [P1] (R4.2-1)
Type: device/simulator. Pre: build where `data.json` was deliberately removed from the bundle (repack a copy of the IPA without `Payload/TubeLM.app/data.json`, re-zip, reinstall to a scratch slot if LiveContainer allows; otherwise run on simulator).
Steps: 1. Launch offline with no cache and no bundle seed.
Expect: honest `No Briefing Yet` empty state; recovers to full feed when network returns (see UAT-011/UAT-042).
Pass if: no crash on the hardest fallback path; recovery on reconnect.

### Group D — Deferred audio session activation (R4.2-2)

Principle: `setActive(true)` must run only on explicit `play()`/`playTrack()`, never in `init`/launch.
Black-box proxy: **another app's audio must survive our launch and navigation**.

#### SEC-10 Launch does not steal background audio [P0] (R4.2-2)
Type: device. Pre: start Music/Podcasts playback, keep it audible.
Steps: 1. While external audio plays, cold-launch TubeLM. 2. Navigate all 3 tabs + open/close the Deck sheet — but press NO Play button. 3. Listen throughout.
Expect: external audio plays uninterrupted; no ducking, no pause, no TubeLM Now-Playing takeover on lockscreen.
Pass if: external audio continuous across launch + full navigation with zero TubeLM playback action.
FAIL pattern (old bug): external audio ducks/stops the moment TubeLM launches = eager activation still present.

#### SEC-11 Session activates only on explicit Play [P0] (R4.2-2)
Type: device. Pre: SEC-10 PASS, external audio still playing (or restart it).
Steps: 1. In TubeLM tap a real episode `Play`. 2. Observe: TubeLM audio starts, external audio yields (correct), lockscreen Now Playing shows TubeLM title/source/elapsed.
Expect: takeover happens exactly at the Play tap — not before.
Pass if: pre-Play silence from TubeLM + post-Play proper takeover with live metadata.

#### SEC-12 Unplayable item never activates session or fakes playback [P0] (R4.2-2 + honest-idle)
Type: device. Pre: feed row with empty/missing `audio_url` (synthetic edge feed or airplane-blocked stream that resolves to nothing playable).
Steps: 1. Tap `Play` on the unplayable item.
Expect: honest idle — `Nothing Playing`/`Pick an episode`, `isPlaying=false` equivalent (play icon stays "play", no progress phantom), external audio (if any) NOT stolen, no crash.
Pass if: idle UI, no stuck "playing with no sound", no session steal.

#### SEC-13 Lockscreen/headphone remotes still work after deferral [P1] (R4.2-2 + R1 audio)
Type: device. Pre: playing a real episode.
Steps: 1. Lock phone → check Now Playing metadata/progress. 2. Headphone play/pause + Control Center.
Expect: identical to pre-fix behavior once playback starts — deferral changed *when* the session activates, not remote handling.
Pass if: lockscreen + headphones fully drive playback.

### Group E — Ad-hoc code signature (R4.2-4)

#### SEC-14 Mach-O carries LC_CODE_SIGNATURE, ad-hoc [P0] (R4.2-4)
Type: host-only. Pre: extracted `Payload/TubeLM.app/TubeLM` from SEC-01.
Steps:
1. `file Payload/TubeLM.app/TubeLM` → expect `Mach-O 64-bit executable, arm64` (however the CI `file` words it, arch must be arm64).
2. `otool -l Payload/TubeLM.app/TubeLM | grep -A3 LC_CODE_SIGNATURE` (macOS) — expect the segment present; on Linux, `llvm-readobj --sections` or CI log line `Applying ad-hoc code signature via codesign/ldid` is acceptable proxy.
3. macOS only: `codesign -dv --verbose=4 Payload/TubeLM.app 2>&1 | grep -i "adhoc\|Signature"` → expect ad-hoc identity (`Signature=adhoc` / `CodeDirectory …adhoc`).
Expect: signature block present; binary non-empty with exec bit; CI refused to ship a binary-less Payload (empty-IPA guard).
Pass if: arch=arm64 AND signature evidence present AND binary non-trivial size.

#### SEC-15 Device install proves AMFI acceptance [P0] (R4.2-4)
Type: device. Pre: SEC-14 PASS.
Steps: 1. Import unsigned IPA one-tap into LiveContainer (no certs, no prompts expected). 2. Launch, keep foreground 10 s. 3. Background mid-playback, foreground again.
Expect: installs without signing/entitlement prompts; process is NOT SIGKILLed on launch (the old unsigned Mach-O died before first frame); background audio continues (audio-only entitlement suffices).
Pass if: install + 10 s foreground + background/foreground cycle with zero kills.

#### SEC-16 Packaging script validation is enforced, not decorative [P1] (packaging harness)
Type: host (negative control). Pre: a scratch copy of a valid `.app` dir.
Steps:
1. Delete one icon from the scratch copy, run `scripts/package_ipa.sh <scratch.app> /tmp/neg-test.ipa` → expect non-zero exit naming the missing icon.
2. Restore icons, delete the `TubeLM` binary, re-run → expect `::error::Missing TubeLM binary` non-zero exit.
Expect: script fails loudly on both mutilations (this is what prevents the old silent green empty-IPA artifact).
Pass if: both negative runs exit non-zero with the naming error.

---

## 6. Comprehensive test matrix (gate + regression index)

Run rows in order. `SEC` = this gate (full steps above). `UAT` = 2026-09-19 plan (full steps there — not repeated here).

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
| SEC-09 | Missing seed → honest empty, recovers | P1 | R4.2-1 | device/sim | YES (waivable w/ defect) |
| SEC-10 | Launch doesn't steal bg audio | P0 | R4.2-2 | device | YES |
| SEC-11 | Session takes over only on Play | P0 | R4.2-2 | device | YES |
| SEC-12 | Unplayable item: honest idle, no steal | P0 | R4.2-2 | device | YES |
| SEC-13 | Lockscreen/remotes intact post-deferral | P1 | R4.2-2, R1 | device | YES (waivable w/ defect) |
| SEC-14 | LC_CODE_SIGNATURE ad-hoc present | P0 | R4.2-4 | host | YES |
| SEC-15 | Install proves AMFI acceptance | P0 | R4.2-4 | device | YES |
| SEC-16 | packager negative controls fail loudly | P1 | harness | host | YES (waivable w/ defect) |
| UAT-001–004 | Install, non-empty IPA, plist audio/encrypt, unsigned-correct | P0/P1 | R2-out, I, J | mixed | after gate |
| UAT-005–012 | Briefing feed, callouts, Watch/Read, taps, queue/bookmark, offline empty, link validation | P0/P1 | R2/R3, F, H | device | after gate |
| UAT-013–021 | Channels search/pills/expand/markdown/completion/Listen/unwatched/durations | P0/P1 | R2/R3, F/H/E | device | after gate |
| UAT-022–025 | Bookmarks save/remove/unlimited/cards/empty | P0/P1/P2 | R2, C | device | after gate |
| UAT-026–038 | Mini-player, Deck, targets, queue ops, streaming, relative URLs, idle, track-end, seek, remotes, bg-audio, tunnel | P0/P1 | R1/R2/R3, D, E | device | after gate |
| UAT-039–043 | SWR refresh, foreground, single-flight, offline cache, timeouts | P0/P1 | R2, B | device | after gate |
| UAT-044–052 | Sync pairing/local-only/autopush/contract/convergence/tombstones/conflicts/auth/headers | P0/P1 | R2, A, C, J | device+curl | after gate |
| UAT-053–056 | Persistence LRU/NaN/atomic/purge-exempt | P0/P1 | C, B | device | after gate |
| UAT-057–061 | data.json schema/ids/ints/payload-shape/bucket | P0/P1 | R2, G, H | host+device | after gate |
| UAT-062–066 | Visual lock, themes, type, haptics, ProMotion | P0/P1 | R3, H, J | device | after gate |
| UAT-067–072 | Adversarial: reorder/payloads/injection/audio-edges/tap-storm/rotation | P0/P1/P2 | D/C/F/E/I | device | after gate |
| UAT-073–075 | Commute performance: cold start, zero-touch week, 8-session loop | P0/P1 | R1, R2 | device | after gate |

Traceability back to §4 root causes: `Bundle.module` fatalError → SEC-04/05/07/08/09; eager `setActive` →
SEC-10/11/12/13; missing plist keys → SEC-02/06 (+ UAT-003); unsigned Mach-O → SEC-14/15/04;
missing icons → SEC-01/02/03; stale committed IPA → §2 rule + SEC-01 step 3; packager guard → SEC-16.

## 7. Execution runbook

1. Record build (§2): `shasum -a 256 <IPA>`, `unzip -l`, feed `run_date`, worker URL, device/iOS/LiveContainer versions.
2. Host checks first (SEC-01, 02, 06, 14, 16) — cheap, no install. Any P0 FAIL → reject before touching the device.
3. Device gate second (SEC-03, 04, 05, 07, 08, 10, 11, 12, 15; plus 09/13 as available).
4. Only on a green gate: run regression UAT-001–UAT-075 per the 2026-09-19 runbook (S0→S11, second sync peer ready for S6, ≥5 s waits after mutations for the 1.5 s debounce).
5. Any FAIL → defect entry (§8) with steps + expected/actual + build + feed `run_date`; continue unless a P0 blocks.
6. Never flip a verdict without re-execution on a fresh build. Note waivers for P1s explicitly in sign-off.

Handy host commands (copy-paste):

```bash
unzip -l TubeLM.ipa | grep -E "AppIcon.*\.png|Payload/TubeLM.app/(TubeLM|Info.plist|data.json)"
rm -rf /tmp/tubelm-uut && mkdir -p /tmp/tubelm-uut && unzip -q TubeLM.ipa -d /tmp/tubelm-uut
python3 -c "from PIL import Image; [print(f, Image.open(f'\"/tmp/tubelm-uut/Payload/TubeLM.app/{f}\"').size) for f in ['AppIcon.png','AppIcon60x60@2x.png','AppIcon60x60@3x.png','AppIcon76x76@2x.png','AppIcon83.5x83.5@2x.png']]"
plutil -p /tmp/tubelm-uut/Payload/TubeLM.app/Info.plist  # or: python3 -c "import plistlib;print(plistlib.load(open('/tmp/tubelm-uut/Payload/TubeLM.app/Info.plist','rb')))"
file /tmp/tubelm-uut/Payload/TubeLM.app/TubeLM
codesign -dv --verbose=4 /tmp/tubelm-uut/Payload/TubeLM.app 2>&1 | head -20   # macOS
otool -l /tmp/tubelm-uut/Payload/TubeLM.app/TubeLM | grep -A3 LC_CODE_SIGNATURE  # macOS
shasum -a 256 TubeLM.ipa
```

## 8. Sign-off

| Role | Name | Build (sha256, 12 chars) | Device / iOS | Date | Verdict |
|---|---|---|---|---|---|
| §4-gate tester | | | iPhone 16 / iOS 26 (LiveContainer) | | PASS / FAIL (+ defect IDs) |
| Regression tester | | | iPhone 16 / iOS 26 (LiveContainer) | | PASS / FAIL |
| Owner | Kedarnath Reddy Vallaboina | | | | Accepted only when §3.4 holds |

Dissenting notes go here, not in chat threads.

## 9. Defect log template

| ID | Case | Sev (P0/P1/P2) | Steps | Expected | Actual | Build | Feed `run_date` | Status |
|---|---|---|---|---|---|---|---|---|
| DEF-001 | SEC-0x | P0 | … | … | … | … | … | open/fixed/verified |
