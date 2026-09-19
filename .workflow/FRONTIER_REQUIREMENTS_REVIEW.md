# Frontier Requirements Review — TubeLM iOS (LiveContainer Native)

Source: `.workflow/REQUIREMENTS.md`
Date: 2026-09-19

## Target User Scale Anchor

**Single-Person Personal Use Only.**

Hard constraints carried through all recommendations below:
- Reject enterprise complexity: no multi-tenant DB, no user auth framework, no remote cloud server / backend API to maintain.
- Host: sideloaded app inside **LiveContainer** on iOS (JIT, no reliable background daemons / push).
- Use pattern: commuter, 7–8 opens/week, intermittent connectivity (subway tunnels).
- Content scale: 37 sources → Top 20 briefing, 2-week rolling retention, weekly `data.json` + audio via GitHub Pages (`vkr1729.github.io/TubeLM/`) or optional R2.

Any recommendation that implies a server, login, or per-user cloud sync violates the anchor and is listed only as a rejected alternative.

---

## Q1 — How does the app survive a `data.json` schema change or partial weekly publish?

**Ambiguity:** §2 says the iOS app consumes pure JSON via a new `desktop/web_reader.py` export hook, with silent ETag / If-Modified-Since refresh on every launch/foreground. No schema version, no atomicity contract, no tolerant-reader rule is specified.

**Edge cases / failure modes:**
- Weekly pipeline adds/renames a field (e.g. new audio URL shape for R2 vs Pages) → old installed `.ipa` crashes or shows blank feed.
- `gh-pages` push lands `data.json` before `/audio/...` files (or vice versa) → feed references 404 audio during commute.
- ETag check succeeds on flaky subway Wi-Fi but body download truncates → corrupt local cache replaces good cache, next cold start in tunnel shows nothing.

**Recommended approach:**
- Versioned, tolerant reader: `data.json` carries `schema_version: 1`; Swift reader decodes with `decodeIfPresent` + defaults, ignores unknown keys, never throws on missing optional fields.
- Atomic swap: download to temp file, validate (JSON parses + `items` non-empty + version supported), then `replaceItemAt` over cached copy. Failed validation keeps last good cache and logs silently.
- Publish-side ordering: `web_reader.py` writes audio assets first, then `data.json` last; optionally add `manifest_etag` / `content_hash` so iOS can skip half-pushed states.

**Alternatives:**
- Strict Codable models (fail-fast) — simpler code but one schema drift bricks offline reading; rejected.
- Server-side version negotiation / forced-update endpoint — violates single-user / no-server anchor; rejected.
- HTML scraping fallback — reintroduces parsing fragility the JSON hook was created to avoid; rejected.

**Decision needed:** Confirm `schema_version` field in export hook + tolerant-decode rule as acceptance criterion.

## Q2 — What happens to Saved / Queue items and `read_state` when the 2-week purge fires?

**Ambiguity:** PROJECT.md enforces strict 14-day purge of digests/notebooks; REQUIREMENTS §2 says full offline text + cached audio, plus bookmark-to-queue and locally persisted `read_state` with optional export. No retention exemption for user-saved items.

**Edge cases / failure modes:**
- User bookmarks a Week-1 deep explainer for later; Week-3 publish purges it remotely → queue entry dangles (text gone, audio 404, or silently disappears — both bad).
- `read_ids` grows unbounded across weeks (PROJECT.md hardening already caps web at `MAX_READ_IDS=5000`); iOS has no cap specified → `Documents/` bloat inside LiveContainer sandbox.
- Stale-while-revalidate overwrites local cache and drops IDs for purged items → unread counters / filters recompute incorrectly.

**Recommended approach:**
- Saved-exempt pinning: queue/bookmarked items are copied to `Documents/pinned/` (text + audio) and exempt from rolling eviction; un-bookmarking makes them eligible for next GC. Cap pins (e.g. 50 items / 500 MB) with oldest-unpinned-first eviction and a settings row showing usage.
- Tombstone read-state: keep `read_ids` as a bounded LRU (e.g. 5000, string-only, matching web hardening), prune IDs whose content hash hasn't existed for >2 cycles; never resurrect purged items as unread.
- Remote purge never deletes local pins — explicit divergence is correct for single-user offline-first.

**Alternatives:**
- Mirror remote purge exactly (delete local saves too) — simplest, but destroys commuter trust; rejected.
- Unlimited local archive (keep everything forever) — blows LiveContainer storage, no GC story; rejected.
- Cloud backup of saves (iCloud / R2 upload) — introduces auth + server maintenance, violates anchor; rejected.

**Decision needed:** Confirm pin-exempt + 50-item / 500 MB cap + LRU `read_ids` bound.

## Q3 — Which audio source is canonical offline, and what bounds pre-download?

**Ambiguity:** §2 allows audio on GitHub Pages `/audio/...` *or* R2 "if configured"; §Interview defaults to hybrid smart caching (stream + one-tap "Pre-download Top 20" / auto Top-10 over Wi-Fi). No canonical URL rule, no size budget, no Wi-Fi-vs-cellular rule inside LiveContainer.

**Edge cases / failure modes:**
- R2 configured mid-week → same episode has two URLs; cached Pages file + new R2 URL double-stores or re-downloads on subway.
- Full Top-20 pre-download over cellular in transit burns data; auto Top-10 over "Wi-Fi" misfires on captive-portal subway Wi-Fi with no internet.
- LiveContainer `Documents/` fills with 37-channel audio (NotebookLM overviews are large) → iOS evicts / LiveContainer fails to launch; no failure UX specified.
- Stream-only fallback dies in tunnel with no graceful degraded state.

**Recommended approach:**
- Canonical-per-item URL: `data.json` emits single `audio_url` + `audio_sha` + `duration_s` + `bytes`; pipeline decides Pages-vs-R2 at build time, app never chooses. Cache key = sha, not URL, so source flips don't duplicate.
- Bounded hybrid: default manual "Download for commute" (Top 20); auto-download Top 10 only on unmetered Wi-Fi with reachability + `allowsExpensiveNetworkAccess=false`; hard storage ceiling (e.g. 1 GB) with LRU audio eviction, pins exempt per Q2. Always show download size before tap.
- Degraded playback: if offline and audio missing, text remains fully readable + inline "audio unavailable offline" state instead of spinner.

**Alternatives:**
- Download-all-37 — guarantees offline but violates lean-storage + Pages bandwidth; rejected (already rejected in interview, reaffirmed here).
- Stream-only — fails the core subway requirement; rejected.
- Background fetch / silent push pre-warm — unreliable under LiveContainer background restrictions (§4); rejected as primary, foreground-only per spec.

**Decision needed:** Confirm per-item canonical URL + sha key, 1 GB ceiling, expensive-network guard.

## Q4 — What does "optionally sync `read_ids`" mean without a server or login?

**Ambiguity:** Interview Q4 says "optionally sync `read_ids` to/from GitHub Pages or TubeLM local server if reachable." Both conflict with the scale anchor: GitHub Pages is static (no write endpoint), and a local server implies pairing, discovery, auth, and conflict resolution for one person.

**Edge cases / failure modes:**
- Split-brain: PWA `localStorage`, desktop GUI `read_state.json`, iOS sandbox diverge → same item read on phone shows unread on desktop, no merge rule.
- Naive last-write-wins over flaky transit network resurrects cleared items or wipes a commute's triage.
- Any writable sync endpoint on Pages or LAN introduces SSRF/auth surface the v4.0 hardening just closed.

**Recommended approach (anchor-compliant):**
- Local-first canonical, file-based portability only: iOS owns its `read_state`; export/import via Share Sheet / Files (`read-state.json`, same string-ID capped format as web) for manual reconciliation. No auto-sync, no network write path in v1.
- If any auto path is wanted later: read-only pull of a static `read-ids.json` published by desktop pipeline is the only Pages-compatible direction — and even that should be explicit opt-in, union-merge only (never delete local reads).

**Alternatives:**
- LAN sync to TubeLM Flask server (Bonjour + token) — doable but adds pairing UX, conflict UI, and a always-on desktop dependency for a 1-user commuter app; defer.
- iCloud KV / CloudKit sync — Apple-native but adds entitlements, container config, and LiveContainer sandbox uncertainty; defer.
- Third-party backend (Firebase/Supabase) — directly violates no-server anchor; rejected.

**Decision needed:** Lock v1 to local-only + manual export/import; remove "sync to GitHub Pages" wording or redefine as read-only pull.

## Q5 — How is foreground-only refresh atomic under flaky transit networking?

**Ambiguity:** §2 + §4 mandate silent ETag revalidate on every launch/foreground (7–8×/week, often mid-transit) with smooth in-place feed update and zero background daemons. No concurrency, ordering, or interruption rule.

**Edge cases / failure modes:**
- Rapid foreground/background cycling in subway triggers overlapping `URLSession` checks → race: older response overwrites newer, or feed re-renders mid-scroll breaking 120 Hz triage.
- ETag says "modified" but full fetch takes 30s on edge network; user starts reading cached copy — does mid-read swap yank scroll position?
- Deploy lands mid-check (new `data.json`, old audio) → Q1 partial-publishns recreates at the refresh layer.

**Recommended approach:**
- Single-flight refresh: coalesce foreground events, one in-flight check at a time, debounce (e.g. min 60s between checks); `ETag`/`Last-Modified` conditional GET, then full-body fetch with timeout (e.g. 15s, matching web SSRF/RSS guard precedent).
- Non-disruptive apply: validate-then-swap (per Q1); if user is scrolled/reading, stage new feed and show quiet "New briefing available — tap to refresh" pill instead of force-reloading; never move scroll under touch.
- Reachability-aware: on expensive/constrained network, still do the cheap header check but defer large audio prefetch; surface failures silently (keep cache, retry next foreground).

**Alternatives:**
- Force-reload on every foreground — simplest but janky mid-triage reloads; rejected.
- Background App Refresh / BGTaskScheduler pre-warm — unreliable in LiveContainer guest container per §4; rejected as dependency (may add opportunistically later).
- Push notification trigger — requires server + APNs + entitlements, violates anchor; rejected.

**Decision needed:** Confirm single-flight + staged-apply-pill + 60s debounce as the refresh contract.
