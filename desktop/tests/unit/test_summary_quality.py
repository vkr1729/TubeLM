import pytest

from notebooklm_service import _validate_summary_text
from summary_quality import strip_follow_up_offers


def test_strips_aevy_tv_audio_upsell():
    summary = """## The Startup Journey — Aevy TV

The founders built a bootstrapped ecosystem and accepted slower growth in exchange for control.

🎧 If you want to listen to this startup's journey on the go, I can generate a high-quality audio overview discussing the trade-offs of their bootstrapped ecosystem.
"""

    cleaned = strip_follow_up_offers(summary)

    assert "bootstrapped ecosystem" in cleaned
    assert "If you want" not in cleaned
    assert "I can generate" not in cleaned


@pytest.mark.parametrize(
    "response",
    [
        "The full deliverable is available in your Studio panel as briefing.md.",
        "## Proposed Briefing Outline\n\nDoes this plan look solid to you?",
    ],
)
def test_rejects_placeholder_summary_responses(response):
    valid, reason = _validate_summary_text(response, 1)
    assert valid is False
    assert reason


def test_requires_one_section_per_item():
    response = "## First item\n\n" + ("Substantive analysis. " * 30)
    valid, reason = _validate_summary_text(response, 2)
    assert valid is False
    assert "1 of 2" in reason


def test_accepts_direct_complete_summary():
    response = (
        "## First item\n\n" + ("Substantive analysis one. " * 12)
        + "\n\n## Second item\n\n" + ("Substantive analysis two. " * 12)
    )
    valid, reason = _validate_summary_text(response, 2)
    assert valid is True
    assert reason == ""


def test_accepts_creator_speech_with_first_person_creation():
    response = (
        "## Omarchy Automation Framework\n\n"
        "In this live coding session, the creator explains: 'I have created an automation framework "
        "that handles window tiling and system setup.' The architecture is modular and fast. " * 3
    )
    valid, reason = _validate_summary_text(response, 1)
    assert valid is True
    assert reason == ""

