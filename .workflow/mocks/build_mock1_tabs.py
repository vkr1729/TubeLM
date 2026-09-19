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

categories = {
    "all": channels,
    "tech": [c for c in channels if c.get("category") == "tech"],
    "health": [c for c in channels if c.get("category") == "health"],
    "deep_explainer": [c for c in channels if c.get("category") in ("deep_explainer", "science")]
}

# Build Briefing HTML cards
top10_cards_html = ""
for it in top10:
    top10_cards_html += f"""
        <div class="card" id="card-{it['rank']}">
          <div class="card-top">
            <div class="rank-pill">#{it['rank']} Priority</div>
            <div class="meta-line">
              <span>{html.escape(it.get('source_name', ''))}</span> · <span>{it.get('duration', '14m')}</span>
            </div>
          </div>
          <div class="card-title">{html.escape(it.get('title', ''))}</div>
          <div class="why-box">
            <div class="why-label">Why It Matters</div>
            <div class="why-text">{html.escape(it.get('why_it_matters', ''))}</div>
          </div>
          <div class="card-actions">
            <button class="btn-audio" onclick="playAudio('{html.escape(it.get('title', ''))}', '{html.escape(it.get('source_name', ''))}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Play Overview
            </button>
            <div class="action-icons">
              <button class="action-btn" id="btn-save-{it['rank']}" onclick="toggleSaveItem({it['rank']}, '{html.escape(it.get('title', ''))}', '{html.escape(it.get('source_name', ''))}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                Save
              </button>
              <button class="action-btn" onclick="toggleRead({it['rank']})">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
                Read
              </button>
            </div>
          </div>
        </div>
"""

next10_cards_html = ""
for it in next10:
    next10_cards_html += f"""
        <div class="card" id="card-{it['rank']}">
          <div class="card-top">
            <span style="font-size:12px; font-weight:800; color:var(--text-muted);">#{it['rank']}</span>
            <div class="meta-line">
              <span>{html.escape(it.get('source_name', ''))}</span> · <span>{it.get('duration', '12m')}</span>
            </div>
          </div>
          <div class="card-title" style="font-size:15px;">{html.escape(it.get('title', ''))}</div>
          <div style="font-size:13px; color:var(--text-muted); line-height:1.45; margin-bottom:12px;">
            {html.escape(it.get('why_it_matters', ''))}
          </div>
          <div class="card-actions">
            <button class="btn-audio" style="padding:5px 12px; font-size:11px;" onclick="playAudio('{html.escape(it.get('title', ''))}', '{html.escape(it.get('source_name', ''))}')">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Audio
            </button>
            <div class="action-icons">
              <button class="action-btn" id="btn-save-{it['rank']}" onclick="toggleSaveItem({it['rank']}, '{html.escape(it.get('title', ''))}', '{html.escape(it.get('source_name', ''))}')">Save</button>
              <button class="action-btn" onclick="toggleRead({it['rank']})">Read</button>
            </div>
          </div>
        </div>
"""

# Build Channels HTML cards
channels_cards_html = ""
for ch in channels:
    initials = "".join([w[0].upper() for w in ch.get('name', 'CH').split()[:2]])
    preview = ch.get('summary_preview') or (ch.get('summary_text') or '')[:140] + "…"
    cat = ch.get('category', 'tech')
    channels_cards_html += f"""
          <div class="channel-card" data-category="{cat}" data-name="{html.escape(ch.get('name', '').lower())}">
            <div class="ch-top">
              <div class="ch-avatar">{initials}</div>
              <div class="ch-meta">
                <div class="ch-name">{html.escape(ch.get('name', ''))}</div>
                <div class="ch-subline">
                  <span style="font-weight:700; text-transform:uppercase; color:var(--accent); font-size:11px;">{cat}</span>
                  · <span>{ch.get('video_count', 1)} video{'s' if ch.get('video_count', 1) > 1 else ''}</span>
                  · <span>{ch.get('read_minutes', 3)}m read</span>
                </div>
              </div>
            </div>
            <div class="ch-preview">{html.escape(preview)}</div>
            <div class="ch-actions">
              <button class="btn-audio" onclick="playAudio('Channel Digest: {html.escape(ch.get('name', ''))}', '{html.escape(cat.upper())}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Listen Summary
              </button>
              <span style="font-size:11px; color:var(--text-muted); font-weight:600;">{ch.get('source_type', 'YouTube').upper()}</span>
            </div>
          </div>
"""

# Template
TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - The Executive Briefing</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,700;1,6..72,400&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }
    
    /* Dynamic Light (Default) / Dark Theming */
    :root[data-theme="light"] {
      --bg: #f8f9fa;
      --surface: #ffffff;
      --surface-elevated: #f1f5f9;
      --border: rgba(15, 23, 42, 0.08);
      --border-focus: rgba(34, 197, 94, 0.4);
      --text: #0f172a;
      --text-muted: #64748b;
      --text-subtle: #94a3b8;
      --accent: #15803d;
      --accent-badge: #d9ff63;
      --accent-badge-text: #171815;
      --accent-soft: rgba(21, 128, 61, 0.12);
      --why-bg: #f0fdf4;
      --why-border: #22c55e;
      --card-shadow: 0 4px 14px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.02);
      --player-bg: rgba(255, 255, 255, 0.94);
      --tab-bg: rgba(255, 255, 255, 0.96);
      --status-color: #0f172a;
    }

    :root[data-theme="dark"] {
      --bg: #0e0f12;
      --surface: #16181d;
      --surface-elevated: #1e2128;
      --border: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(217, 255, 99, 0.4);
      --text: #f5f6f8;
      --text-muted: #8b909a;
      --text-subtle: #64748b;
      --accent: #d9ff63;
      --accent-badge: #d9ff63;
      --accent-badge-text: #171815;
      --accent-soft: rgba(217, 255, 99, 0.14);
      --why-bg: rgba(217, 255, 99, 0.05);
      --why-border: #d9ff63;
      --card-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
      --player-bg: rgba(22, 24, 29, 0.94);
      --tab-bg: rgba(14, 15, 18, 0.96);
      --status-color: #f5f6f8;
    }

    body {
      background: #000; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
      transition: background-color 0.2s, color 0.2s;
    }

    .phone {
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }

    /* iOS Status Bar */
    .status-bar {
      height: 48px; padding: 12px 22px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; color: var(--status-color); flex-shrink: 0; z-index: 50; position: relative;
    }
    .island {
      position: absolute; left: 50%; top: 10px; transform: translateX(-50%); width: 124px; height: 32px;
      background: #000; border-radius: 20px; display: flex; align-items: center; justify-content: space-between;
      padding: 0 12px; cursor: pointer; transition: all 0.25s ease;
    }
    .island-dot { width: 8px; height: 8px; border-radius: 50%; background: #d9ff63; }
    .island-bars { display: flex; gap: 2px; align-items: flex-end; height: 12px; }
    .island-bars span { width: 2.5px; background: #d9ff63; border-radius: 1px; animation: eq 0.8s infinite ease-in-out; }
    .island-bars span:nth-child(2) { animation-delay: 0.2s; }
    .island-bars span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes eq { 0%, 100% { height: 3px; } 50% { height: 12px; } }

    /* Header */
    .header {
      padding: 10px 20px 14px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--border); flex-shrink: 0; background: var(--surface);
    }
    .header-left { display: flex; flex-direction: column; }
    .header-sub { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.2px; color: var(--accent); }
    .header-title { font-family: "Newsreader", serif; font-size: 24px; font-weight: 700; letter-spacing: -0.4px; line-height: 1.1; margin-top: 2px; }
    
    .header-actions { display: flex; align-items: center; gap: 8px; }
    .theme-toggle-btn {
      width: 36px; height: 36px; border-radius: 50%; background: var(--surface-elevated);
      border: 1px solid var(--border); color: var(--text); display: flex; align-items: center;
      justify-content: center; cursor: pointer; transition: transform 0.15s;
    }
    .theme-toggle-btn:active { transform: scale(0.92); }

    /* Main View Container */
    .view-content {
      flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; padding-bottom: 150px;
    }
    .view-content::-webkit-scrollbar { display: none; }

    /* TAB 1: BRIEFING FEED */
    .section-header {
      display: flex; align-items: center; justify-content: space-between; padding: 16px 18px 8px;
    }
    .section-title { font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
    .badge-count { background: var(--surface-elevated); color: var(--text); padding: 2px 7px; border-radius: 10px; font-size: 11px; }

    .card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
      padding: 16px 18px; margin: 0 16px 12px; box-shadow: var(--card-shadow); transition: all 0.2s ease;
      position: relative;
    }
    .card:active { transform: scale(0.985); }
    .card.read { opacity: 0.45; filter: grayscale(0.5); }
    .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .rank-pill {
      font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 6px; background: var(--accent-badge);
      color: var(--accent-badge-text); letter-spacing: 0.3px;
    }
    .meta-line { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted); font-weight: 600; }
    .card-title {
      font-size: 16px; font-weight: 700; line-height: 1.35; color: var(--text); margin-bottom: 10px;
    }
    .why-box {
      background: var(--why-bg); border-left: 3px solid var(--why-border);
      padding: 10px 12px; border-radius: 0 8px 8px 0; margin-bottom: 12px;
    }
    .why-label { font-size: 10px; font-weight: 800; text-transform: uppercase; color: var(--accent); letter-spacing: 0.6px; margin-bottom: 2px; }
    .why-text { font-size: 13px; line-height: 1.45; color: var(--text); }
    
    .card-actions {
      display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border);
      padding-top: 10px; font-size: 12px;
    }
    .btn-audio {
      display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft);
      color: var(--accent); font-weight: 700; padding: 6px 14px; border-radius: 20px; font-size: 12px; border: none; cursor: pointer;
    }
    .btn-audio:active { opacity: 0.8; }
    .action-icons { display: flex; gap: 10px; align-items: center; color: var(--text-muted); }
    .action-btn {
      background: var(--surface-elevated); border: 1px solid var(--border); color: inherit; padding: 6px 10px;
      border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600;
    }
    .action-btn.saved { background: var(--accent-badge); color: var(--accent-badge-text); border-color: var(--accent-badge); }

    /* TAB 2: CHANNELS VIEW */
    .channels-header { padding: 14px 16px 8px; display: flex; flex-direction: column; gap: 10px; }
    .search-box { position: relative; width: 100%; }
    .search-input {
      width: 100%; padding: 10px 14px 10px 36px; border-radius: 12px; border: 1px solid var(--border);
      background: var(--surface); color: var(--text); font-size: 14px; font-weight: 500; outline: none;
    }
    .search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }
    
    .cat-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 4px 0 10px; }
    .cat-scroll::-webkit-scrollbar { display: none; }
    .cat-pill {
      padding: 6px 14px; border-radius: 16px; font-size: 12px; font-weight: 700; white-space: nowrap;
      background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); cursor: pointer;
    }
    .cat-pill.active { background: var(--accent); color: #fff; border-color: var(--accent); }

    .channel-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      padding: 16px; margin: 0 16px 12px; box-shadow: var(--card-shadow);
    }
    .ch-top { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
    .ch-avatar {
      width: 44px; height: 44px; border-radius: 12px; background: var(--surface-elevated);
      color: var(--accent); font-weight: 900; font-size: 16px; display: flex; align-items: center; justify-content: center;
      border: 2px solid var(--border); flex-shrink: 0;
    }
    .ch-meta { flex: 1; min-width: 0; }
    .ch-name { font-size: 15px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .ch-subline { font-size: 12px; color: var(--text-muted); display: flex; gap: 6px; align-items: center; }
    .ch-preview { font-size: 13px; color: var(--text-muted); line-height: 1.45; margin-bottom: 12px; }
    .ch-actions { display: flex; justify-content: space-between; align-items: center; }

    /* TAB 3: SAVED & QUEUE */
    .queue-summary-banner {
      margin: 14px 16px 12px; background: linear-gradient(135deg, var(--accent) 0%, #15803d 100%);
      color: #fff; border-radius: 18px; padding: 18px; box-shadow: 0 8px 24px rgba(22, 163, 74, 0.25);
    }
    :root[data-theme="dark"] .queue-summary-banner {
      background: linear-gradient(135deg, #1c1f26 0%, #111317 100%);
      border: 1px solid var(--border); color: var(--text);
    }
    .q-banner-title { font-size: 18px; font-weight: 800; margin-bottom: 4px; }
    .q-banner-sub { font-size: 13px; opacity: 0.9; margin-bottom: 14px; }
    .btn-play-all {
      display: inline-flex; align-items: center; gap: 8px; background: #fff; color: #15803d;
      font-weight: 800; font-size: 13px; padding: 10px 18px; border-radius: 20px; border: none; cursor: pointer;
    }
    :root[data-theme="dark"] .btn-play-all { background: #d9ff63; color: #11120f; }

    .sync-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      padding: 14px 16px; margin: 0 16px 16px; display: flex; justify-content: space-between; align-items: center;
      box-shadow: var(--card-shadow);
    }
    .sync-title { font-size: 13px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 6px; }
    .sync-status-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }
    .sync-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

    /* Sticky Mini-Player */
    .mini-player {
      position: absolute; bottom: 70px; left: 12px; right: 12px; background: var(--player-bg);
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--border); border-radius: 18px; padding: 10px 14px;
      display: flex; align-items: center; justify-content: space-between; box-shadow: var(--card-shadow);
      z-index: 60;
    }
    .player-info { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
    .player-art {
      width: 38px; height: 38px; border-radius: 10px; background: var(--accent-badge); color: var(--accent-badge-text);
      font-weight: 900; font-size: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .player-titles { min-width: 0; }
    .player-title { font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
    .player-sub { font-size: 11px; color: var(--text-muted); }
    .player-controls { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
    .play-btn {
      width: 36px; height: 36px; border-radius: 50%; background: var(--accent); color: #fff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
    }
    :root[data-theme="dark"] .play-btn { background: #d9ff63; color: #11120f; }
    .speed-pill {
      font-size: 11px; font-weight: 800; background: var(--surface-elevated); padding: 4px 8px; border-radius: 6px;
      cursor: pointer; color: var(--text); border: 1px solid var(--border);
    }

    /* Bottom Tab Bar */
    .tab-bar {
      position: absolute; bottom: 0; left: 0; right: 0; height: 68px; background: var(--tab-bg);
      backdrop-filter: blur(20px); border-top: 1px solid var(--border);
      display: flex; justify-content: space-around; align-items: center; padding-bottom: 14px; z-index: 55;
    }
    .tab-item {
      display: flex; flex-direction: column; align-items: center; gap: 3px; font-size: 10px; font-weight: 700;
      color: var(--text-muted); cursor: pointer; flex: 1; padding: 6px 0; transition: color 0.15s;
    }
    .tab-item.active { color: var(--accent); }
    .tab-item svg { width: 22px; height: 22px; }

    .home-bar {
      position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
      width: 136px; height: 4.5px; background: rgba(0,0,0,0.3); border-radius: 10px; pointer-events: none; z-index: 70;
    }
    :root[data-theme="dark"] .home-bar { background: rgba(255,255,255,0.3); }
  </style>
</head>
<body>
  <div class="phone">
    <!-- Status Bar -->
    <div class="status-bar">
      <span>9:41</span>
      <div class="island" onclick="alert('LiveContainer: Native AVAudioPlayer session active.')">
        <div class="island-dot"></div>
        <div class="island-bars"><span></span><span></span><span></span></div>
      </div>
      <div style="display:flex; gap:6px; font-size:12px; font-weight:700;">5G 100%</div>
    </div>

    <!-- Header -->
    <div class="header">
      <div class="header-left">
        <div class="header-sub" id="headerSub">Executive Intelligence</div>
        <div class="header-title" id="headerTitle">Weekly Briefing</div>
      </div>
      <div class="header-actions">
        <button class="theme-toggle-btn" onclick="toggleTheme()" title="Toggle Light / Dark Mode">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" id="themeIcon">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
          </svg>
        </button>
      </div>
    </div>

    <!-- MAIN SCROLL CONTAINER -->
    <div class="view-content" id="mainContainer">
      
      <!-- TAB 1: BRIEFING CONTENT -->
      <div id="tab-briefing-view">
        <div class="section-header">
          <div class="section-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>
            Top 10 Must-Watch <span class="badge-count">10</span>
          </div>
          <span style="font-size:12px; color:var(--text-muted); font-weight:600;">Ranked Selection</span>
        </div>
        __TOP10_CARDS__

        <div class="section-header" style="margin-top:20px;">
          <div class="section-title">
            Next 10 Notable <span class="badge-count">10</span>
          </div>
          <span style="font-size:12px; color:var(--text-muted); font-weight:600;">High-Signal Fast Reads</span>
        </div>
        __NEXT10_CARDS__
      </div>

      <!-- TAB 2: CHANNELS VIEW -->
      <div id="tab-channels-view" style="display:none;">
        <div class="channels-header">
          <div class="search-box">
            <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="search-input" placeholder="Search 23 curated channels..." oninput="filterChannels(this.value)">
          </div>
          <div class="cat-scroll">
            <div class="cat-pill active" onclick="selectChannelCat(this, 'all')">All Channels (__TOTAL_CHANNELS__)</div>
            <div class="cat-pill" onclick="selectChannelCat(this, 'tech')">Tech & AI (__TECH_COUNT__)</div>
            <div class="cat-pill" onclick="selectChannelCat(this, 'health')">Health & Bio (__HEALTH_COUNT__)</div>
            <div class="cat-pill" onclick="selectChannelCat(this, 'deep_explainer')">Science & Deep (__DEEP_COUNT__)</div>
          </div>
        </div>

        <div id="channels-list">
          __CHANNELS_CARDS__
        </div>
      </div>

      <!-- TAB 3: BOOKMARKS / SAVED COMMUTE QUEUE -->
      <div id="tab-saved-view" style="display:none;">
        <div class="queue-summary-banner">
          <div class="q-banner-title">Commute Queue</div>
          <div class="q-banner-sub" id="queueSummaryText">3 items saved · 38m total audio · Offline ready</div>
          <button class="btn-play-all" onclick="playCommuteQueue()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Play Entire Queue
          </button>
        </div>

        <!-- Cloudflare Worker Sync Card -->
        <div class="sync-card">
          <div>
            <div class="sync-title">
              <div class="sync-status-dot"></div>
              Cloudflare Sync Active
            </div>
            <div class="sync-sub">Connected: tubelm-sync.workers.dev (Laptop ↔ App)</div>
          </div>
          <button class="action-btn" onclick="forceSync()" style="color:var(--accent); font-weight:700;">Sync Now</button>
        </div>

        <div style="padding:0 18px 8px; font-size:12px; font-weight:800; text-transform:uppercase; color:var(--text-muted);">
          Saved for Commute
        </div>

        <div id="saved-items-container">
          <div class="card" id="saved-card-1">
            <div class="card-top">
              <div class="rank-pill">#1 Saved</div>
              <div class="meta-line"><span>Physionic</span> · <span>14m</span></div>
            </div>
            <div class="card-title">Creatine & Cognition: Mechanisms in Sleep-Deprived Adults</div>
            <div class="why-box">
              <div class="why-label">Why It Matters</div>
              <div class="why-text">Rigorous double-blind trial demonstrating acute cognitive preservation under sleep deficits.</div>
            </div>
            <div class="card-actions">
              <button class="btn-audio" onclick="playAudio('Creatine & Cognition', 'Physionic')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Play Audio
              </button>
              <button class="action-btn" onclick="removeSaved(1)">Remove</button>
            </div>
          </div>

          <div class="card" id="saved-card-2">
            <div class="card-top">
              <div class="rank-pill">#2 Saved</div>
              <div class="meta-line"><span>Veritasium</span> · <span>22m</span></div>
            </div>
            <div class="card-title">The Real Reason Quantum Computers Might Never Break RSA</div>
            <div class="why-box">
              <div class="why-label">Why It Matters</div>
              <div class="why-text">In-depth physical error correction scaling analysis against post-quantum cryptographic standards.</div>
            </div>
            <div class="card-actions">
              <button class="btn-audio" onclick="playAudio('Quantum Computers RSA', 'Veritasium')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Play Audio
              </button>
              <button class="action-btn" onclick="removeSaved(2)">Remove</button>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- Sticky Mini-Player -->
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

    <!-- Bottom 3-Tab Bar -->
    <div class="tab-bar">
      <div class="tab-item active" id="nav-briefing" onclick="switchTab('briefing')">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
        Briefing
      </div>
      <div class="tab-item" id="nav-channels" onclick="switchTab('channels')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M4 6h16M4 12h16M4 18h7"/></svg>
        Channels
      </div>
      <div class="tab-item" id="nav-saved" onclick="switchTab('saved')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
        Saved
      </div>
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    let isPlaying = false;
    let currentTheme = 'light';
    let savedCount = 2;

    function toggleTheme() {
      currentTheme = (currentTheme === 'light') ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', currentTheme);
      const icon = document.getElementById('themeIcon');
      if (currentTheme === 'light') {
        icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
      } else {
        icon.innerHTML = '<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>';
      }
    }

    function switchTab(tab) {
      document.querySelectorAll('.tab-item').forEach(function(t) { t.classList.remove('active'); });
      document.getElementById('nav-' + tab).classList.add('active');

      document.getElementById('tab-briefing-view').style.display = (tab === 'briefing') ? 'block' : 'none';
      document.getElementById('tab-channels-view').style.display = (tab === 'channels') ? 'block' : 'none';
      document.getElementById('tab-saved-view').style.display = (tab === 'saved') ? 'block' : 'none';

      const titleEl = document.getElementById('headerTitle');
      const subEl = document.getElementById('headerSub');
      if (tab === 'briefing') {
        titleEl.innerText = 'Weekly Briefing';
        subEl.innerText = 'Executive Intelligence';
      } else if (tab === 'channels') {
        titleEl.innerText = 'Channels';
        subEl.innerText = '23 Curated Sources';
      } else if (tab === 'saved') {
        titleEl.innerText = 'Commute Queue';
        subEl.innerText = 'Saved & Pinned Items';
      }
      document.getElementById('mainContainer').scrollTop = 0;
    }

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

    function toggleSaveItem(rank, title, source) {
      const btn = document.getElementById('btn-save-' + rank);
      btn.classList.toggle('saved');
      if (btn.classList.contains('saved')) {
        btn.innerText = 'Saved';
        savedCount++;
      } else {
        btn.innerText = 'Save';
        savedCount--;
      }
      document.getElementById('queueSummaryText').innerText = savedCount + ' items saved · ' + (savedCount * 12) + 'm total audio · Offline ready';
    }

    function removeSaved(id) {
      const el = document.getElementById('saved-card-' + id);
      if (el) {
        el.style.opacity = '0';
        setTimeout(function() { el.remove(); }, 200);
        savedCount = Math.max(0, savedCount - 1);
        document.getElementById('queueSummaryText').innerText = savedCount + ' items saved · ' + (savedCount * 12) + 'm total audio · Offline ready';
      }
    }

    function filterChannels(q) {
      q = q.toLowerCase();
      document.querySelectorAll('.channel-card').forEach(function(card) {
        const name = card.getAttribute('data-name') || '';
        card.style.display = name.includes(q) ? 'block' : 'none';
      });
    }

    function selectChannelCat(el, cat) {
      document.querySelectorAll('.cat-pill').forEach(function(p) { p.classList.remove('active'); });
      el.classList.add('active');
      document.querySelectorAll('.channel-card').forEach(function(card) {
        const c = card.getAttribute('data-category');
        if (cat === 'all' || c === cat) card.style.display = 'block';
        else card.style.display = 'none';
      });
    }

    function playCommuteQueue() {
      playAudio('Playing Commute Queue', 'Continuous Playback');
    }

    function forceSync() {
      alert('Cloudflare Worker: State synced with tubelm-sync.workers.dev via Durable Object!');
    }
  </script>
</body>
</html>
"""

output_content = TEMPLATE.replace("__TOP10_CARDS__", top10_cards_html)
output_content = output_content.replace("__NEXT10_CARDS__", next10_cards_html)
output_content = output_content.replace("__CHANNELS_CARDS__", channels_cards_html)
output_content = output_content.replace("__TOTAL_CHANNELS__", str(len(channels)))
output_content = output_content.replace("__TECH_COUNT__", str(len(categories['tech'])))
output_content = output_content.replace("__HEALTH_COUNT__", str(len(categories['health'])))
output_content = output_content.replace("__DEEP_COUNT__", str(len(categories['deep_explainer'])))

with open(".workflow/mocks/mock1_executive_briefing.html", "w", encoding="utf-8") as f:
    f.write(output_content)

print("Successfully wrote upgraded Mock 1 with Briefing, Channels, and Saved tabs and Light Mode default!")
