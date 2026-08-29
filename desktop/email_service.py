"""
email_service.py — SMTP email delivery for the weekly digest.

Sends one email per channel. Each email includes:
  - Channel name and notebook link
  - Video list with dates
  - AI summary
  - Infographic (inline PNG attachment if available)

Raises on SMTP failure — errors are NOT swallowed.
"""

import logging
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

from config import Config
import paths
from summary_quality import strip_follow_up_offers

logger = logging.getLogger(__name__)

# Path to the templates directory (same location as this file)
_TEMPLATES_DIR = paths.get_templates_dir()


def _strip_citations(text: str) -> str:
    """Remove citation brackets like [1], [1-3], [1, 4, 5], [12-15] from the text."""
    pattern = r'\s*\[\d+(?:[\s\d,\-–—]*\d+)*\]'
    return re.sub(pattern, '', text)


def _split_markdown_summary_by_videos(summary_text: str, videos: list[dict], channel_name: str) -> dict[str, str]:
    """Split the compiled markdown summary into a dict mapping video URL to its markdown segment."""
    normalized_summary = summary_text.replace("\r\n", "\n")
    if normalized_summary.startswith("## "):
        normalized_summary = "\n" + normalized_summary
    sections = normalized_summary.split("\n## ")
    
    video_summaries = {}
    for section in sections:
        if not section.strip():
            continue
        lines = section.splitlines()
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        
        cleaned_header = header.lower()
        for sep in ["—", "–", "-", " -"]:
            suffix = f"{sep}{channel_name}".lower()
            if cleaned_header.endswith(suffix):
                cleaned_header = cleaned_header[:-len(suffix)].strip()
                break
                
        matched_video = None
        best_overlap = 0
        for v in videos:
            v_title = v["title"].lower()
            if cleaned_header in v_title or v_title in cleaned_header:
                matched_video = v
                best_overlap = 999
                break
            # Word overlap fallback
            words1 = {word for word in re.findall(r"\w+", cleaned_header) if len(word) > 2}
            words2 = {word for word in re.findall(r"\w+", v_title) if len(word) > 2}
            overlap = len(words1.intersection(words2))
            if overlap > best_overlap:
                best_overlap = overlap
                matched_video = v

        # Avoid assigning an unrelated section merely because titles share a
        # common word such as "new" or "video".
        if matched_video and best_overlap >= 2:
            if body.startswith("---"):
                body = body[3:].strip()
            if body.endswith("---"):
                body = body[:-3].strip()
            video_summaries[matched_video["url"]] = body
            
    return video_summaries


def _render_channel_html(
    channel_data: dict, run_date: str, infographic_cid: str | None
) -> str:
    """Render the Jinja2 email template for a single channel.

    Args:
        channel_data: Channel result dict from process_source_items().
        run_date: Human-readable date string (e.g. "2026-05-21").
        infographic_cid: Content-ID for the inline infographic, or None.

    Returns:
        Rendered HTML string.

    Raises:
        jinja2.TemplateNotFound: If the template file is missing.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("email_digest.html")
    
    summary_text = strip_follow_up_offers(channel_data.get("summary_text", ""))
    if summary_text:
        summary_text = _strip_citations(summary_text)
        
    videos = [dict(video) for video in channel_data.get("videos", [])]
    channel_name = channel_data.get("channel_name", "")
    
    # Split and map summary to each video
    video_summaries = {}
    if summary_text and videos:
        video_summaries = _split_markdown_summary_by_videos(summary_text, videos, channel_name)

    # Partial title matching used to hide the global summary as soon as just
    # one item matched, leaving the other item cards blank. Only switch to the
    # per-item layout when every item has a mapped section; otherwise render
    # the complete briefing once as the throughline.
    if len(video_summaries) != len(videos):
        video_summaries = {}
        
    md = MarkdownIt("commonmark", {"html": False})
    for v in videos:
        v_url = v.get("url", "")
        v_summary_md = video_summaries.get(v_url, "")
        v["summary_html"] = md.render(v_summary_md) if v_summary_md else ""
        
    infographic_src = None
    if infographic_cid:
        infographic_src = f"cid:{infographic_cid}"
    else:
        info_path = channel_data.get("infographic_path")
        if info_path and Path(info_path).exists():
            infographic_src = Path(info_path).name

    global_summary_html = md.render(summary_text) if summary_text else ""

    rendered_channel = dict(channel_data)
    rendered_channel["videos"] = videos

    return template.render(
        channel=rendered_channel,
        run_date=run_date,
        total_videos=len(videos),
        infographic_cid=infographic_cid,
        infographic_src=infographic_src,
        summary_html=global_summary_html,
        has_item_summaries=any(video.get("summary_html") for video in videos),
    )


def _render_channel_text(channel_data: dict, run_date: str) -> str:
    """Render a useful plain-text alternative for restrictive email clients."""
    source_type = channel_data.get("source_type", "youtube")
    item_name = {"youtube": "video", "rss": "article", "webpage": "page"}.get(source_type, "item")
    items = channel_data.get("videos", [])
    lines = [
        f"TUBELM BRIEFING — {channel_data.get('channel_name', 'Unknown source')}",
        f"{run_date} · {len(items)} new {item_name}{'' if len(items) == 1 else 's'}",
        "",
    ]
    if channel_data.get("notebook_url"):
        lines.extend([f"Open NotebookLM: {channel_data['notebook_url']}", ""])
    if channel_data.get("error"):
        lines.extend([f"Processing note: {channel_data['error']}", ""])
    for index, item in enumerate(items, start=1):
        lines.extend([
            f"{index}. {item.get('title', 'Untitled')}",
            f"   {item.get('published', '')} · {item.get('url', '')}",
        ])
    if channel_data.get("summary_text"):
        lines.extend(["", "BRIEFING NOTES", "", _strip_citations(channel_data["summary_text"])])
    lines.extend(["", "Generated locally by TubeLM with NotebookLM grounding."])
    return "\n".join(lines)


def _artifact_completion_context(artifact_kind: str, batch: dict) -> dict:
    """Normalize one completed artifact batch for HTML and text rendering."""
    if artifact_kind not in {"audio", "video"}:
        raise ValueError(f"Unsupported artifact kind: {artifact_kind}")

    labels = {
        "audio": ("Audio Overviews", "audio overview"),
        "video": ("Cinematic Videos", "cinematic video"),
    }
    artifact_label, artifact_noun = labels[artifact_kind]
    entries = []
    for raw_entry in sorted(
        batch.get("entries", []),
        key=lambda item: (
            int(item.get("channel_order", 0)),
            item.get("source_name", ""),
            item.get("notebook_id", ""),
        ),
    ):
        entry = dict(raw_entry)
        entry["notebook_url"] = entry.get("notebook_url") or (
            "https://notebooklm.google.com/notebook/"
            f"{entry.get('notebook_id', '')}"
        )
        entries.append(entry)
    return {
        "artifact_kind": artifact_kind,
        "artifact_label": artifact_label,
        "artifact_noun": artifact_noun,
        "entries": entries,
        "week_start": batch.get("week_start", ""),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def _render_artifact_completion_html(artifact_kind: str, batch: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("artifact_completion_email.html").render(
        **_artifact_completion_context(artifact_kind, batch)
    )


def _render_artifact_completion_text(artifact_kind: str, batch: dict) -> str:
    context = _artifact_completion_context(artifact_kind, batch)
    lines = [
        f"TUBELM — {context['artifact_label'].upper()} READY",
        f"Week of {context['week_start']} · {len(context['entries'])} completed",
        "",
    ]
    for entry in context["entries"]:
        lines.append(
            f"{int(entry.get('channel_order', 0)):02d}. "
            f"{entry.get('source_name', 'Source')}"
        )
        if entry.get("artifact_title"):
            lines.append(f"    {entry['artifact_title']}")
        if artifact_kind == "video" and entry.get("filename"):
            lines.append(f"    {entry['filename']}")
        lines.extend([f"    {entry['notebook_url']}", ""])
    return "\n".join(lines).rstrip()


def _send_message(msg: MIMEMultipart, cfg: Config) -> None:
    if cfg.use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port, context=context) as server:
            server.login(cfg.smtp_username, cfg.smtp_password)
            server.sendmail(cfg.sender_email, cfg.recipient_email, msg.as_string())
    else:
        with smtplib.SMTP(cfg.smtp_server, cfg.smtp_port) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(cfg.smtp_username, cfg.smtp_password)
            server.sendmail(cfg.sender_email, cfg.recipient_email, msg.as_string())


def send_artifact_completion_email(
    artifact_kind: str, batch: dict, cfg: Config
) -> None:
    """Send one weekly completion email for Audio or Cinematic Video."""
    context = _artifact_completion_context(artifact_kind, batch)
    count = len(context["entries"])
    subject = f"TubeLM · {context['artifact_label']} Ready · {count} notebook"
    if count != 1:
        subject += "s"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.sender_email
    msg["To"] = cfg.recipient_email
    msg.attach(
        MIMEText(_render_artifact_completion_text(artifact_kind, batch), "plain", "utf-8")
    )
    msg.attach(
        MIMEText(_render_artifact_completion_html(artifact_kind, batch), "html", "utf-8")
    )
    _send_message(msg, cfg)
    logger.info("%s completion email sent for week %s.", context["artifact_label"], context["week_start"])



def send_channel_email(channel_data: dict, cfg: Config) -> None:
    """Build and send a digest email for a single channel.

    Args:
        channel_data: Channel result dict with keys: channel_name, notebook_url,
                      summary_text, infographic_path, videos, error.
        cfg: Loaded Config instance with SMTP credentials.

    Raises:
        smtplib.SMTPException: On any SMTP delivery failure.
        OSError: On network-level connection failures.
    """
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    channel_name = channel_data.get("channel_name", "Unknown Channel")
    item_count = len(channel_data.get("videos", []))
    source_type = channel_data.get("source_type", "youtube")
    item_name = {"youtube": "video", "rss": "article", "webpage": "page"}.get(source_type, "item")
    subject = f"TubeLM Briefing · {channel_name} · {item_count} new {item_name}{'' if item_count == 1 else 's'}"

    # Check for infographic attachment
    infographic_path = channel_data.get("infographic_path", "")
    has_infographic = bool(infographic_path) and Path(infographic_path).exists()
    infographic_cid = "infographic_0" if has_infographic else None

    html_body = _render_channel_html(channel_data, run_date, infographic_cid)
    text_body = _render_channel_text(channel_data, run_date)

    # Build MIME message: "related" for inline images, "alternative" nested inside
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = cfg.sender_email
    msg["To"] = cfg.recipient_email

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(text_body, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt_part)

    # Attach infographic as inline image
    if has_infographic:
        try:
            suffix = Path(infographic_path).suffix.lower()
            subtype = "jpeg" if suffix in (".jpg", ".jpeg") else "png"
            with open(infographic_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype=subtype)
                img.add_header("Content-ID", f"<{infographic_cid}>")
                img.add_header(
                    "Content-Disposition",
                    "inline",
                    filename=Path(infographic_path).name,
                )
                msg.attach(img)
                logger.info(
                    "Attached infographic %s as cid:%s",
                    infographic_path,
                    infographic_cid,
                )
        except OSError:
            logger.exception(
                "Failed to read infographic %s — sending email without it.",
                infographic_path,
            )

    logger.info(
        "Sending digest email for '%s' to %s via %s:%d (%s)…",
        channel_name,
        cfg.recipient_email,
        cfg.smtp_server,
        cfg.smtp_port,
        "SSL" if cfg.use_ssl else "STARTTLS",
    )

    _send_message(msg, cfg)

    logger.info("Digest email sent for '%s'.", channel_name)


def verify_smtp_connection(cfg: Config) -> None:
    """Verify SMTP connection and credentials at startup.

    Raises:
        smtplib.SMTPException: On SMTP or authentication failure.
        OSError: On network-level connection failures.
    """
    logger.info(
        "Verifying SMTP connection to %s:%d (%s)…",
        cfg.smtp_server,
        cfg.smtp_port,
        "SSL" if cfg.use_ssl else "STARTTLS",
    )
    if cfg.use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg.smtp_server, cfg.smtp_port, context=context, timeout=15) as server:
            server.login(cfg.smtp_username, cfg.smtp_password)
    else:
        with smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(cfg.smtp_username, cfg.smtp_password)
    logger.info("SMTP credentials and connection verified successfully.")
