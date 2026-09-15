# TubeLM v4.0.0 — External Reviewer Bug Dossier

> **Status:** ALL 28 FIXED + VERIFIED (2026-09-15) — see § Fix & Verification Record.
> Original sweep date: 2026-09-15 · **Scope:** full-repo hardening sweep (pre-close, A-tier goal)
> **Method:** 1 discovery pass + 6 parallel bug-hunt passes (correctness; contracts/data;
> security/auth; resilience/concurrency; frontend; config/perf/hygiene), then
> deduplicated synthesis. Every surviving claim was re-checked against current file
> bodies. Parent session spot-verified all 6 P0s plus BUG-007/009/027 (see
> § Verification addendum).
> **Reviewer instruction:** verify each BUG entry against the cited file:line, run the
> "Check" step where feasible, and mark Accept / Reject / Needs-evidence before any
> implementation is authorized.

## Repo snapshot

- **Stack:** Python 3.11 pipeline + Flask 3 dashboard (localhost :5000) + vanilla-JS PWA
  reader + dependency-free Cloudflare Worker (R2 sync + audio CDN). `VERSION` = 4.0.0.
- **Layout:** `desktop/` (pipeline, GUI, SSG, services), `worker/` (worker.js +
  wrangler.toml), `shared/prompts/{summary,podcast}/`, `docs/`, `summaries/`, `logs/`.
  57 `.py`, 9 `.html`, 1 `.js`. Largest: gui.py 2209L, main.py 1169L, reader.html
  3802L, gui.html 3298L.
- **Entry points:** `desktop/main.py`
  (`--dry-run/--skip-email/--shutdown-after-run/--resume/--scheduled/--gui/--port/--channels/--sources`;
  `--scheduled` via `run_weekly.sh`) → `gui.py:run_gui()` → `web_reader.py --build-only`
  (SSG). TTS backfill: `tts_service.py --backfill`.
- **Config/state:** `.env` via `config.py:load_config()`; `sources.json` via
  `sources_loader.py`; runtime under `~/.tubelm` (`paths.py`).
- **Tests/CI:** `pytest desktop/tests` (27 unit + 1 integration file), `asyncio_mode=auto`.
  CI (`.github/workflows/verify.yml`): pip install, `compileall`, pytest.
  **No linter, type check, or JS harness.**
- **Deps:** notebooklm-py[browser]==0.8.1, flask, pillow, feedparser, requests, jinja2,
  python-dotenv, rookiepy, markdown-it-py, trafilatura, bs4, lxml, boto3, edge-tts; dev
  adds pytest, pytest-asyncio.

## Executive summary

**28 confirmed bugs: P0 = 6, P1 = 14, P2 = 8.**
(P0 = data loss / sec-breach / crash / core-flow broken.)

**Top 5 risks:** (1) One typo'd `sources.json` entry aborts the entire weekly run
(BUG-006, P0). (2) 4-char sync passphrase is brute-forceable; winner reads/rewrites
victim state (BUG-004, P0). (3) Dashboard Stop wedges the runner forever while orphaned
ffmpeg/yt-dlp hold files (BUG-001, P0). (4) Silent config downgrades across four loaders
— no email, no podcasts, retention wipe, GUI drops keys (BUG-011/012/013/019).
(5) Stored feed-URL XSS in reader (BUG-017) + unbounded `summary_*.mp3` growth (BUG-009).

## Architecture notes

Weekly batch: `main.py` loads sources → one handler per source
(`source_handlers/factory.py`) → discovery since per-source `state.json` checkpoint →
one NotebookLM notebook per channel (cookie auth) → HTML/JSON digests → email
(`email_service.py`) → Edge-TTS narration → static PWA rebuild (`web_reader.py`) → GH
Pages / R2. Flask GUI shells out to `main.py` and streams logs via SSE. Worker
(`worker.js`) merges cross-device read state (signed-timestamp LWW set) into R2 JSON.

Key flows: (a) ingest: youtube (RSS + Data API v3, >3 min) / rss / webpage →
`extractor.py` fallbacks (crawler headers → Jina → Wayback); (b) finalize per channel:
digest + sidecar + TTS → optional email → `save_state` → durable artifact queue;
(c) reader build: 14-day purge → transcode/copy → PWA → deploy; (d) sync: reader
pull/push ⇆ Worker GET/POST merge → R2 `sync/<sha256(key)>.json`.

## Bug catalog

### A. Runner & GUI backend

#### BUG-001 — Stop() orphans grandchildren; stdout-pipe deadlock wedges runner
- **Severity:** P0 · **Confidence:** High
- **File:** `desktop/gui.py:83` (`stop` :83–94, `Popen` :110–117 no `start_new_session`,
  read loop :119, `self.process` assigned outside lock :110)
- **Observed:** `stop()` = bare `proc.terminate()` on direct child; `_run` loops
  `for line in self.process.stdout:`.
- **Why wrong:** grandchildren (yt-dlp/ffmpeg) survive and hold files; any pipe inheritor
  blocks the loop forever → `is_running` stuck `True`, no future runs. Unlocked
  transition in `_run` lets `stop()` miss a starting process.
- **Trigger/Impact:** Stop mid-run → runner wedged until dashboard restart + orphaned processes.
- **Fix:** `start_new_session=True` + `killpg` with `wait(timeout)`/SIGKILL fallback;
  reader thread or `communicate()`; lock all transitions.
- **Check:** start→stop with a grandchild-spawning child; assert zero survivors and
  `is_running is False`.

#### BUG-014 — GUI write-back silently deletes skipped/invalid sources
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/gui.py:999` (`_load_existing_sources` :999–1001 filters via
  `load_sources`; `_write_sources` :1004–1014 rewrites whole file; DELETE :1189–1217)
- **Observed:** every POST/DELETE rewrites the file from the filtered list.
- **Why wrong:** read-path filtering mutates the store; deleting A vaporizes a
  future/typo'd-typed B with 200 OK.
- **Trigger/Impact:** any GUI edit with one legacy entry present → legacy entry lost.
- **Fix:** raw-JSON reads for writes; touch only the targeted entry; 400 on invalid rows.
- **Check:** seed unknown-type entry, DELETE a good source, assert unknown entry byte-preserved.

#### BUG-008 — GUI writes `generate_cinematic_video`, read by nothing
- **Severity:** P1 · **Confidence:** High (grep-verified)
- **File:** `desktop/gui.py:1086` (create :1086–1115, toggle :1158, endpoint :1139–1160;
  shown in `desktop/templates/gui.html:2285`)
- **Observed:** zero readers in `main.py`/factory/services; GUI-created sources never set
  `generate_podcast`.
- **Why wrong:** dead toggle; GUI path can never enable podcasts.
- **Trigger/Impact:** any GUI-managed source → flags silently inert.
- **Fix:** write `generate_podcast` (key `main.py:512` reads); wire or remove the cinematic toggle.
- **Check:** grep shows a reader; POST-created source carries the pipeline-visible key.

#### BUG-024 — DELETE identifier collision: numeric id vs positional index
- **Severity:** P2 · **Confidence:** High
- **File:** `desktop/gui.py:1163` (`_find_and_remove_source` :1163–1187 falls back to
  `int(identifier)` as index)
- **Observed:** unmatched numeric identifier deletes by position instead of 404ing.
- **Why wrong:** ambiguous, order-dependent destructive action.
- **Trigger/Impact:** DELETE `"0"` with no match → first source removed.
- **Fix:** drop index fallback or require explicit `{"index": n}`.
- **Check:** unmatched numeric DELETE → 404, file unchanged.

#### BUG-025 — Login depends on notebooklm private API
- **Severity:** P2 · **Confidence:** High
- **File:** `desktop/gui.py:1615` (imports `_login_with_browser_cookies`; interprets
  `SystemExit` as success)
- **Why wrong:** underscore-private upstream symbol; any bump can break dashboard login opaquely.
- **Trigger/Impact:** dep upgrade → `/api/auth/login` 500s.
- **Fix:** pin + import-fallback adapter, or subprocess the public CLI.
- **Check:** assert symbol exists post-bump; test fails loudly on import change.

#### BUG-026 — Notebook DELETE builds a fresh event loop per request
- **Severity:** P2 · **Confidence:** High
- **File:** `desktop/gui.py:1846` (`new_event_loop` + `set_event_loop` in handler :1846–1868)
- **Why wrong:** `set_event_loop` on threaded Flask workers is fragile; concurrent deletes
  can interfere.
- **Trigger/Impact:** concurrent DELETEs → loop cross-talk / `RuntimeError`.
- **Fix:** `asyncio.run()` scoped to the coroutine, or a shared loop thread.
- **Check:** 5 concurrent DELETEs, all clean, no loop warnings.

#### BUG-023 — SSRF guard fails open on DNS failure
- **Severity:** P2 · **Confidence:** High
- **File:** `desktop/gui.py:228` (`except OSError: … return None` :228–231, documented
  "fail open")
- **Why wrong:** trades availability for SSRF where DNS is attacker-influenced or flaky.
- **Trigger/Impact:** internal hostname pasted during DNS outage → server-side fetch proceeds.
- **Fix:** fail closed, or gate fail-open behind explicit offline-mode flag.
- **Check:** simulated DNS failure → validate returns 400.

### B. Sources / config / state

#### BUG-006 — Loader keeps id-less entries → factory KeyError kills whole run
- **Severity:** P0 · **Confidence:** High (runtime-verified by prior review)
- **File:** `desktop/sources_loader.py:31` (warns "skipping" :32–33, no `continue`,
  appends :39) → `desktop/source_handlers/factory.py:11` (`["channel_id"/"url"]`
  :14/:22/:31) → `desktop/main.py:505` (single list-comp, uncaught)
- **Why wrong:** log promises a skip the code doesn't do; one bad row aborts discovery
  for all sources.
- **Trigger/Impact:** one youtube entry lacking `channel_id` → entire weekly run crashes.
- **Fix:** `continue` after warning (matches siblings :22–30) + per-source handler isolation.
- **Check:** extend `test_invalid_entries_skipped` (currently name/type only) with id-less
  entries; one bad + one good source → good completes.

#### BUG-007 — Global `GENERATE_PODCASTS` dead; loader forces `generate_podcast=False`
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/sources_loader.py:34` (unconditional materialize :34–36) vs
  `desktop/main.py:510` (`source.get("generate_podcast", cfg.generate_podcasts)` :510–517,
  unreachable fallback)
- **Why wrong:** global-on + per-source-absent still disables podcasts.
- **Trigger/Impact:** any global-enable run → zero audio overviews, no warning.
- **Fix:** normalize the key only when present.
- **Check:** env true + key absent → `podcast_selection[key] is True`.

#### BUG-015 — `Z` checkpoint accepted on write, unparseable on read
- **Severity:** P1 · **Confidence:** High
- **File:** write `desktop/gui.py:1321` (validates with `replace("Z","+00:00")` :1323,
  stores original :1325) vs read `desktop/main.py:140` (bare `fromisoformat` :150/:157 →
  caught :163 → default lookback). Intent proof: `desktop/run_control.py:162`.
- **Why wrong:** GUI says saved; pipeline silently falls back to default lookback
  (reprocess/skip).
- **Trigger/Impact:** any Zulu timestamp via dashboard → checkpoint inert.
- **Fix:** normalize on write AND parse defensively on read.
- **Check:** round-trip `"2026-09-01T00:00:00Z"` through API → state reader returns that instant.

#### BUG-011 — `_get_required` dead; required vars silently optional, `smtp_port=0`
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/config.py:26` (docstring :4–6 promises raise; `_get_required` :26–33
  never called; `load_config` :197–221 all-optional; port defaults 0 :157–158) →
  `desktop/main.py:447` (silent skip :448–452)
- **Why wrong:** unfilled `.env` "succeeds" with zero email; port 0 passes validation.
- **Trigger/Impact:** missing/typo'd SMTP var → no delivery, green run.
- **Fix:** `_get_required` for SMTP_*/emails/`YOUTUBE_API_KEY`; reject port 0 when email enabled.
- **Check:** empty env raises naming the key; `SMTP_PORT=0` fails validation.

#### BUG-012 — `.env.example` omits 7 load-bearing keys
- **Severity:** P1 · **Confidence:** High
- **File:** `.env.example:1` lacks `NOTEBOOKS_RETENTION_LIMIT`, `TOP_DIGEST_COUNT`,
  `SEND_CHANNEL_EMAILS`, `DEPLOY_TO_GH_PAGES`, `GH_PAGES_URL` (`desktop/config.py:167–215`),
  `TTS_TIMEOUT_SECONDS` (`desktop/tts_service.py:29`), `TUBELM_COMPRESS_AUDIO`
  (`desktop/web_reader.py:794`)
- **Why wrong:** undiscoverable knobs with biting defaults (retention=2 deletes old digests).
- **Trigger/Impact:** fresh setup → wipes, missing digests, wrong TTS budget, no hints.
- **Fix:** document every key with defaults/effects.
- **Check:** diff `_get_*`/`os.getenv` keys vs example → zero missing.

#### BUG-013 — GUI config write silently drops most supported keys
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/gui.py:275` (`allowed_keys` :276–281 lacks GENERATE_PODCASTS,
  DOWNLOAD_TOP_10_VIDEOS, TOP10_*, TOP_DIGEST_COUNT, SEND_CHANNEL_EMAILS, DEPLOY_TO_GH_PAGES,
  GH_PAGES_URL, COMPRESS_AUDIO, TTS_*, R2_*; `continue` :287–288 + 200 OK)
- **Why wrong:** dashboard reports success while persisting nothing.
- **Trigger/Impact:** `POST /api/config {"TTS_VOICE":…}` → 200, file unchanged.
- **Fix:** allowlist parity with loaders, or 400 unknown keys.
- **Check:** POST each documented key → file changes; unknown key → 400.

#### BUG-019 — Config precedence split; `COMPRESS_AUDIO` default/name mismatch
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/config.py:18` (default True :216) vs `desktop/web_reader.py:784`
  (default False :784; env accepts only `1/true/yes` :793–795, drops config's `on`) vs
  `desktop/gui.py:794` (default False); raw `os.getenv` in `desktop/tts_service.py:32`
- **Why wrong:** same env file, different behavior per entry point; `TUBELM_COMPRESS_AUDIO`
  undocumented.
- **Trigger/Impact:** `COMPRESS_AUDIO=on` + `--build-only` → uncompressed deploy.
- **Fix:** single loader + truthy set; aligned documented defaults; document/drop `TUBELM_` alias.
- **Check:** truthy matrix × {main, build-only, API} → identical result.

### C. Cloudflare Worker

#### BUG-004 — 4-char sync passphrase, no rate limit; hash doubles as object name
- **Severity:** P0 · **Confidence:** High
- **File:** `worker/worker.js:84` (`length < 4` gate :84–86; `sha256(key)` →
  `sync/<hash>.json` :89–90; no throttle anywhere)
- **Why wrong:** enumerable keyspace; no secret comparison, rotation, or scoping — key
  knowledge = read + overwrite.
- **Trigger/Impact:** remote enumeration → history theft + state poisoning.
- **Fix:** ≥128-bit generated secret, env-stored hash + timing-safe compare, rate limiting,
  drop `?key=`.
- **Check:** burst guesses → 429; 4-char rejected; object name not key-derivable.

#### BUG-002 — Sync POST read-modify-write race, no CAS
- **Severity:** P0 · **Confidence:** High
- **File:** `worker/worker.js:134` (GET-merge-PUT :134–149/:178–205; unconditional `put` :203–205)
- **Why wrong:** concurrent POSTs merge from the same base; last writer drops the other's
  keys, defeating LWW intent.
- **Trigger/Impact:** phone + laptop push together → one side's marks vanish silently.
- **Fix:** Durable Object serializer or R2 conditional write + retry loop.
- **Check:** 20 concurrent disjoint-key POSTs → union present.

#### BUG-005 — Unbounded `item_states` = remote storage/CPU DoS
- **Severity:** P0 (remotely triggerable exhaustion) · **Confidence:** High
- **File:** `worker/worker.js:157` (uncapped merge :157–164; arrays sliced :186–192 but
  `item_states` whole :199–203; no payload check :129)
- **Why wrong:** no byte/key-count/length/charset caps; with BUG-004 anyone grows a victim
  object unboundedly → R2 cost, sync slowdown, reader OOM/`localStorage` overflow.
- **Trigger/Impact:** POST millions of entries → victim sync breaks, operator pays.
- **Fix:** payload cap (413), key cap ~5000 with oldest-eviction, key length/charset rules.
- **Check:** 100k-key POST → 413; over-limit → newest 5000 kept.

#### BUG-016 — CORS `*` on credentialed sync API
- **Severity:** P1 · **Confidence:** High (design)
- **File:** `worker/worker.js:18` (`Allow-Origin: *` + `Authorization`/`X-Sync-Key` :18–24)
- **Why wrong:** any visited site can issue credentialed sync calls once the (weak) key is
  known — forfeits origin boundary for a mutating API.
- **Trigger/Impact:** malicious page + guessed key → silent exfil/poison from victim browser.
- **Fix:** allowlist reader origins (GH Pages + localhost); keep `*` only for audio CDN
  if intended.
- **Check:** foreign `Origin` preflight → no echo; GH Pages origin → pass.

#### BUG-021 — POST double-parses stored object (see addendum: likely partition wipe)
- **Severity:** P2 (candidate P0 — see verification addendum) · **Confidence:** High
- **File:** `worker/worker.js:136` (GET+parse :136–149 and again :178–184)
- **Why wrong:** 2× R2 read per push; widens BUG-002 window (torn merge between reads).
  Parent-session verification further found the second `existingObj.json()` re-reads an
  already-consumed body — see addendum.
- **Trigger/Impact:** every sync pays double latency; torn `item_states` vs arrays under
  concurrency.
- **Fix:** fetch once, reuse.
- **Check:** instrument `SYNC_BUCKET.get` per POST → 1.

#### BUG-022 — Errors echo backend `err.message` to caller
- **Severity:** P2 · **Confidence:** High
- **File:** `worker/worker.js:72` (:72, :118, :215)
- **Why wrong:** leaks R2/binding internals past a 4-char gate.
- **Trigger/Impact:** malformed requests harvest storage error strings for probing.
- **Fix:** log server-side; generic error + correlation id outward.
- **Check:** forced R2 failure → body contains no internals.

### D. Reader frontend

#### BUG-017 — Feed URLs raw into `href` (stored `javascript:` XSS)
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/templates/reader.html:2763` (`item.url` :2763, `v.url` :2870, `b.url`
  :3020, `notebook_url` :2908, `audio_url` :2837; titles escaped, URLs never; no
  `rel="noopener"`). Precedent: `desktop/templates/gui.html:1842` `safeExternalUrl()`.
- **Why wrong:** third-party-controlled URLs render clickable; `javascript:` executes in
  reader origin (`localStorage` key theft); plain links allow reverse-tabnabbing.
- **Trigger/Impact:** malicious/compromised feed item + one click → JS as reader.
- **Fix:** port `safeExternalUrl()` to all six sites + `rel="noopener noreferrer"`.
- **Check:** `javascript:` URL fixture → `href="#"`; every `target="_blank"` carries `rel`.

#### BUG-018 — `escapeQuotes()` skips backslashes → inline-handler breakout
- **Severity:** P1 · **Confidence:** Medium (defect confirmed; click-through PoC not run —
  verify before upgrading)
- **File:** `desktop/templates/reader.html:3562` (quote-escape only, no backslash pass
  :3562–3564) in single-quoted JS in double-quoted attrs (:2773, :2763/:2870/:2893/:3020)
- **Why wrong:** `\';alert(1);//` title defeats the quote-escape at click time (classic
  incomplete JS-string escape).
- **Trigger/Impact:** crafted feed title + click → JS as reader (same blast radius as BUG-017).
- **Fix:** escape `\` first; better: `data-*` + listeners, or `JSON.stringify` args
  (cf. `gui.html:inlineArg`).
- **Check:** headless click on backslash/quote title → no alert, intact args.

#### BUG-020 — Sync key sent in URL query string
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/templates/reader.html:2141` (`?key=` :2141 GET and :2183 POST, alongside
  headers that already carry it)
- **Why wrong:** secret into Cloudflare/R2 logs, history, proxies — pure exposure, zero need.
- **Trigger/Impact:** routine sync litters the credential; log readers inherit full sync access.
- **Fix:** drop `?key=` client- and server-side (`worker/worker.js:80`); headers only.
- **Check:** captured sync traffic has no `key=` param; query-only auth → 401.

### E. Email

#### BUG-003 — SMTP send has no timeout; one hang stalls the pipeline
- **Severity:** P0 · **Confidence:** High
- **File:** `desktop/email_service.py:292` (`_send_message` :292–304, no `timeout=`) vs
  `timeout=15` in verify (:455–458); called synchronously per channel (`desktop/main.py:706`)
- **Why wrong:** codebase already bounds SMTP at verify; send omits it; per-channel
  `try/except` can't catch a hang.
- **Trigger/Impact:** one wedged `login`/`sendmail` → run stalls, later channels never deliver.
- **Fix:** `timeout=15` (or configured) on both constructors in `_send_message`.
- **Check:** black-hole MTA → send fails in ~timeout; remaining channels complete.

### F. Audio / retention

#### BUG-009 — 14-day purge never deletes `summary_*.mp3`
- **Severity:** P1 · **Confidence:** High (runtime-verified by prior review)
- **File:** `desktop/web_reader.py:55` (purge `^(\d{4}-\d{2}-\d{2})_` :58) vs producers
  `summary_{date}_{safe}.mp3` (`desktop/tts_service.py:204`, `desktop/main.py:688`)
- **Why wrong:** filename contract mismatch voids the "2-week rolling retention" promise for
  all TTS files.
- **Trigger/Impact:** unbounded MP3 growth on disk + deploy payload.
- **Fix:** match `^(?:summary_)?(date)_` or share one filename builder.
- **Check:** 30-day `summary_…mp3` purged, 13-day kept (extend `test_purge_older_than_14_days`).

#### BUG-027 — `read_state` prune keeps all non-date ids forever
- **Severity:** P2 · **Confidence:** High
- **File:** `desktop/web_reader.py:69` (`else: valid_ids.append(rid)` :85–86)
- **Why wrong:** non-canonical ids are immortal; file grows while prune claims to shrink it.
- **Trigger/Impact:** stale-id accumulation; slower boot, bigger deploys.
- **Fix:** same MAX/recency bound as GUI sanitizer, applied uniformly.
- **Check:** 6k junk ids → bounded output after build.

### G. Ingest & hygiene

#### BUG-010 — RSS discovery fetch has no timeout
- **Severity:** P1 · **Confidence:** High
- **File:** `desktop/source_handlers/rss_handler.py:69` (`feedparser.parse(self._url)` fetches
  unbounded). Siblings bounded: youtube ×4, webpage :67, extractor, GUI validator
  `desktop/gui.py:1243`.
- **Why wrong:** one dead feed host hangs its worker indefinitely.
- **Trigger/Impact:** single unresponsive URL → stage tail explodes; enough of them → run
  never finishes.
- **Fix:** bounded `requests.get(timeout=15)` → `feedparser.parse(bytes)`, mirroring the validator.
- **Check:** black-hole feed → discovery settles in ~15 s; rest of run unaffected.

#### BUG-028 — CI is only `compileall` + pytest; no lint/types/JS gates
- **Severity:** P2 · **Confidence:** High
- **File:** `.github/workflows/verify.yml:1` (:24–30); no ruff/mypy/eslint config; `worker.js`
  covered only by a node-syntax simulation in a Python test
- **Why wrong:** this dossier's bug classes (dead code, bare `except`s, JS escaping) are
  cheapest caught by linters; regressions merge silently.
- **Trigger/Impact:** reintroduction of BUG-006-class defects passes CI.
- **Fix:** ruff (ratcheted) + `node --check` as required gates; mypy on config/loader.
- **Check:** gates present; reintroduced missing-`continue` on a branch → red CI.

## Verification gaps

1. Runner kill semantics — `test_pipeline_runner.py` (11 lines) covers only log replay (BUG-001).
2. Id-less loader rejection — `test_invalid_entries_skipped` covers name/type only, not
   missing `channel_id`/`url` (BUG-006).
3. `Z`-checkpoint round trip API→parser (BUG-015).
4. Purge `summary_*.mp3` fixture; no shared filename builder (BUG-009).
5. Worker concurrency/auth/payload-cap behavior — only in-process merge-math simulation
   (BUG-002/004/005).
6. SMTP-hang fault injection for `_send_message` (BUG-003).
7. Black-hole-feed discovery test (BUG-010).
8. Headless malicious-feed render tests for `javascript:` URLs / backslash titles (BUG-017/018).
9. Config matrix: example completeness, GUI-allowlist coverage, truthy parity (BUG-012/013/019).
10. Podcast fallback: global-on/source-absent + GUI-created sources (BUG-007/008).

## Hardening checklist (prioritized)

1. P0 cluster: BUG-006 (`continue` + isolation), BUG-001 (process-group kill + drain +
   locks), BUG-002 (CAS/DO), BUG-003 (timeout), BUG-004/005 (strong secret + rate limit + caps).
2. Silent-config cluster: BUG-011 (raise), BUG-012 (document), BUG-013 (parity/400),
   BUG-019 (single loader), BUG-007/008 (flag end-to-end).
3. Reader encoding pass: BUG-017/018 (`safeUrl` + `data-*`/listeners + `rel`), drop `?key=`
   (BUG-020), malicious-feed fixtures.
4. Timeout/bound audit: explicit timeout on every network call; cap every unbounded
   collection (copy `output_log`/`_sanitize_read_ids` patterns).
5. CI gates: ruff + `node --check` + the 10 gap tests, required (BUG-028).
6. Rotate any sync key ever sent as `?key=`; confirm `.env` absent from history; keep/extend
   `/api/config` masking.
7. Update run diagrams with the fixed checkpoint/retention semantics.

## Explicit non-findings

- Atomic writes (`_write_sources`, `_atomic_write_json_file`, `_write_state_file`) +
  per-channel checkpoints + `materialize_source_checkpoints`: sound crash recovery.
- `_sanitize_read_ids` (cap/length/dedupe) is the right pattern — Worker should copy it.
- YouTube/webpage/extractor timeouts present and consistent; only RSS missed it.
- GUI binds `127.0.0.1` (`desktop/gui.py:2202`) — no remote unauthenticated GUI exposure.
- `GET /api/config` redacts SMTP_PASSWORD/YOUTUBE_API_KEY; `.env` never read in this review.
- `/api/prompts` allowlists category/type — no traversal. Worker audio CDN (keyless,
  immutable, Range) is coherent if audio is meant public — operator to confirm.
- TTS degrades to `False`; per-channel finalization never advances checkpoints on failure.
  `FFMPEG_TIMEOUT_SECONDS=120` with copy fallback bounds site build.

## Unresolved / needs-info

1. **Truncated prior-review tails** (resilience claimed 19, quality 22; correctness/contracts/
   security/frontend tails cut). Only re-verifiable claims are asserted above. Needed: full
   texts or a follow-up hunt.
2. **BUG-018 click-through PoC** — defect confirmed; weaponization needs a headless-browser run.
3. **NotebookLM retention-sort edge cases** (`notebooklm_service.py:201–222, 460–487`) — not
   fully traced; no finding asserted. Needed: focused read + crafted-list test.
4. **`agy`/Top-10 + yt-dlp failure modes** — timeouts present; quota/auth/partial paths
   unprobed. Needed: fault injection.
5. **GH Pages deploy + R2 upload** — wiring not traced end-to-end. Needed: read + dry-run.
6. **Audio-manifest/PWA cache invalidation** — noted, not verified. Needed: two-run build diff.
7. **Live `.env`/`sources.json` values** — never read (hygiene). Operator must confirm newly
   documented keys post-fix.

## Method (dedup map)

7 prior passes arrived runtime-truncated; every surviving claim was re-checked against
current bodies. Merges: C1+contracts#1→BUG-006; C2→BUG-007+008; C3→BUG-009; R1→BUG-001;
R2→BUG-002 (+twin BUG-021); R3→BUG-003; R4→BUG-010; Q1/Q2/Q3→BUG-011/012/013; Q4→BUG-019;
sec P1-1→BUG-004 (+twin BUG-020); P1-2→BUG-005 (P1→P0: remote exhaustion); P1-3→BUG-016;
FE-01→BUG-017; FE-02→BUG-018; contracts#2/#3→BUG-014/015. New from direct inspection:
BUG-022/023/024/025/026/027/028. No secrets pasted; no `.pyc`/grader artifacts cited.

## Verification addendum (parent session, 2026-09-15)

Spot-verified by re-reading bodies (independent of child agents):

- BUG-001 CONFIRMED — `desktop/gui.py:83-94` bare `terminate()`; `:110-117` no
  `start_new_session`; `:119` blocking stdout loop; `:110` assigns `self.process` outside
  the lock.
- BUG-002/004/005/016/022 CONFIRMED — `worker/worker.js` lines match as cited.
- BUG-003 CONFIRMED — `desktop/email_service.py:292-304` constructs both SMTP clients
  without `timeout=`.
- BUG-006/007 CONFIRMED — `desktop/sources_loader.py:31-39` warns "skipping" with no
  `continue`, then forces `generate_podcast=False`; `desktop/main.py:505` builds handlers
  in one uncaught list-comp; `:510-517` fallback is unreachable.
- BUG-009/027 CONFIRMED — `desktop/web_reader.py:58` requires `YYYY-MM-DD_` prefix while
  `desktop/tts_service.py:204` and `desktop/main.py:688` emit `summary_…`; `:85-86` keeps
  all non-date ids.
- **BUG-021 ESCALATION (new, needs reviewer confirm):** `worker/worker.js:178-184` calls
  `existingObj.json()` a second time on the same R2 object already consumed at `:136-149`.
  R2 object bodies are single-use streams, so the second parse is expected to throw, get
  swallowed by `catch (_) {}`, and silently reset `existingReadIds`/`existingTop20` to `[]`
  on **every** POST — wiping prior partition membership (partially masked by the
  `item_states` merge + incoming arrays). If confirmed against the Workers runtime, upgrade
  BUG-021 to P0 (silent sync data loss) and fix by parsing once and reusing. Suggested
  check: `wrangler dev` + two sequential POSTs with disjoint arrays, then GET and diff
  partitions.

## Reviewer sign-off

| ID | Verdict (Accept/Reject/Needs-evidence) | Notes |
|----|----------------------------------------|-------|
| BUG-001 | | |
| BUG-002 | | |
| BUG-003 | | |
| BUG-004 | | |
| BUG-005 | | |
| BUG-006 | | |
| BUG-007 | | |
| BUG-008 | | |
| BUG-009 | | |
| BUG-010 | | |
| BUG-011 | | |
| BUG-012 | | |
| BUG-013 | | |
| BUG-014 | | |
| BUG-015 | | |
| BUG-016 | | |
| BUG-017 | | |
| BUG-018 | | |
| BUG-019 | | |
| BUG-020 | | |
| BUG-021 (+escalation) | | |
| BUG-022 | | |
| BUG-023 | | |
| BUG-024 | | |
| BUG-025 | | |
| BUG-026 | | |
| BUG-027 | | |
| BUG-028 | | |

Reviewer name / date: ____________________
Decision: __ Proceed to implementation __ Request re-hunt on open items

---

# Fix & Verification Record (2026-09-15)

All 28 dossier bugs were fixed, then a fresh independent residual review
(3 agents + synthesis) found 9 further issues (RES-001…009), all fixed. A
second terse review recovered the truncated tails (U-1/2/3 → RESOLVED) with
22 P2s; 20 fixed, 2 declined with justification below.

Final gates (all observed this session): **270 pytest passed** (`pytest
desktop/tests`), **ruff clean** (`ruff check desktop`, select F), **worker
syntax clean** (`node --check worker/worker.js`).

## Per-bug fix log

- BUG-001 — `gui.py`: `start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP`
  (Windows), `killpg` SIGTERM→SIGKILL with reaping, stdout-close unblock, all
  transitions under lock; kill runs outside the lock (P2 follow-up). Tests:
  `test_pipeline_runner.py` (idle, single-child group kill, grandchild pipe test).
- BUG-002 — `worker.js`: new `SyncCoordinator` Durable Object serializes POST
  read-modify-write per key; `wrangler.toml` binding + `v1` migration; direct-R2
  fallback when unbound (tests, old deploys). Test: DO-routing relay test.
- BUG-003 — `email_service.py`: `SMTP_TIMEOUT_SECONDS = 15` on all 4 SMTP
  constructors (send + verify). Tests: `test_email_service.py` (timeout kwarg +
  login/sendmail invocation).
- BUG-004 — `worker.js`: min key 16 (max 256, no control chars), per-IP
  best-effort limit (CF-Connecting-IP only) + exact per-key DO limit, no query
  auth. Tests: query/short rejection, caps, byte-cap.
- BUG-005 — `worker.js`: 1 MiB byte cap (TextEncoder-measured), 5000-entry
  `item_states` cap evicting stalest intent, id/array validation. Test: 6000-key push.
- BUG-006 — `sources_loader.py`: missing `continue` added; `main.py`: per-source
  handler isolation keeping sources/handlers aligned. Tests: id-less skip + chain test.
- BUG-007 — `sources_loader.py`: flag normalized only when present (strings via
  shared BOOL vocabulary — P2 follow-up). Tests: absent-stays-absent, coerce, strings.
- BUG-008 — GUI create writes pipeline-visible `generate_podcast` (only when
  opted in — RES-003); dead cinematic endpoint replaced by `/api/sources/podcast`;
  `gui.html`: Podcast column + toggle + create checkbox. Tests: toggle, create, omit.
- BUG-009 — `web_reader.py`: `_AUDIO_DATE_RE` tolerates `summary_` prefix. Test: fixtures.
- BUG-010 — `rss_handler.py`: streamed `requests.get(timeout=15)` + 5 MiB cap,
  `feedparser.parse(bytes)`. Tests: timeout kwarg, bytes arg, fetch-failure, oversize.
- BUG-011 — `config.py`: `require_email_config` (names missing keys, rejects port 0),
  `require_youtube_api_key`; `main.py` enforces both. **DEVIATION (see below):**
  the email gate fires only when config was *attempted* (RES-002). Tests:
  `test_config_validation.py`.
- BUG-012 — `.env.example`: all 7 keys documented (+ `TUBELM_COMPRESS_AUDIO` alias,
  bool vocabulary). Test: example↔API parity test posts every key.
- BUG-013 — `gui.py`: `WRITABLE_ENV_KEYS` full parity + 400 on unknown (was silent
  skip + 200); dead `GENERATE_INFOGRAPHICS` select removed from `gui.html`. Tests:
  unknown→400, parity.
- BUG-014 — `gui.py`: `_load_raw_sources()` for all write paths; corrupt file
  refuses (500) instead of clobber. Test: unknown-entry preservation.
- BUG-015 — `gui.py` stores Z-normalized timestamps; `main.py`
  `parse_checkpoint_timestamp()` honors legacy `Z`. Tests: API round-trip + legacy read.
- BUG-016 — `worker.js`: sync CORS echoes allowlisted origins only (reader origin,
  localhost, `ALLOWED_ORIGINS`); audio keeps `*`. Tests: echo + foreign-403.
- BUG-017 — `reader.html`: `safeExternalUrl()` on all 5 dynamic hrefs +
  `rel="noopener noreferrer"` on all 7 blank-target links. Tests: static + node eval.
- BUG-018 — `reader.html`: `escapeQuotes()` escapes backslash first. Test: node eval.
- BUG-019 — `paths.resolve_bool_env()` shared by config/web_reader; `COMPRESS_AUDIO`
  default True everywhere; `TUBELM_COMPRESS_AUDIO` precedence; tri-state
  (`None` = resolve) in `build_reader_site`/CLI (`--no-compress-audio` added)/GUI API.
  Tests: truth-table matrix incl. alias precedence.
- BUG-020 — dropped `?key=` in `reader.html` (headers already sent) and `worker.js`.
  Tests: query-auth 401, fetch-URL scan. Pairing link keeps key in `#fragment` (by design).
- BUG-021 — `worker.js`: single fetch + single parse via `readStoredState()`
  (fixes the confirmed partition-wipe escalation). Test: single-use-body mock.
- BUG-022 — `worker.js`: generic errors + `console.error` + correlation id. (Covered
  by relay tests asserting shapes.)
- BUG-023 — `gui.py`: DNS failure fails closed. Test: gaierror → blocked.
- BUG-024 — `_find_and_remove_source()`: index fallback removed. Tests: channel_id
  delete, numeric-404 with byte-identical file.
- BUG-025 — login import wrapped with actionable error; pin already `==0.8.1`.
  Test: symbol-importable tripwire.
- BUG-026 — `asyncio.run()` in notebook DELETE **and** auth-status (same pattern).
  Test: `set_event_loop` forbidden during DELETE.
- BUG-027 — `web_reader.py`: read_state ids truncated/deduped/capped at 5000/256.
  Test: 6000 junk ids → bounded.
- BUG-028 — `ruff.toml` (select F) + `node --check` + setup-node in `verify.yml`;
  38 findings fixed; `ruff` added to `requirements-dev.txt`. Gates observed green.

## Residuals (RES-001…009) — all fixed

- RES-001 — `gui.html` stored XSS via `encodeURIComponent` in handlers → now
  `inlineArg()`; `decodeURIComponent` removed from callees. New `test_gui_templates.py`.
- RES-002 — email gate vs shipped cron → gate fires only on *attempted* config
  (new `email_config_attempted()`); fully-absent keeps warn-and-skip. See Deviation.
- RES-003 — GUI create stored explicit `generate_podcast:false` → key written only
  when opted in; label documents fallback. Test added.
- RES-004 — short-key state orphan → `worker/README.md` documents wrangler R2
  copy recovery (`sync/<old-sha>.json` → `sync/<new-sha>.json`) + re-pair.
- RES-005 — unsealed purge test → sealed; suite audited (only that one test wrote
  ambient state). **Disclosure:** `~/.tubelm/read_state.json` mtime (Sep 11) predates
  all fix-session runs and its 20-byte size matches an empty list — no operator data
  was pruned by verification runs. Future runs are hermetic.
- RES-006 — compress default flip → **DECISION: keep True** (matches `config.py` and
  the documented `.env.example` default; tri-state + `--no-compress-audio` preserve
  opt-out). Recorded here as the release note.
- RES-007 — legacy merge branch `Array.isArray` guards (heal, don't 500). Test added.
- RES-008 — DO 429 `Retry-After` preserved through relay. Test added.
- RES-009 — audio OPTIONS returns full preflight incl. `Range`. Test added. Live
  browser confirmation remains operator-side (U-4).

## Tail-recovery P2s (U-1/2/3 → RESOLVED)

22 terse P2s returned; 20 fixed: worker NaN-baseTs guard, byte-measured caps,
CF-Connecting-IP-only limiting, bucket-map hard cap, conditional ETag,
`ALLOWED_ORIGINS` wrangler doc; stop()-outside-lock, strict compress type (400),
source-flag coercion, `_bounded_int` bool/float rejection, RSS 5 MiB stream cap,
TTS float-timeout + clamp, loader string-vocabulary, SMTP constant reuse; reader
gate max/control mirror, `video_id` producer allowlist (`_clean_video_id`), test
hygiene (alias delenv, rename, send asserts, dual-quote handler scan).
2 declined with cause: (a) whitespace-only email values — `_get_optional()` strips
before `require_email_config` ever sees values, so the check is unreachable;
(b) `has_smtp` port-blindness — unreachable, because attempted configs hit the
port-checking require gate first. Both verified by reading the call chain.

## DEVIATION from BUG-011's prescribed check

The dossier's check ("empty env raises") is superseded: a fully-absent email
config keeps warn-and-skip (the shipped `run_weekly.sh` and dashboard defaults
rely on it), while ANY partial config (incl. port-only) is fatal and names the
missing keys. Rationale: fully-absent = legitimate local-only install; partial =
typo/omission. The realistic typo (1 of 5 vars wrong) is still caught loudly.

## Coupled-deployment & operator notes

1. **Deploy worker + reader together.** `?key=` removal is coupled: new worker
   rejects query auth that only the new reader stops sending. Deploy worker first,
   then the reader; mixed states fail closed (401), not silently.
2. **Durable Object migration:** `wrangler deploy` applies the `v1` migration;
   verify `SYNC_COORDINATOR` binding exists post-deploy or pushes use the racy
   fallback (logged behavior, still correct merge math).
3. **Short passphrases:** rotate per `worker/README.md` migration section.
4. **New fatal paths:** partial SMTP (fix vars or `--skip-email`); YouTube sources
   without `YOUTUBE_API_KEY` (add key or filter sources). Both name the fix.
5. **GUI breaks:** `/api/sources/cinematic` removed (→ `/api/sources/podcast`);
   numeric DELETE now 404s; unknown `/api/config` keys now 400.
6. **Unresolved carried forward:** U-4 (live-browser ranged-audio check); dossier
   § Unresolved items 2–6 (NotebookLM edges, yt-dlp faults, deploy wiring, PWA
   cache) were out of the fix scope and remain future work.
