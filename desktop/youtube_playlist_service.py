"""YouTube Playlist Publisher Service for TubeLM.

Handles:
1. Google Cloud OAuth 2.0 credentials & persistent refresh token management.
2. Interactive one-time authorization CLI flow (`--youtube-auth`).
3. Publishing weekly curated Top 20 video briefings to YouTube playlists (`playlists.insert` and `playlistItems.insert`).
4. Idempotency tracking to prevent duplicate playlists on re-runs.
5. Historical playlist backfill for past weekly runs.
"""

from __future__ import annotations

import html
import http.server
import json
import logging
import os
import re
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import paths

logger = logging.getLogger(__name__)

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
PLAYLISTS_API = "https://www.googleapis.com/youtube/v3/playlists"
PLAYLIST_ITEMS_API = "https://www.googleapis.com/youtube/v3/playlistItems"
VALID_PRIVACY_STATUSES = {"public", "unlisted", "private"}


class YouTubeAuthError(RuntimeError):
    """Raised when YouTube OAuth authorization or token retrieval fails."""


class YouTubePlaylistError(RuntimeError):
    """Raised when playlist creation or video insertion fails."""


def _atomic_write_json(file_path: Path, data: Any, mode: int | None = None) -> None:
    """Safely write JSON data using an atomic replace with secure permissions."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_name(f".{file_path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    target_mode = mode if mode is not None else 0o644
    content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    try:
        fd = os.open(str(temp_path), flags, target_mode)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        if mode is not None:
            try:
                os.chmod(temp_path, mode)
            except OSError:
                pass
        os.replace(temp_path, file_path)
        if mode is not None:
            try:
                os.chmod(file_path, mode)
            except OSError:
                pass
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def get_oauth_client_info(cfg: Any = None) -> dict[str, str]:
    """Retrieve Google OAuth Client ID and Secret.

    Checks:
    1. paths.get_youtube_client_secret_file() (~/.tubelm/client_secret.json or project dir)
    2. cfg.youtube_client_id and cfg.youtube_client_secret
    3. os.environ['YOUTUBE_CLIENT_ID'] and os.environ['YOUTUBE_CLIENT_SECRET']
    """
    secret_file = paths.get_youtube_client_secret_file()
    if secret_file.exists():
        try:
            raw = json.loads(secret_file.read_text(encoding="utf-8"))
            data = raw.get("installed") or raw.get("web") or raw
            client_id = str(data.get("client_id") or "").strip()
            client_secret = str(data.get("client_secret") or "").strip()
            if client_id and client_secret:
                return {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "source": str(secret_file),
                }
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to parse client secret file %s: %s", secret_file, exc)

    client_id = ""
    client_secret = ""
    if cfg is not None:
        client_id = str(getattr(cfg, "youtube_client_id", "") or "").strip()
        client_secret = str(getattr(cfg, "youtube_client_secret", "") or "").strip()

    if not client_id:
        client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    if not client_secret:
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()

    if client_id and client_secret:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "source": "environment",
        }

    raise YouTubeAuthError(
        "YouTube OAuth credentials not found. Provide ~/.tubelm/client_secret.json "
        "or set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env."
    )


def load_token() -> dict[str, Any] | None:
    """Load stored OAuth token data."""
    token_file = paths.get_youtube_token_file()
    if not token_file.exists():
        return None
    try:
        data = json.loads(token_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        logger.warning("Corrupt YouTube token file; ignoring %s.", token_file)
        return None


def save_token(token_data: dict[str, Any]) -> None:
    """Save OAuth token data to paths.get_youtube_token_file() with 0o600 permissions."""
    _atomic_write_json(paths.get_youtube_token_file(), token_data, mode=0o600)


def refresh_access_token(
    token_data: dict[str, Any], client_info: dict[str, str]
) -> dict[str, Any]:
    """Exchange refresh token for a fresh access token."""
    refresh_tok = token_data.get("refresh_token")
    if not refresh_tok:
        raise YouTubeAuthError("Stored token has no refresh_token; re-authorization required.")

    payload = {
        "client_id": client_info["client_id"],
        "client_secret": client_info["client_secret"],
        "refresh_token": refresh_tok,
        "grant_type": "refresh_token",
    }
    response = requests.post(TOKEN_ENDPOINT, data=payload, timeout=20)
    if response.status_code != 200:
        if response.status_code == 400 and "invalid_grant" in response.text:
            try:
                paths.get_youtube_token_file().unlink(missing_ok=True)
            except OSError:
                pass
            raise YouTubeAuthError(
                "YouTube refresh token has been revoked or expired (invalid_grant). "
                "Please run: .venv/bin/python desktop/main.py --youtube-auth"
            )
        raise YouTubeAuthError(
            f"Failed to refresh YouTube access token ({response.status_code}): {response.text}"
        )

    res_data = response.json()
    new_access_token = str(res_data.get("access_token") or "")
    if not new_access_token:
        raise YouTubeAuthError(f"OAuth token refresh response missing access_token: {res_data}")

    new_token = dict(token_data)
    new_token["access_token"] = new_access_token
    try:
        expires_in = int(res_data.get("expires_in", 3600))
    except (ValueError, TypeError):
        expires_in = 3600
    new_token["expires_at"] = time.time() + expires_in
    if res_data.get("refresh_token"):
        new_token["refresh_token"] = res_data["refresh_token"]

    save_token(new_token)
    logger.info("Successfully refreshed YouTube access token (expires in %ds).", expires_in)
    return new_token


def get_valid_access_token(cfg: Any = None) -> str:
    """Return a valid access token, refreshing if needed."""
    token_data = load_token()
    if not token_data:
        raise YouTubeAuthError(
            "No YouTube token found. Please run: python desktop/main.py --youtube-auth"
        )

    try:
        expires_at = float(token_data.get("expires_at", 0))
    except (ValueError, TypeError):
        expires_at = 0.0

    # Refresh if expired or expiring within 90 seconds
    if time.time() >= (expires_at - 90):
        client_info = get_oauth_client_info(cfg)
        token_data = refresh_access_token(token_data, client_info)

    access_token = str(token_data.get("access_token") or "")
    if not access_token:
        raise YouTubeAuthError("Invalid access token in YouTube token store.")
    return access_token


def get_authenticated_channel_info(access_token: str) -> dict[str, str]:
    """Fetch the channel title, customUrl, and ID for the authorized token."""
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                return {
                    "id": str(items[0].get("id") or ""),
                    "title": str(snippet.get("title") or ""),
                    "custom_url": str(snippet.get("customUrl") or ""),
                }
    except Exception as exc:
        logger.warning("Could not fetch authenticated channel info: %s", exc)
    return {}


def run_interactive_oauth_login(cfg: Any = None) -> bool:
    """Guide the user through one-time OAuth consent and persist tokens."""
    client_info = get_oauth_client_info(cfg)
    client_id = client_info["client_id"]
    client_secret = client_info["client_secret"]

    # Pick a local port by attempting direct bind
    server = None
    port = 8080
    for test_port in (8080, 8085, 8088, 8090, 8999):
        try:
            class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    parsed = urllib.parse.urlparse(self.path)
                    if parsed.path == "/callback":
                        query = urllib.parse.parse_qs(parsed.query)
                        query_state = query.get("state", [""])[0]
                        if query_state != oauth_state:
                            error_msg = "OAuth state mismatch (potential CSRF request)"
                            auth_code_holder["error"] = error_msg
                            self.send_response(400)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(f"<h2>&#10060; Authorization failed: {html.escape(error_msg)}</h2>".encode("utf-8"))
                            auth_event.set()
                            return

                        if "code" in query:
                            auth_code_holder["code"] = query["code"][0]
                            self.send_response(200)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(
                                b"<html><body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
                                b"<h2>&#9989; TubeLM Authorization Successful!</h2>"
                                b"<p>You can close this tab and return to the terminal.</p>"
                                b"</body></html>"
                            )
                        else:
                            error_msg = query.get("error", ["Unknown error"])[0]
                            auth_code_holder["error"] = error_msg
                            self.send_response(400)
                            self.send_header("Content-Type", "text/html; charset=utf-8")
                            self.end_headers()
                            self.wfile.write(f"<h2>&#10060; Authorization failed: {html.escape(error_msg)}</h2>".encode("utf-8"))
                        auth_event.set()
                    else:
                        self.send_response(404)
                        self.end_headers()

                def log_message(self, format, *args):
                    pass

            server = http.server.HTTPServer(("127.0.0.1", test_port), OAuthCallbackHandler)
            port = test_port
            break
        except OSError:
            continue

    if server is None:
        raise YouTubeAuthError("Unable to bind local OAuth callback server on candidate ports.")

    redirect_uri = f"http://localhost:{port}/callback"

    oauth_state = secrets.token_urlsafe(32)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": YOUTUBE_SCOPE,
        "access_type": "offline",
        "prompt": "select_account consent",
        "state": oauth_state,
    }
    auth_url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    auth_code_holder: dict[str, str] = {}
    auth_event = threading.Event()

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print("\n" + "=" * 65)
    print("TubeLM YouTube OAuth Authorization")
    print("=" * 65)
    print(f"\n1. Opening your browser to authorize TubeLM with YouTube:\n\n{auth_url}\n")
    print("2. If the browser does not open automatically, copy and paste the link above into your browser.")
    print("3. Log in and click 'Allow' to grant playlist management permissions.\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    try:
        # Wait up to 180 seconds for browser callback
        print(f"Waiting for local callback on {redirect_uri} (timeout in 180s)...")
        auth_event.wait(timeout=180)
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass

    if "error" in auth_code_holder:
        raise YouTubeAuthError(f"OAuth authorization failed: {auth_code_holder['error']}")

    code = auth_code_holder.get("code")
    if not code:
        print("\nCould not receive callback automatically. If Google gave you an authorization code, paste it here:")
        try:
            code = input("Authorization Code (or press Enter to cancel): ").strip()
        except EOFError:
            code = ""

    if not code:
        raise YouTubeAuthError("OAuth authorization was not completed.")

    # Exchange code for tokens
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    response = requests.post(TOKEN_ENDPOINT, data=payload, timeout=20)
    if response.status_code != 200:
        raise YouTubeAuthError(
            f"Failed to exchange code for tokens ({response.status_code}): {response.text}"
        )

    res_data = response.json()
    new_access_token = str(res_data.get("access_token") or "")
    if not new_access_token:
        raise YouTubeAuthError(f"OAuth token response missing access_token: {res_data}")

    try:
        expires_in = int(res_data.get("expires_in", 3600))
    except (ValueError, TypeError):
        expires_in = 3600

    existing_token = load_token() or {}
    refresh_token = res_data.get("refresh_token") or existing_token.get("refresh_token", "")
    token_record = {
        "access_token": new_access_token,
        "refresh_token": refresh_token,
        "token_type": res_data.get("token_type", "Bearer"),
        "expires_at": time.time() + expires_in,
        "scope": res_data.get("scope", YOUTUBE_SCOPE),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "client_id": client_id,
    }
    ch_info = get_authenticated_channel_info(token_record["access_token"])
    if ch_info:
        token_record["channel_id"] = ch_info.get("id", "")
        token_record["channel_title"] = ch_info.get("title", "")
        token_record["channel_custom_url"] = ch_info.get("custom_url", "")
        save_token(token_record)
        print(f"\n✅ YouTube authorization successful!")
        print(f"   Connected Channel: {ch_info.get('title')} ({ch_info.get('custom_url') or ch_info.get('id')})")
        print(f"   Tokens saved to {paths.get_youtube_token_file()}.\n")
    else:
        save_token(token_record)
        print(f"\n✅ YouTube authorization successful! Tokens saved to {paths.get_youtube_token_file()}.\n")
    return True


def load_playlist_history() -> dict[str, Any]:
    """Read the durable record of created playlists by run_date."""
    history_file = paths.get_youtube_playlists_file()
    if not history_file.exists():
        return {}
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        logger.warning("Unreadable playlist history file: %s", history_file)
        return {}


def save_playlist_history(history: dict[str, Any]) -> None:
    """Save playlist history atomically."""
    _atomic_write_json(paths.get_youtube_playlists_file(), history)


def delete_playlist(playlist_id: str, access_token: str) -> bool:
    """Best-effort deletion of an empty or failed playlist."""
    if not playlist_id:
        return False
    try:
        resp = requests.delete(
            f"{PLAYLISTS_API}?id={playlist_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if resp.status_code in (200, 204):
            logger.info("Successfully cleaned up empty playlist %s.", playlist_id)
            return True
        logger.warning("Failed to delete empty playlist %s (%d): %s", playlist_id, resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Error deleting empty playlist %s: %s", playlist_id, exc)
    return False


def _extract_video_id(item: dict[str, Any]) -> str:
    """Extract 11-char YouTube video ID from item dict."""
    vid = str(item.get("video_id") or "").strip()
    if len(vid) == 11 and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return vid
    url = str(item.get("url") or "").strip()
    match = re.search(r"(?:v=|/vi/|/shorts/|/embed/|/live/|/v/|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if match:
        return match.group(1)
    return ""


def create_weekly_playlist(
    run_date: str,
    items: list[dict[str, Any]],
    privacy_status: str = "public",
    cfg: Any = None,
) -> dict[str, Any]:
    """Publish the Top 20 items to a weekly YouTube playlist.

    Idempotent: if run_date already has a playlist in history, returns existing info.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", run_date):
        raise YouTubePlaylistError(f"Invalid run_date format '{run_date}'. Expected YYYY-MM-DD.")

    privacy_status = str(privacy_status or "public").strip().lower()
    if privacy_status not in VALID_PRIVACY_STATUSES:
        raise YouTubePlaylistError(
            f"Invalid privacyStatus '{privacy_status}'; must be one of {sorted(VALID_PRIVACY_STATUSES)}"
        )

    if not items:
        raise YouTubePlaylistError(f"Cannot create playlist for {run_date} with zero items.")

    history = load_playlist_history()
    if run_date in history:
        existing = history[run_date]
        if existing.get("playlist_url") and existing.get("added_videos_count", 0) > 0:
            logger.info(
                "Reusing existing YouTube playlist for %s: %s",
                run_date,
                existing.get("playlist_url"),
            )
            return existing
        logger.warning(
            "Existing history entry for %s has 0 videos added. Re-creating.",
            run_date,
        )

    # Deduplicate video IDs and track non-video candidates
    seen_video_ids: set[str] = set()
    unique_items: list[dict[str, Any]] = []
    skipped_non_videos: list[str] = []

    for it in items:
        vid = _extract_video_id(it)
        if not vid:
            skipped_non_videos.append(str(it.get("title") or "Untitled"))
            continue
        if vid not in seen_video_ids:
            seen_video_ids.add(vid)
            unique_items.append(it)

    if not unique_items:
        raise YouTubePlaylistError(f"No playable YouTube videos found in {len(items)} items for {run_date}.")

    access_token = get_valid_access_token(cfg)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    item_count = len(unique_items)
    title = f"TubeLM Top {item_count} - {run_date}"
    description_lines = [
        f"TubeLM Editor's Top {item_count} curated briefing for the week of {run_date}.",
        "Selected for high signal, depth, and practical impact.",
        "",
        "Curated items:",
    ]
    for idx, it in enumerate(unique_items, start=1):
        item_title = str(it.get("title") or "Untitled").strip()
        source = str(it.get("source_name") or "").strip()
        description_lines.append(f"{idx}. {item_title} ({source})" if source else f"{idx}. {item_title}")

    description = "\n".join(description_lines)[:4900]

    playlist_payload = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    ch_info = get_authenticated_channel_info(access_token)
    ch_name = f"'{ch_info['title']}'" if ch_info.get("title") else "your channel"
    logger.info("Creating YouTube playlist on %s: '%s' (privacy: %s)...", ch_name, title, privacy_status)
    resp = requests.post(
        f"{PLAYLISTS_API}?part=snippet,status",
        headers=headers,
        json=playlist_payload,
        timeout=25,
    )
    if resp.status_code not in (200, 201):
        raise YouTubePlaylistError(
            f"Failed to create playlist ({resp.status_code}): {resp.text}"
        )

    res_json = resp.json()
    playlist_id = res_json.get("id")
    if not playlist_id:
        raise YouTubePlaylistError("YouTube did not return a playlist ID.")

    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
    logger.info("Created YouTube playlist %s (%s). Adding videos...", playlist_id, playlist_url)

    added_videos: list[str] = []
    failed_videos: list[str] = []

    for it in unique_items:
        video_id = _extract_video_id(it)
        if not video_id:
            continue

        item_payload = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        }
        try:
            item_resp = requests.post(
                f"{PLAYLIST_ITEMS_API}?part=snippet",
                headers=headers,
                json=item_payload,
                timeout=15,
            )
            if item_resp.status_code == 401:
                # Refresh token and retry once
                access_token = get_valid_access_token(cfg)
                headers["Authorization"] = f"Bearer {access_token}"
                item_resp = requests.post(
                    f"{PLAYLIST_ITEMS_API}?part=snippet",
                    headers=headers,
                    json=item_payload,
                    timeout=15,
                )

            if item_resp.status_code in (200, 201):
                added_videos.append(video_id)
            else:
                logger.warning(
                    "Could not add video %s to playlist (%s): %s",
                    video_id,
                    item_resp.status_code,
                    item_resp.text,
                )
                failed_videos.append(video_id)
        except Exception as exc:
            logger.warning("Error adding video %s to playlist: %s", video_id, exc)
            failed_videos.append(video_id)

    if items and len(added_videos) == 0:
        logger.error(
            "Failed to add any videos to playlist %s for %s (%d candidate items failed). Deleting empty playlist.",
            playlist_id,
            run_date,
            len(items),
        )
        delete_playlist(playlist_id, access_token)
        raise YouTubePlaylistError(
            f"Failed to add any videos to playlist for {run_date} (0 of {len(items)} added). Empty playlist was cleaned up."
        )

    record = {
        "playlist_id": playlist_id,
        "playlist_url": playlist_url,
        "title": title,
        "run_date": run_date,
        "privacy_status": privacy_status,
        "added_videos_count": len(added_videos),
        "failed_videos_count": len(failed_videos),
        "skipped_non_videos_count": len(skipped_non_videos),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    history[run_date] = record
    save_playlist_history(history)
    logger.info(
        "Successfully finalized YouTube playlist for %s with %d videos: %s",
        run_date,
        len(added_videos),
        playlist_url,
    )
    return record


def backfill_playlists(run_dates: list[str], cfg: Any = None) -> list[dict[str, Any]]:
    """Backfill YouTube playlists for the specified run dates from local summaries."""
    results: list[dict[str, Any]] = []
    summaries_dir = paths.get_summaries_dir()

    privacy = getattr(cfg, "youtube_playlist_privacy", "public") if cfg else "public"

    for r_date in run_dates:
        # Match e.g. 2026-09-25_TubeLM_Top_*_digest.json
        matching_json = list(summaries_dir.glob(f"{r_date}_TubeLM_Top_*_digest.json"))
        if not matching_json:
            # Fall back to html if json missing
            matching_html = list(summaries_dir.glob(f"{r_date}_TubeLM_Top_*_digest.html"))
            if not matching_html:
                logger.warning("No digest found for run date %s in %s.", r_date, summaries_dir)
                continue
            # Parse candidates from HTML using parse_top20_digest
            from web_reader import parse_top20_digest
            parsed = parse_top20_digest(matching_html[0])
            items = parsed.get("items", [])
        else:
            try:
                top_data = json.loads(matching_json[0].read_text(encoding="utf-8"))
                items = top_data.get("items", [])
            except Exception as exc:
                logger.error("Failed to read %s: %s", matching_json[0], exc)
                continue

        if not items:
            logger.warning("No items in digest for run date %s.", r_date)
            continue

        try:
            record = create_weekly_playlist(r_date, items, privacy_status=privacy, cfg=cfg)
            results.append(record)

            # Update sidecar json with playlist_url if present
            if matching_json:
                try:
                    s_data = json.loads(matching_json[0].read_text(encoding="utf-8"))
                    s_data["playlist_url"] = record["playlist_url"]
                    s_data["playlist_id"] = record["playlist_id"]
                    _atomic_write_json(matching_json[0], s_data)
                except Exception:
                    pass

        except Exception as exc:
            logger.error("Failed to backfill playlist for %s: %s", r_date, exc)

    return results
