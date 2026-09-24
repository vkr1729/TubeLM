# Frontier Requirements Review — TubeLM Web & Mobile Sync

Source: `.workflow/REQUIREMENTS.md` (working-tree rewrite, uncommitted diff vs `main`: +62/−109)
Date: 2026-09-24
Reviewer: Muse Spark (verified against `desktop/web_reader.py`, `desktop/tts_service.py`,
`desktop/main.py`, `desktop/top10_service.py`, `desktop/email_service.py`,
`desktop/scripts/`, `desktop/templates/reader.html`, `ios/Sources`, `.github/workflows/`)

> Note: the prior review in this file (2026-09-20, old REQUIREMENTS §5: theme default,
> watched-to-bottom, sync identity, TTS asyncio, player deck) is superseded by the
> REQUIREMENTS rewrite and preserved in git history. This review covers only the new
> scope (§2 A–D). The later plan-level findings in `.workflow/FRONTIER_PLAN_REVIEW.md`
> (schema divergence resolved, worker sync contract, LiveContainer audio spike) still stand
> where they do not conflict with the new requirements.

## Target User Scale Anchor

**Single-Person Personal Use Exclusively** (§1) — hard constraint carried through every
recommendation:

- Reject enterprise complexity: no auth frameworks, no microservices, no distributed DBs,
  no maintained backend logic, no new dependencies for a one-user weekly job.
- Hosts: GitHub Pages static site + Cloudflare Worker/R2 (already deployed) + sideloaded
  `.ipa` in LiveContainer on iOS.
- Every Q below is answered with the cheapest pipeline-local or client-local fix;
  anything requiring per-user ops, server state changes, or background daemons is flagged
  as anchor-violating.

---

## Q1 — §2.A: Which N is canonical, and does the regex contradict §2.B?

**Ambiguity:** §2.A mandates matching `r".*_TubeLM_Top_(\d+)(?:_interim)?_digest\.(html|json)$"`
while §2.B bans interim files from ever being created. The digest count N has at least
four competing definitions (filename digits, `len(items)`, `candidate_count`,
`cfg.top_digest_count`), and "everywhere file matching occurs" is not enumerated. The
empty-digest case (N=0) is unspecified despite the iOS gate on non-empty items.

**Code-verified edge cases / failure modes:**
- Hardcoded match sites beyond the two named files: `web_reader.py:1061`
  (`"Top_20" in f.name or "Top_10" in ...`), `tts_service.py:255` (same check),
  `desktop/scripts/download_top10.py:31` (glob `*_TubeLM_Top_*_digest.html`),
  `desktop/scripts/send_top10_from_digests.py:48` (`"TubeLM_Top_" in name`).
- Filename N is informational only: `rank_top10_candidates` silently shrinks the target
  via `effective_target_count = min(requested_count, len(candidates))`
  (`top10_service.py:390`), so a "Top 20" request yields a `Top_14` file — the Top 14
  breakdown in the primary objective is this line working as coded, not a separate bug.
- `candidate_count` is always overwritten with `len()` after dedupe (`web_reader.py:1148`;
  mobile export `web_reader.py:1237`), so `top20.candidate_count: N` can never disagree
  with `len(items)` — the contract as written is untestable.
- Display caps contradict dynamic-N: iOS `BriefingView.swift:50` does `prefix(20)`
  (a Top 25 silently loses 5 items), `reader.html:2744` hardcodes "Top 20 curated videos",
  and RSS truncates to `top20_items[:10]` (`web_reader.py:763`).
- N=0: `ContentStore.swift` requires `!feed.top20.items.isEmpty` (4 sites), so a
  zero-candidate week renders as blank/seed state with no specified fallback.

**Recommended approach:**
- Canonical N = `len(final items after dedupe)`; filename digits are a hint, never parsed
  for display. Drop `(?:_interim)?` from the canonical regex (interim is banned — matching
  it re-admits the removed concept); instead do a one-time sweep deleting stale
  `*_interim_digest.*` files (see Q3).
- Enumerate and convert all five match sites above to the single regex helper; add a test
  with Top_14/Top_20/Top_25 filenames plus a stale-interim file asserting skip-or-sweep.
- Replace `prefix(20)` / hardcoded "Top 20" / `[:10]` with the dynamic count (or record an
  explicit cap policy, e.g. "display all, RSS first 10" — state it, don't leave it).
- Define N=0 explicitly: render an honest empty state ("No Top picks this week — N
  candidates") rather than the corrupt-cache path.
- Anchor-fit: pure pipeline + template string changes, no infra.

**Alternatives:**
- Keep `(?:_interim)?` in the regex as stale-file tolerance — defensible, but it silently
  preserves the removed feature's surface; rejected unless Q3 decides stale files linger.
- Pad/truncate selection to exactly `top_digest_count` — predictable UI, but fabricates
  rankings (pad) or discards signal (truncate) for one reader; rejected.
- Treat filename N as canonical — breaks the day `min()` shrinks the set; rejected.

**Decision needed:** Confirm len-after-dedupe as canonical N, interim-free regex, the five
match sites as the complete list, and the N=0 empty-state wording.

## Q2 — §2.B: What exactly is "success rate," and what does partial publish disclose?

**Ambiguity:** The 80%/70%/unconditional thresholds name a "success rate" with no
numerator, denominator, or cumulative-vs-per-stage semantics. "Proceed to digest
generation and publish" after Iteration 3 at <70% does not say what a partial digest
contains or discloses. The mapping onto the existing fixed 3-stage loop is undefined.

**Code-verified edge cases / failure modes:**
- No gating exists today: `main.py:587-591` runs Initial/Fast-Retry-1/Fast-Retry-2
  unconditionally with fixed 30s/60s delays; the only threshold is the interim trigger
  (`completion_ratio >= 0.70` at `main.py:795-815`) — which §2.B deletes along with the
  interim itself.
- Counting is non-obvious: sources with no new content count as success
  (`main.py:634-637`), transient discovery failures (`items is None`, `:629-632`) count as
  failed, and a quota-deferral (`quota_deferred_until`, `:691-697`) breaks the stage loop
  — none of these are assigned to the rate.
- `completed_source_keys` (`main.py:594`) is already a cumulative set across stages, so
  the machinery for a cumulative rate exists; but "retry failed sources" vs "reprocess
  all" matters because the Top-10 batch accumulates via `record_top10_source`
  (`main.py:729-732`) — reprocessing successes would double-record candidates.
- With ~23 sources, 80% = 19 and 70% = 17 (rounding unspecified); one flaky source can
  force a full extra iteration for zero gain.

**Recommended approach:**
- Rate = `|completed_source_keys| / total_initial_handlers`, evaluated cumulatively after
  each stage; keep no-new-content as success; quota-deferral pauses the run (neither
  success nor retry-trigger — it exits to the existing deferral path).
- Map Iteration 1/2/3 onto the existing three stages with gate checks between; retries
  process only `failed_handlers`, never successes (protects batch accumulation).
- Partial publish carries a one-line disclosure in the digest ("Built from X of Y
  sources; Z deferred") so the single reader knows coverage without any new system.
- Anchor-fit: ~20 lines of gating around the existing loop, no new scheduling.

**Alternatives:**
- Always run all 3 stages (status quo minus interim) — most predictable runtime for a
  weekly cron, but wastes up to 90s + API calls when Iteration 1 is already clean;
  acceptable fallback if thresholds prove flaky.
- Time-box retries instead of percentage gates — simpler to reason about, but restarts
  the tuning debate (how long?) the percentages already settled; rejected.

**Decision needed:** Confirm cumulative-rate definition, retry-only-failures, rounding
(ceil vs floor at 80%/70%), and the partial-publish disclosure line.

## Q3 — §2.B: What is the full blast radius of "completely remove interim"?

**Ambiguity:** §2.B names `desktop/main.py` and `desktop/top10_service.py`, but interim
logic leaks into at least four more surfaces, plus on-disk and in-state leftovers. No
disposition is given for stale interim files or old batch state.

**Code-verified edge cases / failure modes:**
- `top10_service.py`: `is_interim` parameter + branch (`:501-516`), batch fields
  `interim_sent_at`/`interim_candidate_count`/`interim_selected_candidate_ids`
  (`:510-514`), the final-identical-to-interim skip path (`:518-529`), `_interim` filename
  suffix (`:570`), `rotate_downloads=(not had_interim)` coupling (`:538`).
- `email_service.py`: `is_interim` → "EARLY EDITION" and `is_final_after_interim` →
  "FINAL EDITION" labels (`:201-204`, `:416-421`) — dead labels after removal unless cut.
- `main.py`: `interim_top10_sent` flag + Stage-0 trigger block (`:596`, `:795-815`).
- Leftovers: prior runs' `*_interim_digest.html/.json` files on disk still match the §2.A
  regex if `(?:_interim)?` survives (see Q1); old batch JSON with `interim_sent_at` set
  must still parse; tests referencing interim behavior will fail.

**Recommended approach:**
- Single removal checklist: `main.py` trigger block + flag; `top10_service.py` param,
  both branches, suffix, batch fields (tolerant-read old keys, never write them),
  `rotate_downloads` constant; `email_service.py` edition labels; scripts + tests updated;
  one-time startup sweep deleting `*_interim_digest.*` (log what was swept).
- Verify by grep: zero hits for `is_interim|interim_sent_at|final_after_interim` outside
  the tolerant-read shim, plus a test asserting no interim artifacts after a full run.
- Anchor-fit: deletion-only change, zero new runtime behavior.

**Alternatives:**
- Keep interim behind a config flag — directly contradicts the decision log (Q4:
  "Completely remove"); rejected.
- Leave dead code paths in place — zero behavior risk today, but the next reader (or
  model) will re-trigger the interim path by accident; rejected.

**Decision needed:** Confirm delete-vs-ignore for stale on-disk interim files, and that
tolerant-read of old batch fields (without migrating them) is sufficient.

## Q4 — §2.C: Where does each audio fix actually live? (Build-time vs client)

**Ambiguity:** §2.C prescribes fixes at specific layers, but the data flow already
resolves audio upstream of two of the three prescribed fixes — so the symptom locations
named may not be the defect locations. Each sub-item has an unspecified exact semantic.

**Code-verified edge cases / failure modes:**
- Pipeline already embeds fallback audio: `_normalize_mobile_item` and
  `_normalize_mobile_video` take `fallback_audio`, and the `data.json` exporter passes
  `channel_audio_map` (`web_reader.py:1231-1232`), so `item.audio_url` is pre-resolved.
  `RootTabView.resolveAudioUrl` (`:530-544`) is therefore a second-chance path hit only
  when build-time resolution missed — and the miss happens at build time:
  `channel_audio_map` keys are exact lowercased names (`web_reader.py:1220`), so
  `Peter Attia, MD` (item `source_name`) vs `Peter Attia MD` (channel name) never joins.
  Fuzzy matching in Swift patches over a build-time key bug per item per launch.
- `buildQueue` is NotebookLM-only *by design comment* (`reader.html:3163` "ONLY
  NotebookLM podcasts! Keep TTS completely separate"): mixing summaries in changes queue
  identity (`isSummary` flag, `isHeard(src)` keys, title/category sort). "Include
  summaries when podcasts are absent" needs the per-channel vs whole-queue trigger
  defined, or one missing podcast flips the entire queue to TTS.
- `playIndex` (`reader.html:3192-3217`) double-starts playback (`begin()` immediately at
  `:3213` AND on `loadedmetadata` at `:3210`); errors are swallowed (`.catch(() => {})`
  at `:3201`). The fix order matters: set `src` → await `canplay` → `play()` →
  update icons from the promise outcome, not optimistically at `:3214-3215`.
- `AudioPlayerManager.playTrack` (`:101-104`) resolves via `URL(string:relativeTo:)`
  against the Pages base — pre-encoding the string first (as prescribed) breaks relative
  resolution of `audio/...` paths; only the absolute-URL branch (R2 `https://...`) needs
  sanitizing. `player.playImmediately(atRate:)` is for pre-rolled items and skips the
  stall-recovery the same bullet asks to observe; `play()` + rate (already at `:113-114`)
  is the correct primitive. No `AVPlayerItem.status` observation exists — adding KVO
  needs a lifetime rule (observer tied to current item, torn down on replace) or it
  leaks/over-fires across track changes.
- Channel Audio Overview card renders only when `ch.has_audio && ch.audio_url`
  (`reader.html:2823`); summary-listen buttons already exist in channel views (`:2929`,
  `:3049`) — whether Editorial Picks cards have them is unverified and is the actual gap
  to check, not the channel views.

**Recommended approach:**
- Fix the join at build time: normalize `channel_audio_map` keys (lowercase, strip
  punctuation/extra spaces) and apply the same normalization to `source_name` lookup —
  one function, tested with the `Peter Attia` / `Nutrition Made Simple!` pairs; keep the
  iOS exact-match fallback as-is (no fuzzy engine).
- `buildQueue`: per-channel fallback (a channel contributes its `summary_audio_url`
  only when it has no `audio_url`), preserving the NotebookLM-first ordering; explicit
  `isSummary` flags so `isHeard` keys never collide.
- `playIndex`: single-start (await `canplay`, then one `play()`), icon state driven by
  the promise + `playing`/`pause` events, errors surfaced to the mini-player, never
  swallowed.
- iOS: sanitize-and-encode only absolute URLs before `URL(string:)`; keep relative
  resolution untouched; keep `play()` + rate; add item-scoped `status` observation with
  teardown on `replaceCurrentItem`.
- Anchor-fit: no new deps, no server change, no audio re-encoding.

**Alternatives:**
- Full fuzzy/slug engine in Swift — fixes display-time misses but re-runs per launch
  and diverges from the pipeline's keys; rejected in favor of the build-time join.
- Unified queue always mixing podcasts + summaries — simplest code, but destroys the
  deliberate separation the comment documents and doubles queue length; rejected.
- `playImmediately(atRate:)` everywhere — lower latency on pre-rolled items, but wrong
  primitive for cold URL loads and fights stall handling; rejected.

**Decision needed:** Confirm build-time normalized join (and the normalization rule),
per-channel vs whole-queue TTS fallback trigger, promise-driven icon semantics, and the
item-scoped KVO lifetime for `AVPlayerItem.status`.

## Q5 — §2.D: What are the runnable exit criteria for UAT, CI, and deploy?

**Ambiguity:** §2.D names activities (Playwright UAT, CI build, deploy) without targets,
assertions, or actors. "Push changes to GitHub" is process, not product. Headless audio
verification, theme assertions, viewport breakpoints, the `verify.yml` role, and the
deploy safety gates are all unspecified — and deploy has a hard refusal path that can
fail the whole stage.

**Code-verified edge cases / failure modes:**
- Playwright harnesses already exist (`desktop/scripts/run_browser_uat.py`,
  `desktop/scripts/test_gui_e2e.py`) but §2.D does not say whether the target is
  `file://`, a localhost server, or the live Pages URL — `file://` breaks `fetch`-based
  `data.json` loads; live-URL testing conflates deploy lag with regressions.
- Headless Chromium autoplay policy blocks audible `.play()`; "verify audio playback
  controls and audio element loading" cannot mean audible playback without a headed
  browser + fake audio device. What *is* assertable: controls present, `src` resolves
  HTTP 200, `canplay` fires.
- Theme contract exists (`localStorage 'tubelm-theme'`, `data-theme`, `reader.html:31-33`)
  but no assertion pins it; responsive breakpoints are undefined.
- CI already does the named work (`build-ios.yml`: Core tests → simulator UAT +
  screenshot → release build → `package_ipa.sh` → IPA commit). `verify.yml`'s role in
  this stage is unstated — duplicate gate or separate lint/unit lane?
- Deploy can hard-fail: `deploy_to_gh_pages` refuses any file > 5 MB (`web_reader.py:1280`)
  and force-pushes an orphan branch (`:1272`); the R2-active path deletes large
  `site/audio` files post-build (`:1263-1267`). A successful build with one stray MP3 =
  built-but-never-deployed with no specified recovery or ordering (audio → R2 first,
  `data.json` last, single atomic push).

**Recommended approach:**
- Playwright target: localhost server over the built `site/` dir (not `file://`, not
  live). Assertions: Editorial Picks header/count for Top-14 and Top-20 fixtures; no
  `TubeLM_Top_*` in channel list; audio = controls present + `src` 200 + `canplay`
  (never audible); theme = `data-theme` flip persists via localStorage; viewports
  390 / 768 / 1280.
- CI: keep `build-ios.yml` as the single gate; document `verify.yml` as pre-build
  unit/lint (or merge the lanes — pick one, don't run two authorities).
- Deploy: local actor after UAT green; order audio→R2, `data.json` last, single push;
  pre-deploy 5 MB scan as an explicit gate (not a surprise refusal); live check =
  fetch `https://vkr1729.github.io/TubeLM/data.json`, assert `run_date` equals local.
- Anchor-fit: uses existing harnesses and CI; no new services, no headed-browser farm.

**Alternatives:**
- Test against the live site only — zero local server setup, but every run depends on
  deploy freshness and network; rejected as the primary gate (keep as a post-deploy
  smoke check).
- Full audible-playback verification — highest fidelity, but needs headed Chromium with
  `--autoplay-policy=no-user-gesture-required` + fake audio on a runner for a static
  page's `<audio>` tag; disproportionate for one user; rejected.

**Decision needed:** Confirm localhost (not live) as the UAT target, the `canplay`-not-
  audible audio bar, the three viewports, `verify.yml`'s lane, and the deploy
  ordering + live `run_date` check as §2.D exit criteria.
