"""
config.py — Centralised configuration loader.

All settings come from the .env file (or environment variables).
Required variables raise ConfigurationError at import time so the script
crashes loudly rather than silently producing wrong results.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

import paths

paths.ensure_data_dir()
load_dotenv(paths.get_env_file())



class ConfigurationError(Exception):
    """Raised when a required configuration value is missing."""


def _get_required(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ConfigurationError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file against .env.example."
        )
    return value


def _get_optional(key: str, default: str = "") -> str:
    val = os.getenv(key, "").strip()
    return val if val else default


def _get_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{key} must be true or false, got: {value!r}")


def _load_prompt_file(filename: str) -> str:
    """Load a prompt override, falling back to the bundled default.

    Returns the file content stripped of leading/trailing whitespace,
    or an empty string if the file is missing or empty.
    """
    for prompt_dir in (paths.get_user_prompts_dir(), paths.get_prompts_dir()):
        path = prompt_dir / filename
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content
    return ""


_DEFAULT_CATEGORY = "tech"
_VALID_CATEGORIES = ("health", "tech", "deep_explainer", "news_feed")


def load_category_prompt(category: str, prompt_type: str) -> str:
    """Load a category-specific prompt for either 'summary' or 'podcast'.

    Looks for  shared/prompts/{prompt_type}/{category}.md.
    Falls back to  shared/prompts/{prompt_type}/tech.md  if the
    category file is missing or empty.
    Returns empty string only if even the fallback is absent.
    """
    if category not in _VALID_CATEGORIES:
        category = _DEFAULT_CATEGORY

    content = _load_prompt_file(f"{prompt_type}/{category}.md")
    if content:
        return content

    # Fallback to default category
    if category != _DEFAULT_CATEGORY:
        content = _load_prompt_file(f"{prompt_type}/{_DEFAULT_CATEGORY}.md")
        if content:
            return content

    return ""


@dataclass(frozen=True)
class Config:
    # SMTP — all required for email delivery
    smtp_server: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    sender_email: str
    recipient_email: str

    # YouTube Data API key (REQUIRED for duration-based Shorts filtering)
    youtube_api_key: str



    # Local file paths
    sources_file: Path
    state_file: Path

    # Retention configuration
    notebooks_retention_limit: int

    # Infographics are retained as an opt-in feature because they are rarely used.
    generate_infographics: bool = False

    # Cross-source Top digest email selected by agy/Gemini after summaries complete.
    generate_top10_digest: bool = False
    top_digest_count: int = 20

    # Automatically download ranked Top YouTube videos locally using yt-dlp.
    download_top10_videos: bool = False
    top10_download_dir: Path = field(default_factory=paths.get_top10_video_download_dir)
    top10_prev_dir: Path = field(default_factory=paths.get_top10_previous_video_download_dir)

    # Web reader and delivery configuration
    send_channel_emails: bool = False
    deploy_to_gh_pages: bool = True
    gh_pages_url: str = "https://vkr1729.github.io/TubeLM/"
    compress_audio: bool = False

    # Default browser for NotebookLM extraction (chrome, edge, safari, firefox, opera, etc.)
    notebooklm_browser: str = "chrome"

    # Derived: use SSL (port 465) or STARTTLS (port 587)
    use_ssl: bool = field(init=False)

    def __post_init__(self) -> None:
        # frozen=True means we must use object.__setattr__ for derived fields
        object.__setattr__(self, "use_ssl", self.smtp_port == 465)


def load_config() -> Config:
    """Load and validate all configuration from environment variables.

    Raises:
        ConfigurationError: If ports are invalid integers.
    """
    smtp_port_raw = _get_optional("SMTP_PORT")
    smtp_port = 0
    if smtp_port_raw:
        try:
            smtp_port = int(smtp_port_raw)
        except ValueError as exc:
            raise ConfigurationError(
                f"SMTP_PORT must be an integer, got: {smtp_port_raw!r}"
            ) from exc

    retention_limit_raw = _get_optional("NOTEBOOKS_RETENTION_LIMIT", "2")
    try:
        notebooks_retention_limit = int(retention_limit_raw) if retention_limit_raw.strip() else 2
    except ValueError as exc:
        raise ConfigurationError(
            f"NOTEBOOKS_RETENTION_LIMIT must be an integer, got: {retention_limit_raw!r}"
        ) from exc

    top_digest_count_raw = _get_optional("TOP_DIGEST_COUNT", "20")
    try:
        top_digest_count = int(top_digest_count_raw) if top_digest_count_raw.strip() else 20
    except ValueError as exc:
        raise ConfigurationError(
            f"TOP_DIGEST_COUNT must be an integer, got: {top_digest_count_raw!r}"
        ) from exc

    top10_download_dir_raw = _get_optional("TOP10_DOWNLOAD_DIR")
    top10_download_dir = (
        Path(top10_download_dir_raw).expanduser().resolve()
        if top10_download_dir_raw
        else paths.get_top10_video_download_dir()
    )

    top10_prev_dir_raw = _get_optional("TOP10_PREV_DIR")
    top10_prev_dir = (
        Path(top10_prev_dir_raw).expanduser().resolve()
        if top10_prev_dir_raw
        else paths.get_top10_previous_video_download_dir()
    )

    return Config(
        smtp_server=_get_optional("SMTP_SERVER"),
        smtp_port=smtp_port,
        smtp_username=_get_optional("SMTP_USERNAME"),
        smtp_password=_get_optional("SMTP_PASSWORD"),
        sender_email=_get_optional("SENDER_EMAIL"),
        recipient_email=_get_optional("RECIPIENT_EMAIL"),
        youtube_api_key=_get_optional("YOUTUBE_API_KEY"),
        sources_file=paths.get_sources_file(),
        state_file=paths.get_state_file(),
        notebooks_retention_limit=notebooks_retention_limit,
        generate_infographics=_get_bool("GENERATE_INFOGRAPHICS", False),
        generate_top10_digest=_get_bool("GENERATE_TOP_10_DIGEST", False),
        top_digest_count=top_digest_count,
        download_top10_videos=_get_bool("DOWNLOAD_TOP_10_VIDEOS", False),
        top10_download_dir=top10_download_dir,
        top10_prev_dir=top10_prev_dir,
        send_channel_emails=_get_bool("SEND_CHANNEL_EMAILS", False),
        deploy_to_gh_pages=_get_bool("DEPLOY_TO_GH_PAGES", True),
        gh_pages_url=_get_optional("GH_PAGES_URL", "https://vkr1729.github.io/TubeLM/"),
        compress_audio=_get_bool("COMPRESS_AUDIO", False),
        notebooklm_browser=_get_optional("NOTEBOOKLM_BROWSER", "chrome"),
    )
