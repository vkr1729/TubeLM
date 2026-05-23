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

logger = logging.getLogger(__name__)

# Path to the templates directory (same location as this file)
_TEMPLATES_DIR = Path(__file__).parent / "templates"


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
                break
            # Word overlap fallback
            words1 = set(re.findall(r"\w+", cleaned_header))
            words2 = set(re.findall(r"\w+", v_title))
            overlap = len(words1.intersection(words2))
            if overlap > best_overlap:
                best_overlap = overlap
                matched_video = v
                
        if matched_video:
            if body.startswith("---"):
                body = body[3:].strip()
            if body.endswith("---"):
                body = body[:-3].strip()
            video_summaries[matched_video["url"]] = body
            
    return video_summaries


def _render_channel_html(channel_data: dict, run_date: str, infographic_cid: str | None) -> str:
    """Render the Jinja2 email template for a single channel.

    Args:
        channel_data: Channel result dict from process_channel_videos().
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
    
    summary_text = channel_data.get("summary_text", "")
    if summary_text:
        summary_text = _strip_citations(summary_text)
        
    videos = channel_data.get("videos", [])
    channel_name = channel_data.get("channel_name", "")
    
    # Split and map summary to each video
    video_summaries = {}
    if summary_text and videos:
        video_summaries = _split_markdown_summary_by_videos(summary_text, videos, channel_name)
        
    md = MarkdownIt()
    for v in videos:
        v_url = v.get("url", "")
        v_summary_md = video_summaries.get(v_url, "")
        v["summary_html"] = md.render(v_summary_md) if v_summary_md else ""
        
    return template.render(
        channel=channel_data,
        run_date=run_date,
        total_videos=len(videos),
        infographic_cid=infographic_cid,
    )


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
    video_count = len(channel_data.get("videos", []))
    subject = (
        f"📹 {channel_name} — {run_date} "
        f"({video_count} video{'s' if video_count != 1 else ''})"
    )

    # Check for infographic attachment
    infographic_path = channel_data.get("infographic_path", "")
    has_infographic = bool(infographic_path) and Path(infographic_path).exists()
    infographic_cid = "infographic_0" if has_infographic else None

    html_body = _render_channel_html(channel_data, run_date, infographic_cid)

    # Build MIME message: "related" for inline images, "alternative" nested inside
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = cfg.sender_email
    msg["To"] = cfg.recipient_email

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt_part)

    # Attach infographic as inline image
    if has_infographic:
        try:
            with open(infographic_path, "rb") as f:
                img = MIMEImage(f.read(), _subtype="png")
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

