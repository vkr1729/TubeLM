"""Central path helpers for the source-checkout TubeLM application."""

import os
from pathlib import Path
import re
import shutil


def ensure_user_bin_on_path() -> None:
    """Ensure ~/.local/bin is on PATH so systemd/cron services can find user tools."""
    user_bin = str(Path.home() / ".local" / "bin")
    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    if user_bin not in path_parts and Path(user_bin).exists():
        os.environ["PATH"] = f"{user_bin}{os.pathsep}{current_path}" if current_path else user_bin


ensure_user_bin_on_path()

DESKTOP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DESKTOP_DIR.parent


def is_frozen() -> bool:
    """Retained for old scheduler branches; source-checkout runs are never frozen."""
    return False


def get_bundle_dir() -> Path:
    """Return the directory containing the Python application."""
    return DESKTOP_DIR


def get_data_dir() -> Path:
    """Return the private runtime directory."""
    return (Path.home() / ".tubelm").resolve()


def get_templates_dir() -> Path:
    return DESKTOP_DIR / "templates"


def get_prompts_dir() -> Path:
    return PROJECT_DIR / "shared" / "prompts"


def get_user_prompts_dir() -> Path:
    return get_data_dir() / "prompts"


def get_env_file() -> Path:
    local = PROJECT_DIR / ".env"
    return local if local.exists() else get_data_dir() / ".env"


def get_sources_file() -> Path:
    local = PROJECT_DIR / "sources.json"
    return local if local.exists() else get_data_dir() / "sources.json"


def get_state_file() -> Path:
    return get_data_dir() / "state.json"


def get_pipeline_lock_file() -> Path:
    return get_data_dir() / "pipeline.lock"


def get_resume_request_file() -> Path:
    return get_data_dir() / "resume_request.json"


def get_scheduled_request_file() -> Path:
    return get_data_dir() / "scheduled_request.json"


def get_compute_deferral_file() -> Path:
    return get_data_dir() / "compute_deferral.json"


def get_deferred_artifacts_file() -> Path:
    return get_data_dir() / "deferred_artifacts.json"


def get_weekly_video_batches_file() -> Path:
    return get_data_dir() / "weekly_video_batches.json"


def get_weekly_audio_batches_file() -> Path:
    return get_data_dir() / "weekly_audio_batches.json"


def get_video_download_dir() -> Path:
    return Path.home() / "Downloads" / "TorBox" / "TubeLM"


def get_previous_video_download_dir() -> Path:
    return Path.home() / "Downloads" / "TorBox" / "TubeLM_Prev"


def get_top10_video_download_dir() -> Path:
    return Path.home() / "Downloads" / "TorBox" / "Top_10"


def get_top10_previous_video_download_dir() -> Path:
    return Path.home() / "Downloads" / "TorBox" / "Top_10_Prev"


def get_notebook_links_cache_file() -> Path:
    return get_data_dir() / "notebook_links_cache.json"


def get_summaries_dir() -> Path:
    return get_data_dir() / "summaries"


def get_audio_dir() -> Path:
    return get_data_dir() / "audio"


def get_site_dir() -> Path:
    return get_data_dir() / "site"


def get_read_state_file() -> Path:
    return get_data_dir() / "read_state.json"


def get_top10_digest_batch_file() -> Path:
    return get_data_dir() / "top10_digest_batch.json"


def get_top_article_videos_file() -> Path:
    return get_data_dir() / "top_article_videos.json"


def ensure_data_dir() -> None:
    """Create runtime directories and seed missing personal configuration."""
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_summaries_dir().mkdir(exist_ok=True)
    get_audio_dir().mkdir(exist_ok=True)
    get_site_dir().mkdir(exist_ok=True)

    env_target = get_env_file()
    env_example = PROJECT_DIR / ".env.example"
    if not env_target.exists() and env_example.exists():
        shutil.copy(env_example, env_target)

    sources_target = get_sources_file()
    sources_example = PROJECT_DIR / "sources.json.example"
    if not sources_target.exists() and sources_example.exists():
        shutil.copy(sources_example, sources_target)


def get_notebooklm_bin() -> str:
    """Resolve the NotebookLM CLI from this checkout or the system PATH."""
    local = PROJECT_DIR / ".venv" / "bin" / "notebooklm"
    if local.exists():
        return str(local)
    return shutil.which("notebooklm") or "notebooklm"


def get_agy_bin() -> str | None:
    """Resolve the agy CLI from the system PATH or standard install locations."""
    found = shutil.which("agy")
    if found:
        return found
    candidates = [
        Path.home() / ".local" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
        Path("/usr/bin/agy"),
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def safe_channel_name(name: str) -> str:
    """Return a filesystem-safe source name."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
