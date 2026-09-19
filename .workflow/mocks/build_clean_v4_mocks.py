import json
import html
import re
from pathlib import Path

data_path = Path(".workflow/mocks/mock_data.json")
with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

run_date = data.get("run_date", "2026-09-18")
top20 = data.get("top20", {}).get("items", [])[:20]
channels = data.get("channels", [])

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

# TAB 1: ALL 20 BRIEFING CARDS (CONTINUOUS, NO DIVIDERS, NO FLUFF)
briefing_cards_html = ""
for idx, it in enumerate(top20):
    rank = idx + 1
    title = html.escape(it.get("title", ""))
    source = html.escape(it.get("source_name", ""))
    duration = it.get("duration", "14m")
    why = html.escape(it.get("why_it_matters", ""))
    stype = it.get("source_type", "youtube").lower()
    is_article = (stype in ("rss", "article", "newsletter"))
    action_label = "Read" if is_article else "Watch"
    action_icon = """<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>""" if is_article else """<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>"""
    
    briefing_cards_html += f"""
        <div class="card" id="brief-card-{rank}">
          <div class="card-top">
            <div class="rank-pill">#{rank}</div>
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
              <button class="action-btn-clean" id="btn-queue-{rank}" onclick="toggleQueueItem('brief-{rank}', '{title}', '{source}', '{duration}')" title="Add to Queue">
                + Queue
              </button>
              <button class="action-btn-clean" id="btn-bm-{rank}" onclick="toggleBookmarkItem('{title}', '{source}')" title="Bookmark">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
              </button>
            </div>
          </div>
        </div>
    """

# TAB 2: CHANNELS LIST (Clean, no floating instructions, rendered markdown)
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
                <button class="btn-clean-action" onclick="toggleBookmarkItem('{v_title}', '{name}')" title="Bookmark">
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
            <span id="listen-label-{ch_id}">Listen Unwatched ({unwatched})</span>
          </button>
          
          <button class="btn-clean-action" onclick="toggleQueueItem('ch-{ch_id}', '{name} ({vid_count} Items)', '{name}', '{vid_count * 10}m')">
            + Queue
          </button>
        </div>

        <div class="channel-videos-panel" id="panel-{ch_id}" style="display:{initially_open};">
          {vids_html}
        </div>
      </div>
    """

# MASTER HTML TEMPLATE - CLEAN & MINIMALIST
MAIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM</title>
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
      padding: 5px 14px; border-radius: 20px; box-shadow: 0 4px 14px rgba(0,0,0,0.18);
      display: flex; align-items: center; gap: 6px; z-index: 80; opacity: 0; pointer-events: none;
      transition: opacity 0.3s, transform 0.3s;
    }
    .sync-toast.show { opacity: 1; transform: translateX(-50%) translateY(4px); }

    /* Header - Clean, No Fluff */
    .header {
      padding: 10px 18px 14px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--border); flex-shrink: 0; background: var(--surface);
    }
    .header-title { font-family: "Newsreader", serif; font-size: 26px; font-weight: 700; letter-spacing: -0.4px; line-height: 1.1; }
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
    .card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
      padding: 16px 18px; margin: 12px 16px; box-shadow: var(--card-shadow); transition: all 0.2s ease;
    }
    .card.is-watched { opacity: 0.45; filter: grayscale(0.5); }
    .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .rank-pill {
      font-size: 11px; font-weight: 800; padding: 2px 7px; border-radius: 6px; background: var(--accent-badge);
      color: var(--accent-badge-text); font-family: 'JetBrains Mono', monospace;
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
    .action-icons { display: flex; gap: 6px; }
    .action-btn-clean {
      display: inline-flex; align-items: center; gap: 4px; background: var(--surface-elevated);
      border: 1px solid var(--border); color: var(--text); font-size: 11px; font-weight: 700;
      padding: 6px 10px; border-radius: 8px; cursor: pointer; transition: background 0.15s;
    }

    /* Tab 2: Channels UI */
    .channels-header {
      padding: 12px 16px 8px;
    }
    .search-input {
      width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
      padding: 10px 14px; font-size: 14px; color: var(--text); outline: none;
    }
    .search-input::placeholder { color: var(--text-muted); }

    .channel-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      margin: 8px 16px 12px; padding: 14px; box-shadow: var(--card-shadow);
    }
    .ch-top { display: flex; align-items: center; gap: 12px; cursor: pointer; }
    .ch-avatar {
      width: 42px; height: 42px; border-radius: 12px; background: var(--surface-elevated);
      border: 1px solid var(--border); display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 14px; color: var(--accent); flex-shrink: 0;
    }
    .ch-meta { flex: 1; min-width: 0; }
    .ch-name { font-size: 15px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .ch-subline { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
    .acc-toggle-icon { font-size: 12px; color: var(--text-muted); transition: transform 0.2s; }

    .ch-preview-box {
      margin: 10px 0; font-size: 13px; line-height: 1.45; color: var(--text-muted);
      background: var(--surface-elevated); padding: 10px 12px; border-radius: 10px;
    }

    .ch-actions-bar {
      display: flex; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);
    }
    .btn-listen-smart {
      flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      background: var(--accent-badge); color: var(--accent-badge-text); font-size: 12px; font-weight: 800;
      padding: 8px 12px; border-radius: 10px; border: none; cursor: pointer;
    }
    .btn-clean-action {
      background: var(--surface-elevated); border: 1px solid var(--border); color: var(--text);
      font-size: 11px; font-weight: 700; padding: 7px 12px; border-radius: 8px; cursor: pointer;
    }

    /* Expandable Videos Panel */
    .channel-videos-panel {
      margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border-strong);
    }
    .video-subcard {
      background: var(--surface-elevated); border: 1px solid var(--border); border-radius: 12px;
      padding: 12px; margin-bottom: 10px; transition: all 0.2s;
    }
    .video-subcard.is-watched { opacity: 0.45; }
    .v-subcard-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
    .v-watch-check { display: flex; align-items: flex-start; gap: 8px; flex: 1; }
    .v-watch-check input[type="checkbox"] { width: 16px; height: 16px; margin-top: 2px; accent-color: var(--accent); cursor: pointer; }
    .v-subcard-title { font-size: 13px; font-weight: 700; line-height: 1.35; color: var(--text); cursor: pointer; }
    .v-dur-badge { font-size: 11px; color: var(--text-muted); font-weight: 600; white-space: nowrap; }
    
    .v-summary-body { font-size: 12px; line-height: 1.45; color: var(--text); margin: 6px 0 8px 24px; }
    .v-summary-body strong { color: var(--text); font-weight: 700; }
    .v-summary-body ul { margin-left: 16px; margin-bottom: 6px; }
    .v-summary-body li { margin-bottom: 3px; }

    .v-subcard-actions { display: flex; justify-content: space-between; align-items: center; margin-left: 24px; padding-top: 6px; border-top: 1px solid var(--border); }
    .btn-clean-link {
      background: transparent; border: none; color: var(--accent); font-size: 11px; font-weight: 800;
      display: inline-flex; align-items: center; gap: 4px; cursor: pointer; padding: 2px 0;
    }

    /* Sticky Mini-Player */
    .mini-player {
      position: absolute; bottom: 76px; left: 12px; right: 12px; height: 56px;
      background: var(--player-bg); backdrop-filter: blur(20px); border: 1px solid var(--border-strong);
      border-radius: 16px; display: flex; align-items: center; justify-content: space-between;
      padding: 0 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.15); z-index: 60; cursor: pointer;
    }
    .player-info { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .player-art {
      width: 36px; height: 36px; border-radius: 10px; background: var(--accent-badge);
      color: var(--accent-badge-text); display: flex; align-items: center; justify-content: center;
      font-weight: 900; font-size: 13px; flex-shrink: 0;
    }
    .player-titles { min-width: 0; }
    .player-title { font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .player-sub { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
    .q-pill-badge {
      background: var(--accent-soft); color: var(--accent); font-size: 9px; font-weight: 800;
      padding: 1px 6px; border-radius: 6px;
    }
    .play-btn {
      width: 36px; height: 36px; border-radius: 50%; background: var(--surface-elevated);
      border: 1px solid var(--border); color: var(--text); display: flex; align-items: center;
      justify-content: center; cursor: pointer;
    }

    /* Player & Commute Queue Drawer Sheet */
    .player-sheet-overlay {
      position: absolute; inset: 0; background: rgba(0,0,0,0.5); backdrop-filter: blur(4px);
      z-index: 100; opacity: 0; pointer-events: none; transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .player-sheet-overlay.open { opacity: 1; pointer-events: auto; }
    .player-sheet {
      position: absolute; bottom: 0; left: 0; right: 0; height: 86%; background: var(--sheet-bg);
      border-radius: 28px 28px 0 0; display: flex; flex-direction: column; overflow: hidden;
      transform: translateY(100%); transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
      box-shadow: 0 -10px 40px rgba(0,0,0,0.3); border-top: 1px solid var(--border-strong);
    }
    .player-sheet-overlay.open .player-sheet { transform: translateY(0); }
    .sheet-handle {
      width: 38px; height: 5px; background: var(--border-strong); border-radius: 3px;
      margin: 10px auto 4px; flex-shrink: 0; cursor: pointer;
    }
    .sheet-header {
      padding: 10px 20px 14px; display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    .sheet-title { font-size: 15px; font-weight: 800; color: var(--text); }
    .btn-close-sheet {
      background: var(--surface-elevated); border: none; color: var(--text-muted); width: 28px; height: 28px;
      border-radius: 50%; font-size: 13px; font-weight: 800; cursor: pointer;
    }
    .sheet-scroll-body { flex: 1; overflow-y: auto; padding: 18px 20px 30px; }
    .sheet-scroll-body::-webkit-scrollbar { display: none; }

    .player-hero-deck {
      text-align: center; padding-bottom: 20px; border-bottom: 1px solid var(--border);
    }
    .full-player-art {
      width: 80px; height: 80px; border-radius: 20px; background: var(--accent-badge);
      color: var(--accent-badge-text); display: flex; align-items: center; justify-content: center;
      font-weight: 900; font-size: 28px; margin: 0 auto 14px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);
    }
    .full-player-title { font-size: 17px; font-weight: 800; color: var(--text); margin-bottom: 4px; }
    .full-player-sub { font-size: 12px; color: var(--text-muted); margin-bottom: 16px; }

    .full-scrubber {
      height: 4px; background: var(--surface-elevated); border-radius: 2px; position: relative;
      margin: 12px 0 6px; cursor: pointer;
    }
    .full-scrubber-fill { width: 35%; height: 100%; background: var(--accent); border-radius: 2px; }
    .full-scrubber-times { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }

    .full-controls {
      display: flex; justify-content: center; align-items: center; gap: 20px; margin-top: 16px;
    }
    .full-btn-play {
      width: 58px; height: 58px; border-radius: 50%; background: var(--accent); color: #fff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
      box-shadow: 0 6px 20px rgba(0,0,0,0.2);
    }
    .full-btn-skip {
      width: 40px; height: 40px; border-radius: 50%; background: var(--surface-elevated);
      border: 1px solid var(--border); color: var(--text); font-size: 12px; font-weight: 700;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
    }

    /* Queue Section in Drawer */
    .queue-sheet-section { margin-top: 20px; }
    .queue-section-header {
      display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
    }
    .queue-section-title { font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px; color: var(--text); }
    .queue-item-row {
      display: flex; align-items: center; justify-content: space-between; background: var(--surface-elevated);
      border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; margin-bottom: 8px;
    }
    .queue-item-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .queue-item-drag { font-size: 14px; color: var(--text-muted); cursor: grab; }
    .queue-item-title { font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .queue-item-sub { font-size: 11px; color: var(--text-muted); }
    .btn-remove-q { background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; }

    /* Tab Bar */
    .tab-bar {
      height: 76px; background: var(--tab-bg); backdrop-filter: blur(20px); border-top: 1px solid var(--border);
      display: flex; justify-content: space-around; align-items: center; padding: 0 10px 18px;
      flex-shrink: 0; z-index: 40;
    }
    .tab-item {
      display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 10px; font-weight: 700;
      color: var(--text-muted); cursor: pointer; transition: color 0.15s; width: 60px;
    }
    .tab-item.active { color: var(--accent); }
    .tab-item svg { width: 22px; height: 22px; }

    .home-bar {
      position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); width: 134px; height: 5px;
      background: var(--text); border-radius: 3px; opacity: 0.2; pointer-events: none; z-index: 70;
    }
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

    <!-- Header - Clean, No Fluff -->
    <div class="header">
      <div class="header-title" id="headerTitle">Weekly Briefing</div>
      <button class="theme-toggle-btn" onclick="toggleTheme()" title="Toggle Light / Dark Mode">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" id="themeIcon">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      </button>
    </div>

    <!-- MAIN VIEWS CONTAINER -->
    <div class="view-content" id="mainContainer">
      
      <!-- TAB 1: BRIEFING (ALL 20 ITEMS CONTINUOUS, NO DIVIDER, NO FLUFF) -->
      <div id="tab-briefing-view">
        __BRIEFING_CARDS__
      </div>

      <!-- TAB 2: CHANNELS (Clean Search + Direct Lists) -->
      <div id="tab-channels-view" style="display:none;">
        <div class="channels-header">
          <input type="text" class="search-input" placeholder="Search channels..." oninput="filterChannels(this.value)">
        </div>

        <div id="channels-list">
          __CHANNELS_HTML__
        </div>
      </div>

      <!-- TAB 3: BOOKMARKS (Clean Saved Text Articles) -->
      <div id="tab-saved-view" style="display:none;">
        <div id="bookmarks-container" style="padding: 12px 16px;">
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
              <button class="btn-clean-link" onclick="openItemLink('3Blue1Brown Attention', 'Watch', 'bm1')">Watch</button>
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
              <button class="btn-clean-link" onclick="openItemLink('Physionic Saturated Fats', 'Watch', 'bm2')">Watch</button>
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
          <div class="player-title" id="playerTitle">Weekly Briefing Audio</div>
          <div class="player-sub">
            <span id="playerSub">Overview · 14m</span>
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
          <div class="sheet-title">Now Playing</div>
          <button class="btn-close-sheet" onclick="closePlayerSheet()">✕</button>
        </div>

        <div class="sheet-scroll-body">
          <!-- Full Player Hero -->
          <div class="player-hero-deck">
            <div class="full-player-art">TL</div>
            <div class="full-player-title" id="fullSheetTitle">Weekly Briefing Audio</div>
            <div class="full-player-sub" id="fullSheetSub">1 of 4 in Queue</div>

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
              <div class="queue-section-title">Up Next</div>
              <span style="font-size:11px; font-weight:700; color:var(--accent);" id="queueRemainingText">3 items · 38m</span>
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

    function toggleTheme() {
      currentTheme = (currentTheme === 'light') ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', currentTheme);
      const icon = document.getElementById('themeIcon');
      if (currentTheme === 'dark') {
        icon.innerHTML = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
      } else {
        icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
      }
    }

    function switchTab(tab) {
      document.querySelectorAll('.tab-item').forEach(function(t) { t.classList.remove('active'); });
      document.getElementById('nav-' + tab).classList.add('active');

      document.getElementById('tab-briefing-view').style.display = (tab === 'briefing') ? 'block' : 'none';
      document.getElementById('tab-channels-view').style.display = (tab === 'channels') ? 'block' : 'none';
      document.getElementById('tab-saved-view').style.display = (tab === 'saved') ? 'block' : 'none';

      const titleEl = document.getElementById('headerTitle');
      if (tab === 'briefing') {
        titleEl.innerText = 'Weekly Briefing';
      } else if (tab === 'channels') {
        titleEl.innerText = 'Channels';
      } else if (tab === 'saved') {
        titleEl.innerText = 'Bookmarks';
      }
      document.getElementById('mainContainer').scrollTop = 0;
    }

    /* Cloudflare Sync Auto-Pulse Toast */
    let syncTimeout = null;
    function triggerCloudflareSync(eventReason) {
      const toast = document.getElementById('syncToast');
      const text = document.getElementById('syncToastText');
      text.innerText = 'Synced: ' + eventReason;
      toast.classList.add('show');
      if (syncTimeout) clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => toast.classList.remove('show'), 2000);
    }

    /* Open Link & Auto-Mark Watched */
    function openItemLink(title, actionType, id) {
      const card = document.getElementById('brief-card-' + id) || document.getElementById('vcard-' + id);
      if (card) card.classList.add('is-watched');
      
      const chk = document.getElementById('chk-' + id);
      if (chk) {
        chk.checked = true;
        const parts = String(id).split('-');
        if (parts.length === 2) onItemCheckChanged(parts[0], parseInt(parts[1]), 'Source', true);
      }
      
      triggerCloudflareSync(actionType + ': ' + title.substring(0, 18) + '…');
      alert('Opening in ' + (actionType === 'Watch' ? 'YouTube' : 'Safari') + ':\n\n' + title + '\n\n✓ Marked as ' + (actionType === 'Watch' ? 'watched' : 'read'));
    }

    /* Queue Handling */
    function toggleQueueItem(id, title, source, dur) {
      const btn = document.getElementById('btn-queue-' + id) || document.getElementById('btn-vqueue-' + id);
      const isQueued = btn && btn.innerText.includes('Queued');
      
      if (isQueued) {
        if (btn) { btn.innerText = '+ Queue'; btn.style.background = 'var(--surface-elevated)'; }
        queueCount = Math.max(0, queueCount - 1);
        triggerCloudflareSync('Removed from Queue');
      } else {
        if (btn) { btn.innerText = '✓ Queued'; btn.style.background = 'var(--accent-soft)'; }
        queueCount++;
        
        const qlist = document.getElementById('sheet-queue-list');
        const rowId = 'qrow-' + Date.now();
        const row = document.createElement('div');
        row.className = 'queue-item-row';
        row.id = rowId;
        row.innerHTML = `
          <div class="queue-item-left">
            <span class="queue-item-drag">☰</span>
            <div style="min-width:0;">
              <div class="queue-item-title">${title}</div>
              <div class="queue-item-sub">${source} · ${dur}</div>
            </div>
          </div>
          <button class="btn-remove-q" onclick="removeQueueRow('${rowId}')">✕</button>
        `;
        qlist.appendChild(row);
        triggerCloudflareSync('Added to Queue');
      }
      updateQueueUI();
    }

    function removeQueueRow(rowId) {
      const r = document.getElementById(rowId);
      if (r) r.remove();
      queueCount = Math.max(0, queueCount - 1);
      updateQueueUI();
      triggerCloudflareSync('Queue Updated');
    }

    function updateQueueUI() {
      document.getElementById('miniQueueBadge').innerText = queueCount + ' in Queue';
      document.getElementById('queueRemainingText').innerText = queueCount + ' items';
    }

    function openPlayerSheet() {
      document.getElementById('playerSheetOverlay').classList.add('open');
    }

    function closePlayerSheet() {
      document.getElementById('playerSheetOverlay').classList.remove('open');
    }

    /* Bookmarking */
    function toggleBookmarkItem(title, source) {
      triggerCloudflareSync('Saved Bookmark');
      alert('✓ Saved to Bookmarks:\\n\\n' + title);
    }

    function removeBookmark(id) {
      const el = document.getElementById(id);
      if (el) el.remove();
      triggerCloudflareSync('Removed Bookmark');
    }

    /* Channel Accordion & Progress */
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

    function onItemCheckChanged(chId, idx, chName, isChecked) {
      const vcard = document.getElementById('vcard-' + chId + '-' + idx);
      if (vcard) {
        if (isChecked) vcard.classList.add('is-watched');
        else vcard.classList.remove('is-watched');
      }

      const chPanel = document.getElementById('panel-' + chId);
      const allCheckboxes = chPanel.querySelectorAll('input[type="checkbox"]');
      const total = allCheckboxes.length;
      let watched = 0;
      allCheckboxes.forEach(cb => { if (cb.checked) watched++; });

      const progEl = document.getElementById('ch-progress-' + chId);
      const listenBtn = document.getElementById('listen-label-' + chId);
      const unwatched = total - watched;

      if (watched === total) {
        progEl.innerText = '✓ Completed';
        progEl.style.color = 'var(--accent)';
      } else {
        progEl.innerText = watched + '/' + total + ' Completed';
        progEl.style.color = 'var(--text)';
      }

      if (listenBtn) {
        listenBtn.innerText = 'Listen Unwatched (' + unwatched + ')';
      }

      triggerCloudflareSync(chName + ': ' + watched + '/' + total + ' watched');
    }

    /* Smart Unwatched Listening */
    function listenUnwatchedChannel(chId, chName) {
      const chPanel = document.getElementById('panel-' + chId);
      const allCheckboxes = chPanel.querySelectorAll('input[type="checkbox"]');
      let watched = 0, unwatched = 0;
      allCheckboxes.forEach(cb => { if (cb.checked) watched++; else unwatched++; });

      if (unwatched > 0) {
        playAudio('Unwatched Summaries (' + unwatched + ')', chName);
        alert('Listening ' + unwatched + ' unwatched summaries from ' + chName + '.\\n' +
              (watched > 0 ? '(Skipping ' + watched + ' already watched summaries)' : ''));
      } else {
        playAudio('Channel Overview', chName);
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

final_html = MAIN_TEMPLATE.replace("__BRIEFING_CARDS__", briefing_cards_html)
final_html = final_html.replace("__CHANNELS_HTML__", channels_html)

with open(".workflow/mocks/mock1_executive_briefing.html", "w", encoding="utf-8") as f:
    f.write(final_html)

print("Generated clean mock1_executive_briefing.html with all 20 items and 0 fluff text!")
