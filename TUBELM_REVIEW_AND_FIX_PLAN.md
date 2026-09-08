# TubeLM — Architectural & Runtime Review and Fix Plan

**Repository:** `vkr1729/TubeLM` @ `b68fa6e` (main), `gh-pages` @ `57ee157` (built 2026-09-06 12:30 UTC)
**Review target:** iPhone 16 / iOS 26+ standalone PWA reader on GitHub Pages; Ubuntu weekly pipeline with NotebookLM (`notebooklm-py 0.8.1`), `agy` Top 20 ranking, systemd resume.
**Evidence base:** full read of `desktop/main.py`, `notebooklm_service.py`, `web_reader.py`, `top10_service.py`, `weekly_audio_service.py`, `weekly_video_service.py`, `run_control.py`, `paths.py`, `config.py`, all source handlers, `templates/reader.html`; parsed the live `gh-pages` tree, embedded `SITE_DATA`, and `feed.xml`.

---

## 1. Executive Health Score

| Area | Score | One-line verdict |
| --- | --- | --- |
| Multi-source ingestion (RSS / YouTube / webpage) | **8 / 10** | Careful: per-source checkpoints, `None`-vs-`[]` semantics, API fallback, key never logged. Good engineering. |
| NotebookLM orchestration & durable resume | **7 / 10** | Locking, atomic state writes, quota deferral and systemd resume are well done. Two ordering bugs mean the output of that work (audio) doesn't reach the reader when it should. |
| Data hand-off between stages | **3 / 10** | Structured results are rendered to email HTML and then *re-parsed with BeautifulSoup* to build the reader. Audio is joined to digests by guessing filenames. Both joins are already producing wrong output on the live site. |
| Deployment | **2 / 10** | **Verified:** the current `gh-pages` commit is 303.7 MB, of which 303 MB is nine MP3s. It is force-pushed every week. This is a repo-bloat trap and a push-failure trap. |
| PWA reader (iOS 26 WebKit) | **5 / 10** | Layout and mobile stack nav depend on a runtime Tailwind CDN script; audio "stall recovery" restarts playback from 0:00 on healthy iOS streams; unbounded YouTube iframes. |
| **Overall** | **5 / 10** | The pipeline is the strongest part of either project. The last mile (join → build → deploy → play) is where it breaks. |

**Top three things to fix first:** (1) get MP3s out of git (host on the existing zero-cost R2 bucket), (2) replace filename-guessing with an explicit audio manifest and fix the week/run-date mismatch, (3) build and deploy the reader whenever new audio lands, and use `completed_source_keys` (not the last stage's list) to decide whether to build.

---

## 2. Critical Bugs & Architectural Flaws

Severity legend: **S1** = corrupts the weekly deliverable or breaks the deploy; **S2** = major degradation; **S3** = contained.

### T1 · S1 · 300 MB of MP3s are committed to `gh-pages` and force-pushed weekly

**ELI15.** Git is a database of every version of every file. Force-pushing an orphan branch does not delete the old commit on GitHub; it just makes it unreachable, and GitHub keeps unreachable objects around for a long time before garbage-collecting. So each week adds another ~300 MB of MP3 blobs to the repository's storage. GitHub starts nagging at 1 GB, throttles around 5 GB, and rejects any single file over 100 MB. A 40-minute multi-speaker overview at NotebookLM's native bitrate is 30–40 MB today (verified: `Think_School.mp3` = 40.3 MB); a longer notebook or a bitrate change pushes a file past 100 MB and the *entire* deploy fails (`git push` returns non-zero → `deploy_to_gh_pages` returns `False` → nothing on the phone updates and no one is told). Separately, pushing 300 MB over HTTPS from a home connection every week takes minutes and is the most likely step to time out.

**Verified.** `git ls-tree -r -l gh-pages`: 19 files, 303 716 690 bytes; nine files > 27 MB.

**Root cause.** `web_reader.build_reader_site()` copies audio into `site/audio/` (`web_reader.py:490-501`) and `deploy_to_gh_pages()` commits the whole directory (`:565-576`). `compress_audio` defaults to `False` (`config.py:134`), and even compressed audio would still be binary-in-git.

**Real-world trigger.** Any week with a >100 MB overview; any week the push is interrupted; three months of weekly pushes hitting GitHub's storage warnings.

**Surgical remediation.** You already run a zero-cost, Range-capable, `immutable`-cached media origin for Instagram Digest (Cloudflare R2 behind a Worker, `access-control-allow-origin: *` verified). Put TubeLM audio there under its own prefix, purge on the same 14-day rule, and reference the URL from the reader. `gh-pages` drops to < 1 MB.

New `desktop/audio_storage.py` (mirrors `Instagram_digest/storage_r2.py`, boto3 already a dependency there; add `boto3>=1.34` to `desktop/requirements.txt`):
```python
"""Zero-cost audio hosting on Cloudflare R2 (shared bucket with Instagram Digest)."""
from __future__ import annotations
import logging, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
PREFIX = "tubelm/audio"

def _client():
    acct, key, secret = (os.getenv(k, "").strip() for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))
    if not (acct and key and secret):
        return None
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=f"https://{acct}.r2.cloudflarestorage.com",
                        aws_access_key_id=key, aws_secret_access_key=secret, region_name="auto",
                        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}))

def bucket() -> str: return os.getenv("R2_BUCKET_NAME", "instagram-digest").strip()
def public_domain() -> str: return os.getenv("R2_PUBLIC_DOMAIN", "").strip().rstrip("/")
def is_configured() -> bool: return _client() is not None and bool(public_domain())

def upload_audio(local: Path, run_date: str) -> str:
    """Upload (idempotent) and return the public URL, or '' when R2 is not configured/available."""
    s3 = _client()
    if not s3 or not public_domain():
        return ""
    key = f"{PREFIX}/{run_date}/{local.name}"
    url = f"{public_domain()}/{key}"
    try:
        s3.head_object(Bucket=bucket(), Key=key)
        return url
    except Exception:
        pass
    try:
        s3.upload_file(str(local), bucket(), key, ExtraArgs={
            "ContentType": "audio/mpeg",
            "CacheControl": "public, max-age=1209600, immutable"})
        logger.info("Uploaded audio to R2: %s", url)
        return url
    except Exception:
        logger.exception("R2 audio upload failed for %s", local.name)
        return ""

def purge_audio(max_age_days: int = 14) -> int:
    s3 = _client()
    if not s3:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).date()
    stale = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=PREFIX + "/"):
        for obj in page.get("Contents") or []:
            m = re.search(r"/(\d{4}-\d{2}-\d{2})/", obj["Key"])
            if m and datetime.strptime(m.group(1), "%Y-%m-%d").date() < cutoff:
                stale.append({"Key": obj["Key"]})
    for i in range(0, len(stale), 1000):
        s3.delete_objects(Bucket=bucket(), Delete={"Objects": stale[i:i + 1000], "Quiet": True})
    return len(stale)
```
`web_reader.build_reader_site()` — replace the copy block (`:490-501`):
```python
                        if ch_data.get("audio_path") and Path(ch_data["audio_path"]).exists():
                            src_audio = Path(ch_data["audio_path"])
                            remote = audio_storage.upload_audio(src_audio, d_str) if audio_storage.is_configured() else ""
                            if remote:
                                ch_data["audio_url"] = remote
                            else:                                   # local-only fallback (GUI /reader), never for gh-pages
                                dest_audio = site_audio_dir / src_audio.name
                                if not dest_audio.exists() or dest_audio.stat().st_size != src_audio.stat().st_size:
                                    shutil.copy(src_audio, dest_audio)
                                ch_data["audio_url"] = f"audio/{src_audio.name}"
```
`deploy_to_gh_pages()` — hard guard so this can never regress:
```python
    big = [p for p in site_dir.rglob("*") if p.is_file() and p.stat().st_size > 5 * 1024 * 1024]
    if big:
        logger.error("Refusing to deploy: %d file(s) over 5 MB in site dir (binary assets belong on R2): %s",
                     len(big), ", ".join(p.name for p in big[:5]))
        return False
```
and add `audio_storage.purge_audio(14)` next to `purge_old_digests_and_audio`. Add the five `R2_*` keys to `.env.example`. One-time cleanup: after the first R2 deploy, ask GitHub Support to run GC on the repo, or simply delete and recreate the `gh-pages` branch (Settings → Pages → re-select branch) — unreachable blobs are dropped on the next server-side GC.

---

### T2 · S1 · Audio overviews are attached to the wrong week (verified on the live site)

**ELI15.** The audio service names files by the **Monday of the week** (`current_week_start()` → `2026-08-31_Think_School.mp3`), but the reader looks for audio named by the **digest's run date** (`2026-09-04_Think_School.mp3`). That lookup always misses, so the reader falls back to `sorted(glob("*Think_School*.mp3"))[0]` — the *alphabetically first*, i.e. the **oldest** matching file. The result on the live site: the previous-week digest (run 2026-08-29) shows `2026-08-31_*.mp3`, which was generated from the *following* week's videos; and when two weeks of audio coexist, the current week gets last week's overview.

**Verified.** In `gh-pages/index.html` `SITE_DATA`: `prev` (run_date `2026-08-29`) → Felix & Friends, Two Minute Papers, MIT Tech Review, Doctor Alex, IBM Technology all point at `audio/2026-08-31_*.mp3`. `current` (run_date `2026-09-04`) → same `2026-08-31_*.mp3` files. Same MP3 attached to two different digests with different video lists.

**Root cause.** Two independent modules each "remember" a filename convention, and neither matches the other:
- `weekly_audio_service._start_or_poll_audio()` (`:134-135`) names the file `f"{entry.get('week_start') or 'current'}_{safe_name}.mp3"`. `register_weekly_audio()` never copies `week_start` onto the entry (only onto the batch), so the **committed code writes `current_<name>.mp3`** — one file per channel, overwritten every week, never matched by the purge regex `^\d{4}-\d{2}-\d{2}_`, and picked up by the glob for *every* week. The live site's `2026-08-31_*.mp3` names show the deployed machine ran a variant that used the batch's Monday `week_start`; that variant is wrong in the way described above, the committed one is wrong in a worse way.
- `web_reader.parse_channel_digest()` (`:244-263`) expects `{run_date}_{safe_name}.mp3` (the digest's run date), tries three guesses, then falls back to `sorted(glob("*name*.mp3"))[0]`.

**Surgical remediation.** Stop guessing. Carry the digest date on the entry and write an explicit manifest.

`notebooklm_service.process_source_items()` — record the date the digest belongs to:
```python
    result: dict = {
        "channel_name": source_name, "run_date": today, ...
```
`notebooklm_service.schedule_artifacts_after_delivery()` → `register_weekly_audio(..., run_date=result["run_date"])`.

`weekly_audio_service.register_weekly_audio()` — accept and store it:
```python
def register_weekly_audio(*, notebook_id, notebook_url, source_name, channel_order, source_ids, instructions,
                          run_date: str, week_start: str | None = None) -> None:
    ...
    entry.update({..., "run_date": run_date})
```
`_start_or_poll_audio()` — name by run date and write the manifest:
```python
                run_date = entry.get("run_date") or entry.get("week_start") or date.today().isoformat()
                audio_filename = f"{run_date}_{safe_name}.mp3"
                ...
                entry["audio_file"] = audio_filename
                _record_audio_manifest(run_date, entry["notebook_id"], entry.get("source_name", ""), audio_filename)
```
with
```python
def _record_audio_manifest(run_date: str, notebook_id: str, source_name: str, filename: str) -> None:
    path = paths.get_audio_dir() / "manifest.json"
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): data = {}
    data[f"{run_date}|{paths.safe_channel_name(source_name)}"] = {"notebook_id": notebook_id, "file": filename}
    tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(data, indent=2), encoding="utf-8"); os.replace(tmp, path)
```
`web_reader.parse_channel_digest()` — exact join only:
```python
    manifest = _load_audio_manifest(audio_dir)             # {"run_date|safe_name": {"file": ...}}
    hit = manifest.get(f"{run_date}|{safe_name}")
    if len(videos) > 1 and hit:
        p = audio_dir / hit["file"]
        if p.exists() and p.stat().st_size > 0:
            has_audio, audio_path, audio_filename = True, p, p.name
    # fallback ONLY for legacy files: exact run_date prefix, never a glob
    if not has_audio and len(videos) > 1:
        p = audio_dir / f"{run_date}_{safe_name}.mp3"
        if p.exists() and p.stat().st_size > 0:
            has_audio, audio_path, audio_filename = True, p, p.name
```
Delete the `*{safe_name}*.mp3` glob. Wrong audio is worse than no audio.

---

### T3 · S1 · The reader is built/deployed only if the **last retry stage** had successes

**ELI15.** `successful_keys` is re-created at the top of every retry stage. After the loop, `if not dry_run and successful_keys:` (`main.py:832`) looks at the *last* stage's list. Stage 0 can finish 30 channels; if the two fast retries then fail their remaining 3 channels, `successful_keys` is `[]` and the site is never built — 30 fresh digests sit on disk and the phone shows last week. If `handlers` is empty (fresh install, filter mismatch), the loop `break`s before `successful_keys` is ever assigned → `NameError` at line 832 after all NotebookLM work is done.

**Remediation.**
```python
    successful_keys: list[str] = []          # before the `for stage_idx, stage in enumerate(retry_stages)` loop
    ...
    if not dry_run and completed_source_keys:  # line 832: use the run-wide set
```

---

### T4 · S1 · Audio finishes hours later, but nothing rebuilds the reader when it lands

**ELI15.** Audio Overviews take 10–30 minutes each and run as a background queue with 15-minute polling and systemd resume. The reader is built *immediately* after the queue is merely *started* (`main.py:823` then `:832-846`). Later, the resume runs use `artifacts_only=True`, which returns from `async_main` before the build step (`:516-522`). So audio only shows up on the phone when a *later* run happens to rebuild — by then the week has rolled to "Previous". (This is the mechanism behind the 2026-09-06 rebuild that surfaced the 08-31 audio two days after the 09-04 run.)

**Remediation.** Detect newly-landed audio and rebuild (cheap once T1 removes MP3s from the push).
```python
def _audio_inventory() -> set[str]:
    d = paths.get_audio_dir()
    return {p.name for p in d.glob("*.mp3")} if d.exists() else set()

async def _finish_background_artifacts(cfg, *, seal_video_batch, send_completion_emails=True) -> tuple[bool, bool]:
    before = _audio_inventory()
    ...existing body...
    new_audio = bool(_audio_inventory() - before)
    return (not pending), new_audio
```
Update the three call sites to unpack `(ok, new_audio)`, and add a helper used both at the end of `async_main` and in the `artifacts_only` branch:
```python
def _build_and_deploy_reader(cfg) -> None:
    from web_reader import build_reader_site, deploy_to_gh_pages
    build_reader_site(paths.get_summaries_dir(), paths.get_audio_dir(), paths.get_site_dir(),
                      cfg.sources_file, compress_audio=getattr(cfg, "compress_audio", False))
    if getattr(cfg, "deploy_to_gh_pages", True):
        deploy_to_gh_pages(paths.get_site_dir())

        if artifacts_only:
            ok, new_audio = await _finish_background_artifacts(cfg, seal_video_batch=False,
                                                              send_completion_emails=completion_emails_enabled)
            if new_audio:
                try: _build_and_deploy_reader(cfg)
                except Exception: logger.exception("Reader rebuild after audio completion failed.")
            return ok
```

---

### T5 · S2 · `feed.xml` is not well-formed XML (verified)

**ELI15.** Channel names are dropped raw into `<title>`. "Felix & Friends (Goat Academy)" puts a bare `&` in XML, which is illegal; every strict feed reader (Apple News, NetNewsWire, Feedly's validator) rejects the whole feed.

**Verified.** `xml.etree.ElementTree.fromstring(feed.xml)` → `not well-formed (invalid token): line 126, column 37`.

**Remediation (`web_reader.generate_rss_feed`).**
```python
from xml.sax.saxutils import escape as xml_escape
def _cdata(s: str) -> str: return "<![CDATA[" + (s or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"
...
      <title>{xml_escape(f"[{ch.get('category','Digest').upper()}] {ch.get('name','Source')} — TubeLM Briefing")}</title>
      <link>{xml_escape(link)}</link>
      <guid isPermaLink="false">{xml_escape(f"{base_url}#{ch.get('id')}-{run_date}")}</guid>
      <description>{_cdata(desc)}</description>
```
Apply `xml_escape` to every interpolated value (`title`, `link`, `guid`, the Top 20 `<li>` text inside the CDATA is fine). Also set `pubDate` from the digest date, not `now()`, so readers don't mark everything unread on each rebuild. Add a unit test that parses the generated feed with `ElementTree`.

---

### T6 · S2 · Structured data round-trips through rendered email HTML and is re-parsed with BeautifulSoup

**ELI15.** `main.py` has a rich `result` dict (channel, notebook URL, items, summary). It renders that to the *email template* and saves the HTML. `web_reader.py` then loads that HTML and scrapes it back into a dict using selectors like `h1`, `.item-card`, `.summary-html`, a `div` whose `string` contains "Published", and for Top 20, `tr .rank-cell` and `div[style*="uppercase"]` (`web_reader.py:138-182, 190-237`). Any change to `email_digest.html` or `top10_digest.html` — a class rename, a wrapper div — silently makes channels, dates, links or the whole Top 20 vanish from the reader. There is no error, just a thinner site. Same pattern in `top10_service.load_candidates_from_html_digests()`.

**Remediation.** Emit a JSON sidecar next to every HTML digest, and make the reader prefer it.

`main.py` (after `html_path.write_text(...)`, `:684`):
```python
                    sidecar = {
                        "run_date": run_date, "channel_name": result["channel_name"],
                        "source_type": result.get("source_type"), "category": handler.category,
                        "notebook_url": result.get("notebook_url", ""), "notebook_id": result.get("notebook_id", ""),
                        "summary_text": result.get("summary_text", ""), "items": result.get("items", []),
                    }
                    (html_path.with_suffix(".json")).write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
```
`top10_service._rank_render_and_send()` (after writing HTML): `output_path.with_suffix(".json").write_text(json.dumps(selection, ...))`.

`web_reader.py`: `parse_channel_digest_json(path, sources_map, audio_dir)` that builds the same dict, rendering `summary_html` with the same tools the email uses:
```python
from email_service import _split_markdown_summary_by_videos, _strip_citations
from markdown_it import MarkdownIt
_md = MarkdownIt("commonmark", {"html": False})
    per_item = _split_markdown_summary_by_videos(_strip_citations(data["summary_text"]), data["items"], data["channel_name"])
    for it in data["items"]:
        videos.append({..., "summary_html": _md.render(per_item.get(it["url"], "")) if per_item else ""})
```
In `build_reader_site`, iterate `*.json` first and only fall back to HTML parsing for files with no sidecar. Add `purge_old_digests_and_audio` handling for `.json`.

---

### T7 · S2 · The PWA's layout and mobile navigation depend on a runtime Tailwind CDN script

**ELI15.** `<script src="https://cdn.tailwindcss.com">` is the *Play CDN*: a ~110 KB (gzipped) compiler that runs in the browser, scans the DOM, and generates CSS on the fly, on every page load. Tailwind itself prints "should not be used in production" in the console. On the reader, the classes that implement the **mobile stack navigation** (`hidden`, `md:hidden`, `md:block`, `flex`, `flex-1`, `overflow-hidden`, `space-y-*`, `max-w-4xl`, the modal's `fixed inset-0 z-50`) are all Tailwind utilities. If the CDN is slow, blocked, or the phone is offline, the PWA shows the sidebar *and* the reading pane stacked, "← Channels" does nothing, the video theater modal renders inline at the bottom of the page. It also delays first paint by the script download + JIT time (200–500 ms on an iPhone 16 on LTE) and re-runs the JIT after every `innerHTML` re-render because the CDN build installs a `MutationObserver`.

**Root cause.** `reader.html:26`; the CSS custom-property design is already 90 % hand-written, only ~45 utilities are used.

**Remediation.** Replace the CDN with ~60 lines of hand-written utilities and delete the script tag. The complete set used by the template:
```css
/* --- utilities formerly from Tailwind Play CDN --- */
.hidden{display:none!important}.flex{display:flex}.inline-flex{display:inline-flex}.block{display:block}
.flex-1{flex:1 1 0%}.flex-col{flex-direction:column}.items-center{align-items:center}.items-baseline{align-items:baseline}
.justify-between{justify-content:space-between}.justify-center{justify-content:center}.flex-shrink-0{flex-shrink:0}
.gap-1{gap:4px}.gap-1\.5{gap:6px}.gap-2{gap:8px}.gap-4{gap:16px}
.space-y-1>*+*{margin-top:4px}.space-y-2>*+*{margin-top:8px}.space-y-4>*+*{margin-top:16px}.space-y-6>*+*{margin-top:24px}
.p-2{padding:8px}.p-3{padding:12px}.p-4{padding:16px}.px-2{padding-left:8px;padding-right:8px}.px-4{padding-left:16px;padding-right:16px}
.py-1{padding-top:4px;padding-bottom:4px}.py-3{padding-top:12px;padding-bottom:12px}.py-6{padding-top:24px;padding-bottom:24px}.py-20{padding-top:80px;padding-bottom:80px}
.pt-2{padding-top:8px}.pb-0\.5{padding-bottom:2px}.pb-1{padding-bottom:4px}.pb-2{padding-bottom:8px}.pb-4{padding-bottom:16px}
.mb-1{margin-bottom:4px}.mb-1\.5{margin-bottom:6px}.mb-4{margin-bottom:16px}.mt-1{margin-top:4px}.mx-auto{margin-left:auto;margin-right:auto}
.w-full{width:100%}.w-px{width:1px}.h-4{height:16px}.h-full{height:100%}.max-w-4xl{max-width:56rem}.max-w-\[75\%\]{max-width:75%}
.overflow-hidden{overflow:hidden}.overflow-y-auto{overflow-y:auto}.overflow-x-auto{overflow-x:auto}.relative{position:relative}.fixed{position:fixed}.inset-0{inset:0}.z-50{z-index:50}
.rounded-xl{border-radius:12px}.border{border-width:1px;border-style:solid}.border-b{border-bottom:1px solid}.truncate{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.text-xs{font-size:12px;line-height:16px}.text-sm{font-size:14px;line-height:20px}.text-2xl{font-size:24px;line-height:32px}.text-\[10px\]{font-size:10px}.text-\[11px\]{font-size:11px}
.font-mono{font-family:'JetBrains Mono',ui-monospace,monospace}.font-semibold{font-weight:600}.font-bold{font-weight:700}.uppercase{text-transform:uppercase}.tracking-tight{letter-spacing:-.025em}.tracking-wider{letter-spacing:.05em}
.text-center{text-align:center}.text-white{color:#fff}.text-gray-400{color:#9ca3af}.text-amber-400{color:#fbbf24}
.aspect-video{aspect-ratio:16/9}.bg-black{background:#000}.bg-black\/80{background:rgba(0,0,0,.8)}.backdrop-blur-sm{backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}.shadow-2xl{box-shadow:0 25px 50px -12px rgba(0,0,0,.5)}
.w-3\.5{width:14px}.h-3\.5{height:14px}.w-72{width:18rem}.w-80{width:20rem}
.text-\[var\(--text-muted\)\]{color:var(--text-muted)}.text-\[var\(--text-primary\)\]{color:var(--text-primary)}.text-\[var\(--success\)\]{color:var(--success)}
.border-\[var\(--border-color\)\]{border-color:var(--border-color)}.bg-\[\#11120f\]{background:#11120f}.bg-\[\#171815\]{background:#171815}
.hover\:text-white:hover{color:#fff}
@media(min-width:640px){.sm\:inline{display:inline}.sm\:block{display:block}.sm\:flex-row{flex-direction:row}.sm\:items-center{align-items:center}.sm\:gap-3{gap:12px}}
@media(min-width:768px){.md\:block{display:block}.md\:hidden{display:none!important}.md\:w-72{width:18rem}}
@media(min-width:1024px){.lg\:w-80{width:20rem}}
```
Verification for the agent: `grep -o 'class="[^"]*"' reader.html | tr ' ' '\n' | sort -u` must be a subset of the classes defined above plus the template's own `.classes`. Keep the Google Fonts `<link>` but give every `font-family` a system fallback (already true) so an offline load still renders.

---

### T8 · S2 · `</script>` injection breaks the whole reader; raw titles break cards

**ELI15.** `SITE_DATA` is `json.dumps(...)` dropped inside a `<script>` block with `| safe`. HTML parsing does not care that it's inside a JSON string: the first `</script>` anywhere in any summary ends the script, and the reader renders blank. Tech summaries about web security are exactly where the literal string `</script>` shows up. Separately, titles and `why_it_matters` are interpolated into `innerHTML` unescaped; a YouTube title like `AI <3 Rust` or `<Untitled>` produces broken markup.

**Remediation.**
`web_reader.py`:
```python
    site_data_json = json.dumps(site_data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
```
`reader.html`: add `function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}` and wrap `item.title`, `item.source_name`, `item.why_it_matters`, `ch.name`, `v.title`, `v.published` in `esc()` inside `renderSidebar` / `renderActiveView`. Leave `summary_html` as is (it is your own markdown renderer's output with `html: False`).

---

### T9 · S2 · iOS audio "stall recovery" restarts a 40-minute overview from 0:00, and fires on healthy playback

**ELI15.** Safari on iOS emits `stalled` routinely during normal HTTP buffering (it means "no bytes arrived for a moment", not "playback is broken"). The recovery handler waits 1.5 s, then **re-assigns `src`** and sets `currentTime = lastTime`. Setting `currentTime` on an element whose new source hasn't loaded metadata yet is ignored by WebKit, so playback restarts at 0:00. So the "fix" for a hiccup is to throw away 25 minutes of listening progress — and it can trigger when nothing was wrong.

**Root cause.** `reader.html:1578-1608`.

**Remediation.** Recover only on real errors or a progress watchdog; restore position after `loadedmetadata`; persist position per track so a real restart resumes anyway.
```js
let lastAudioProgressAt = 0;
globalAudio.addEventListener('timeupdate', () => { lastAudioProgressAt = performance.now();
  try { localStorage.setItem('tubelm_pos:' + currentAudioSrc, String(globalAudio.currentTime)); } catch (_) {} });
globalAudio.removeEventListener?.('stalled', ...);   // delete the stalled handler entirely
globalAudio.addEventListener('waiting', () => setAudioBuffering(true));
globalAudio.addEventListener('playing', () => { setAudioBuffering(false); isAudioRecovering = false; });
globalAudio.addEventListener('error', () => { if (isAudioPlaying) tryRecoverAudio(); });
setInterval(() => {
  if (!isAudioPlaying || globalAudio.paused || isAudioRecovering) return;
  if (performance.now() - lastAudioProgressAt > 12000 && globalAudio.readyState < 3) tryRecoverAudio();
}, 3000);

function tryRecoverAudio() {
  if (!currentAudioSrc || isAudioRecovering) return;
  isAudioRecovering = true;
  const resumeAt = globalAudio.currentTime || 0;
  const src = currentAudioSrc;
  globalAudio.addEventListener('loadedmetadata', function once() {
    globalAudio.removeEventListener('loadedmetadata', once);
    if (resumeAt > 0 && resumeAt < globalAudio.duration) globalAudio.currentTime = resumeAt;
    globalAudio.play().catch(() => {}).finally(() => { isAudioRecovering = false; });
  });
  globalAudio.src = src + (src.includes('?') ? '&' : '?') + 'r=' + Date.now();   // bust a poisoned cache entry
  globalAudio.load();
}
```
In `toggleAudio()`, when starting a new `src`, read `tubelm_pos:<src>` and seek in `loadedmetadata` — free "resume where I left off".

---

### T10 · S2 · Full-pane `innerHTML` re-render desyncs the audio controller and kills inline players

**ELI15.** "Mark as Read" calls `renderActiveView()`, which rebuilds the entire reading pane with `innerHTML`. The audio keeps playing (the `<audio>` element lives outside the pane) but the freshly rendered button shows the *play* icon, the progress bar starts from 0 %, and any YouTube iframe you were watching is destroyed mid-video. Tapping the play button then *pauses* (same `src`) while the icon suggested it would play.

**Remediation.** Render controller state from state, and update in place for the read toggle:
```js
// in the audioSection template:
const playing = isAudioPlaying && currentAudioSrc === ch.audio_url;
<svg id="play-icon" viewBox="0 0 24 24"><path d="${playing ? 'M6 19h4V5H6v14zm8-14v14h4V5h-4z' : 'M8 5v14l11-7z'}"/></svg>
// toggleRead(): replace `renderSidebar(); renderActiveView();` with
renderSidebar();
const btn = document.querySelector('[data-role="read-toggle"]'); if (btn) btn.textContent = nowRead ? 'Mark as Unread' : 'Mark as Read ✓';
```
(Give the button `data-role="read-toggle"`.) Also make `globalAudio.ontimeupdate` a no-op when the pane doesn't contain the current track's player (`document.querySelector('[data-audio-src]')?.dataset.audioSrc === currentAudioSrc`).

---

### T11 · S2 · YouTube iframes accumulate and can play simultaneously

**ELI15.** Each facade click mounts a `youtube-nocookie` iframe and nothing ever unmounts it. A channel with 6–7 videos (verified: The PrimeTime 6, WorldofAI 7, MIT Tech Review 7) lets the user open all of them; each YouTube player is its own process-heavy web view (~60–120 MB in WebKit). On an iPhone that is a fast path to the "This webpage was reloaded because it was using significant memory" banner, and two players can be playing audio at once because YouTube iframes don't coordinate.

**Remediation.** Single-active-player policy:
```js
let activePlayerWrapper = null;
function unmountPlayer(wrapper) {
  if (!wrapper || !wrapper.dataset.facade) return;
  wrapper.innerHTML = wrapper.dataset.facade;      // restore the thumbnail facade
}
function toggleVideoPlayer(wrapperId, videoId, title) {
  const wrapper = document.getElementById(wrapperId); if (!wrapper) return;
  if (isAudioPlaying && !globalAudio.paused) { globalAudio.pause(); isAudioPlaying = false; updatePlayIcon(); }
  if (activePlayerWrapper && activePlayerWrapper !== wrapper) unmountPlayer(activePlayerWrapper);
  if (!wrapper.querySelector('iframe')) {
    wrapper.dataset.facade = wrapper.innerHTML;
    wrapper.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${videoId}?playsinline=1&rel=0" ...></iframe>`;
    activePlayerWrapper = wrapper;
  }
}
```
Note `autoplay=1` was removed: iOS never honours autoplay inside a cross-origin iframe, so it only costs a wasted play attempt; the user taps YouTube's own play button either way. `closeVideoModal()` and `renderActiveView()` should set `activePlayerWrapper = null`.

---

### T12 · S2 · Orphan notebooks are never pruned → `NotebookLimitError` halts the whole batch

**ELI15.** Retention deletes only notebooks whose title starts with `"<current source name> Digest — "`. Rename a source, remove it from `sources.json`, or have a run crash after creating the notebook but before summarizing, and that notebook lives forever. NotebookLM caps notebooks per account; when the cap is hit, `NotebookLimitError` stops processing every remaining source in the stage (`main.py:656-659`).

**Remediation.** One global sweep at the start of the run (`notebooklm_service.py`):
```python
_DIGEST_TITLE = re.compile(r"^(?P<name>.+) Digest — (?P<date>\d{4}-\d{2}-\d{2})$")

async def prune_stale_digest_notebooks(client, max_age_days: int = 14) -> int:
    cutoff = date.today() - timedelta(days=max_age_days)
    deleted = 0
    for nb in await client.notebooks.list():
        m = _DIGEST_TITLE.match(nb.title or "")
        if m and date.fromisoformat(m.group("date")) < cutoff:
            try:
                await client.notebooks.delete(nb.id); deleted += 1
            except Exception:
                logger.warning("Could not delete stale notebook %s", nb.id)
    return deleted
```
Call it once after the auth gate in `async_main` (inside a short-lived `NotebookLMClient.from_storage()`), and keep the per-source limit as a second line of defence.

---

### T13 · S3 · The `agy` prompt is passed as a single argv string that can exceed Linux's 128 KB per-argument limit

**ELI15.** `top10_service` builds a prompt containing up to 80 000 characters of summaries plus JSON quoting and instructions, and passes it as `-p <prompt>`. Linux limits a single argument to `MAX_ARG_STRLEN` = 131 072 **bytes**; UTF-8 curly quotes, em dashes and non-Latin titles are 2–3 bytes each. Cross the line and `subprocess.run` raises `OSError: [Errno 7] Argument list too long` → `Top10DigestError("agy could not be started")` → no Top 20 that week.

**Remediation.** Write the prompt to a temp file and pass it on stdin (or `-p "$(cat file)"` is the same problem; use stdin):
```python
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as pf:
        pf.write(prompt); prompt_path = pf.name
    command = [agy_bin, "-p", "-", "--model", AGY_MODEL, ...]      # if agy supports '-' for stdin; otherwise use its --prompt-file flag
    completed = subprocess.run(command, input=prompt, ...)
```
Verify the exact `agy` flag once; also lower the budget: `80_000 // n` → `60_000 // n` keeps the worst case comfortably below 128 KB even at 3 bytes/char.

---

### T14 · S3 · Week partitioning by "days since the newest file" mis-files deferred resumes; purge runs inside the build

Digests are bucketed as "current" if within 4 days of the newest file, "prev" if 5–14 days. A compute-deferred resume that completes 3 sources on day 5 lands them in "prev" (and the reader then shows them under last week's date). Also `build_reader_site()` *deletes* files (`purge_old_digests_and_audio`) — a `--build-only` preview is destructive.

**Remediation.** Bucket by ISO week of the run date (`date.isocalendar()[:2]`), not by distance from the newest file; move the purge into `main.py` after the build (`if deploy succeeded: purge`). This keeps `web_reader.py` a pure function of its inputs.

---

## 3. Major Performance Bottlenecks

| # | Bottleneck | Where | Impact | Fix |
| --- | --- | --- | --- | --- |
| B1 | **300 MB git push per week; MP3 in git.** | `web_reader.deploy_to_gh_pages` | Multi-minute deploys, push failures, repo bloat, 100 MB file rejection. | T1. |
| B2 | **Uncompressed 30–40 MB MP3 per channel over cellular.** | `config.compress_audio=False` | 9 overviews ≈ 300 MB/week of phone data; slow seeks. | Default `COMPRESS_AUDIO=true`; `ffmpeg -c:a libmp3lame -b:a 64k -ac 1 -ar 44100` gives ~15 MB for 40 min with no audible loss on speech. iOS plays MP3 with full Range/seek support. |
| B3 | **Fully serial NotebookLM pipeline.** 120 s cooldown × (N−1) + per-source `wait_for_sources` (≤300 s) + summary retries. 37 sources ≈ 3–4 h. | `main.py:648-651`, `notebooklm_service.process_source_items` | Long runs; the machine must stay awake; the deferral machinery gets exercised more than it should. | Overlap *ingestion* of source N+1 with the *wait* of source N (bounded depth 2), keep the 120 s cooldown between **chat** calls only. Implement as two `asyncio` tasks with a `Semaphore(2)` around `ingest+wait` and a `Lock` around `chat.ask`. Expected 35–45 % wall-clock reduction. Put it behind `PIPELINE_OVERLAP=true` until a full run confirms NotebookLM doesn't rate-limit it. |
| B4 | **Runtime Tailwind JIT on every load and after every `innerHTML` mutation.** | `reader.html:26` | +200–500 ms first paint on LTE; CPU on every render. | T7. |
| B5 | **`/reader` GET rebuilds the entire site** (purge + Pillow icons + audio copy + Jinja) on every request. | `gui.py:658-665` | 2–10 s page loads locally; destructive purge as a side effect of a GET. | Build once per pipeline run; serve `~/.tubelm/site/index.html` statically; expose "Rebuild" as the existing `POST /api/reader/build` only. |
| B6 | **`index.html` embeds both weeks' full summaries (485 KB) and re-renders the whole pane per click.** | `web_reader.py:533`, `reader.html:1271` | Fine today; grows linearly with sources × 2 weeks. | Optional: split `SITE_DATA.weeks.prev` into `data/prev.json` fetched lazily on first "Previous Week" tap. |

---

## 4. Execution Blueprint (ordered for an autonomous coding agent)

Constraints: flat two-layer "boring code"; no Node toolchain; keep `notebooklm-py 0.8.1`; every state write via the existing `tmp + os.replace` pattern; run `PYTHONPATH=desktop pytest desktop/tests -q` after each step.

- [ ] **Step 1 — Audio off git (T1, B2).** Add `desktop/audio_storage.py`; `boto3` to requirements; `R2_*` to `.env.example`; `build_reader_site` uses R2 URL when configured; `deploy_to_gh_pages` refuses files > 5 MB; `purge_audio(14)` added; `COMPRESS_AUDIO` default `true`. Test: build with a fake 6 MB file in `site/` → deploy returns `False` before `git init`.
- [ ] **Step 2 — Audio manifest & run-date join (T2).** `run_date` on `result`, on audio entries, in filenames; `manifest.json`; reader joins by exact key; glob fallback deleted. Test: two audio files `2026-08-24_X.mp3` and `2026-08-31_X.mp3` with a digest dated `2026-09-04` and a manifest entry → reader picks the manifest file; with no manifest entry → `has_audio=False`.
- [ ] **Step 3 — Build trigger correctness (T3, T4).** `successful_keys` initialised before the loop; build condition uses `completed_source_keys`; `_finish_background_artifacts` returns `(ok, new_audio)`; `artifacts_only` path rebuilds when new audio landed. Test: unit test `test_pipeline_runner.py` where stage 0 succeeds and stage 2 fails → `build_reader_site` called once.
- [ ] **Step 4 — Sidecar JSON (T6).** Write `.json` next to every channel and Top 20 HTML; reader prefers JSON; BeautifulSoup path retained only as fallback; purge covers `.json`. Test: rename `.item-card` in the email template → reader output unchanged.
- [ ] **Step 5 — Valid RSS (T5).** Escape all interpolations; digest-dated `pubDate`; ElementTree parse test.
- [ ] **Step 6 — Reader hardening (T7, T8).** Inline utility CSS, delete Tailwind CDN script; `</`-escaped `SITE_DATA`; `esc()` on all user-visible strings. Test: load `index.html` with network blocked for `cdn.tailwindcss.com` (Playwright route abort) → mobile "← Channels" still hides the sidebar.
- [ ] **Step 7 — Audio controller (T9, T10).** Remove `stalled` handler; watchdog + `loadedmetadata` resume; per-track position persistence; state-driven play icon; in-place read toggle.
- [ ] **Step 8 — Single active YouTube player (T11).** Facade restore, `autoplay` removed, `activePlayerWrapper` reset on modal close/pane render.
- [ ] **Step 9 — Notebook sweep (T12).** `prune_stale_digest_notebooks` after the auth gate.
- [ ] **Step 10 — agy prompt via stdin (T13).** Confirm flag; reduce summary budget.
- [ ] **Step 11 — Pure build + ISO-week bucketing (T14, B5).** Purge moved to `main.py`; `/reader` serves the static build.
- [ ] **Step 12 — Overlapped ingestion behind a flag (B3).**

**Definition of done:** `gh-pages` under 1 MB; every channel's audio in the reader matches its own run date; a run where only stage 0 succeeds still deploys; the reader renders and navigates on an iPhone in Airplane Mode after one prior online load; `feed.xml` validates; a 10-minute audio listen on LTE never jumps back to 0:00.
