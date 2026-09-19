import json
import html
from pathlib import Path

# Load mock1_executive_briefing.html
content = open(".workflow/mocks/mock1_executive_briefing.html", "r", encoding="utf-8").read()

# Generate Channels Standalone
channels_content = content.replace(
    'id="tab-briefing-view"', 'id="tab-briefing-view" style="display:none;"'
).replace(
    'id="tab-channels-view" style="display:none;"', 'id="tab-channels-view"'
).replace(
    '<div class="header-title" id="headerTitle">Weekly Briefing</div>',
    '<div class="header-title" id="headerTitle">Channels</div>'
).replace(
    '<div class="header-sub" id="headerSub">Executive Intelligence</div>',
    '<div class="header-sub" id="headerSub">23 Curated Sources</div>'
).replace(
    '<div class="tab-item active" id="nav-briefing"',
    '<div class="tab-item" id="nav-briefing"'
).replace(
    '<div class="tab-item" id="nav-channels"',
    '<div class="tab-item active" id="nav-channels"'
)

with open(".workflow/mocks/mock1_channels_tab.html", "w", encoding="utf-8") as f:
    f.write(channels_content)
print("Wrote mock1_channels_tab.html")

# Generate Saved Standalone
saved_content = content.replace(
    'id="tab-briefing-view"', 'id="tab-briefing-view" style="display:none;"'
).replace(
    'id="tab-saved-view" style="display:none;"', 'id="tab-saved-view"'
).replace(
    '<div class="header-title" id="headerTitle">Weekly Briefing</div>',
    '<div class="header-title" id="headerTitle">Commute Queue</div>'
).replace(
    '<div class="header-sub" id="headerSub">Executive Intelligence</div>',
    '<div class="header-sub" id="headerSub">Saved & Pinned Items</div>'
).replace(
    '<div class="tab-item active" id="nav-briefing"',
    '<div class="tab-item" id="nav-briefing"'
).replace(
    '<div class="tab-item" id="nav-saved"',
    '<div class="tab-item active" id="nav-saved"'
)

with open(".workflow/mocks/mock1_saved_tab.html", "w", encoding="utf-8") as f:
    f.write(saved_content)
print("Wrote mock1_saved_tab.html")
