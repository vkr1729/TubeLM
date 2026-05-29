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


def _load_prompt_file(filename: str) -> str:
    """Load a prompt template from a Markdown file in the shared prompts directory.

    Returns the file content stripped of leading/trailing whitespace,
    or an empty string if the file is missing or empty.
    """
    path = paths.get_prompts_dir() / filename
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
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

    # Custom prompt templates from Markdown files
    summary_prompt: str   # Content of Summary_Prompt.md (or empty → use default)
    podcast_prompt: str   # Content of Podcast_Prompt.md (or empty → use default)

    # Local file paths
    channels_file: Path
    state_file: Path

    # Retention configuration
    notebooks_retention_limit: int

    # Default browser for NotebookLM extraction (chrome, edge, safari, firefox, opera, etc.)
    notebooklm_browser: str = "chrome"

    # Premium email theme template name
    email_theme: str = "email_digest.html"

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

    retention_limit_raw = _get_optional("NOTEBOOKS_RETENTION_LIMIT", "0")
    try:
        notebooks_retention_limit = int(retention_limit_raw) if retention_limit_raw.strip() else 0
    except ValueError as exc:
        raise ConfigurationError(
            f"NOTEBOOKS_RETENTION_LIMIT must be an integer, got: {retention_limit_raw!r}"
        ) from exc

    return Config(
        smtp_server=_get_optional("SMTP_SERVER"),
        smtp_port=smtp_port,
        smtp_username=_get_optional("SMTP_USERNAME"),
        smtp_password=_get_optional("SMTP_PASSWORD"),
        sender_email=_get_optional("SENDER_EMAIL"),
        recipient_email=_get_optional("RECIPIENT_EMAIL"),
        youtube_api_key=_get_optional("YOUTUBE_API_KEY"),
        summary_prompt=_load_prompt_file("Summary_Prompt.md"),
        podcast_prompt=_load_prompt_file("Podcast_Prompt.md"),
        channels_file=paths.get_channels_file(),
        state_file=paths.get_state_file(),
        notebooks_retention_limit=notebooks_retention_limit,
        notebooklm_browser=_get_optional("NOTEBOOKLM_BROWSER", "chrome"),
        email_theme=_get_optional("EMAIL_THEME", "email_digest.html"),
    )
