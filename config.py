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

load_dotenv()


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
    return os.getenv(key, default).strip()


def _load_prompt_file(filename: str) -> str:
    """Load a prompt template from a Markdown file in the project root.

    Returns the file content stripped of leading/trailing whitespace,
    or an empty string if the file is missing or empty.
    """
    path = Path(filename)
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

    # Derived: use SSL (port 465) or STARTTLS (port 587)
    use_ssl: bool = field(init=False)

    def __post_init__(self) -> None:
        # frozen=True means we must use object.__setattr__ for derived fields
        object.__setattr__(self, "use_ssl", self.smtp_port == 465)


def load_config() -> Config:
    """Load and validate all configuration from environment variables.

    Raises:
        ConfigurationError: If any required variable is missing.
        ValueError: If SMTP_PORT is not a valid integer.
    """
    smtp_port_raw = _get_required("SMTP_PORT")
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"SMTP_PORT must be an integer, got: {smtp_port_raw!r}"
        ) from exc

    return Config(
        smtp_server=_get_required("SMTP_SERVER"),
        smtp_port=smtp_port,
        smtp_username=_get_required("SMTP_USERNAME"),
        smtp_password=_get_required("SMTP_PASSWORD"),
        sender_email=_get_required("SENDER_EMAIL"),
        recipient_email=_get_required("RECIPIENT_EMAIL"),
        youtube_api_key=_get_required("YOUTUBE_API_KEY"),
        summary_prompt=_load_prompt_file("Summary_Prompt.md"),
        podcast_prompt=_load_prompt_file("Podcast_Prompt.md"),
        channels_file=Path(_get_optional("CHANNELS_FILE", "channels.json")),
        state_file=Path(_get_optional("STATE_FILE", "state.json")),
    )
