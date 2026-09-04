from pathlib import Path
from types import SimpleNamespace
import pytest

import top10_downloader


def test_sanitize_filename_part():
    dirty = 'Why AI / ML is 100% "Awesome": A <Deep> Dive *?|'
    clean = top10_downloader.sanitize_filename_part(dirty)
    assert "/" not in clean
    assert "\\" not in clean
    assert ":" not in clean
    assert "*" not in clean
    assert "?" not in clean
    assert '"' not in clean
    assert "<" not in clean
    assert ">" not in clean
    assert "|" not in clean
    assert clean == "Why AI ML is 100% Awesome A Deep Dive"


def test_build_video_filename():
    filename = top10_downloader.build_video_filename(
        rank=1,
        source_name="Dr Brad Stanfield",
        title="This Vaccine Just Changed Cancer Forever",
    )
    assert filename == "01 - Dr Brad Stanfield - This Vaccine Just Changed Cancer Forever.mp4"


def test_is_youtube_video_item():
    yt_item = {
        "source_type": "youtube",
        "url": "https://www.youtube.com/watch?v=12345678901",
        "video_id": "12345678901",
    }
    rss_item = {
        "source_type": "rss",
        "url": "https://techcrunch.com/article-1",
        "video_id": "",
    }
    web_item = {
        "source_type": "webpage",
        "url": "https://openai.com/news/post",
        "video_id": "",
    }
    yt_url_item = {
        "source_type": "unknown",
        "url": "https://youtu.be/12345678901",
    }

    assert top10_downloader.is_youtube_video_item(yt_item) is True
    assert top10_downloader.is_youtube_video_item(yt_url_item) is True
    assert top10_downloader.is_youtube_video_item(rss_item) is False
    assert top10_downloader.is_youtube_video_item(web_item) is False


def test_rotate_top10_folders(tmp_path):
    dest_dir = tmp_path / "Top_10"
    prev_dir = tmp_path / "Top_10_Prev"
    dest_dir.mkdir()
    prev_dir.mkdir()

    # Create old files in prev_dir (from 2 weeks ago)
    old_video = prev_dir / "stale_video.mp4"
    old_video.write_text("old")

    # Create unwatched videos in dest_dir (from last week)
    unwatched_video1 = dest_dir / "01 - Channel - Video 1.mp4"
    unwatched_video1.write_text("video 1")
    unwatched_video2 = dest_dir / "03 - Channel - Video 3.mp4"
    unwatched_video2.write_text("video 3")

    top10_downloader.rotate_top10_folders(dest_dir, prev_dir)

    # Stale video should be purged
    assert not old_video.exists()

    # Unwatched videos should now be in prev_dir
    assert (prev_dir / "01 - Channel - Video 1.mp4").exists()
    assert (prev_dir / "03 - Channel - Video 3.mp4").exists()

    # dest_dir should be empty
    assert list(dest_dir.iterdir()) == []


def test_download_top10_videos_with_mock(monkeypatch, tmp_path):
    dest_dir = tmp_path / "Top_10"
    prev_dir = tmp_path / "Top_10_Prev"
    commands_executed = []

    def fake_run(command, **kwargs):
        commands_executed.append(command)
        return SimpleNamespace(returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(top10_downloader.subprocess, "run", fake_run)
    monkeypatch.setattr(top10_downloader, "resolve_yt_dlp_bin", lambda: "/usr/bin/yt-dlp")

    selection = {
        "items": [
            {
                "rank": 1,
                "source_type": "youtube",
                "source_name": "Channel A",
                "title": "Video One",
                "url": "https://www.youtube.com/watch?v=aaaaa111111",
            },
            {
                "rank": 2,
                "source_type": "rss",
                "source_name": "Tech Blog",
                "title": "Article Two",
                "url": "https://blog.com/2",
            },
            {
                "rank": 3,
                "source_type": "youtube",
                "source_name": "Channel B",
                "title": "Video Three",
                "url": "https://www.youtube.com/watch?v=bbbbb222222",
            },
        ]
    }

    summary = top10_downloader.download_top10_videos(
        selection=selection,
        dest_dir=dest_dir,
        prev_dir=prev_dir,
    )

    assert summary["total_videos"] == 2
    assert summary["skipped_non_video"] == 1
    assert summary["downloaded"] == 2
    assert summary["failed"] == 0

    assert len(commands_executed) == 2
    cmd1 = commands_executed[0]
    assert cmd1[0] == "/usr/bin/yt-dlp"
    assert "01 - Channel A - Video One.%(ext)s" in cmd1[cmd1.index("--output") + 1]
    assert cmd1[-1] == "https://www.youtube.com/watch?v=aaaaa111111"

    cmd2 = commands_executed[1]
    assert "03 - Channel B - Video Three.%(ext)s" in cmd2[cmd2.index("--output") + 1]
    assert cmd2[-1] == "https://www.youtube.com/watch?v=bbbbb222222"


def test_extract_items_from_top10_html(tmp_path):
    sample_html = """<!doctype html>
    <html>
    <body>
      <table>
        <tr>
          <td class="rank-cell">01</td>
          <td>
            <div style="text-transform:uppercase;">Watch / Dr Brad / 2026-08-25</div>
            <h2 class="item-title"><a href="https://www.youtube.com/watch?v=test1234567">Test Title</a></h2>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    html_file = tmp_path / "top10.html"
    html_file.write_text(sample_html, encoding="utf-8")

    items = top10_downloader.extract_items_from_top10_html(html_file)
    assert len(items) == 1
    assert items[0]["rank"] == 1
    assert items[0]["source_name"] == "Dr Brad"
    assert items[0]["title"] == "Test Title"
    assert items[0]["url"] == "https://www.youtube.com/watch?v=test1234567"
    assert items[0]["source_type"] == "youtube"


def test_config_top10_paths(monkeypatch, tmp_path):
    from config import load_config

    custom_dest = tmp_path / "Custom_Top10"
    custom_prev = tmp_path / "Custom_Top10_Prev"

    monkeypatch.setenv("TOP10_DOWNLOAD_DIR", str(custom_dest))
    monkeypatch.setenv("TOP10_PREV_DIR", str(custom_prev))
    monkeypatch.setenv("DOWNLOAD_TOP_10_VIDEOS", "true")

    cfg = load_config()
    assert cfg.top10_download_dir == custom_dest
    assert cfg.top10_prev_dir == custom_prev
    assert cfg.download_top10_videos is True


def test_download_single_video_skips_existing_file(monkeypatch, tmp_path):
    dest_file = tmp_path / "01 - Channel - Video One.mp4"
    dest_file.write_bytes(b"x" * 2048)

    executed = []
    monkeypatch.setattr(top10_downloader.subprocess, "run", lambda *args, **kwargs: executed.append(args))

    success = top10_downloader.download_single_video(
        url="https://youtube.com/watch?v=123",
        output_path=dest_file,
    )
    assert success is True
    assert len(executed) == 0  # Skipped because file already exists!


def test_download_single_video_renames_existing_file_with_different_rank(monkeypatch, tmp_path):
    old_file = tmp_path / "01 - Channel - Video One.mp4"
    old_file.write_bytes(b"x" * 2048)

    new_file = tmp_path / "02 - Channel - Video One.mp4"

    executed = []
    monkeypatch.setattr(top10_downloader.subprocess, "run", lambda *args, **kwargs: executed.append(args))

    success = top10_downloader.download_single_video(
        url="https://youtube.com/watch?v=123",
        output_path=new_file,
    )
    assert success is True
    assert len(executed) == 0
    assert not old_file.exists()
    assert new_file.exists()
    assert new_file.stat().st_size == 2048


def test_download_top10_videos_skips_rotation_when_rotate_false(monkeypatch, tmp_path):
    dest_dir = tmp_path / "Top_10"
    prev_dir = tmp_path / "Top_10_Prev"
    dest_dir.mkdir()
    prev_dir.mkdir()

    existing_video = dest_dir / "01 - Channel A - Video One.mp4"
    existing_video.write_bytes(b"x" * 2048)

    rotation_called = []
    monkeypatch.setattr(
        top10_downloader, "rotate_top10_folders", lambda d, p: rotation_called.append((d, p))
    )
    monkeypatch.setattr(top10_downloader, "resolve_yt_dlp_bin", lambda: "/usr/bin/yt-dlp")

    selection = {
        "items": [
            {
                "rank": 1,
                "source_type": "youtube",
                "source_name": "Channel A",
                "title": "Video One",
                "url": "https://www.youtube.com/watch?v=aaaaa111111",
            }
        ]
    }

    summary = top10_downloader.download_top10_videos(
        selection=selection,
        dest_dir=dest_dir,
        prev_dir=prev_dir,
        rotate=False,
    )

    assert len(rotation_called) == 0  # Folder rotation skipped!
    assert existing_video.exists()
    assert summary["downloaded"] == 1

