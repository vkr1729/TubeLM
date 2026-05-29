"""
paths.py — Centralised path resolution utility.

Detects whether the application is running from a PyInstaller frozen bundle
or in development mode, and returns the appropriate directories for configuration,
templates, prompts, and binary scripts.
"""

import sys
import os
import shutil
from pathlib import Path

def is_frozen() -> bool:
    """Returns True if the application is running in a PyInstaller frozen bundle."""
    return getattr(sys, 'frozen', False)

def get_bundle_dir() -> Path:
    """Returns the bundle root directory.
    In frozen mode, this is the extraction/mount directory (sys._MEIPASS).
    In dev mode, this is the desktop/ directory (where this file resides).
    """
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).parent.resolve()

def get_data_dir() -> Path:
    """Returns the canonical user data directory (~/.tubelm/)."""
    data_dir = Path.home() / ".tubelm"
    return data_dir.resolve()

def get_templates_dir() -> Path:
    """Returns the directory containing UI templates."""
    return get_bundle_dir() / "templates"

def get_prompts_dir() -> Path:
    """Returns the directory containing prompt Markdown templates.
    In frozen mode, they are bundled in the root of the extraction dir.
    In dev mode, they are in the shared prompts directory.
    """
    if is_frozen():
        return get_bundle_dir()
    return get_bundle_dir().parent / "shared" / "prompts"

def get_assets_dir() -> Path:
    """Returns the directory containing visual assets.
    In frozen mode, they are bundled in the assets/ subdirectory of extraction dir.
    In dev mode, they are in the shared assets directory.
    """
    if is_frozen():
        return get_bundle_dir() / "assets"
    return get_bundle_dir().parent / "shared" / "assets"

def get_env_file() -> Path:
    """Returns the path to the user's .env file."""
    if not is_frozen():
        local_env = get_bundle_dir().parent / ".env"
        if local_env.exists():
            return local_env
    return get_data_dir() / ".env"

def get_channels_file() -> Path:
    """Returns the path to the user's channels.json file."""
    if not is_frozen():
        local_ch = get_bundle_dir().parent / "channels.json"
        if local_ch.exists():
            return local_ch
    return get_data_dir() / "channels.json"

def get_state_file() -> Path:
    """Returns the path to the user's state.json file."""
    return get_data_dir() / "state.json"

def get_summaries_dir() -> Path:
    """Returns the path to the user's summaries/ directory."""
    return get_data_dir() / "summaries"

def ensure_data_dir() -> None:
    """Bootstraps the user data directory (~/.tubelm/) if it does not exist.
    Copies bundled example configuration files if the user's config files are missing.
    """
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    get_summaries_dir().mkdir(exist_ok=True)

    # Resolve example file paths
    # In frozen mode, they are collected in the bundle root.
    # In dev mode, they are in the workspace root.
    if is_frozen():
        src_env = get_bundle_dir() / ".env.example"
        src_channels = get_bundle_dir() / "channels.json.example"
    else:
        src_env = get_bundle_dir().parent / ".env.example"
        src_channels = get_bundle_dir().parent / "channels.json.example"

    dest_env = get_env_file()
    if not dest_env.exists() and src_env.exists():
        shutil.copy(src_env, dest_env)

    dest_channels = get_channels_file()
    if not dest_channels.exists() and src_channels.exists():
        shutil.copy(src_channels, dest_channels)

def get_notebooklm_bin() -> str:
    """Resolve the location of the bundled or environment-installed notebooklm CLI."""
    # 1. Check frozen-specific locations
    if is_frozen():
        bundle_dir = get_bundle_dir()
        paths_to_check = []
        if sys.platform == "win32":
            paths_to_check.extend([
                bundle_dir / "notebooklm.exe",
                bundle_dir / "Scripts" / "notebooklm.exe",
                bundle_dir / "_internal" / "Scripts" / "notebooklm.exe",
            ])
        else:
            paths_to_check.extend([
                bundle_dir / "notebooklm",
                bundle_dir / "bin" / "notebooklm",
                bundle_dir / "_internal" / "bin" / "notebooklm",
            ])
        for p in paths_to_check:
            if p.exists():
                return str(p.resolve())

    # 2. Check dev venv locations relative to get_bundle_dir() (which is desktop/)
    bundle_dir = get_bundle_dir()
    paths_to_check = []
    if sys.platform == "win32":
        paths_to_check.extend([
            bundle_dir.parent / ".venv" / "Scripts" / "notebooklm.exe",
            bundle_dir.parent / ".venv" / "Scripts" / "notebooklm",
            bundle_dir / ".venv" / "Scripts" / "notebooklm.exe",
            bundle_dir / ".venv" / "Scripts" / "notebooklm",
        ])
    else:
        paths_to_check.extend([
            bundle_dir.parent / ".venv" / "bin" / "notebooklm",
            bundle_dir / ".venv" / "bin" / "notebooklm",
        ])
    for p in paths_to_check:
        if p.exists():
            return str(p.resolve())

    # 3. Fall back to finding it in the system PATH
    which_bin = shutil.which("notebooklm")
    if which_bin:
        return which_bin

    # 4. Final fallback
    return "notebooklm"


def safe_channel_name(name: str) -> str:
    """Return a filesystem-safe version of a channel name.

    Replaces every character that is not alphanumeric, underscore, or dash
    with an underscore.  This is the single canonical sanitiser used by both
    notebooklm_service.py and main.py so that infographic filenames and HTML
    digest filenames always agree.
    """
    import re
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
