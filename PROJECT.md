# TubeLM Top 10 Video Downloader & Rotating Cache

## Outcome
Automatically download the top-ranked weekly YouTube videos locally into `/home/kedarnath-reddy-vallaboina/Downloads/TorBox/Top_10` to avoid algorithm rabbit holes and keep focus on high-signal content. Maintains a clean 2-week rolling window by rotating unwatched videos to `Top_10_Prev` and purging stale videos older than two weeks.

## Scope
- **Current module:**
  1. Safe two-week folder rotation: permanently purge `Top_10_Prev`, then move remaining unwatched files from `Top_10` to `Top_10_Prev`.
  2. Filter Top 10 items for YouTube videos (ignoring text/web articles) and download them via `yt-dlp` in 1080p MP4.
  3. Format video filenames as `{rank:02d} - {channel_name} - {clean_title}.mp4` preserving absolute digest ranks, with graceful per-video error handling.
- **Later modules:**
  - Desktop GUI status badge or manual download triggers from the history tab.
- **Not included:**
  - Downloading non-video articles or webpage briefs.
  - Re-encoding or transcribing local video files after download.

## Architecture and why
- **Design:** A dedicated lightweight module (`desktop/top10_downloader.py`) executed just-in-time immediately after Top 10 digest ranking and email dispatch. Integrates directly with `top10_service.py` and provides a standalone CLI entry point.
- **Why it fits:** Keeps external video acquisition and filesystem rotation decoupled from ranking and email logic while using the existing batch state and `yt-dlp` executable.
- **Tradeoff:** Sequential downloading of up to 10 videos takes a few minutes on weekly runs, but avoids complexity, network saturations, or race conditions.
- **Rejected alternative:** Asynchronous background daemon or celery/queue workers, which introduces unnecessary complexity and dependency overhead for a simple weekly personal task.

## How it works
1. **Input:** Ranked Top 10 items dictionary from `top10_service.py` (containing `rank`, `source_type`, `source_name`, `title`, `url`, `video_id`).
2. **Filter & Plan:** Retain only items where `source_type == "youtube"` or URL is a valid YouTube video. Generate clean filenames matching `{rank:02d} - {source_name} - {title}.mp4` (sanitizing illegal filesystem characters like `/`, `:`, `?`, `*`, `"`, `<`, `>`, `|`).
3. **Rotate Folders:**
   - Empty `/home/kedarnath-reddy-vallaboina/Downloads/TorBox/Top_10_Prev`.
   - Move any surviving files from `Top_10` into `Top_10_Prev`.
   - Ensure `Top_10` exists and is empty for the new weekly batch.
4. **Download:** Invoke `yt-dlp` with format selection `bv*[height<=1080]+ba/b[height<=1080]/b` remuxed to MP4 into `Top_10`.
5. **Output:** Downloaded MP4 video files ready in `/home/kedarnath-reddy-vallaboina/Downloads/TorBox/Top_10`.

## File map
| Path | What it contains | Why it exists / connects to |
| --- | --- | --- |
| `desktop/top10_downloader.py` | Folder rotation logic, filename sanitizer, and `yt-dlp` download runner. | Core module for downloading Top 10 videos. Connects to `top10_service.py`. |
| `desktop/config.py` | `download_top10_videos` and directory path configuration options. | Allows configuration and toggle of download behavior. |
| `desktop/top10_service.py` | Hook calling `download_top10_videos_batch` after digest rendering/sending. | Connects ranking pipeline to download module. |
| `desktop/scripts/download_top10.py` | Standalone CLI script to trigger download from recent batch or digest. | Allows testing and manual on-demand downloads. |
| `desktop/tests/unit/test_top10_downloader.py` | Unit tests for rotation, filename sanitizing, and filtering. | Verifies rotation safety and naming logic without hitting YouTube. |

## Implementation
1. **Config & Downloader Core (`desktop/config.py`, `desktop/top10_downloader.py`):**
   - Add default paths (`TOP10_DOWNLOAD_DIR`, `TOP10_PREV_DIR`) and config flag `download_top10_videos`.
   - Implement `rotate_top10_folders(dest_dir, prev_dir)` with safe file operations.
   - Implement `download_top10_videos(selection, dest_dir, prev_dir)` using `yt-dlp`.
2. **Integration (`desktop/top10_service.py`, `desktop/scripts/download_top10.py`):**
   - Call `download_top10_videos` inside `_rank_render_and_send` if enabled in config.
   - Create standalone script `desktop/scripts/download_top10.py`.
3. **Verification & Testing (`desktop/tests/unit/test_top10_downloader.py`):**
   - Test folder rotation (purging prev, moving remaining from current to prev).
   - Test filename sanitization and non-video skipping.
   - Test mock `yt-dlp` execution and graceful failure recovery.

## Proof checks
1. `pytest desktop/tests/unit/test_top10_downloader.py -v` — verifies folder rotation, filename formatting, and error tolerance.
2. `python desktop/scripts/download_top10.py --dry-run` — verifies candidate extraction, rotation simulation, and planned command generation.
3. Live test: Download a single top video to verify `yt-dlp` and `ffmpeg` integration.

## Run and limitations
- **Run:** Triggered automatically weekly when Top 10 digest runs, or manually via `python desktop/scripts/download_top10.py`.
- **Limitations:** Only YouTube videos are downloaded; RSS/web articles are skipped. Requires `yt-dlp` and `ffmpeg` installed on the system.
