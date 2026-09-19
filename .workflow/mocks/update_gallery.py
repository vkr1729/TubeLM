gallery_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TubeLM iOS - Mock 1 Complete Tab Gallery & Reviews</title>
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
    .nav-btn.secondary { border: 1px solid rgba(255,255,255,0.1); }

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

    .badge-pill {
      display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 700;
      background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3);
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-pill">TubeLM iOS</div>
      <div>
        <div class="brand-title">Mock 1: The Executive Briefing (Full Tabs)</div>
        <div class="brand-sub">Light Mode Default · Channels Directory · Commute Queue & Cloudflare Sync</div>
      </div>
    </div>
    <div class="nav-bar">
      <button class="nav-btn active" onclick="loadPage('mock1_executive_briefing.html', 'tab1')">1. Briefing (Feed)</button>
      <button class="nav-btn" onclick="loadPage('mock1_channels_tab.html', 'tab2')">2. Channels (23 Sources)</button>
      <button class="nav-btn" onclick="loadPage('mock1_saved_tab.html', 'tab3')">3. Saved (Commute Queue)</button>
    </div>
  </header>

  <div class="main-container">
    <div class="phone-stage">
      <div class="iphone-frame">
        <iframe id="mockFrame" src="mock1_executive_briefing.html"></iframe>
      </div>
      <span style="font-size:12px; color:#94a3b8;">Click tab bar inside frame to navigate, or use top buttons</span>
    </div>

    <div class="panel" id="panelContent">
      <!-- Injected details -->
    </div>
  </div>

  <script>
    const TAB_INFO = {
      'tab1': {
        title: "Tab 1: Weekly Briefing (Executive Top 20)",
        tag: "Light Mode Default (with Dark Mode toggle in header)",
        score: "Selected",
        highlights: [
          "Ranked priority badges (#1 to #10 Must-Watch, #11 to #20 Next Notable).",
          "Prominent 'Why It Matters' editorial callout box on every card.",
          "Sticky mini-player stays accessible at bottom with waveform scrubber, 1.25x commuter speed toggle.",
          "1-Tap 'Save' button adds items directly to your Commute Queue in Tab 3.",
          "Interactive Light/Dark Mode toggle in the top right header."
        ]
      },
      'tab2': {
        title: "Tab 2: Channels (23 Curated Sources)",
        tag: "Searchable Directory & Category Segmentation",
        score: "Live Mock",
        highlights: [
          "Live instant search across all 23 curated channels (Physionic, Veritasium, 3Blue1Brown, Doctor Alex, etc.).",
          "Category pills: All (23), Tech & AI (10), Health & Bio (7), Science & Deep (6).",
          "Channel cards display avatar with category color-coding, video count, and read time.",
          "One-tap 'Listen Summary' plays the entire channel's weekly overview immediately."
        ]
      },
      'tab3': {
        title: "Tab 3: Commute Queue & Cloudflare Sync",
        tag: "Offline Subway Staging & Cross-Device Sync",
        score: "Live Mock",
        highlights: [
          "Commute Queue summary banner showing total saved items and cumulative audio playback duration.",
          "1-Tap '▶ Play Entire Queue' for continuous audio narration while riding transit.",
          "Cloudflare Worker State Sync Card: Pairs with tubelm-sync.workers.dev (Durable Object CRDT merge) so read items sync between iPhone app and laptop web reader!",
          "Individual remove / reorder actions for commute triage."
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
          <h4>Tab Experience & Ergonomics</h4>
          <ul>
            ${info.highlights.map(h => `<li style="margin-bottom:8px;">${h}</li>`).join('')}
          </ul>
        </div>

        <div style="background:rgba(34, 197, 94, 0.08); border-left:3px solid #22c55e; padding:14px 16px; border-radius:0 10px 10px 0; font-size:13px; color:#cbd5e1; line-height:1.5;">
          <strong>Design Locked:</strong> This completes the full 3-tab visual interface for <em>Mock 1: The Executive Briefing</em>. Ready for Stage 2 planning and architecture lock.
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
print("Updated gallery index.html")
