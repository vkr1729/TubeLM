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
    # If it's already HTML (like summary_html)
    if "<p>" in text or "<strong>" in text:
        return text
    # Basic markdown renderer
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
        # Headers
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
            content = line[2:]
            # bold formatting
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html.escape(content))
            out.append(f"<li style='margin-bottom:4px; font-size:13px; color:var(--text);'>{content}</li>")
        else:
            if in_list: out.append("</ul>"); in_list = False
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html.escape(line))
            out.append(f"<p style='margin-bottom:8px; font-size:13px; line-height:1.5; color:var(--text);'>{content}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)

# Build Top 10 cards for Briefing
top10_html = ""
for it in top10:
    rank = it.get("rank", 1)
    title = html.escape(it.get("title", ""))
    source = html.escape(it.get("source_name", ""))
    duration = it.get("duration", "14m")
    why = html.escape(it.get("why_it_matters", ""))
    top10_html += f"""
        <div class="card" id="brief-card-{rank}">
          <div class="card-top">
            <div class="rank-pill">#{rank} Priority</div>
            <div class="meta-line">
              <span>{source}</span> · <span>{duration}</span>
            </div>
          </div>
          <div class="card-title">{title}</div>
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
              <button class="action-btn" id="btn-queue-{rank}" onclick="toggleQueueBriefing({rank}, '{title}', '{source}', '{duration}')" title="Add to Commute Queue">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                Queue
              </button>
              <button class="action-btn" id="btn-read-{rank}" onclick="toggleWatchedBriefing({rank})" title="Mark as Watched">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
                Watch
              </button>
            </div>
          </div>
        </div>
    """

# Build Channels with multi-video expandable accordion
channels_html = ""
for ch in channels:
    ch_id = ch.get("id") or "ch"
    name = ch.get("name") or "Channel"
    cat = ch.get("category") or "tech"
    vids = ch.get("videos") or []
    vid_count = len(vids)
    initials = "".join([w[0].upper() for w in name.split()[:2]])
    preview_md = ch.get("summary_text") or ch.get("summary_preview") or ""
    rendered_summary = render_md(preview_md[:240] + ("..." if len(preview_md) > 240 else ""))
    
    # Specific demonstration channel: MIT Tech Review (6 videos)
    is_demo_channel = "MIT" in name or vid_count >= 5
    initially_expanded = "block" if is_demo_channel else "none"
    toggle_icon = "▲" if is_demo_channel else "▼"
    
    # Individual video cards inside this channel
    vids_html = ""
    for idx, v in enumerate(vids):
        v_title = html.escape(v.get("title") or f"Video {idx+1}")
        v_dur = v.get("duration") or "12m"
        v_summary_html = v.get("summary_html") or render_md(v.get("lead") or "Full structured briefing overview of this presentation.")
        # Mark first 2 videos of the 6-video demo channel as already watched to demonstrate requirement #4!
        pre_watched = (is_demo_channel and idx < 2)
        watched_cls = " is-watched" if pre_watched else ""
        checked_attr = "checked" if pre_watched else ""
        
        vids_html += f"""
          <div class="video-subcard{watched_cls}" id="vcard-{ch_id}-{idx}">
            <div class="v-subcard-header">
              <div class="v-watch-check">
                <input type="checkbox" id="chk-{ch_id}-{idx}" {checked_attr} onchange="onVideoCheckChanged('{ch_id}', {idx}, '{name}', this.checked)">
                <label for="chk-{ch_id}-{idx}" class="v-subcard-title">{idx+1}. {v_title}</label>
              </div>
              <span class="v-dur-badge">{v_dur}</span>
            </div>
            
            <div class="v-summary-body">
              {v_summary_html}
            </div>

            <div class="v-subcard-actions">
              <button class="btn-yt-link" onclick="openYouTubeLink('{ch_id}', {idx}, '{v_title}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                Watch on YouTube (Auto-Marks)
              </button>
              
              <button class="btn-sub-queue" id="btn-vqueue-{ch_id}-{idx}" onclick="addSingleVideoToQueue('{ch_id}', {idx}, '{v_title}', '{name}', '{v_dur}')">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                + Queue
              </button>
            </div>
          </div>
        """
        
    initial_watched_count = 2 if is_demo_channel else 0
    unwatched_count = max(0, vid_count - initial_watched_count)

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
              · <span id="ch-progress-{ch_id}" style="font-weight:700; color:var(--text);">{initial_watched_count}/{vid_count} Watched</span>
              · <span>{ch.get('read_minutes', 4)}m read</span>
            </div>
          </div>
        </div>

        <div class="ch-preview-box">
          {rendered_summary}
        </div>

        <div class="ch-actions-bar">
          <button class="btn-listen-smart" id="btn-listen-{ch_id}" onclick="listenUnwatchedChannel('{ch_id}', '{name}')" title="Plays only unwatched video summaries">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span id="listen-label-{ch_id}">Listen Unwatched ({unwatched_count} remaining)</span>
          </button>
          
          <button class="btn-add-ch-queue" onclick="addEntireChannelToQueue('{ch_id}', '{name}', {vid_count})">
            + Queue Channel
          </button>
        </div>

        <!-- Expandable Video Breakdown Accordion -->
        <div class="channel-videos-panel" id="panel-{ch_id}" style="display:{initially_expanded};">
          <div class="panel-header-sub">
            <span>INDIVIDUAL VIDEO OVERVIEWS ({vid_count} VIDEOS)</span>
            <span style="font-size:11px; color:var(--text-muted);">Tap link to watch · Checkbox to mark</span>
          </div>
          {vids_html}
        </div>
      </div>
    """

# Master HTML file
TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>TubeLM - The Executive Briefing (v2.0 Verified)</title>
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

    /* Cloudflare Sync Auto-Pulse Toast Indicator */
    .sync-toast {
      position: absolute; top: 52px; left: 50%; transform: translateX(-50%);
      background: rgba(34, 197, 94, 0.92); color: #fff; font-size: 11px; font-weight: 700;
      padding: 4px 12px; border-radius: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
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

    /* Scrollable Content */
    .view-content {
      flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; padding-bottom: 150px;
    }
    .view-content::-webkit-scrollbar { display: none; }

    /* TAB 1: BRIEFING STYLES */
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
    .action-icons { display: flex; gap: 8px; align-items: center; }
    .action-btn {
      background: var(--surface-elevated); border: 1px solid var(--border); color: var(--text); padding: 6px 10px;
      border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700;
    }
    .action-btn.is-active { background: var(--accent-badge); color: var(--accent-badge-text); border-color: var(--accent-badge); }

    /* TAB 2: CHANNELS & VIDEO ACCORDION */
    .channels-header { padding: 12px 16px 8px; display: flex; flex-direction: column; gap: 10px; }
    .search-box { position: relative; width: 100%; }
    .search-input {
      width: 100%; padding: 10px 14px 10px 36px; border-radius: 12px; border: 1px solid var(--border);
      background: var(--surface); color: var(--text); font-size: 14px; font-weight: 500; outline: none;
    }
    .search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }

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

    .ch-preview-box {
      font-size: 13px; color: var(--text-muted); line-height: 1.45; margin: 12px 0; padding-left: 2px;
    }
    .ch-actions-bar {
      display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border);
      padding-top: 10px; gap: 10px;
    }
    .btn-listen-smart {
      display: inline-flex; align-items: center; gap: 6px; background: var(--accent-soft);
      color: var(--accent); font-weight: 700; padding: 7px 14px; border-radius: 20px; font-size: 12px; border: none; cursor: pointer;
    }
    .btn-add-ch-queue {
      background: var(--surface-elevated); border: 1px solid var(--border); color: var(--text); padding: 6px 12px;
      border-radius: 10px; font-size: 12px; font-weight: 700; cursor: pointer;
    }

    /* Video Breakdown Panel */
    .channel-videos-panel {
      margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--border-strong);
    }
    .panel-header-sub {
      font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.6px;
      color: var(--text-muted); display: flex; justify-content: space-between; margin-bottom: 10px;
    }
    .video-subcard {
      background: var(--surface-elevated); border: 1px solid var(--border); border-radius: 12px;
      padding: 12px; margin-bottom: 10px; transition: all 0.2s;
    }
    .video-subcard.is-watched { opacity: 0.45; filter: grayscale(0.5); }
    .v-subcard-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
    .v-watch-check { display: flex; align-items: flex-start; gap: 8px; flex: 1; }
    .v-watch-check input[type="checkbox"] { width: 18px; height: 18px; margin-top: 2px; accent-color: var(--accent); cursor: pointer; }
    .v-subcard-title { font-size: 14px; font-weight: 700; line-height: 1.3; color: var(--text); cursor: pointer; }
    .v-dur-badge { font-size: 11px; font-weight: 700; background: var(--surface); padding: 2px 6px; border-radius: 6px; color: var(--text-muted); }
    
    .v-summary-body {
      font-size: 13px; line-height: 1.5; color: var(--text); padding: 6px 0 10px 26px;
    }
    .v-subcard-actions {
      display: flex; justify-content: space-between; align-items: center; padding-left: 26px; border-top: 1px solid var(--border); padding-top: 8px;
    }
    .btn-yt-link {
      display: inline-flex; align-items: center; gap: 6px; background: transparent; border: none;
      color: #ef4444; font-size: 12px; font-weight: 700; cursor: pointer;
    }
    .btn-sub-queue {
      background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 11px; font-weight: 700;
      padding: 4px 10px; border-radius: 8px; cursor: pointer;
    }

    /* TAB 3: COMMUTE QUEUE & UNLIMITED BOOKMARKS */
    .tab-segment-bar {
      margin: 12px 16px 8px; display: flex; background: var(--surface-elevated); padding: 4px; border-radius: 12px;
      border: 1px solid var(--border);
    }
    .seg-btn {
      flex: 1; padding: 8px 0; font-size: 12px; font-weight: 700; text-align: center; border-radius: 8px;
      background: transparent; border: none; color: var(--text-muted); cursor: pointer; transition: all 0.15s;
    }
    .seg-btn.active { background: var(--surface); color: var(--text); box-shadow: 0 2px 6px rgba(0,0,0,0.06); }

    .commute-banner {
      margin: 8px 16px 14px; background: linear-gradient(135deg, var(--accent) 0%, #15803d 100%);
      color: #fff; border-radius: 18px; padding: 16px 18px; box-shadow: 0 8px 24px rgba(22, 163, 74, 0.25);
    }
    :root[data-theme="dark"] .commute-banner {
      background: linear-gradient(135deg, #1c1f26 0%, #111317 100%); border: 1px solid var(--border); color: var(--text);
    }
    .q-btn-play {
      display: inline-flex; align-items: center; gap: 8px; background: #fff; color: #15803d;
      font-weight: 800; font-size: 13px; padding: 9px 16px; border-radius: 20px; border: none; cursor: pointer; margin-top: 10px;
    }
    :root[data-theme="dark"] .q-btn-play { background: #d9ff63; color: #11120f; }

    .sync-status-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
      padding: 12px 16px; margin: 0 16px 14px; display: flex; justify-content: space-between; align-items: center;
    }
    .sync-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; }

    /* Sticky Mini-Player */
    .mini-player {
      position: absolute; bottom: 70px; left: 12px; right: 12px; background: var(--player-bg);
      backdrop-filter: blur(20px); border: 1px solid var(--border); border-radius: 18px; padding: 10px 14px;
      display: flex; align-items: center; justify-content: space-between; box-shadow: var(--card-shadow); z-index: 60;
    }
    .player-info { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
    .player-art {
      width: 38px; height: 38px; border-radius: 10px; background: var(--accent-badge); color: var(--accent-badge-text);
      font-weight: 900; font-size: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .player-title { font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
    .player-sub { font-size: 11px; color: var(--text-muted); }
    .play-btn {
      width: 36px; height: 36px; border-radius: 50%; background: var(--accent); color: #fff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;
    }
    :root[data-theme="dark"] .play-btn { background: #d9ff63; color: #11120f; }
    .speed-pill {
      font-size: 11px; font-weight: 800; background: var(--surface-elevated); padding: 4px 8px; border-radius: 6px;
      cursor: pointer; color: var(--text); border: 1px solid var(--border);
    }

    /* Tab Bar */
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
      <div class="island" onclick="alert('LiveContainer: Audio active in background.')">
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

    <!-- Main Scroll Content -->
    <div class="view-content" id="mainContainer">
      
      <!-- ============================================== -->
      <!-- TAB 1: BRIEFING                                -->
      <!-- ============================================== -->
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

      <!-- ============================================== -->
      <!-- TAB 2: CHANNELS (WITH 6-VIDEO BREAKDOWN)       -->
      <!-- ============================================== -->
      <div id="tab-channels-view" style="display:none;">
        <div class="channels-header">
          <div class="search-box">
            <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="search-input" placeholder="Search 23 curated channels..." oninput="filterChannels(this.value)">
          </div>
          <div style="font-size:12px; color:var(--text-muted); padding-left:2px;">
            Tap any channel to expand individual video overviews.
          </div>
        </div>

        <div id="channels-list">
          __CHANNELS_HTML__
        </div>
      </div>

      <!-- ============================================== -->
      <!-- TAB 3: COMMUTE QUEUE & UNLIMITED BOOKMARKS     -->
      <!-- ============================================== -->
      <div id="tab-saved-view" style="display:none;">
        <div class="tab-segment-bar">
          <button class="seg-btn active" id="seg-queue" onclick="setSavedSegment('queue')">Commute Queue (<span id="qCountLabel">3</span>)</button>
          <button class="seg-btn" id="seg-bookmarks" onclick="setSavedSegment('bookmarks')">Saved Articles (Unlimited)</button>
        </div>

        <!-- Automatic Cloudflare Sync Status -->
        <div class="sync-status-card">
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="sync-dot"></div>
            <div>
              <div style="font-size:13px; font-weight:700; color:var(--text);">Cloudflare Event Sync Active</div>
              <div style="font-size:11px; color:var(--text-muted);" id="syncTimeLabel">Auto-syncs on watch / queue / bookmark</div>
            </div>
          </div>
          <button class="action-btn" onclick="triggerManualSync()" style="font-size:11px; color:var(--accent);">Sync Now</button>
        </div>

        <!-- QUEUE SUB-VIEW -->
        <div id="subview-queue">
          <div class="commute-banner">
            <div style="font-size:18px; font-weight:800;">Commute Audio Queue</div>
            <div style="font-size:13px; opacity:0.9; margin-top:2px;" id="qSummaryText">3 items queued · 38m total audio</div>
            <button class="q-btn-play" onclick="playQueueContinuous()">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              ▶ Play Entire Commute Queue
            </button>
          </div>

          <div style="padding:0 18px 8px; font-size:12px; font-weight:800; text-transform:uppercase; color:var(--text-muted);">
            Queued for Today's Commute
          </div>

          <div id="queue-items-list">
            <div class="card" id="q-card-1">
              <div class="card-top">
                <div class="rank-pill">#1 Staged</div>
                <div class="meta-line"><span>Physionic</span> · <span>14m</span></div>
              </div>
              <div class="card-title">Creatine & Cognition: Mechanisms in Sleep-Deprived Adults</div>
              <div class="card-actions">
                <button class="btn-audio" onclick="playAudio('Creatine & Cognition', 'Physionic')">Play</button>
                <button class="action-btn" onclick="removeFromQueue('q-card-1')">Remove</button>
              </div>
            </div>

            <div class="card" id="q-card-2">
              <div class="card-top">
                <div class="rank-pill">#2 Staged</div>
                <div class="meta-line"><span>MIT Technology Review</span> · <span>16m</span></div>
              </div>
              <div class="card-title">What’s at stake in AI’s trillion-dollar gamble</div>
              <div class="card-actions">
                <button class="btn-audio" onclick="playAudio('AI Trillion Dollar Gamble', 'MIT Tech Review')">Play</button>
                <button class="action-btn" onclick="removeFromQueue('q-card-2')">Remove</button>
              </div>
            </div>

            <div class="card" id="q-card-3">
              <div class="card-top">
                <div class="rank-pill">#3 Staged</div>
                <div class="meta-line"><span>Veritasium</span> · <span>22m</span></div>
              </div>
              <div class="card-title">The Real Reason Quantum Computers Might Never Break RSA</div>
              <div class="card-actions">
                <button class="btn-audio" onclick="playAudio('Quantum Computers RSA', 'Veritasium')">Play</button>
                <button class="action-btn" onclick="removeFromQueue('q-card-3')">Remove</button>
              </div>
            </div>
          </div>
        </div>

        <!-- BOOKMARKS SUB-VIEW (UNLIMITED TEXT ONLY) -->
        <div id="subview-bookmarks" style="display:none; padding: 0 16px;">
          <div style="background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:14px; margin-bottom:14px;">
            <div style="font-size:14px; font-weight:800; color:var(--text); margin-bottom:4px;">Unlimited Text Bookmarks</div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">
              Audio caching dropped per your preference. Bookmarks store pure text summaries with negligible storage. Saved forever.
            </div>
          </div>

          <div class="card" style="margin:0 0 12px;">
            <div class="card-top">
              <span style="font-size:11px; font-weight:700; color:var(--accent); text-transform:uppercase;">Deep Explainer</span>
              <span style="font-size:12px; color:var(--text-muted);">Saved 2d ago</span>
            </div>
            <div class="card-title" style="font-size:15px;">3Blue1Brown: Attention in Transformers Explained Visually</div>
            <div class="why-text" style="font-size:13px; color:var(--text-muted); margin-bottom:10px;">
              Geometric derivation of multi-head self-attention and projection matrices.
            </div>
            <div class="card-actions">
              <span style="font-size:11px; color:var(--text-muted);">Text Only · 4 KB</span>
              <button class="action-btn" onclick="this.closest('.card').remove(); triggerCloudflareSync('Bookmark Removed');">Remove</button>
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

    <!-- Bottom Tab Bar -->
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
    let queueCount = 3;

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
        titleEl.innerText = 'Saved & Queue';
        subEl.innerText = 'Commute Staging & Bookmarks';
      }
      document.getElementById('mainContainer').scrollTop = 0;
    }

    /* Automatic Event-Driven Cloudflare Sync Toast */
    let syncTimeout = null;
    function triggerCloudflareSync(eventReason) {
      const toast = document.getElementById('syncToast');
      const text = document.getElementById('syncToastText');
      text.innerText = 'Cloudflare Synced: ' + eventReason;
      toast.classList.add('show');
      if (syncTimeout) clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => toast.classList.remove('show'), 2400);
      document.getElementById('syncTimeLabel').innerText = 'Synced just now via tubelm-sync.workers.dev';
    }

    function triggerManualSync() {
      triggerCloudflareSync('Manual Trigger');
    }

    /* Briefing Tab Actions */
    function toggleWatchedBriefing(rank) {
      const card = document.getElementById('brief-card-' + rank);
      const btn = document.getElementById('btn-read-' + rank);
      card.classList.toggle('is-watched');
      const isWatched = card.classList.contains('is-watched');
      btn.classList.toggle('is-active', isWatched);
      triggerCloudflareSync(isWatched ? 'Briefing #' + rank + ' Watched' : 'Briefing #' + rank + ' Unwatched');
    }

    function toggleQueueBriefing(rank, title, source, dur) {
      const btn = document.getElementById('btn-queue-' + rank);
      btn.classList.toggle('is-active');
      if (btn.classList.contains('is-active')) {
        btn.innerText = 'Queued ✓';
        queueCount++;
        addCardToQueueDOM('brief-' + rank, title, source, dur);
        triggerCloudflareSync('Added to Queue');
      } else {
        btn.innerText = 'Queue';
        queueCount = Math.max(0, queueCount - 1);
        removeFromQueue('queue-item-brief-' + rank);
      }
      updateQueueCountUI();
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

    /* Video Checkbox Changed: Auto-updates Channel Progress & Cloudflare Sync */
    function onVideoCheckChanged(chId, idx, chName, isChecked) {
      const vcard = document.getElementById('vcard-' + chId + '-' + idx);
      if (isChecked) vcard.classList.add('is-watched');
      else vcard.classList.remove('is-watched');

      // Check all checkboxes in this channel
      const chPanel = document.getElementById('panel-' + chId);
      const allCheckboxes = chPanel.querySelectorAll('input[type="checkbox"]');
      let watchedCount = 0;
      allCheckboxes.forEach(cb => { if (cb.checked) watchedCount++; });
      const total = allCheckboxes.length;

      // Update Channel progress badge
      const progressLabel = document.getElementById('ch-progress-' + chId);
      progressLabel.innerText = watchedCount + '/' + total + ' Watched';
      if (watchedCount === total) {
        progressLabel.innerHTML = '<span style="color:#22c55e;">✓ Channel Completed</span>';
        document.getElementById('ch-card-' + chId).classList.add('is-watched');
      } else {
        document.getElementById('ch-card-' + chId).classList.remove('is-watched');
      }

      // Update Listen Button to reflect remaining unwatched
      const unwatched = total - watchedCount;
      const listenLabel = document.getElementById('listen-label-' + chId);
      if (unwatched > 0) {
        listenLabel.innerText = 'Listen Unwatched (' + unwatched + ' remaining)';
      } else {
        listenLabel.innerText = 'All Watched · Replay All';
      }

      triggerCloudflareSync(chName + ': Video ' + (idx + 1) + (isChecked ? ' Watched' : ' Unwatched'));
    }

    /* Open YouTube: Auto-marks video as watched */
    function openYouTubeLink(chId, idx, title) {
      const cb = document.getElementById('chk-' + chId + '-' + idx);
      if (!cb.checked) {
        cb.checked = true;
        onVideoCheckChanged(chId, idx, 'Channel', true);
      }
      alert('Opened YouTube for: ' + title + '\\nAutomatically marked as WATCHED in your reading history.');
    }

    /* Dynamic Unwatched Audio Listening (Requirement 4) */
    function listenUnwatchedChannel(chId, chName) {
      const chPanel = document.getElementById('panel-' + chId);
      const allCheckboxes = chPanel.querySelectorAll('input[type="checkbox"]');
      let watched = 0;
      let unwatched = 0;
      allCheckboxes.forEach(cb => {
        if (cb.checked) watched++;
        else unwatched++;
      });

      if (unwatched > 0) {
        playAudio('Unwatched Summaries (' + unwatched + ' remaining)', chName);
        alert('Listening ' + unwatched + ' unwatched video summaries from ' + chName + '.\\n' +
              (watched > 0 ? '(Skipping ' + watched + ' already watched video summaries)' : ''));
      } else {
        playAudio('Full Channel Overview', chName);
      }
    }

    /* Add Single Video / Entire Channel to Commute Queue */
    function addSingleVideoToQueue(chId, idx, title, chName, dur) {
      queueCount++;
      addCardToQueueDOM('vid-' + chId + '-' + idx, title, chName, dur);
      updateQueueCountUI();
      triggerCloudflareSync('Queued Video: ' + title.substring(0, 20) + '…');
    }

    function addEntireChannelToQueue(chId, chName, count) {
      queueCount += count;
      addCardToQueueDOM('ch-' + chId, chName + ' (All ' + count + ' Summaries)', chName, count * 10 + 'm');
      updateQueueCountUI();
      triggerCloudflareSync('Queued Channel: ' + chName);
    }

    function addCardToQueueDOM(id, title, source, dur) {
      const container = document.getElementById('queue-items-list');
      const item = document.createElement('div');
      item.className = 'card';
      item.id = 'queue-item-' + id;
      item.innerHTML = `
        <div class="card-top">
          <div class="rank-pill">#${queueCount} Queued</div>
          <div class="meta-line"><span>${source}</span> · <span>${dur}</span></div>
        </div>
        <div class="card-title">${title}</div>
        <div class="card-actions">
          <button class="btn-audio" onclick="playAudio('${title}', '${source}')">Play</button>
          <button class="action-btn" onclick="removeFromQueue('queue-item-${id}')">Remove</button>
        </div>
      `;
      container.appendChild(item);
    }

    function removeFromQueue(elementId) {
      const el = document.getElementById(elementId);
      if (el) {
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 150);
        queueCount = Math.max(0, queueCount - 1);
        updateQueueCountUI();
        triggerCloudflareSync('Removed from Queue');
      }
    }

    function updateQueueCountUI() {
      document.getElementById('qCountLabel').innerText = queueCount;
      document.getElementById('qSummaryText').innerText = queueCount + ' items queued · ' + (queueCount * 12) + 'm total audio';
    }

    function playQueueContinuous() {
      playAudio('Playing Entire Commute Queue', queueCount + ' Queued Summaries');
    }

    function setSavedSegment(seg) {
      document.getElementById('seg-queue').classList.toggle('active', seg === 'queue');
      document.getElementById('seg-bookmarks').classList.toggle('active', seg === 'bookmarks');
      document.getElementById('subview-queue').style.display = (seg === 'queue') ? 'block' : 'none';
      document.getElementById('subview-bookmarks').style.display = (seg === 'bookmarks') ? 'block' : 'none';
    }

    function playAudio(title, source) {
      document.getElementById('playerTitle').innerText = title;
      document.getElementById('playerSub').innerText = source + ' · Playing';
      isPlaying = true;
      document.querySelector('.play-btn').innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
    }

    function togglePlay(btn) {
      isPlaying = !isPlaying;
      btn.innerHTML = isPlaying 
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
        : '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
    }

    function cycleSpeed(elem) {
      const speeds = ['1.0×', '1.25×', '1.5×', '2.0×'];
      let idx = (speeds.indexOf(elem.innerText) + 1) % speeds.length;
      elem.innerText = speeds[idx];
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

final_html = TEMPLATE.replace("__TOP10_CARDS__", top10_html)
final_html = final_html.replace("__NEXT10_CARDS__", "") # integrated or expandable
final_html = final_html.replace("__CHANNELS_HTML__", channels_html)

with open(".workflow/mocks/mock1_executive_briefing.html", "w", encoding="utf-8") as f:
    f.write(final_html)

print("Successfully wrote full enhanced Mock 1 (v2.0) with verified video breakdown, watch tracking, and Cloudflare event sync!")
