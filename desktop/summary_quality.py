"""Small, deterministic quality filters for NotebookLM briefing text."""

from __future__ import annotations

import re


_FOLLOW_UP_OFFER_PATTERNS = (
    r"\bif you (?:want|would like)\b",
    r"\bwould you like (?:me )?to\b",
    r"\bi can (?:also )?(?:create|generate|turn|translate|compile|prepare|make)\b",
    r"\blet me know if\b",
    r"\bavailable in your studio panel\b",
    r"\byou can (?:read|find|open) the complete\b",
)


def strip_follow_up_offers(text: str) -> str:
    """Drop assistant-style upsells while preserving analytical recommendations."""
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", text.strip())
    kept = []
    for block in blocks:
        normalized = re.sub(r"^[\s🎧📊💡✨]+", "", block).strip()
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in _FOLLOW_UP_OFFER_PATTERNS):
            continue
        kept.append(block.strip())
    return "\n\n".join(kept).strip()
