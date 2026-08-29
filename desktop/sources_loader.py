import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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
        entry["generate_cinematic_video"] = bool(
            entry.get("generate_cinematic_video", False)
        )
        sources.append(entry)
    return sources
