import json
import html
import re
from pathlib import Path

data_path = Path(".workflow/mocks/mock_data.json")
with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

run_date = data.get("run_date", "2026-09-18")
top20 = data.get("top20", {}).get("items", [])
channels = data.get("channels", [])

top10 = top20[:10]
next10 = top20[10:20]

def render_md(text):
    if not text:
        return ""
    if "<p>" in text or "<strong>" in text:
        return text
    lines = text.strip().split("\n")
    out = []
    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if line.startswith("### "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h4 style='font-size:14px; font-weight:800; margin:10px 0 4px; color:var(--text);'>{html.escape(line[4:])}</h4>")
        elif line.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h3 style='font-size:15px; font-weight:800; margin:12px 0 6px; color:var(--text);'>{html.escape(line[3:])}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul style='margin-left:18px; margin-bottom:8px; line-height:1.5;'>")
                in_list = True
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html.escape(line[2:]))
            out.append(f"<li style='margin-bottom:4px; font-size:13px; color:var(--text);'>{content}</li>")
        else:
            if in_list: out.append("</ul>"); in_list = False
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html.escape(line))
            out.append(f"<p style='margin-bottom:8px; font-size:13px; line-height:1.5; color:var(--text);'>{content}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)

# TAB 1: BRIEFING CARDS
top10_html = ""
for it in top10:
    rank = it.get("rank", 1)
    title = html.escape(it.get("title", ""))
    source = html.escape(it.get("source_name", ""))
    duration = it.get("duration", "14m")
    why = html.escape(it.get("why_it_matters", ""))
    stype = it.get("source_type", "youtube").lower()
    is_article = (stype in ("rss", "article", "newsletter"))
    action_label = "Read" if is_article else "Watch"
    action_icon = """<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>""" if is_article else """<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>"""
    
    top10_html += f"""
        <div class="card" id="brief-card-{rank}">
          <div class="card-top">
            <div class="rank-pill">#{rank} Priority</div>
            <div class="meta-line">
              <span>{source}</span> · <span>{duration}</span>
            </div>
          </div>
          <div class="card-title" onclick="openItemLink('{title}', '{action_label}', {rank})" style="cursor:pointer;" title="Tap to open and mark watched">
            {title}
          </div>
          <div class="why-box">
            <div class="why-label">Why It Matters</div>
            <div class="why-text">{why}</div>
          </div>
          <div class="card-actions">
            <button class="btn-audio" onclick="playAudio('{title}', '{source}')">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              Play
            </button>
            <div class="action-icons">
              <button class="action-btn-clean" onclick="openItemLink('{title}', '{action_label}', {rank})">
                {action_icon} {action_label}
              </button>
              <button class="action-btn-clean" id="btn-queue-{rank}" onclick="toggleQueueItem('brief-{rank}', '{title}', '{source}', '{duration}')" title="Add to Commute Queue">
                + Queue
              </button>
              <button class="action-btn-clean" id="btn-bm-{rank}" onclick="toggleBookmarkItem('{title}', '{source}')" title="Save Bookmark">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
              </button>
            </div>
          </div>
        </div>
    """

# TAB 2: CHANNELS LIST (With individual videos/articles)
channels_html = ""
for ch in channels:
    ch_id = ch.get("id") or "ch"
    name = ch.get("name") or "Channel"
    cat = ch.get("category") or "tech"
    vids = ch.get("videos") or []
    vid_count = len(vids)
    initials = "".join([w[0].upper() for w in name.split()[:2]])
    preview_md = ch.get("summary_text") or ch.get("summary_preview") or ""
    rendered_summary = render_md(preview_md[:220] + ("..." if len(preview_md) > 220 else ""))
    
    is_demo = "MIT" in name or vid_count >= 5
    initially_open = "block" if is_demo else "none"
    toggle_icon = "▲" if is_demo else "▼"
    
    vids_html = ""
    for idx, v in enumerate(vids):
        v_title = html.escape(v.get("title") or f"Item {idx+1}")
        v_dur = v.get("duration") or "12m"
        v_summary = v.get("summary_html") or render_md(v.get("lead") or "Full concise overview of this source update.")
        v_type = v.get("source_type", "youtube").lower()
        v_is_article = (v_type in ("rss", "article", "newsletter"))
        v_action_label = "Read" if v_is_article else "Watch"
        v_icon = """<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>""" if v_is_article else """<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>"""
        
        pre_watched = (is_demo and idx < 2)
        watched_cls = " is-watched" if pre_watched else ""
        checked_attr = "checked" if pre_watched else ""
        
        vids_html += f"""
          <div class="video-subcard{watched_cls}" id="vcard-{ch_id}-{idx}">
            <div class="v-subcard-header">
              <div class="v-watch-check">
                <input type="checkbox" id="chk-{ch_id}-{idx}" {checked_attr} onchange="onItemCheckChanged('{ch_id}', {idx}, '{name}', this.checked)">
                <span class="v-subcard-title" onclick="openItemLink('{v_title}', '{v_action_label}', '{ch_id}-{idx}')">{idx+1}. {v_title}</span>
              </div>
              <span class="v-dur-badge">{v_dur}</span>
            </div>
            
            <div class="v-summary-body">
              {v_summary}
            </div>

            <div class="v-subcard-actions">
              <button class="btn-clean-link" onclick="openItemLink('{v_title}', '{v_action_label}', '{ch_id}-{idx}')">
                {v_icon} {v_action_label}
              </button>
              <div style="display:flex; gap:6px;">
                <button class="btn-clean-action" id="btn-vqueue-{ch_id}-{idx}" onclick="toggleQueueItem('v-{ch_id}-{idx}', '{v_title}', '{name}', '{v_dur}')">
                  + Queue
                </button>
                <button class="btn-clean-action" onclick="toggleBookmarkItem('{v_title}', '{name}')" title="Save Bookmark">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                </button>
              </div>
            </div>
          </div>
        """
        
    initial_watched = 2 if is_demo else 0
    unwatched = max(0, vid_count - initial_watched)

    channels_html += f"""
      <div class="channel-card" id="ch-card-{ch_id}" data-category="{cat}" data-name="{name.lower()}">
        <div class="ch-top" onclick="toggleChannelAccordion('{ch_id}')">
          <div class="ch-avatar">{initials}</div>
          <div class="ch-meta">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div class="ch-name">{html.escape(name)}</div>
              <span class="acc-toggle-icon" id="acc-icon-{ch_id}">{toggle_icon}</span>
            </div>
            <div class="ch-subline">
              <span style="font-weight:700; text-transform:uppercase; color:var(--accent); font-size:11px;">{cat}</span>
              · <span id="ch-progress-{ch_id}" style="font-weight:700; color:var(--text);">{initial_watched}/{vid_count} Completed</span>
              · <span>{ch.get('read_minutes', 4)}m</span>
            </div>
          </div>
        </div>

        <div class="ch-preview-box">
          {rendered_summary}
        </div>

        <div class="ch-actions-bar">
          <button class="btn-listen-smart" id="btn-listen-{ch_id}" onclick="listenUnwatchedChannel('{ch_id}', '{name}')" title="Plays only unwatched summaries">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span id="listen-label-{ch_id}">Listen Unwatched ({unwatched} remaining)</span>
          </button>
          
          <button class="btn-clean-action" onclick="toggleQueueItem('ch-{ch_id}', '{name} (All {vid_count} Items)', '{name}', '{vid_count * 10}m')">
            + Queue Channel
          </button>
        </div>

        <div class="channel-videos-panel" id="panel-{ch_id}" style="display:{initially_open};">
          <div class="panel-header-sub">
            <span>INDIVIDUAL OVERVIEWS ({vid_count} ITEMS)</span>
            <span style="font-size:11px; color:var(--text-muted);">Tap title to watch/read</span>
          </div>
          {vids_html}
        </div>
      </div>
    """

# MASTER HTML
MAIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - The Executive Briefing (v3.0)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Newsreader:ital,opsz,wght@0,6..72,500;0,6..72,700;1,6..72,400&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }
    
    :root[data-theme="light"] {
      --bg: #f8f9fa;
      --surface: #ffffff;
      --surface-elevated: #f1f5f9;
      --border: rgba(15, 23, 42, 0.08);
      --border-strong: rgba(15, 23, 42, 0.16);
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #15803d;
      --accent-badge: #d9ff63;
      --accent-badge-text: #171815;
      --accent-soft: rgba(21, 128, 61, 0.10);
      --why-bg: #f0fdf4;
      --why-border: #22c55e;
      --card-shadow: 0 4px 16px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.02);
      --player-bg: rgba(255, 255, 255, 0.96);
      --tab-bg: rgba(255, 255, 255, 0.98);
      --sheet-bg: #ffffff;
      --status-color: #0f172a;
    }

    :root[data-theme="dark"] {
      --bg: #0e0f12;
      --surface: #16181d;
      --surface-elevated: #1e2128;
      --border: rgba(255, 255, 255, 0.08);
      --border-strong: rgba(255, 255, 255, 0.16);
      --text: #f5f6f8;
      --text-muted: #8b909a;
      --accent: #d9ff63;
      --accent-badge: #d9ff63;
      --accent-badge-text: #171815;
      --accent-soft: rgba(217, 255, 99, 0.14);
      --why-bg: rgba(217, 255, 99, 0.05);
      --why-border: #d9ff63;
      --card-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
      --player-bg: rgba(22, 24, 29, 0.96);
      --tab-bg: rgba(14, 15, 18, 0.98);
      --sheet-bg: #16181d;
      --status-color: #f5f6f8;
    }

    body {
      background: #000; color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      height: 100vh; overflow: hidden; display: flex; justify-content: center;
      transition: background-color 0.2s, color 0.2s;
    }

    .phone {
      width: 100%; max-width: 430px; height: 100%; background: var(--bg); display: flex; flex-direction: column;
      position: relative; overflow: hidden; box-shadow: 0 0 60px rgba(0,0,0,0.8);
    }

    /* Status Bar */
    .status-bar {
      height: 48px; padding: 12px 22px 0; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; color: var(--status-color); flex-shrink: 0; z-index: 50; position: relative;
    }
    .island {
      position: absolute; left: 50%; top: 10px; transform: translateX(-50%); width: 124px; height: 32px;
      background: #000; border-radius: 20px; display: flex; align-items: center; justify-content: space-between;
      padding: 0 12px; cursor: pointer;
    }
    .island-dot { width: 8px; height: 8px; border-radius: 50%; background: #d9ff63; }
    .island-bars { display: flex; gap: 2px; align-items: flex-end; height: 12px; }
    .island-bars span { width: 2.5px; background: #d9ff63; border-radius: 1px; animation: eq 0.8s infinite ease-in-out; }
    .island-bars span:nth-child(2) { animation-delay: 0.2s; }
    .island-bars span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes eq { 0%, 100% { height: 3px; } 50% { height: 12px; } }

    /* Cloudflare Sync Toast */
    .sync-toast {
      position: absolute; top: 52px; left: 50%; transform: translateX(-50%);
      background: rgba(34, 197, 94, 0.95); color: #fff; font-size: 11px; font-weight: 700;
      padding: 4px 14px; border-radius: 20px; box-shadow: 0 4px 14px rgba(0,0,0,0.18);
      display: flex; align-items: center; gap: 6px; z-index: 80; opacity: 0; pointer-events: none;
      transition: opacity 0.3s, transform 0.3s;
    }
    .sync-toast.show { opacity: 1; transform: translateX(-50%) translateY(4px); }

    /* Header */
    .header {
      padding: 8px 18px 12px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--border); flex-shrink: 0; background: var(--surface);
    }
    .header-sub { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.2px; color: var(--accent); }
    .header-title { font-family: "Newsreader", serif; font-size: 24px; font-weight: 700; letter-spacing: -0.4px; line-height: 1.1; margin-top: 2px; }
    .theme-toggle-btn {
      width: 36px; height: 36px; border-radius: 50%; background: var(--surface-elevated);
      border: 1px solid var(--border); color: var(--text); display: flex; align-items: center;
      justify-content: center; cursor: pointer;
    }

    /* Scroll View */
    .view-content {
      flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; padding-bottom: 150px;
    }
    .view-content::-webkit-scrollbar { display: none; }

    /* Cards */
    .section-header {
      display: flex; align-items: center; justify-content: space-between; padding: 14px 18px 8px;
    }
    .section-title { font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
    .badge-count { background: var(--surface-elevated); color: var(--text); padding: 2px 7px; border-radius: 10px; font-size: 11px; }

    .card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
      padding: 16px 18px; margin: 0 16px 12px; box-shadow: var(--card-shadow); transition: all 0.2s ease;
    }
    .card.is-watched { opacity: 0.45; filter: grayscale(0.5); }
    .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .rank-pill {
      font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 6px; background: var(--accent-badge);
      color: var(--accent-badge-text);
    }
    .meta-line { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted); font-weight: 600; }
    .card-title { font-size: 16px; font-weight: 700; line-height: 1.35; margin-bottom: 10px; color: var(--text); }
    
    .why-box {
      background: var(--why-bg); border-left: 3px solid var(--why-border);
      padding: 10px 12px; border-radius: 0 8px 8px 0; margin-bottom: 12px;
    }
    .why-label { font-size: 10px; font-weight: 800; text-transform: uppercase; color: var(--accent); letter-spacing: 0.6px; margin-bottom: 2px; }
    .why-text { font-size: 13px; line-height: 1.45; color: var(--text); }

    .card-actions {
      display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border);
      padding-top: 10px;
    }
    .btn-audio {
      display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft);
      color: var(--accent); font-weight: 700; padding: 6px 14px; border-radius: 20px; font-size: 12px; border: none; cursor: pointer;
    }
    .action-icons { display: flex; gap: 6px; align-items: center; }
    .action-btn-clean {
      background: var(--surface-elevated); border: 1px solid var(--border); color: var(--text); padding: 6px 10px;
      border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700;
    }
    .action-btn-clean:active { transform: scale(0.95); }
    .action-btn-clean.is-active { background: var(--accent-badge); color: var(--accent-badge-text); border-color: var(--accent-badge); }

    /* TAB 2: CHANNELS */
    .channels-header { padding: 12px 16px 8px; display: flex; flex-direction: column; gap: 10px; }
    .search-input {
      width: 100%; padding: 10px 14px 10px 36px; border-radius: 12px; border: 1px solid var(--border);
      background: var(--surface); color: var(--text); font-size: 14px; font-weight: 500; outline: none;
    }

    .channel-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
      padding: 16px; margin: 0 16px 14px; box-shadow: var(--card-shadow);
    }
    .ch-top { display: flex; align-items: center; gap: 12px; cursor: pointer; }
    .ch-avatar {
      width: 44px; height: 44px; border-radius: 12px; background: var(--surface-elevated);
      color: var(--accent); font-weight: 900; font-size: 16px; display: flex; align-items: center; justify-content: center;
      border: 2px solid var(--border); flex-shrink: 0;
    }
    .ch-meta { flex: 1; min-width: 0; }
    .ch-name { font-size: 15px; font-weight: 700; color: var(--text); }
    .ch-subline { font-size: 12px; color: var(--text-muted); display: flex; gap: 6px; align-items: center; margin-top: 2px; }
    .acc-toggle-icon { font-size: 11px; color: var(--text-muted); padding: 4px 8px; background: var(--surface-elevated); border-radius: 6px; }

    .ch-preview-box { font-size: 13px; color: var(--text-muted); line-height: 1.45; margin: 12px 0; }
    .ch-actions-bar {
      display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border);
      padding-top: 10px; gap: 10px;
    }
    .btn-listen-smart {
      display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft);
      color: var(--accent); font-weight: 700; padding: 7px 14px; border-radius: 20px; font-size: 12px; border: none; cursor: pointer;
    }

    .channel-videos-panel { margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--border-strong); }
    .panel-header-sub {
      font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px;
      color: var(--text-muted); display: flex; justify-content: space-between; margin-bottom: 10px;
    }
    .video-subcard {
      background: var(--surface-elevated); border: 1px solid var(--border); border-radius: 12px;
      padding: 12px; margin-bottom: 10px;
    }
    .video-subcard.is-watched { opacity: 0.45; filter: grayscale(0.5); }
    .v-subcard-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
    .v-watch-check { display: flex; align-items: flex-start; gap: 8px; flex: 1; }
    .v-watch-check input[type="checkbox"] { width: 18px; height: 18px; margin-top: 2px; accent-color: var(--accent); cursor: pointer; }
    .v-subcard-title { font-size: 14px; font-weight: 700; line-height: 1.3; color: var(--text); cursor: pointer; }
    .v-dur-badge { font-size: 11px; font-weight: 700; background: var(--surface); padding: 2px 6px; border-radius: 6px; color: var(--text-muted); }
    .v-summary-body { font-size: 13px; line-height: 1.5; color: var(--text); padding: 6px 0 10px 26px; }
    .v-subcard-actions {
      display: flex; justify-content: space-between; align-items: center; padding-left: 26px; border-top: 1px solid var(--border); padding-top: 8px;
    }
    .btn-clean-link {
      display: inline-flex; align-items: center; gap: 5px; background: transparent; border: none;
      color: #ef4444; font-size: 12px; font-weight: 700; cursor: pointer;
    }
    .btn-clean-action {
      background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 11px; font-weight: 700;
      padding: 5px 10px; border-radius: 8px; cursor: pointer;
    }

    /* TAB 3: BOOKMARKS (UNLIMITED TEXT ONLY) */
    .sync-status-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      padding: 12px 16px; margin: 12px 16px 14px; display: flex; justify-content: space-between; align-items: center;
      box-shadow: var(--card-shadow);
    }
    .sync-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }

    /* STICKY MINI-PLAYER (Clicks open Full Player & Queue Sheet) */
    .mini-player {
      position: absolute; bottom: 70px; left: 12px; right: 12px; background: var(--player-bg);
      backdrop-filter: blur(20px); border: 1px solid var(--border); border-radius: 18px; padding: 10px 14px;
      display: flex; align-items: center; justify-content: space-between; box-shadow: var(--card-shadow); z-index: 60;
      cursor: pointer;
    }
    .player-info { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
    .player-art {
      width: 38px; height: 38px; border-radius: 10px; background: var(--accent-badge); color: var(--accent-badge-text);
      font-weight: 900; font-size: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .player-titles { min-width: 0; }
    .player-title { font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
    .player-sub { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
    .q-pill-badge { background: var(--accent-soft); color: var(--accent); padding: 1px 6px; border-radius: 8px; font-weight: 800; font-size: 10px; }
    
    .player-controls { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .play-btn {
      width: 36px; height: 36px; border-radius: 50%; background: var(--accent); color: #fff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
    }
    :root[data-theme="dark"] .play-btn { background: #d9ff63; color: #11120f; }

    /* FULL PLAYER & COMMUTE QUEUE MODAL SHEET */
    .player-sheet-overlay {
      position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5);
      z-index: 100; opacity: 0; pointer-events: none; transition: opacity 0.3s;
    }
    .player-sheet-overlay.open { opacity: 1; pointer-events: auto; }
    
    .player-sheet {
      position: absolute; left: 0; right: 0; bottom: 0; height: 86%; background: var(--sheet-bg);
      border-radius: 32px 32px 0 0; box-shadow: 0 -10px 40px rgba(0,0,0,0.4); z-index: 101;
      display: flex; flex-direction: column; transform: translateY(100%); transition: transform 0.32s cubic-bezier(0.16, 1, 0.3, 1);
      overflow: hidden;
    }
    .player-sheet-overlay.open .player-sheet { transform: translateY(0); }

    .sheet-handle {
      width: 44px; height: 5px; background: rgba(150, 150, 150, 0.4); border-radius: 3px;
      margin: 12px auto 8px; flex-shrink: 0; cursor: pointer;
    }
    .sheet-header {
      padding: 6px 20px 12px; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
    }
    .sheet-title { font-size: 14px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-muted); }
    .btn-close-sheet {
      background: var(--surface-elevated); border: none; color: var(--text); width: 30px; height: 30px;
      border-radius: 50%; font-weight: 700; cursor: pointer;
    }

    .sheet-scroll-body { flex: 1; overflow-y: auto; padding: 10px 20px 30px; }
    .sheet-scroll-body::-webkit-scrollbar { display: none; }

    /* Full Player Hero */
    .player-hero-deck {
      text-align: center; margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--border);
    }
    .full-player-art {
      width: 140px; height: 140px; border-radius: 24px; background: var(--accent-badge); color: var(--accent-badge-text);
      font-size: 56px; font-weight: 900; display: flex; align-items: center; justify-content: center;
      margin: 0 auto 16px; box-shadow: var(--card-shadow);
    }
    .full-player-title { font-size: 18px; font-weight: 800; line-height: 1.3; color: var(--text); margin-bottom: 4px; }
    .full-player-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 18px; }

    .full-scrubber {
      height: 6px; background: var(--surface-elevated); border-radius: 3px; position: relative; margin-bottom: 6px;
    }
    .full-scrubber-fill { width: 34%; height: 100%; background: var(--accent); border-radius: 3px; }
    .full-scrubber-times { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); font-weight: 600; }

    .full-controls {
      display: flex; justify-content: space-between; align-items: center; max-width: 280px; margin: 16px auto 0;
    }
    .full-btn-skip { background: none; border: none; color: var(--text); font-size: 12px; font-weight: 700; cursor: pointer; }
    .full-btn-play {
      width: 64px; height: 64px; border-radius: 50%; background: var(--accent); color: #fff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
    }
    :root[data-theme="dark"] .full-btn-play { background: #d9ff63; color: #11120f; }

    /* Commute Queue Section inside Sheet */
    .queue-sheet-section {
      background: var(--surface-elevated); border-radius: 18px; padding: 16px; border: 1px solid var(--border);
    }
    .queue-section-header {
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
    }
    .queue-section-title { font-size: 13px; font-weight: 800; text-transform: uppercase; color: var(--text); letter-spacing: 0.6px; }
    .queue-item-row {
      display: flex; justify-content: space-between; align-items: center; background: var(--surface);
      border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; margin-bottom: 8px;
    }
    .queue-item-left { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
    .queue-item-drag { color: var(--text-muted); cursor: grab; font-size: 14px; }
    .queue-item-title { font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .queue-item-sub { font-size: 11px; color: var(--text-muted); }
    .btn-remove-q { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; }

    /* Bottom Tab Bar */
    .tab-bar {
      position: absolute; bottom: 0; left: 0; right: 0; height: 68px; background: var(--tab-bg);
      backdrop-filter: blur(20px); border-top: 1px solid var(--border);
      display: flex; justify-content: space-around; align-items: center; padding-bottom: 14px; z-index: 55;
    }
    .tab-item {
      display: flex; flex-direction: column; align-items: center; gap: 3px; font-size: 10px; font-weight: 700;
      color: var(--text-muted); cursor: pointer; flex: 1; padding: 6px 0;
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
      <div class="island" onclick="openPlayerSheet()">
        <div class="island-dot"></div>
        <div class="island-bars"><span></span><span></span><span></span></div>
      </div>
      <div style="display:flex; gap:6px; font-size:12px; font-weight:700;">5G 100%</div>
    </div>

    <!-- Automatic Cloudflare Event Sync Toast -->
    <div class="sync-toast" id="syncToast">
      <div style="width:6px; height:6px; border-radius:50%; background:#fff;"></div>
      <span id="syncToastText">Cloudflare Synced</span>
    </div>

    <!-- Header -->
    <div class="header">
      <div>
        <div class="header-sub" id="headerSub">Executive Intelligence</div>
        <div class="header-title" id="headerTitle">Weekly Briefing</div>
      </div>
      <button class="theme-toggle-btn" onclick="toggleTheme()" title="Toggle Light / Dark Mode">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" id="themeIcon">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      </button>
    </div>

    <!-- MAIN VIEWS CONTAINER -->
    <div class="view-content" id="mainContainer">
      
      <!-- TAB 1: BRIEFING -->
      <div id="tab-briefing-view">
        <div class="section-header">
          <div class="section-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>
            Top 10 Must-Watch <span class="badge-count">10</span>
          </div>
          <span style="font-size:12px; color:var(--text-muted); font-weight:600;">Ranked Selection</span>
        </div>
        __TOP10_CARDS__
      </div>

      <!-- TAB 2: CHANNELS -->
      <div id="tab-channels-view" style="display:none;">
        <div class="channels-header">
          <input type="text" class="search-input" placeholder="Search 23 curated channels..." oninput="filterChannels(this.value)">
          <div style="font-size:12px; color:var(--text-muted); padding-left:2px;">
            Tap any channel to expand individual video/article overviews.
          </div>
        </div>

        <div id="channels-list">
          __CHANNELS_HTML__
        </div>
      </div>

      <!-- TAB 3: BOOKMARKS (SAVED ARTICLES ONLY) -->
      <div id="tab-saved-view" style="display:none;">
        <div class="sync-status-card">
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="sync-dot"></div>
            <div>
              <div style="font-size:13px; font-weight:700; color:var(--text);">Cloudflare Sync Active</div>
              <div style="font-size:11px; color:var(--text-muted);" id="syncTimeLabel">Real-time sync to tubelm-sync.workers.dev</div>
            </div>
          </div>
          <span style="font-size:11px; font-weight:700; color:var(--accent);" id="bmCountHeader">2 Bookmarks</span>
        </div>

        <div style="padding:0 18px 8px; font-size:12px; font-weight:800; text-transform:uppercase; color:var(--text-muted);">
          Saved Articles & Digests (Unlimited Text)
        </div>

        <div id="bookmarks-container" style="padding: 0 16px;">
          <div class="card" id="bm-1" style="margin:0 0 12px;">
            <div class="card-top">
              <span style="font-size:11px; font-weight:700; color:var(--accent); text-transform:uppercase;">Deep Explainer</span>
              <span style="font-size:12px; color:var(--text-muted);">Saved 2d ago</span>
            </div>
            <div class="card-title" style="font-size:15px;">3Blue1Brown: Attention in Transformers Explained Visually</div>
            <div class="why-text" style="font-size:13px; color:var(--text-muted); margin-bottom:10px;">
              Geometric derivation of multi-head self-attention and projection matrices.
            </div>
            <div class="card-actions">
              <span style="font-size:11px; color:var(--text-muted);">Pure Text · Unlimited</span>
              <button class="action-btn-clean" onclick="removeBookmark('bm-1')">Remove</button>
            </div>
          </div>

          <div class="card" id="bm-2" style="margin:0 0 12px;">
            <div class="card-top">
              <span style="font-size:11px; font-weight:700; color:var(--accent); text-transform:uppercase;">Health</span>
              <span style="font-size:12px; color:var(--text-muted);">Saved 4d ago</span>
            </div>
            <div class="card-title" style="font-size:15px;">Physionic: Saturated Fats and LDL Receptor Clearance Rates</div>
            <div class="why-text" style="font-size:13px; color:var(--text-muted); margin-bottom:10px;">
              Comprehensive breakdown of ApoB and hepatic uptake mechanisms.
            </div>
            <div class="card-actions">
              <span style="font-size:11px; color:var(--text-muted);">Pure Text · Unlimited</span>
              <button class="action-btn-clean" onclick="removeBookmark('bm-2')">Remove</button>
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- STICKY MINI-PLAYER (Tapping expands into Commute Queue Sheet) -->
    <div class="mini-player" id="miniPlayer" onclick="openPlayerSheet()">
      <div class="player-info">
        <div class="player-art">TL</div>
        <div class="player-titles">
          <div class="player-title" id="playerTitle">Executive Briefing Audio</div>
          <div class="player-sub">
            <span id="playerSub">Top 20 Overview · 14m</span>
            <span class="q-pill-badge" id="miniQueueBadge">3 in Queue</span>
          </div>
        </div>
      </div>
      <div class="player-controls" onclick="event.stopPropagation()">
        <button class="play-btn" onclick="togglePlay(this)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" id="playIcon"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </button>
      </div>
    </div>

    <!-- FULL PLAYER & COMMUTE QUEUE MODAL SHEET -->
    <div class="player-sheet-overlay" id="playerSheetOverlay" onclick="closePlayerSheet()">
      <div class="player-sheet" onclick="event.stopPropagation()">
        <div class="sheet-handle" onclick="closePlayerSheet()"></div>
        <div class="sheet-header">
          <div class="sheet-title">Now Playing · Commute Deck</div>
          <button class="btn-close-sheet" onclick="closePlayerSheet()">✕</button>
        </div>

        <div class="sheet-scroll-body">
          <!-- Full Player Hero -->
          <div class="player-hero-deck">
            <div class="full-player-art">TL</div>
            <div class="full-player-title" id="fullSheetTitle">Executive Briefing Audio</div>
            <div class="full-player-sub" id="fullSheetSub">Playing 1 of 4 in Commute Queue</div>

            <!-- Scrubber -->
            <div class="full-scrubber">
              <div class="full-scrubber-fill"></div>
            </div>
            <div class="full-scrubber-times">
              <span>05:12</span>
              <span>14:48</span>
            </div>

            <!-- Controls -->
            <div class="full-controls">
              <button class="full-btn-skip" onclick="skipSec(-15)">-15s</button>
              <button class="full-btn-play" onclick="toggleFullPlay(this)">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              </button>
              <button class="full-btn-skip" onclick="skipSec(15)">+15s</button>
              <button class="full-btn-skip" onclick="cycleSpeed(this)">
                <span id="speedIndicator">1.25×</span>
              </button>
            </div>
          </div>

          <!-- COMMUTE QUEUE (ANCHORED DIRECTLY TO PLAYER) -->
          <div class="queue-sheet-section">
            <div class="queue-section-header">
              <div class="queue-section-title">Up Next in Commute Queue</div>
              <span style="font-size:11px; font-weight:700; color:var(--accent);" id="queueRemainingText">3 items · 38m total</span>
            </div>

            <div id="sheet-queue-list">
              <div class="queue-item-row" id="qrow-1">
                <div class="queue-item-left">
                  <span class="queue-item-drag">☰</span>
                  <div style="min-width:0;">
                    <div class="queue-item-title">Creatine & Cognition: Mechanisms</div>
                    <div class="queue-item-sub">Physionic · 14m</div>
                  </div>
                </div>
                <button class="btn-remove-q" onclick="removeQueueRow('qrow-1')">✕</button>
              </div>

              <div class="queue-item-row" id="qrow-2">
                <div class="queue-item-left">
                  <span class="queue-item-drag">☰</span>
                  <div style="min-width:0;">
                    <div class="queue-item-title">What’s at stake in AI gamble</div>
                    <div class="queue-item-sub">MIT Technology Review · 16m</div>
                  </div>
                </div>
                <button class="btn-remove-q" onclick="removeQueueRow('qrow-2')">✕</button>
              </div>

              <div class="queue-item-row" id="qrow-3">
                <div class="queue-item-left">
                  <span class="queue-item-drag">☰</span>
                  <div style="min-width:0;">
                    <div class="queue-item-title">Quantum Computers RSA Physics</div>
                    <div class="queue-item-sub">Veritasium · 22m</div>
                  </div>
                </div>
                <button class="btn-remove-q" onclick="removeQueueRow('qrow-3')">✕</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 3-Tab Bar (Briefing, Channels, Bookmarks) -->
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
        Bookmarks
      </div>
    </div>
    <div class="home-bar"></div>
  </div>

  <script>
    let isPlaying = false;
    let currentTheme = 'light';
    let queueCount = 3;
    let bookmarkCount = 2;

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
        titleEl.innerText = 'Bookmarks';
        subEl.innerText = 'Saved Articles (Unlimited)';
      }
      document.getElementById('mainContainer').scrollTop = 0;
    }

    /* Cloudflare Sync Auto-Pulse Toast */
    let syncTimeout = null;
    function triggerCloudflareSync(eventReason) {
      const toast = document.getElementById('syncToast');
      const text = document.getElementById('syncToastText');
      text.innerText = 'Cloudflare Synced: ' + eventReason;
      toast.classList.add('show');
      if (syncTimeout) clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => toast.classList.remove('show'), 2200);
      const timeLbl = document.getElementById('syncTimeLabel');
      if (timeLbl) timeLbl.innerText = 'Synced just now via tubelm-sync.workers.dev';
    }

    /* Open Link & Auto-Mark Watched (Req #3 & #6) */
    function openItemLink(title, actionType, id) {
      // Auto-mark watched in UI
      const card = document.getElementById('brief-card-' + id) || document.getElementById('vcard-' + id);
      if (card) card.classList.add('is-watched');
      
      const chk = document.getElementById('chk-' + id);
      if (chk) {
        chk.checked = true;
        const parts = String(id).split('-');
        if (parts.length === 2) onItemCheckChanged(parts[0], parseInt(parts[1]), 'Source', true);
      }
      
      triggerCloudflareSync(actionType + ': ' + title.substring(0, 18) + '…');
      alert('Opening ' + (actionType === 'Read' ? 'Article: ' : 'YouTube: ') + title + '\\n\\n✓ Automatically marked as ' + (actionType === 'Read' ? 'Read' : 'Watched') + ' in your history.');
    }

    /* Commute Queue Integration (Req #5) */
    function toggleQueueItem(id, title, source, dur) {
      const btn = document.getElementById('btn-queue-' + id) || document.getElementById('btn-vqueue-' + id);
      if (btn) btn.classList.toggle('is-active');
      queueCount++;
      updateQueueUI();
      
      // Add row to full player sheet queue
      const list = document.getElementById('sheet-queue-list');
      const row = document.createElement('div');
      row.className = 'queue-item-row';
      row.id = 'sheet-q-' + id;
      row.innerHTML = `
        <div class="queue-item-left">
          <span class="queue-item-drag">☰</span>
          <div style="min-width:0;">
            <div class="queue-item-title">${title}</div>
            <div class="queue-item-sub">${source} · ${dur}</div>
          </div>
        </div>
        <button class="btn-remove-q" onclick="removeQueueRow('sheet-q-${id}')">✕</button>
      `;
      list.appendChild(row);
      triggerCloudflareSync('Queued: ' + title.substring(0, 16) + '…');
    }

    function removeQueueRow(rowId) {
      const el = document.getElementById(rowId);
      if (el) {
        el.remove();
        queueCount = Math.max(0, queueCount - 1);
        updateQueueUI();
        triggerCloudflareSync('Removed from Queue');
      }
    }

    function updateQueueUI() {
      document.getElementById('miniQueueBadge').innerText = queueCount + ' in Queue';
      document.getElementById('queueRemainingText').innerText = queueCount + ' items · ' + (queueCount * 12) + 'm total';
    }

    /* Player Sheet Modal */
    function openPlayerSheet() {
      document.getElementById('playerSheetOverlay').classList.add('open');
    }
    function closePlayerSheet() {
      document.getElementById('playerSheetOverlay').classList.remove('open');
    }

    /* Bookmark System (Unlimited Text) */
    function toggleBookmarkItem(title, source) {
      bookmarkCount++;
      document.getElementById('bmCountHeader').innerText = bookmarkCount + ' Bookmarks';
      const container = document.getElementById('bookmarks-container');
      const card = document.createElement('div');
      card.className = 'card';
      card.style.margin = '0 0 12px';
      card.innerHTML = `
        <div class="card-top">
          <span style="font-size:11px; font-weight:700; color:var(--accent); text-transform:uppercase;">${source}</span>
          <span style="font-size:12px; color:var(--text-muted);">Saved just now</span>
        </div>
        <div class="card-title" style="font-size:15px;">${title}</div>
        <div class="card-actions">
          <span style="font-size:11px; color:var(--text-muted);">Pure Text · Unlimited</span>
          <button class="action-btn-clean" onclick="this.closest('.card').remove(); bookmarkCount--; document.getElementById('bmCountHeader').innerText = bookmarkCount + ' Bookmarks'; triggerCloudflareSync('Bookmark Removed');">Remove</button>
        </div>
      `;
      container.prepend(card);
      triggerCloudflareSync('Bookmarked: ' + title.substring(0, 16) + '…');
    }

    function removeBookmark(id) {
      const el = document.getElementById(id);
      if (el) {
        el.remove();
        bookmarkCount = Math.max(0, bookmarkCount - 1);
        document.getElementById('bmCountHeader').innerText = bookmarkCount + ' Bookmarks';
        triggerCloudflareSync('Bookmark Removed');
      }
    }

    /* Channel Accordion & Video Breakdown */
    function toggleChannelAccordion(chId) {
      const panel = document.getElementById('panel-' + chId);
      const icon = document.getElementById('acc-icon-' + chId);
      if (panel.style.display === 'none' || !panel.style.display) {
        panel.style.display = 'block';
        icon.innerText = '▲';
      } else {
        panel.style.display = 'none';
        icon.innerText = '▼';
      }
    }

    /* Item Checkbox Changed */
    function onItemCheckChanged(chId, idx, chName, isChecked) {
      const vcard = document.getElementById('vcard-' + chId + '-' + idx);
      if (vcard) {
        if (isChecked) vcard.classList.add('is-watched');
        else vcard.classList.remove('is-watched');
      }

      const chPanel = document.getElementById('panel-' + chId);
      if (chPanel) {
        const allCheckboxes = chPanel.querySelectorAll('input[type="checkbox"]');
        let watchedCount = 0;
        allCheckboxes.forEach(cb => { if (cb.checked) watchedCount++; });
        const total = allCheckboxes.length;

        const progressLabel = document.getElementById('ch-progress-' + chId);
        if (progressLabel) {
          progressLabel.innerText = watchedCount + '/' + total + ' Completed';
          if (watchedCount === total) {
            progressLabel.innerHTML = '<span style="color:#22c55e;">✓ Channel Completed</span>';
            document.getElementById('ch-card-' + chId).classList.add('is-watched');
          } else {
            document.getElementById('ch-card-' + chId).classList.remove('is-watched');
          }
        }

        const unwatched = total - watchedCount;
        const listenLabel = document.getElementById('listen-label-' + chId);
        if (listenLabel) {
          listenLabel.innerText = (unwatched > 0) ? 'Listen Unwatched (' + unwatched + ' remaining)' : 'All Watched · Replay';
        }
      }

      triggerCloudflareSync(chName + ' item ' + (isChecked ? 'completed' : 'uncompleted'));
    }

    /* Smart Unwatched Listening */
    function listenUnwatchedChannel(chId, chName) {
      const chPanel = document.getElementById('panel-' + chId);
      const allCheckboxes = chPanel.querySelectorAll('input[type="checkbox"]');
      let watched = 0, unwatched = 0;
      allCheckboxes.forEach(cb => { if (cb.checked) watched++; else unwatched++; });

      if (unwatched > 0) {
        playAudio('Unwatched Summaries (' + unwatched + ' remaining)', chName);
        alert('Listening ' + unwatched + ' unwatched summaries from ' + chName + '.\\n' +
              (watched > 0 ? '(Skipping ' + watched + ' already watched summaries)' : ''));
      } else {
        playAudio('Full Channel Overview', chName);
      }
    }

    /* Audio Playback Controls */
    function playAudio(title, source) {
      document.getElementById('playerTitle').innerText = title;
      document.getElementById('playerSub').innerText = source + ' · Playing';
      document.getElementById('fullSheetTitle').innerText = title;
      document.getElementById('fullSheetSub').innerText = source + ' · Now Playing';
      isPlaying = true;
      document.querySelector('.play-btn').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
    }

    function togglePlay(btn) {
      isPlaying = !isPlaying;
      btn.innerHTML = isPlaying 
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
        : '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    }

    function toggleFullPlay(btn) {
      togglePlay(document.querySelector('.play-btn'));
      btn.innerHTML = isPlaying
        ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
        : '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    }

    function skipSec(s) { alert('Skipped ' + s + 's'); }
    function cycleSpeed(btn) {
      const speeds = ['1.0×', '1.25×', '1.5×', '2.0×'];
      let sp = document.getElementById('speedIndicator');
      let idx = (speeds.indexOf(sp.innerText) + 1) % speeds.length;
      sp.innerText = speeds[idx];
    }

    function filterChannels(q) {
      q = q.toLowerCase();
      document.querySelectorAll('.channel-card').forEach(function(card) {
        const name = card.getAttribute('data-name') || '';
        card.style.display = name.includes(q) ? 'block' : 'none';
      });
    }
  </script>
</body>
</html>
"""

final_html = MAIN_TEMPLATE.replace("__TOP10_CARDS__", top10_html)
final_html = final_html.replace("__CHANNELS_HTML__", channels_html)

with open(".workflow/mocks/mock1_executive_briefing.html", "w", encoding="utf-8") as f:
    f.write(final_html)

print("Successfully wrote v3.0 of Mock 1!")
