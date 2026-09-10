"""Regression tests for T1/T2/T5 handover fixes."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import web_reader

_REAL_DEPLOY = web_reader.deploy_to_gh_pages


def test_deploy_refuses_files_over_5mb(tmp_path, monkeypatch):
    monkeypatch.setattr(web_reader, "deploy_to_gh_pages", _REAL_DEPLOY)
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("<html></html>")
    big = site_dir / "audio" / "big.mp3"
    big.parent.mkdir()
    big.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    assert web_reader.deploy_to_gh_pages(site_dir) is False
    assert (site_dir / ".git").exists() is False


def test_feed_xml_well_formed_with_ampersand(tmp_path):
    site_data = {
        "weeks": {
            "current": {
                "run_date": "2026-09-04",
                "channels": [
                    {
                        "id": "Felix_Friends",
                        "name": "Felix & Friends (Goat Academy)",
                        "category": "tech",
                        "notebook_url": "https://example.com/nb?a=1&b=2",
                        "summary_preview": "Brief",
                        "full_summary_html": "<p>hi</p>",
                    }
                ],
                "top20": {"items": []},
            }
        }
    }
    out = tmp_path / "feed.xml"
    web_reader.generate_rss_feed(site_data, out)
    ET.fromstring(out.read_text(encoding="utf-8"))


def test_exact_audio_manifest_join_no_glob(tmp_path, monkeypatch):
    summaries = tmp_path / "summaries"
    audio = tmp_path / "audio"
    summaries.mkdir()
    audio.mkdir()
    run_date = "2026-09-04"
    safe = "Think_School"
    html = summaries / f"{run_date}_{safe}_digest.html"
    html.write_text(
        "<html><body><h1>Think School</h1>"
        '<div class="item-card"><h2><a href="https://www.youtube.com/watch?v=AAAAAAAAAAA">V1</a></h2>'
        '<div>Published 2026-09-01</div><div class="summary-html"><p>s1</p></div></div>'
        '<div class="item-card"><h2><a href="https://www.youtube.com/watch?v=BBBBBBBBBBB">V2</a></h2>'
        '<div>Published 2026-09-02</div><div class="summary-html"><p>s2</p></div></div>'
        "</body></html>"
    )
    old_audio = audio / f"2026-08-24_{safe}.mp3"
    old_audio.write_bytes(b"old" * 100)
    new_audio = audio / f"2026-08-31_{safe}.mp3"
    new_audio.write_bytes(b"new" * 100)
    # Manifest points at the 08-31 file for a digest dated 09-04? No: manifest miss -> exact fallback miss -> no audio.
    import paths
    monkeypatch.setattr(paths, "get_audio_dir", lambda: audio)
    got = web_reader.parse_channel_digest(html, {}, audio, run_date)
    assert got["has_audio"] is False
    # Now exact legacy file for run_date exists -> picked.
    exact = audio / f"{run_date}_{safe}.mp3"
    exact.write_bytes(b"exact" * 100)
    got2 = web_reader.parse_channel_digest(html, {}, audio, run_date)
    assert got2["has_audio"] is True
    assert got2["audio_filename"] == exact.name
    # Manifest entry wins over legacy exact file.
    manifest = {"2026-09-04|Think_School": {"notebook_id": "nb1", "file": new_audio.name}}
    (audio / "manifest.json").write_text(json.dumps(manifest))
    got3 = web_reader.parse_channel_digest(html, {}, audio, run_date)
    assert got3["audio_filename"] == new_audio.name
    # Oldest-file glob must never attach: delete manifest+exact, only stale files remain -> no audio.
    (audio / "manifest.json").unlink()
    exact.unlink()
    got4 = web_reader.parse_channel_digest(html, {}, audio, run_date)
    assert got4["has_audio"] is False

