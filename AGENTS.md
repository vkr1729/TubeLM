# AGENTS.md — Operational & Testing Rules for TubeLM

This document outlines mandatory operational, development, and testing rules that every agent working on TubeLM must strictly observe.

---

## 1. Never Run Bare `python desktop/main.py`
Running `python desktop/main.py` without arguments triggers a **full production sync** across all 37+ sources, consumes NotebookLM compute/quota, generates audio, updates production `state.json`, and saves durable resume markers.

### Required Testing Patterns:
- **For dry testing discovery & parsing:**
  ```bash
  .venv/bin/python desktop/main.py --dry-run
  ```
- **For testing a specific channel without sending emails:**
  ```bash
  .venv/bin/python desktop/main.py --sources "Aevy TV" --skip-email
  ```
- **For testing standalone subsystems, use their dedicated flags:**
  - **YouTube Playlist Publishing:** `.venv/bin/python desktop/main.py --publish-playlist 2026-10-02`
  - **YouTube Auth:** `.venv/bin/python desktop/main.py --youtube-auth`
  - **Web Reader Build:** `.venv/bin/python desktop/web_reader.py --build-only`
  - **GUI Server:** `.venv/bin/python desktop/main.py --gui --port 5000`

---

## 2. Never Leave `~/.tubelm/resume_request.json` Lingering
- If a manual test run is stopped midway (via `Ctrl+C`, `SIGTERM`, or crash), ensure no lingering `resume_request.json` remains in `~/.tubelm/`:
  ```bash
  rm -f ~/.tubelm/resume_request.json
  ```
- Any lingering resume file risks being resumed by background runners. (Note: A 3-hour TTL safeguard is now enforced in `run_control.py`, but hygiene requires manual cleanup after failed/interrupted tests).

---

## 3. Weekly Pipeline Orchestration Precedence
- The weekly pipeline is orchestrated on **Saturday evenings at 18:00** by **`friday-overnight.service`** (located in `~/Instagram_digest/run_friday_overnight.sh`), which executes:
  1. **Instagram Digest** first (`Instagram_digest/run_weekly.sh`).
  2. **TubeLM** second (`~/.tubelm/run_weekly.sh`).
  3. System power-off.
- **Do NOT re-enable `tubelm-resume.service` or `tubelm-sync.timer`** under systemd user `default.target`. TubeLM must only be triggered in sequence by `friday-overnight.sh` or explicitly by the user.

---

## 4. Recent Completion Guard (36-Hour Midnight-Safe Window)
- A `--scheduled` run will automatically exit with code `0` if a Top 20 digest has already been finalized and sent recently (within 36 hours, covering runs where `Instagram_digest` runs past midnight into Saturday morning).
- Never force an ad-hoc full sync on a day or weekend a digest has already been delivered, as re-initializing the cross-source batch risks overwriting the finalized Top 20 briefing with an incomplete partial batch.

---

## 5. Secret & Environment Protection
- Never view, edit, print, or expose `.env` credentials in chat, transcripts, or commit messages.
- Always inspect `.env.example` and `desktop/config.py` for schema, variable names, and defaults.
- Always check that `.gitignore` prevents secret and data leakages before committing.
