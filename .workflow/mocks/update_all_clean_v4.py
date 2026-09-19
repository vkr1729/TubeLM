c = open(".workflow/mocks/mock1_executive_briefing.html", "r", encoding="utf-8").read()

# 1. Channels Standalone
ch_page = c.replace(
    'id="tab-briefing-view"', 'id="tab-briefing-view" style="display:none;"'
).replace(
    'id="tab-channels-view" style="display:none;"', 'id="tab-channels-view"'
).replace(
    '<div class="header-title" id="headerTitle">Weekly Briefing</div>',
    '<div class="header-title" id="headerTitle">Channels</div>'
).replace(
    '<div class="tab-item active" id="nav-briefing"',
    '<div class="tab-item" id="nav-briefing"'
).replace(
    '<div class="tab-item" id="nav-channels"',
    '<div class="tab-item active" id="nav-channels"'
)

with open(".workflow/mocks/mock1_channels_tab.html", "w", encoding="utf-8") as f:
    f.write(ch_page)

# 2. Bookmarks Standalone
bm_page = c.replace(
    'id="tab-briefing-view"', 'id="tab-briefing-view" style="display:none;"'
).replace(
    'id="tab-saved-view" style="display:none;"', 'id="tab-saved-view"'
).replace(
    '<div class="header-title" id="headerTitle">Weekly Briefing</div>',
    '<div class="header-title" id="headerTitle">Bookmarks</div>'
).replace(
    '<div class="tab-item active" id="nav-briefing"',
    '<div class="tab-item" id="nav-briefing"'
).replace(
    '<div class="tab-item" id="nav-saved"',
    '<div class="tab-item active" id="nav-saved"'
)

with open(".workflow/mocks/mock1_saved_tab.html", "w", encoding="utf-8") as f:
    f.write(bm_page)

# 3. Master Gallery Index
gallery_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TubeLM iOS - Executive Briefing (Clean Minimalist)</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #08090b; color: #f1f5f9; font-family: 'Inter', -apple-system, sans-serif;
      min-height: 100vh; display: flex; flex-direction: column;
    }
    header {
      background: #0f1117; border-bottom: 1px solid rgba(255,255,255,0.08);
      padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-pill {
      background: #d9ff63; color: #111; font-weight: 900; font-size: 12px; padding: 4px 8px; border-radius: 6px;
    }
    .brand-title { font-size: 18px; font-weight: 800; letter-spacing: -0.3px; }
    .brand-sub { font-size: 12px; color: #94a3b8; }

    .nav-bar {
      display: flex; gap: 6px; overflow-x: auto; padding: 4px; background: #161922; border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.06);
    }
    .nav-btn {
      background: transparent; border: none; color: #94a3b8; padding: 7px 14px; border-radius: 8px;
      font-size: 12px; font-weight: 700; cursor: pointer; transition: all 0.15s; white-space: nowrap;
    }
    .nav-btn:hover { color: #fff; }
    .nav-btn.active { background: #d9ff63; color: #0f1117; }

    .main-container {
      flex: 1; display: grid; grid-template-columns: 460px 1fr; gap: 24px; padding: 24px; max-width: 1600px;
      margin: 0 auto; width: 100%;
    }
    @media (max-width: 1080px) {
      .main-container { grid-template-columns: 1fr; }
    }

    .phone-stage {
      display: flex; flex-direction: column; align-items: center; gap: 12px;
    }
    .iphone-frame {
      width: 412px; height: 852px; background: #000; border-radius: 54px;
      box-shadow: 0 0 0 12px #26272b, 0 0 0 14px #1a1a1c, 0 30px 80px rgba(0,0,0,0.8);
      position: relative; overflow: hidden; border: 4px solid #000;
    }
    iframe { width: 100%; height: 100%; border: none; background: #fff; }

    .panel {
      background: #0f1117; border: 1px solid rgba(255,255,255,0.08); border-radius: 20px;
      padding: 24px; display: flex; flex-direction: column; gap: 20px;
    }
    .panel-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .mock-title { font-size: 22px; font-weight: 800; margin-bottom: 4px; }
    .mock-tag { font-size: 13px; color: #38bdf8; font-weight: 600; }
    .overall-score {
      font-size: 28px; font-weight: 900; color: #d9ff63; background: rgba(217, 255, 99, 0.1);
      padding: 6px 14px; border-radius: 12px; border: 1px solid rgba(217, 255, 99, 0.2);
    }

    .feature-box {
      background: #161922; border-radius: 14px; padding: 16px; font-size: 14px; line-height: 1.6; color: #cbd5e1;
    }
    .feature-box h4 { font-size: 13px; font-weight: 800; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px; }
    .feature-box ul { margin-left: 20px; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-pill">TubeLM iOS</div>
      <div>
        <div class="brand-title">Executive Briefing (Clean Minimalist v4.0)</div>
        <div class="brand-sub">All 20 Items Continuous · Zero Dividers · Fluff Text Stripped</div>
      </div>
    </div>
    <div class="nav-bar">
      <button class="nav-btn active" onclick="loadPage('mock1_executive_briefing.html', 'tab1')">1. Briefing (20 Items Continuous)</button>
      <button class="nav-btn" onclick="loadPage('mock1_channels_tab.html', 'tab2')">2. Channels</button>
      <button class="nav-btn" onclick="loadPage('mock1_saved_tab.html', 'tab3')">3. Bookmarks</button>
    </div>
  </header>

  <div class="main-container">
    <div class="phone-stage">
      <div class="iphone-frame">
        <iframe id="mockFrame" src="mock1_executive_briefing.html"></iframe>
      </div>
      <span style="font-size:12px; color:#94a3b8;">Tap the Mini-Player to open the Commute Queue Drawer!</span>
    </div>

    <div class="panel" id="panelContent"></div>
  </div>

  <script>
    const TAB_INFO = {
      'tab1': {
        title: "Tab 1: Weekly Briefing",
        tag: "20 Items Continuous · Zero Dividers · Zero Fluff",
        score: "Clean v4.0",
        highlights: [
          "All 20 videos and articles rendered in a single, uninterrupted, continuous feed.",
          "Removed 'Top 10 Must-Watch', 'Ranked Selection', and any dividers.",
          "Subtitles ('Executive Intelligence', 'Priority' suffix) completely removed for crisp minimalism.",
          "Cards feature clean rank '#1' to '#20', Why It Matters summary, audio player, concise 'Watch'/'Read', '+ Queue', and bookmark action."
        ]
      },
      'tab2': {
        title: "Tab 2: Channels",
        tag: "Clean Search & Direct Expandable Overviews",
        score: "Clean v4.0",
        highlights: [
          "Clean header and minimal search bar with 'Search channels...' placeholder.",
          "Removed instructional fluff ('Tap any channel to expand...', 'INDIVIDUAL OVERVIEWS').",
          "MIT Technology Review shows all 6 individual items with fully formatted markdown summaries.",
          "Clean 'Listen Unwatched' button shows remaining count and dynamic skipping."
        ]
      },
      'tab3': {
        title: "Tab 3: Bookmarks",
        tag: "Minimal Saved Library",
        score: "Clean v4.0",
        highlights: [
          "Removed big sync status banner, dev notes, and 'Pure Text · Unlimited' labels.",
          "Clean cards with category, title, concise overview, and 1-tap Remove action.",
          "Automatic background Cloudflare sync on every action via discreet toast."
        ]
      }
    };

    function loadPage(url, tabKey) {
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('mockFrame').src = url;
      renderPanel(tabKey);
    }

    function renderPanel(key) {
      const info = TAB_INFO[key];
      const panel = document.getElementById('panelContent');
      panel.innerHTML = `
        <div class="panel-header">
          <div>
            <div class="mock-title">${info.title}</div>
            <div class="mock-tag">${info.tag}</div>
          </div>
          <div class="overall-score">${info.score}</div>
        </div>

        <div class="feature-box">
          <h4>What Changed in Clean v4.0</h4>
          <ul>
            ${info.highlights.map(h => `<li style="margin-bottom:8px;">${h}</li>`).join('')}
          </ul>
        </div>

        <div style="background:rgba(34, 197, 94, 0.08); border-left:3px solid #22c55e; padding:14px 16px; border-radius:0 10px 10px 0; font-size:13px; color:#cbd5e1; line-height:1.5;">
          <strong>Distraction-Free Experience:</strong> All dev labels, section dividers, and instructional helper text have been completely eliminated. Tap the mini-player to open the native <strong>Commute Deck & Queue Sheet</strong>!
        </div>
      `;
    }

    renderPanel('tab1');
  </script>
</body>
</html>
"""

with open(".workflow/mocks/index.html", "w", encoding="utf-8") as f:
    f.write(gallery_html)

print("Updated all pages and gallery index!")
