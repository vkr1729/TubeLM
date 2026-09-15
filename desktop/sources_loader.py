import json
import logging
from pathlib import Path

from paths import BOOL_FALSE_VALUES, BOOL_TRUE_VALUES

logger = logging.getLogger(__name__)


def _coerce_flag(value) -> bool:
    """Coerce a hand-edited flag: bool("false") is True, so parse strings."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in BOOL_TRUE_VALUES:
            return True
        if normalized in BOOL_FALSE_VALUES:
            return False
        logger.warning("Unrecognized flag value %r; treating as false.", value)
        return False
    return bool(value)


def load_sources(sources_file: Path) -> list[dict]:
    if not sources_file.exists():
        logger.warning("Sources file not found: %s. Returning empty list.", sources_file)
        return []
    try:
        data = json.loads(sources_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("sources.json is not valid JSON: %s", exc)
        return []
    if not isinstance(data, list):
        logger.error("sources.json must contain a JSON array.")
        return []
    sources = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict) or not entry.get("name"):
            logger.warning("sources.json entry %d missing 'name' — skipping.", i)
            continue
        if "type" not in entry:
            logger.warning("sources.json entry %d has no 'type' — skipping.", i)
            continue
        if entry["type"] not in {"youtube", "rss", "webpage"}:
            logger.warning("Entry %d has unsupported type %r — skipping.", i, entry["type"])
            continue
        required_field = "channel_id" if entry["type"] == "youtube" else "url"
        if not entry.get(required_field):
            logger.warning("Entry %d missing %r — skipping.", i, required_field)
            continue
        # Normalize only when the author set the key: an absent flag must stay
        # absent so main.py can fall back to the global GENERATE_PODCASTS value.
        if "generate_podcast" in entry:
            entry["generate_podcast"] = _coerce_flag(entry["generate_podcast"])
        if entry["type"] == "rss":
            entry["behind_paywall"] = bool(entry.get("behind_paywall", True))
        sources.append(entry)
    return sources
