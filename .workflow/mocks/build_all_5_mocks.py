import json
import html
from pathlib import Path

data_path = Path(".workflow/mocks/mock_data.json")
with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

run_date = data.get("run_date", "2026-09-18")
top20 = data.get("top20", {}).get("items", [])
channels = data.get("channels", [])

top10 = top20[:10]
next10 = top20[10:20]

def escape_js(s):
    return json.dumps(s or "")

# Pre-process items for safety and rich display
for it in top20:
    it["rank"] = it.get("rank") or 1
    it["title"] = it.get("title") or "Executive Briefing"
    it["why_it_matters"] = it.get("why_it_matters") or "Key industry development highlighted this week."
    it["source_name"] = it.get("source_name") or "Curated Source"
    it["category"] = it.get("category") or "tech"
    it["duration"] = it.get("duration") or "14m"

# -------------------------------------------------------------
# MOCK 1: The Executive Briefing (Artifact & Apple News)
# -------------------------------------------------------------
mock1_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - Executive Briefing</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,700;1,6..72,400&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }}
    :root {{
      --bg: #0e0f12;
      --surface: #16181d;
      --surface-elevated: #1e2128;
      --border: rgba(255, 255, 255, 0.08);
      --text: #f5f6f8;
      --text-muted: #8b909a;
      --accent: #d9ff63;
      --accent-ink: #171815;
      --accent-soft: rgba(217, 255, 99, 0.12);
      --danger: #f87171;
    }}
    body {{
      background: #000; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
    }}
    .phone {{
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }}
    /* Status Bar */
    .status-bar {{
      height: 48px; padding: 12px 24px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; flex-shrink: 0; z-index: 50;
    }}
    .island {{
      position: absolute; left: 50%; top: 10px; transform: translateX(-50%); width: 124px; height: 32px;
      background: #000; border-radius: 20px; display: flex; align-items: center; justify-content: space-between;
      padding: 0 12px; cursor: pointer; transition: all 0.25s ease;
    }}
    .island-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }}
    .island-bars {{ display: flex; gap: 2px; align-items: flex-end; height: 12px; }}
    .island-bars span {{ width: 2.5px; background: var(--accent); border-radius: 1px; animation: eq 0.8s infinite ease-in-out; }}
    .island-bars span:nth-child(2) {{ animation-delay: 0.2s; }}
    .island-bars span:nth-child(3) {{ animation-delay: 0.4s; }}
    @keyframes eq {{ 0%, 100% {{ height: 3px; }} 50% {{ height: 12px; }} }}
    
    /* Header */
    .header {{
      padding: 12px 20px 16px; display: flex; justify-content: space-between; align-items: flex-end;
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }}
    .header-sub {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: var(--accent); }}
    .header-title {{ font-family: "Newsreader", serif; font-size: 26px; font-weight: 700; letter-spacing: -0.5px; line-height: 1.1; margin-top: 2px; }}
    .date-chip {{ font-size: 12px; font-weight: 600; color: var(--text-muted); background: var(--surface); padding: 4px 10px; border-radius: 12px; }}

    /* Feed Container */
    .feed {{ flex: 1; overflow-y: auto; padding: 16px 16px 140px; -webkit-overflow-scrolling: touch; }}
    .feed::-webkit-scrollbar {{ display: none; }}

    /* Section Banner */
    .section-header {{
      display: flex; align-items: center; justify-content: space-between; margin: 20px 0 12px;
    }}
    .section-title {{ font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }}
    .section-title .badge-count {{ background: var(--surface-elevated); color: var(--text); padding: 2px 7px; border-radius: 10px; font-size: 11px; }}

    /* Ranked Card */
    .card {{
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      padding: 16px; margin-bottom: 12px; transition: all 0.2s ease; position: relative;
    }}
    .card:active {{ transform: scale(0.985); background: var(--surface-elevated); }}
    .card.read {{ opacity: 0.45; filter: grayscale(0.6); }}
    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }}
    .rank-pill {{
      font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 6px; background: var(--surface-elevated);
      color: var(--accent); border: 1px solid rgba(217, 255, 99, 0.2);
    }}
    .meta-line {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted); font-weight: 500; }}
    .card-title {{
      font-size: 16px; font-weight: 700; line-height: 1.35; color: var(--text); margin-bottom: 10px;
    }}
    /* Why It Matters Callout */
    .why-box {{
      background: rgba(217, 255, 99, 0.05); border-left: 3px solid var(--accent);
      padding: 8px 12px; border-radius: 0 8px 8px 0; margin-bottom: 12px;
    }}
    .why-label {{ font-size: 10px; font-weight: 800; text-transform: uppercase; color: var(--accent); letter-spacing: 0.6px; margin-bottom: 2px; }}
    .why-text {{ font-size: 13px; line-height: 1.45; color: #d1d5db; }}
    
    .card-actions {{
      display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.04);
      padding-top: 10px; font-size: 12px;
    }}
    .btn-audio {{
      display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft);
      color: var(--accent); font-weight: 700; padding: 6px 12px; border-radius: 20px; font-size: 12px; border: none; cursor: pointer;
    }}
    .action-icons {{ display: flex; gap: 12px; align-items: center; color: var(--text-muted); }}
    .action-btn {{ background: none; border: none; color: inherit; cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 12px; }}

    /* Sticky Mini-Player */
    .mini-player {{
      position: absolute; bottom: 64px; left: 12px; right: 12px; background: rgba(30, 33, 40, 0.94);
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255,255,255,0.12); border-radius: 16px; padding: 10px 14px;
      display: flex; align-items: center; justify-content: space-between; box-shadow: 0 12px 32px rgba(0,0,0,0.6);
      z-index: 60;
    }}
    .player-info {{ display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }}
    .player-art {{
      width: 36px; height: 36px; border-radius: 8px; background: var(--accent); color: var(--accent-ink);
      font-weight: 900; font-size: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }}
    .player-titles {{ min-width: 0; }}
    .player-title {{ font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .player-sub {{ font-size: 11px; color: var(--text-muted); }}
    .player-controls {{ display: flex; align-items: center; gap: 12px; flex-shrink: 0; }}
    .play-btn {{
      width: 34px; height: 34px; border-radius: 50%; background: var(--text); color: var(--bg);
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
    }}
    .speed-pill {{
      font-size: 11px; font-weight: 800; background: rgba(255,255,255,0.1); padding: 4px 8px; border-radius: 6px;
      cursor: pointer; color: var(--accent);
    }}

    /* Bottom Tab Bar */
    .tab-bar {{
      position: absolute; bottom: 0; left: 0; right: 0; height: 64px; background: rgba(14, 15, 18, 0.96);
      backdrop-filter: blur(20px); border-top: 1px solid var(--border);
      display: flex; justify-content: space-around; align-items: center; padding-bottom: 12px; z-index: 55;
    }}
    .tab-item {{ display: flex; flex-direction: column; align-items: center; gap: 3px; font-size: 10px; font-weight: 600; color: var(--text-muted); cursor: pointer; }}
    .tab-item.active {{ color: var(--accent); }}
    .tab-item svg {{ width: 20px; height: 20px; }}

    /* Home Bar */
    .home-bar {{
      position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
      width: 136px; height: 4.5px; background: rgba(255,255,255,0.3); border-radius: 10px; pointer-events: none; z-index: 70;
    }}
  </style>
</head>
<body>
  <div class="phone">
    <!-- Status Bar -->
    <div class="status-bar">
      <span>9:41</span>
      <div class="island" onclick="toggleIsland()">
        <div class="island-dot"></div>
        <div class="island-bars"><span></span><span></span><span></span></div>
      </div>
      <div style="display:flex; gap:6px; font-size:12px;">5G 100%</div>
    </div>

    <!-- Header -->
    <div class="header">
      <div>
        <div class="header-sub">Executive Intelligence</div>
        <div class="header-title">Weekly Briefing</div>
      </div>
      <div class="date-chip">Week {run_date[-5:]}</div>
    </div>

    <!-- Feed -->
    <div class="feed" id="feed">
      <div class="section-header">
        <div class="section-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>
          Top 10 Must-Watch <span class="badge-count">10</span>
        </div>
        <span style="font-size:11px; color:var(--text-muted);">Curated by Rank</span>
      </div>
"""

for it in top10:
    mock1_html += f"""
      <div class="card" id="card-{it['rank']}">
        <div class="card-top">
          <div class="rank-pill">#{it['rank']} Priority</div>
          <div class="meta-line">
            <span>{html.escape(it['source_name'])}</span> · <span>{it['duration']}</span>
          </div>
        </div>
        <div class="card-title">{html.escape(it['title'])}</div>
        <div class="why-box">
          <div class="why-label">Why It Matters</div>
          <div class="why-text">{html.escape(it['why_it_matters'])}</div>
        </div>
        <div class="card-actions">
          <button class="btn-audio" onclick="playAudio('{html.escape(it['title'])}', '{html.escape(it['source_name'])}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Play Summary
          </button>
          <div class="action-icons">
            <button class="action-btn" onclick="toggleRead({it['rank']})">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
              Mark
            </button>
            <button class="action-btn" onclick="shareSummary('{html.escape(it['title'])}')">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
            </button>
          </div>
        </div>
      </div>
"""

mock1_html += f"""
      <div class="section-header" style="margin-top:28px;">
        <div class="section-title">
          Next 10 Notable <span class="badge-count">10</span>
        </div>
        <span style="font-size:11px; color:var(--text-muted);">High-Signal Fast Reads</span>
      </div>
"""

for it in next10:
    mock1_html += f"""
      <div class="card" id="card-{it['rank']}">
        <div class="card-top">
          <span style="font-size:12px; font-weight:800; color:var(--text-muted);">#{it['rank']}</span>
          <div class="meta-line">
            <span>{html.escape(it['source_name'])}</span> · <span>{it['duration']}</span>
          </div>
        </div>
        <div class="card-title" style="font-size:15px;">{html.escape(it['title'])}</div>
        <div style="font-size:13px; color:var(--text-muted); line-height:1.4; margin-bottom:10px;">
          {html.escape(it['why_it_matters'])}
        </div>
        <div class="card-actions">
          <button class="btn-audio" style="padding:4px 10px; font-size:11px;" onclick="playAudio('{html.escape(it['title'])}', '{html.escape(it['source_name'])}')">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Audio
          </button>
          <button class="action-btn" onclick="toggleRead({it['rank']})">Mark Read</button>
        </div>
      </div>
"""

mock1_html += """
    </div>

    <!-- Mini-Player -->
    <div class="mini-player" id="miniPlayer">
      <div class="player-info">
        <div class="player-art">TL</div>
        <div class="player-titles">
          <div class="player-title" id="playerTitle">Executive Briefing Audio</div>
          <div class="player-sub" id="playerSub">Top 20 Overview · 14m remaining</div>
        </div>
      </div>
      <div class="player-controls">
        <span class="speed-pill" onclick="cycleSpeed(this)">1.25×</span>
        <button class="play-btn" onclick="togglePlay(this)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" id="playIcon"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </button>
      </div>
    </div>

    <!-- Tab Bar -->
    <div class="tab-bar">
      <div class="tab-item active">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
        Briefing
      </div>
      <div class="tab-item">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h7"/></svg>
        Channels
      </div>
      <div class="tab-item">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
        Saved
      </div>
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    let isPlaying = false;
    function togglePlay(btn) {
      isPlaying = !isPlaying;
      btn.innerHTML = isPlaying 
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
        : '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    }
    function playAudio(title, source) {
      document.getElementById('playerTitle').innerText = title;
      document.getElementById('playerSub').innerText = source + ' · Playing';
      isPlaying = true;
      document.querySelector('.play-btn').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
    }
    function cycleSpeed(elem) {
      const speeds = ['1.0×', '1.25×', '1.5×', '2.0×'];
      let idx = (speeds.indexOf(elem.innerText) + 1) % speeds.length;
      elem.innerText = speeds[idx];
    }
    function toggleRead(rank) {
      const el = document.getElementById('card-' + rank);
      if (el) el.classList.toggle('read');
    }
    function shareSummary(title) {
      if (navigator.share) navigator.share({ title: title });
      else alert('Link copied to clipboard: ' + title);
    }
    function toggleIsland() {
      alert('LiveContainer: Audio active in background via AVAudioPlayer.');
    }
  </script>
</body>
</html>
"""

with open(".workflow/mocks/mock1_executive_briefing.html", "w", encoding="utf-8") as f:
    f.write(mock1_html)
print("Wrote mock1_executive_briefing.html")

# -------------------------------------------------------------
# MOCK 2: Commute Triage & Queue (Castro & Readwise Reader)
# -------------------------------------------------------------
mock2_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - Commute Triage</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }}
    :root {{
      --bg: #090d16;
      --surface: #111827;
      --surface-card: #162032;
      --border: rgba(56, 189, 248, 0.12);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.15);
      --amber: #fbbf24;
    }}
    body {{
      background: #000; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
    }}
    .phone {{
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }}
    .status-bar {{
      height: 48px; padding: 12px 24px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; flex-shrink: 0;
    }}
    /* Triage Segment Switcher */
    .triage-nav {{
      padding: 8px 16px 12px; display: flex; gap: 8px; flex-shrink: 0;
    }}
    .triage-tab {{
      flex: 1; padding: 10px 0; text-align: center; border-radius: 12px; font-size: 13px; font-weight: 700;
      background: var(--surface); color: var(--text-muted); cursor: pointer; transition: all 0.2s;
      display: flex; align-items: center; justify-content: center; gap: 6px;
    }}
    .triage-tab.active {{ background: var(--accent); color: #082f49; }}
    .triage-badge {{ font-size: 11px; padding: 1px 6px; border-radius: 8px; background: rgba(0,0,0,0.25); }}

    /* Feed */
    .feed {{ flex: 1; overflow-y: auto; padding: 12px 16px 130px; }}
    .feed::-webkit-scrollbar {{ display: none; }}

    /* Triage Item Card */
    .triage-card {{
      background: var(--surface-card); border: 1px solid var(--border); border-radius: 16px;
      padding: 14px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px;
    }}
    .t-header {{ display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted); }}
    .t-source {{ font-weight: 700; color: var(--accent); }}
    .t-title {{ font-size: 15px; font-weight: 700; line-height: 1.35; }}
    .t-preview {{ font-size: 13px; color: #cbd5e1; line-height: 1.45; }}

    /* Quick Action Thumb Zone (Castro Swipe / 1-Tap) */
    .thumb-actions {{
      display: flex; gap: 8px; margin-top: 4px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 10px;
    }}
    .btn-queue {{
      flex: 2; padding: 10px; border-radius: 10px; background: var(--accent-soft); color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.3); font-size: 13px; font-weight: 700; cursor: pointer;
      display: flex; align-items: center; justify-content: center; gap: 6px;
    }}
    .btn-queue:active {{ background: var(--accent); color: #000; }}
    .btn-dismiss {{
      flex: 1; padding: 10px; border-radius: 10px; background: rgba(255,255,255,0.05); color: var(--text-muted);
      border: none; font-size: 13px; font-weight: 600; cursor: pointer; text-align: center;
    }}

    /* Commute Play All Floating Pill */
    .commute-bar {{
      position: absolute; bottom: 74px; left: 16px; right: 16px; background: #0284c7; color: #fff;
      padding: 12px 18px; border-radius: 28px; display: flex; align-items: center; justify-content: space-between;
      box-shadow: 0 10px 25px rgba(2, 132, 199, 0.4); z-index: 60; cursor: pointer;
    }}
    .commute-title {{ font-size: 13px; font-weight: 700; }}
    .commute-sub {{ font-size: 11px; opacity: 0.9; }}

    .tab-bar {{
      position: absolute; bottom: 0; left: 0; right: 0; height: 64px; background: rgba(9, 13, 22, 0.98);
      border-top: 1px solid var(--border); display: flex; justify-content: space-around; align-items: center;
      padding-bottom: 12px; z-index: 55;
    }}
    .tab-item {{ font-size: 11px; font-weight: 600; color: var(--text-muted); text-align: center; }}
    .tab-item.active {{ color: var(--accent); }}
    .home-bar {{
      position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
      width: 136px; height: 4.5px; background: rgba(255,255,255,0.3); border-radius: 10px; pointer-events: none;
    }}
  </style>
</head>
<body>
  <div class="phone">
    <div class="status-bar">
      <span>9:41</span>
      <span style="color:var(--accent); font-weight:700;">Subway Mode · Offline Ready</span>
      <span>100%</span>
    </div>

    <!-- Triage Switcher -->
    <div class="triage-nav">
      <div class="triage-tab active" onclick="setTab(this, 'inbox')">
        Inbox <span class="triage-badge">{len(top20)}</span>
      </div>
      <div class="triage-tab" onclick="setTab(this, 'queue')">
        Commute Queue <span class="triage-badge" id="queueBadge">3</span>
      </div>
      <div class="triage-tab" onclick="setTab(this, 'done')">
        Done
      </div>
    </div>

    <!-- Feed -->
    <div class="feed" id="feed">
"""

for i, it in enumerate(top20):
    mock2_html += f"""
      <div class="triage-card" id="t-card-{i}">
        <div class="t-header">
          <span class="t-source">{html.escape(it['source_name'])}</span>
          <span>{it['duration']} · #{it['rank']}</span>
        </div>
        <div class="t-title">{html.escape(it['title'])}</div>
        <div class="t-preview">{html.escape(it['why_it_matters'])}</div>
        <div class="thumb-actions">
          <button class="btn-queue" onclick="addToQueue({i}, '{html.escape(it['title'])}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add to Commute Queue
          </button>
          <button class="btn-dismiss" onclick="dismissItem({i})">Dismiss</button>
        </div>
      </div>
"""

mock2_html += """
    </div>

    <!-- Floating Commute Queue Action -->
    <div class="commute-bar" onclick="startCommutePlayback()">
      <div>
        <div class="commute-title">▶ Play Commute Queue</div>
        <div class="commute-sub" id="commuteCountText">3 items queued · 38m total audio</div>
      </div>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
    </div>

    <!-- Tab Bar -->
    <div class="tab-bar">
      <div class="tab-item active">Triage</div>
      <div class="tab-item">Channels</div>
      <div class="tab-item">Settings</div>
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    let queueCount = 3;
    function addToQueue(idx, title) {
      queueCount++;
      document.getElementById('queueBadge').innerText = queueCount;
      document.getElementById('commuteCountText').innerText = queueCount + ' items queued · ' + (queueCount * 12) + 'm audio';
      const card = document.getElementById('t-card-' + idx);
      card.style.transform = 'translateX(100px)';
      card.style.opacity = '0';
      setTimeout(() => card.style.display = 'none', 200);
    }
    function dismissItem(idx) {
      const card = document.getElementById('t-card-' + idx);
      card.style.opacity = '0';
      setTimeout(() => card.style.display = 'none', 150);
    }
    function startCommutePlayback() {
      alert('Commute playback started: Continuous queue audio streaming through headphones.');
    }
    function setTab(el, type) {
      document.querySelectorAll('.triage-tab').forEach(t => t.classList.remove('active'));
      el.classList.add('active');
    }
  </script>
</body>
</html>
"""

with open(".workflow/mocks/mock2_commute_triage.html", "w", encoding="utf-8") as f:
    f.write(mock2_html)
print("Wrote mock2_commute_triage.html")

# -------------------------------------------------------------
# MOCK 3: The Minimalist Reader (Matter & Instapaper)
# -------------------------------------------------------------
mock3_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - Minimalist Reader</title>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }}
    :root {{
      --bg: #000000;
      --card: #121212;
      --text: #f4f4f0;
      --text-muted: #888884;
      --border: rgba(255, 255, 255, 0.08);
      --accent: #e2e8f0;
    }}
    body {{
      background: #000; color: var(--text); font-family: "Newsreader", Georgia, serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
    }}
    .phone {{
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }}
    .status-bar {{
      height: 48px; padding: 12px 24px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 13px; font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif; font-weight: 500;
      color: var(--text-muted); flex-shrink: 0;
    }}
    .header {{
      padding: 16px 24px 12px; display: flex; justify-content: space-between; align-items: baseline;
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }}
    .brand {{ font-size: 20px; font-weight: 600; letter-spacing: -0.5px; }}
    .font-switch {{
      font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif; font-size: 12px; font-weight: 600;
      color: var(--text-muted); background: var(--card); padding: 4px 10px; border-radius: 14px; border: 1px solid var(--border);
      cursor: pointer;
    }}
    .feed {{
      flex: 1; overflow-y: auto; padding: 20px 24px 120px; -webkit-overflow-scrolling: touch;
    }}
    .feed::-webkit-scrollbar {{ display: none; }}

    .article-item {{
      margin-bottom: 32px; border-bottom: 1px solid var(--border); padding-bottom: 24px;
    }}
    .article-meta {{
      font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif; font-size: 12px;
      color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px;
    }}
    .article-title {{
      font-size: 21px; font-weight: 500; line-height: 1.35; margin-bottom: 10px; color: #fff;
    }}
    .article-excerpt {{
      font-size: 16px; line-height: 1.65; color: #b8b8b0; margin-bottom: 14px;
    }}
    .article-footer {{
      display: flex; justify-content: space-between; align-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif; font-size: 12px; color: var(--text-muted);
    }}
    .read-time {{ display: flex; align-items: center; gap: 4px; }}
    .btn-listen {{
      background: transparent; border: 1px solid var(--border); color: #fff; padding: 4px 12px; border-radius: 14px;
      cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 12px;
    }}

    /* Minimal Floating Audio Pill */
    .minimal-player {{
      position: absolute; bottom: 34px; left: 50%; transform: translateX(-50%);
      background: rgba(24, 24, 24, 0.92); backdrop-filter: blur(16px);
      border: 1px solid rgba(255,255,255,0.12); border-radius: 30px; padding: 8px 18px;
      display: flex; align-items: center; gap: 14px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
      font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif; font-size: 12px; font-weight: 500;
      z-index: 50;
    }}
    .home-bar {{
      position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
      width: 136px; height: 4.5px; background: rgba(255,255,255,0.2); border-radius: 10px; pointer-events: none;
    }}
  </style>
</head>
<body>
  <div class="phone" id="phoneContainer">
    <div class="status-bar">
      <span>9:41</span>
      <span>TubeLM</span>
      <span>100%</span>
    </div>

    <div class="header">
      <div class="brand">TubeLM Digest</div>
      <button class="font-switch" onclick="toggleTypography()">Serif / Sans</button>
    </div>

    <div class="feed">
"""

for it in top20[:12]:
    mock3_html += f"""
      <div class="article-item">
        <div class="article-meta">{html.escape(it['source_name'])} · #{it['rank']} Priority</div>
        <div class="article-title">{html.escape(it['title'])}</div>
        <div class="article-excerpt">{html.escape(it['why_it_matters'])}</div>
        <div class="article-footer">
          <div class="read-time">3 min read · {it['duration']}</div>
          <button class="btn-listen" onclick="listenNow('{html.escape(it['title'])}')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Listen
          </button>
        </div>
      </div>
"""

mock3_html += """
    </div>

    <div class="minimal-player" id="minPlayer">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      <span id="minPlayerTitle">Playing Overview · 14m</span>
      <span style="opacity:0.6; font-size:11px;">1.5×</span>
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    let isSans = false;
    function toggleTypography() {
      isSans = !isSans;
      document.body.style.fontFamily = isSans ? '-apple-system, BlinkMacSystemFont, "Inter", sans-serif' : '"Newsreader", Georgia, serif';
    }
    function listenNow(title) {
      document.getElementById('minPlayerTitle').innerText = title.substring(0, 24) + '…';
    }
  </script>
</body>
</html>
"""

with open(".workflow/mocks/mock3_minimalist_reader.html", "w", encoding="utf-8") as f:
    f.write(mock3_html)
print("Wrote mock3_minimalist_reader.html")

# -------------------------------------------------------------
# MOCK 4: Bento Pulse & Channels (Linear & iOS 18 Control Center)
# -------------------------------------------------------------
mock4_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - Bento Pulse</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }}
    :root {{
      --bg: #0d0e12;
      --card: #15171e;
      --card-highlight: #1c1f28;
      --border: rgba(255, 255, 255, 0.08);
      --accent: #10b981;
      --lime: #d9ff63;
      --text: #f9fafb;
      --text-muted: #9ca3af;
    }}
    body {{
      background: #000; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
    }}
    .phone {{
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }}
    .status-bar {{
      height: 48px; padding: 12px 24px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; flex-shrink: 0;
    }}
    .header {{
      padding: 10px 18px 12px; display: flex; justify-content: space-between; align-items: center;
      flex-shrink: 0;
    }}
    .header-logo {{ font-size: 20px; font-weight: 900; letter-spacing: -0.5px; display: flex; align-items: center; gap: 8px; }}
    .logo-badge {{ background: var(--lime); color: #000; padding: 2px 6px; border-radius: 6px; font-size: 11px; }}

    .feed {{ flex: 1; overflow-y: auto; padding: 4px 16px 120px; }}
    .feed::-webkit-scrollbar {{ display: none; }}

    /* Bento Grid */
    .bento-grid {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px;
    }}
    .bento-card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 18px; padding: 14px;
      display: flex; flex-direction: column; justify-content: space-between;
    }}
    .bento-hero {{
      grid-column: span 2; background: linear-gradient(135deg, #15171e 0%, #1a221f 100%);
      border: 1px solid rgba(16, 185, 129, 0.25);
    }}
    .bento-hero-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
    .bento-hero-title {{ font-size: 15px; font-weight: 800; line-height: 1.3; margin-bottom: 4px; }}
    .bento-hero-desc {{ font-size: 12px; color: var(--text-muted); line-height: 1.4; }}
    .bento-stat-num {{ font-size: 24px; font-weight: 900; color: var(--lime); }}
    .bento-stat-label {{ font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }}

    /* Category Chips */
    .cat-chips {{
      display: flex; gap: 8px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 8px;
    }}
    .cat-chips::-webkit-scrollbar {{ display: none; }}
    .chip {{
      padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 700; white-space: nowrap;
      background: var(--card); color: var(--text-muted); border: 1px solid var(--border); cursor: pointer;
    }}
    .chip.active {{ background: var(--text); color: #000; border-color: var(--text); }}

    /* Streamlined Cards */
    .pulse-card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 14px;
      padding: 12px 14px; margin-bottom: 10px; display: flex; gap: 12px; align-items: flex-start;
    }}
    .pulse-rank {{
      width: 28px; height: 28px; border-radius: 8px; background: var(--card-highlight);
      display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800;
      color: var(--lime); flex-shrink: 0;
    }}
    .pulse-content {{ flex: 1; min-width: 0; }}
    .pulse-source {{ font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }}
    .pulse-title {{ font-size: 14px; font-weight: 700; line-height: 1.3; margin: 2px 0 4px; }}
    .pulse-desc {{ font-size: 12px; color: #94a3b8; line-height: 1.4; }}

    .tab-bar {{
      position: absolute; bottom: 0; left: 0; right: 0; height: 64px; background: rgba(13, 14, 18, 0.96);
      border-top: 1px solid var(--border); display: flex; justify-content: space-around; align-items: center;
      padding-bottom: 12px; z-index: 55;
    }}
    .tab-item {{ font-size: 11px; font-weight: 600; color: var(--text-muted); }}
    .tab-item.active {{ color: var(--lime); }}
    .home-bar {{
      position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
      width: 136px; height: 4.5px; background: rgba(255,255,255,0.3); border-radius: 10px; pointer-events: none;
    }}
  </style>
</head>
<body>
  <div class="phone">
    <div class="status-bar">
      <span>9:41</span>
      <span>Pulse</span>
      <span>100%</span>
    </div>

    <div class="header">
      <div class="header-logo">
        TubeLM <span class="logo-badge">iOS</span>
      </div>
      <div style="font-size:12px; color:var(--text-muted); font-weight:600;">{run_date}</div>
    </div>

    <div class="feed">
      <!-- Bento Grid -->
      <div class="bento-grid">
        <div class="bento-card bento-hero">
          <div class="bento-hero-top">
            <span style="font-size:11px; font-weight:800; color:var(--lime); text-transform:uppercase;">#1 Must-Watch Breakthrough</span>
            <span style="font-size:11px; background:rgba(0,0,0,0.4); padding:2px 8px; border-radius:10px;">{top10[0]['duration']}</span>
          </div>
          <div class="bento-hero-title">{html.escape(top10[0]['title'])}</div>
          <div class="bento-hero-desc">{html.escape(top10[0]['why_it_matters'][:110])}…</div>
        </div>

        <div class="bento-card">
          <div class="bento-stat-num">20</div>
          <div class="bento-stat-label">Executive Briefs</div>
        </div>

        <div class="bento-card">
          <div class="bento-stat-num">1h 42m</div>
          <div class="bento-stat-label">Audio Downloaded</div>
        </div>
      </div>

      <!-- Categories -->
      <div class="cat-chips">
        <div class="chip active" onclick="filterCat(this, 'all')">All Briefs</div>
        <div class="chip" onclick="filterCat(this, 'tech')">Tech & AI</div>
        <div class="chip" onclick="filterCat(this, 'health')">Health & Bio</div>
        <div class="chip" onclick="filterCat(this, 'deep_explainer')">Science & Deep</div>
      </div>

      <!-- Pulse Cards -->
"""

for it in top20:
    mock4_html += f"""
      <div class="pulse-card">
        <div class="pulse-rank">{it['rank']}</div>
        <div class="pulse-content">
          <div class="pulse-source">{html.escape(it['source_name'])} · {it['duration']}</div>
          <div class="pulse-title">{html.escape(it['title'])}</div>
          <div class="pulse-desc">{html.escape(it['why_it_matters'])}</div>
        </div>
      </div>
"""

mock4_html += """
    </div>

    <div class="tab-bar">
      <div class="tab-item active">Pulse</div>
      <div class="tab-item">Channels</div>
      <div class="tab-item">Audio Deck</div>
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    function filterCat(el, cat) {
      document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      el.classList.add('active');
    }
  </script>
</body>
</html>
"""

with open(".workflow/mocks/mock4_bento_pulse.html", "w", encoding="utf-8") as f:
    f.write(mock4_html)
print("Wrote mock4_bento_pulse.html")

# -------------------------------------------------------------
# MOCK 5: Audio-First Commuter Deck (Curio & Spotify Podcast)
# -------------------------------------------------------------
mock5_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - Audio-First Commuter Deck</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }}
    :root {{
      --bg: #0c0a09;
      --card: #1c1917;
      --border: rgba(245, 158, 11, 0.15);
      --amber: #f59e0b;
      --orange: #f97316;
      --text: #fafaf9;
      --text-muted: #a8a29e;
    }}
    body {{
      background: #000; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
    }}
    .phone {{
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }}
    .status-bar {{
      height: 48px; padding: 12px 24px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; flex-shrink: 0;
    }}
    
    /* Top Audio Deck */
    .audio-hero {{
      padding: 16px 20px 20px; background: linear-gradient(180deg, #1c1917 0%, #0c0a09 100%);
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }}
    .audio-badge {{
      display: inline-flex; align-items: center; gap: 6px; background: rgba(245, 158, 11, 0.15);
      color: var(--amber); padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;
      text-transform: uppercase; margin-bottom: 8px;
    }}
    .track-title {{ font-size: 18px; font-weight: 800; line-height: 1.3; margin-bottom: 4px; }}
    .track-sub {{ font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }}

    /* Scrubber */
    .scrubber-container {{ margin-bottom: 12px; }}
    .progress-track {{
      height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; position: relative; cursor: pointer;
    }}
    .progress-fill {{ width: 35%; height: 100%; background: var(--amber); border-radius: 3px; }}
    .time-row {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-top: 6px; }}

    /* Large Ergonomic Touch Controls */
    .deck-controls {{
      display: flex; justify-content: space-between; align-items: center; padding: 0 16px;
    }}
    .ctrl-skip {{
      background: none; border: none; color: var(--text); cursor: pointer; display: flex; flex-direction: column;
      align-items: center; font-size: 11px; font-weight: 700; gap: 2px;
    }}
    .ctrl-play {{
      width: 62px; height: 62px; border-radius: 50%; background: var(--amber); color: #000;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
      box-shadow: 0 8px 20px rgba(245, 158, 11, 0.35);
    }}

    /* Synchronized Takeaways Feed */
    .feed {{ flex: 1; overflow-y: auto; padding: 16px; -webkit-overflow-scrolling: touch; }}
    .feed::-webkit-scrollbar {{ display: none; }}
    .feed-header {{ font-size: 12px; font-weight: 800; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px; letter-spacing: 0.8px; }}

    .chapter-card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 14px;
      padding: 12px 14px; margin-bottom: 10px; transition: all 0.2s;
    }}
    .chapter-card.active {{
      border-color: var(--amber); background: rgba(245, 158, 11, 0.08);
    }}
    .chapter-top {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--amber); font-weight: 700; margin-bottom: 4px; }}
    .chapter-title {{ font-size: 14px; font-weight: 700; margin-bottom: 4px; }}
    .chapter-body {{ font-size: 12px; color: #d6d3d1; line-height: 1.4; }}

    .home-bar {{
      position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
      width: 136px; height: 4.5px; background: rgba(255,255,255,0.3); border-radius: 10px; pointer-events: none;
    }}
  </style>
</head>
<body>
  <div class="phone">
    <div class="status-bar">
      <span>9:41</span>
      <span style="color:var(--amber); font-weight:700;">Headphones Connected</span>
      <span>100%</span>
    </div>

    <!-- Audio Hero Deck -->
    <div class="audio-hero">
      <div class="audio-badge">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>
        Week of {run_date} · Offline Cached
      </div>
      <div class="track-title" id="trackTitle">Top 20 Executive Overview</div>
      <div class="track-sub" id="trackSub">Chapter 1 of 20: {html.escape(top10[0]['title'])}</div>

      <!-- Scrubber -->
      <div class="scrubber-container">
        <div class="progress-track" onclick="seekAudio(event)">
          <div class="progress-fill" id="progressFill"></div>
        </div>
        <div class="time-row">
          <span id="curTime">05:12</span>
          <span>14:48</span>
        </div>
      </div>

      <!-- 56pt Large Ergonomic Controls -->
      <div class="deck-controls">
        <button class="ctrl-skip" onclick="skip(-15)">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5"/></svg>
          -15s
        </button>

        <button class="ctrl-play" onclick="togglePlay(this)">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
        </button>

        <button class="ctrl-skip" onclick="skip(15)">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg>
          +15s
        </button>

        <button class="ctrl-skip" onclick="cycleSpeed(this)">
          <span style="font-size:14px; font-weight:800;" id="speedLabel">1.25×</span>
          Speed
        </button>
      </div>
    </div>

    <!-- Synchronized Live Takeaways -->
    <div class="feed">
      <div class="feed-header">Synchronized Key Chapters</div>
"""

for i, it in enumerate(top10):
    active_cls = " active" if i == 0 else ""
    mock5_html += f"""
      <div class="chapter-card{active_cls}" onclick="selectChapter({i}, '{html.escape(it['title'])}')">
        <div class="chapter-top">
          <span>CHAPTER {i+1} · {it['duration']}</span>
          <span>{html.escape(it['source_name'])}</span>
        </div>
        <div class="chapter-title">{html.escape(it['title'])}</div>
        <div class="chapter-body">{html.escape(it['why_it_matters'])}</div>
      </div>
"""

mock5_html += """
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    let isPlaying = true;
    function togglePlay(btn) {
      isPlaying = !isPlaying;
      btn.innerHTML = isPlaying 
        ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
        : '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    }
    function skip(sec) {
      alert('Skipped ' + sec + ' seconds');
    }
    function cycleSpeed(btn) {
      const speeds = ['1.0×', '1.25×', '1.5×', '2.0×'];
      let lbl = document.getElementById('speedLabel');
      let idx = (speeds.indexOf(lbl.innerText) + 1) % speeds.length;
      lbl.innerText = speeds[idx];
    }
    function selectChapter(idx, title) {
      document.querySelectorAll('.chapter-card').forEach((c, i) => {
        c.classList.toggle('active', i === idx);
      });
      document.getElementById('trackSub').innerText = 'Chapter ' + (idx + 1) + ' of 20: ' + title;
    }
  </script>
</body>
</html>
"""

with open(".workflow/mocks/mock5_audio_first_deck.html", "w", encoding="utf-8") as f:
    f.write(mock5_html)
print("Wrote mock5_audio_first_deck.html")

# -------------------------------------------------------------
# MASTER GALLERY INDEX: Interactive Switcher & Rating Scorecard
# -------------------------------------------------------------
gallery_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TubeLM iOS - 5 UI Archetype Mocks & Evaluation</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #08090b; color: #f1f5f9; font-family: 'Inter', -apple-system, sans-serif;
      min-height: 100vh; display: flex; flex-direction: column;
    }
    header {
      background: #0f1117; border-bottom: 1px solid rgba(255,255,255,0.08);
      padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-pill {
      background: #d9ff63; color: #111; font-weight: 900; font-size: 12px; padding: 4px 8px; border-radius: 6px;
    }
    .brand-title { font-size: 18px; font-weight: 800; letter-spacing: -0.3px; }
    .brand-sub { font-size: 12px; color: #94a3b8; }

    /* Mock Switcher Tabs */
    .mock-nav {
      display: flex; gap: 8px; overflow-x: auto; padding: 4px; background: #161922; border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.06);
    }
    .nav-btn {
      background: transparent; border: none; color: #94a3b8; padding: 8px 16px; border-radius: 8px;
      font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.15s; white-space: nowrap;
    }
    .nav-btn:hover { color: #fff; }
    .nav-btn.active { background: #d9ff63; color: #0f1117; }

    /* Main Layout */
    .main-container {
      flex: 1; display: grid; grid-template-columns: 480px 1fr; gap: 24px; padding: 24px; max-width: 1600px;
      margin: 0 auto; width: 100%;
    }
    @media (max-width: 1080px) {
      .main-container { grid-template-columns: 1fr; }
    }

    /* iPhone 16 Pro Realistic Frame */
    .phone-stage {
      display: flex; justify-content: center; align-items: flex-start;
    }
    .iphone-frame {
      width: 412px; height: 852px; background: #000; border-radius: 54px;
      box-shadow: 0 0 0 12px #26272b, 0 0 0 14px #1a1a1c, 0 30px 80px rgba(0,0,0,0.8);
      position: relative; overflow: hidden; border: 4px solid #000;
    }
    iframe {
      width: 100%; height: 100%; border: none; background: #000;
    }

    /* Scorecard & Analysis Panel */
    .panel {
      background: #0f1117; border: 1px solid rgba(255,255,255,0.08); border-radius: 20px;
      padding: 24px; display: flex; flex-direction: column; gap: 20px;
    }
    .panel-header { display: flex; justify-content: space-between; align-items: flex-start; }
    .mock-title { font-size: 22px; font-weight: 800; margin-bottom: 4px; }
    .mock-inspiration { font-size: 13px; color: #38bdf8; font-weight: 600; }
    .overall-score {
      font-size: 32px; font-weight: 900; color: #d9ff63; background: rgba(217, 255, 99, 0.1);
      padding: 6px 16px; border-radius: 12px; border: 1px solid rgba(217, 255, 99, 0.2);
    }

    .criteria-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
    }
    .crit-item {
      background: #161922; border: 1px solid rgba(255,255,255,0.04); border-radius: 12px; padding: 12px 14px;
    }
    .crit-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 4px; }
    .crit-val { font-size: 16px; font-weight: 800; color: #f1f5f9; display: flex; justify-content: space-between; }
    .crit-score { color: #d9ff63; font-family: 'JetBrains Mono', monospace; }

    .analysis-box {
      background: #161922; border-radius: 14px; padding: 16px; font-size: 14px; line-height: 1.6; color: #cbd5e1;
    }
    .analysis-box h4 { font-size: 13px; font-weight: 800; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px; }

    .btn-select-mock {
      background: #d9ff63; color: #11120f; font-size: 15px; font-weight: 800; padding: 14px 20px;
      border-radius: 12px; border: none; cursor: pointer; transition: all 0.15s; text-align: center;
      box-shadow: 0 4px 20px rgba(217, 255, 99, 0.25);
    }
    .btn-select-mock:hover { background: #e4ff8c; transform: translateY(-1px); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-pill">TubeLM iOS</div>
      <div>
        <div class="brand-title">UI/UX Pro Max Archetype Gallery</div>
        <div class="brand-sub">Native iOS Experience for LiveContainer · Commute Optimized</div>
      </div>
    </div>
    <div class="mock-nav">
      <button class="nav-btn active" onclick="loadMock(1)">1. Executive Briefing</button>
      <button class="nav-btn" onclick="loadMock(2)">2. Commute Triage</button>
      <button class="nav-btn" onclick="loadMock(3)">3. Minimalist Reader</button>
      <button class="nav-btn" onclick="loadMock(4)">4. Bento Pulse</button>
      <button class="nav-btn" onclick="loadMock(5)">5. Audio-First Deck</button>
    </div>
  </header>

  <div class="main-container">
    <!-- iPhone Viewport -->
    <div class="phone-stage">
      <div class="iphone-frame">
        <iframe id="mockFrame" src="mock1_executive_briefing.html"></iframe>
      </div>
    </div>

    <!-- Rating & Deep Review Panel -->
    <div class="panel" id="reviewPanel">
      <!-- Injected via JavaScript -->
    </div>
  </div>

  <script>
    const MOCK_REVIEWS = {
      1: {
        title: "Mock 1: The Executive Briefing",
        inspiration: "Inspired by Artifact & Apple News",
        overall: "9.5 / 10",
        tagline: "High-Signal Ranked Editorial Feed with Sticky Audio Dock",
        criteria: [
          { name: "Visual Hierarchy", score: "9.8/10", note: "Immediate clarity on #1 to #20 with 'Why It Matters'" },
          { name: "Commuter Ergonomics", score: "9.4/10", note: "Skimmable in 15s; sticky audio mini-player" },
          { name: "LiveContainer / Offline", score: "9.6/10", note: "Clean lightweight DOM; zero heavy dependencies" },
          { name: "Audio Integration", score: "9.3/10", note: "Persistent waveform scrubber + 1.25x speed" }
        ],
        strengths: [
          "Preserves the signature TubeLM brand identity (Obsidian + Lime #d9ff63).",
          "Separates 'Top 10 Must-Watch' from 'Next 10 Notable' perfectly.",
          "Features a prominent 'Why It Matters' box on every card for fast subway glances.",
          "Sticky mini-player stays accessible anywhere in the feed without covering content."
        ],
        drawbacks: [
          "Slightly longer vertical scroll than Mock 4's compact bento grid."
        ],
        verdict: "RECOMMENDED ARCHETYPE. Hits the exact sweet spot of editorial authority, subway glanceability, and seamless audio playback."
      },
      2: {
        title: "Mock 2: Commute Triage & Queue",
        inspiration: "Inspired by Castro Podcast & Readwise Reader",
        overall: "9.2 / 10",
        tagline: "Action-Oriented Inbox Triage with Dedicated Commute Queue",
        criteria: [
          { name: "One-Handed Ergonomics", score: "9.9/10", note: "Large thumb buttons in bottom reach zone" },
          { name: "Commuter Workflow", score: "9.5/10", note: "Stage only what you want to hear on the train" },
          { name: "Visual Polish", score: "8.8/10", note: "Functional utility aesthetic" },
          { name: "Audio Flow", score: "9.4/10", note: "Continuous queue playback" }
        ],
        strengths: [
          "Superb one-handed thumb reachability; perfect for standing on a crowded subway holding a handrail.",
          "Stage 3-4 items into your Commute Queue with one tap, then hit Play All.",
          "Dismiss read items effortlessly."
        ],
        drawbacks: [
          "Requires active triaging before you hit play, rather than just scrolling a pre-ranked list."
        ],
        verdict: "Outstanding for power users who want an episode-style queue rather than a passive feed."
      },
      3: {
        title: "Mock 3: The Minimalist Reader",
        inspiration: "Inspired by Matter & Instapaper",
        overall: "8.9 / 10",
        tagline: "Pure Swiss Typography & OLED Pitch Black",
        criteria: [
          { name: "Reading Comfort", score: "9.7/10", note: "Newsreader serif type with generous leading" },
          { name: "Battery & OLED", score: "9.8/10", note: "True #000000 black saves battery during commute" },
          { name: "Information Density", score: "8.2/10", note: "Spacious layout; fewer items per screen" },
          { name: "Audio Integration", score: "8.6/10", note: "Subtle floating pill audio bar" }
        ],
        strengths: [
          "Distraction-free reading experience that feels like a luxury physical book.",
          "True black OLED background is easy on eyes during early morning or late night commutes.",
          "Dynamic serif / sans-serif toggle."
        ],
        drawbacks: [
          "Lower visual signal density; audio player is minimalist and lacks deep chapter scrubbing."
        ],
        verdict: "Best for deep readers who prioritize peaceful reading typography over dashboard density."
      },
      4: {
        title: "Mock 4: Bento Pulse & Channels",
        inspiration: "Inspired by Linear Mobile & iOS 18 Control Center",
        overall: "9.1 / 10",
        tagline: "Bento Grid Intelligence Dashboard & Category Segments",
        criteria: [
          { name: "Glanceability", score: "9.6/10", note: "Weekly stats + #1 Hero tile in the first viewport" },
          { name: "Category Filtering", score: "9.5/10", note: "Quick chips for Tech, Health, Deep Explainer" },
          { name: "One-Handed Flow", score: "8.7/10", note: "Multiple interactive elements at the top" },
          { name: "Visual Modernity", score: "9.5/10", note: "Futuristic iOS 18 titanium aesthetic" }
        ],
        strengths: [
          "Displays high-level intelligence stats (1h 42m audio, 20 items) instantly.",
          "Great category filtering to jump straight to Tech or Health summaries.",
          "Compact card layout lets you see 3 cards at once."
        ],
        drawbacks: [
          "Bento tiles take up prime top-screen real estate on smaller phones."
        ],
        verdict: "Ideal if you love dashboard-style glanceability and category segmentation."
      },
      5: {
        title: "Mock 5: Audio-First Commuter Deck",
        inspiration: "Inspired by Curio, Pocket & Spotify Podcasts",
        overall: "9.3 / 10",
        tagline: "Audio as Primary Modality with Synchronized Key Takeaways",
        criteria: [
          { name: "Hands-Free Transit", score: "9.9/10", note: "Giant 56pt buttons, walking/subway optimized" },
          { name: "Audio Controls", score: "9.8/10", note: "15s skip, chapter scrubber, speed pills" },
          { name: "Text Accompanying", score: "8.8/10", note: "Bullets scroll in sync with playback" },
          { name: "Information Density", score: "8.7/10", note: "Focus is on current playing track" }
        ],
        strengths: [
          "Designed specifically for when you cannot read text (walking to transit or packed subway cars).",
          "Giant touch targets can be operated without looking at the screen.",
          "Synchronized chapter takeaways follow along with the audio narration."
        ],
        drawbacks: [
          "Less suitable if you want to quickly skim read text without listening to audio."
        ],
        verdict: "The absolute best choice if audio overviews are your #1 way of consuming TubeLM during commutes."
      }
    };

    function renderReview(id) {
      const r = MOCK_REVIEWS[id];
      const panel = document.getElementById('reviewPanel');
      panel.innerHTML = `
        <div class="panel-header">
          <div>
            <div class="mock-title">${r.title}</div>
            <div class="mock-inspiration">${r.inspiration}</div>
            <div style="font-size:14px; color:#94a3b8; margin-top:4px;">${r.tagline}</div>
          </div>
          <div class="overall-score">${r.overall}</div>
        </div>

        <div class="criteria-grid">
          ${r.criteria.map(c => `
            <div class="crit-item">
              <div class="crit-label">${c.name}</div>
              <div class="crit-val">
                <span>${c.note}</span>
                <span class="crit-score">${c.score}</span>
              </div>
            </div>
          `).join('')}
        </div>

        <div class="analysis-box">
          <h4>Key Strengths</h4>
          <ul style="margin-left:18px; margin-bottom:12px;">
            ${r.strengths.map(s => `<li>${s}</li>`).join('')}
          </ul>
          <h4>Considerations / Trade-offs</h4>
          <ul style="margin-left:18px;">
            ${r.drawbacks.map(d => `<li>${d}</li>`).join('')}
          </ul>
        </div>

        <div style="background:rgba(217,255,99,0.06); border-left:3px solid #d9ff63; padding:12px 16px; border-radius:0 8px 8px 0; font-size:13px; color:#e2e8f0;">
          <strong>Verdict:</strong> ${r.verdict}
        </div>

        <button class="btn-select-mock" onclick="selectMock(${id})">
          Select ${r.title} for Development
        </button>
      `;
    }

    function loadMock(id) {
      document.querySelectorAll('.nav-btn').forEach((btn, idx) => {
        btn.classList.toggle('active', idx + 1 === id);
      });
      const frame = document.getElementById('mockFrame');
      const mockFiles = {
        1: 'mock1_executive_briefing.html',
        2: 'mock2_commute_triage.html',
        3: 'mock3_minimalist_reader.html',
        4: 'mock4_bento_pulse.html',
        5: 'mock5_audio_first_deck.html'
      };
      frame.src = mockFiles[id];
      renderReview(id);
    }

    function selectMock(id) {
      alert('Selected ' + MOCK_REVIEWS[id].title + '! Inform the agent in chat to lock this archetype for implementation.');
    }

    // Initialize with Mock 1
    renderReview(1);
  </script>
</body>
</html>
"""

with open(".workflow/mocks/index.html", "w", encoding="utf-8") as f:
    f.write(gallery_html)
print("Wrote gallery index.html successfully.")
