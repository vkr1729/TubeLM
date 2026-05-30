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
    sources = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict) or not entry.get("name"):
            logger.warning("sources.json entry %d missing 'name' — skipping.", i)
            continue
        if "type" not in entry:
            if entry.get("channel_id"):
                entry["type"] = "youtube"
            else:
                logger.warning("Entry %d has no 'type' or 'channel_id' — skipping.", i)
                continue
        sources.append(entry)
    return sources
