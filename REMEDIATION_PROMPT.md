# Code Review Feedback & Remediation Request for TubeLM (Muse Spark 1.3)

A thorough audit of your changes against [TUBELM_REVIEW_AND_FIX_PLAN.md](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/TUBELM_REVIEW_AND_FIX_PLAN.md) and [HANDOVER_PROMPT.md](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/HANDOVER_PROMPT.md) was completed. 

The majority of your surgical fixes (T2–T14, Tailwind CDN elimination, XML escaping, JSON sidecars, audio manifest join, cinematic opt-in) are solid and well-crafted. However, there are **two critical gaps and one skipped architectural item** that prevent sign-off:

---

## 1. Refuting "Pre-Existing Failures" & Fixing `test_immediate_checkpointing.py`

### The Fact Check
Prior to your changes, `.venv/bin/pytest desktop/tests -q` on the pristine tree passed completely: **147 passed in 48.62s (0 failures)**. The failures were not sandbox issues:
- `test_audio_and_video_queues_advance_independently` and `test_interim_top10...` failed because `_finish_background_artifacts()` was changed to return `tuple[bool, bool]` instead of `bool`. You patched those two tests, which now pass.
- However, **`test_each_channel_is_checkpointed_before_the_next_is_processed` is still failing (`1 failed, 150 passed`)**.

### The Root Cause
In `desktop/main.py`:
```python
if pending_weekly_audio_count() or pending_weekly_video_count() or pending_top_article_video_count():
    async with NotebookLMClient.from_storage(keepalive=600) as client:
```
In `desktop/tests/unit/test_immediate_checkpointing.py:52-53`, the test mocks:
```python
monkeypatch.setattr(main, "pending_weekly_video_count", lambda: 0)
monkeypatch.setattr(main, "pending_weekly_audio_count", lambda: 0)
```
Notice `pending_top_article_video_count` is **not mocked**. It reads the real `~/.tubelm/top_article_videos.json`, which contains jobs queued from local test runs. Because it returns `> 0`, `_finish_background_artifacts()` attempts to build a real `NotebookLMClient`, catches `_LoginRedirectError`, sets `artifacts_ok = False`, and causes `async_main()` to return `False`.

### Action Required
In [desktop/tests/unit/test_immediate_checkpointing.py](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/tests/unit/test_immediate_checkpointing.py), add:
```python
monkeypatch.setattr(main, "pending_top_article_video_count", lambda: 0)
```
alongside the other count mocks in `test_each_channel_is_checkpointed_before_the_next_is_processed`.

---

## 2. Missing R2 Purge Routine (T1 Incomplete)

### The Issue
You implemented `purge_audio(max_age_days: int = 14)` in [desktop/audio_storage.py](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/audio_storage.py), but **it is never called anywhere in the codebase**. 
In `desktop/main.py:_build_and_deploy_reader()`, only local `purge_old_digests_and_audio(...)` is invoked. As a result, files uploaded to Cloudflare R2 will accumulate forever without 14-day purging.

### Action Required
In [desktop/main.py](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/main.py) inside `_build_and_deploy_reader(cfg)`:
Call `audio_storage.purge_audio(14)` right alongside `purge_old_digests_and_audio`:
```python
    if deployed:
        try:
            purge_old_digests_and_audio(paths.get_summaries_dir(), paths.get_audio_dir(), max_age_days=14)
            import audio_storage
            if audio_storage.is_configured():
                audio_storage.purge_audio(max_age_days=14)
        except Exception:
            logger.exception("Post-deploy purge failed.")
```

---

## 3. Step 12 / Bottleneck B3: Overlapped Ingestion (`PIPELINE_OVERLAP`)

### The Issue
Step 12 in Section 4 of `TUBELM_REVIEW_AND_FIX_PLAN.md` (and Bottleneck B3) was completely skipped.
Section 3 explains:
> "Overlap ingestion of source N+1 with the wait of source N (bounded depth 2), keep the 120 s cooldown between chat calls only. Implement as two asyncio tasks with a Semaphore(2) around ingest+wait and a Lock around chat.ask. Expected 35–45 % wall-clock reduction. Put it behind PIPELINE_OVERLAP=true until a full run confirms NotebookLM doesn't rate-limit it."

### Action Required
- Add `pipeline_overlap: bool = False` to [desktop/config.py](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/config.py) (backed by `os.getenv("PIPELINE_OVERLAP", "false")`).
- Implement bounded depth-2 overlap in [desktop/main.py](file:///home/kedarnath-reddy-vallaboina/youtube-project-2/desktop/main.py) when `cfg.pipeline_overlap` is enabled, or ensure it gracefully falls back to serial execution by default.

---

## 4. Required Verification Protocol

Before declaring done, execute:
1. **Full Test Suite**:
   ```bash
   .venv/bin/pytest desktop/tests -v
   ```
   Must yield **0 failures (151 passed, 0 failed)**.
2. **Dry Run**:
   ```bash
   .venv/bin/python desktop/main.py --dry-run
   ```
   Must complete and exit code 0.
3. **Confirm R2 Purge Call**:
   Verify with `git grep "purge_audio"` that `audio_storage.purge_audio` is actually called in `desktop/main.py`.

Provide the exact terminal test output showing 100% test pass rate.
