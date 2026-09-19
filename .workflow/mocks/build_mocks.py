import json
import html
from pathlib import Path

data_path = Path(".workflow/mocks/mock_data.json")
if not data_path.exists():
    print("mock_data.json not found")
    exit(1)

with open(data_path, "r", encoding="utf-8") as f:
    data = json.load(f)

run_date = data.get("run_date", "2026-09-18")
top20 = data.get("top20", {}).get("items", [])
channels = data.get("channels", [])

top10 = top20[:10]
next10 = top20[10:20]

print(f"Loaded {len(top20)} top items and {len(channels)} channels.")

# Base iOS Shell CSS & SVG Icons
SHARED_HEAD = """
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; margin: 0; padding: 0; }
    html, body { height: 100%; width: 100%; overflow: hidden; background: #000; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", sans-serif; }
    
    /* iOS Phone Container */
    .ios-shell {
      display: flex; flex-direction: column; height: 100%; width: 100%; max-width: 430px; margin: 0 auto;
      position: relative; overflow: hidden; background: var(--bg-main); color: var(--text-main);
      box-shadow: 0 0 60px rgba(0,0,0,0.8);
    }
    
    /* iOS Dynamic Island & Status Bar */
    .ios-status-bar {
      height: 48px; padding: 12px 24px 0 24px; display: flex; justify-content: space-between; align-items: center;
      font-size: 14px; font-weight: 600; z-index: 100; flex-shrink: 0; position: relative;
    }
    .dynamic-island {
      position: absolute; left: 50%; top: 10px; transform: translateX(-50%);
      width: 120px; height: 32px; background: #000; border-radius: 20px;
      display: flex; align-items: center; justify-content: space-between; padding: 0 10px;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      cursor: pointer; z-index: 101;
    }
    .dynamic-island.expanded {
      width: 280px; height: 48px; top: 8px;
    }
    .island-left { display: flex; align-items: center; gap: 6px; }
    .island-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); }
    .island-wave { width: 16px; height: 12px; display: flex; align-items: flex-end; gap: 2px; }
    .island-wave span { width: 3px; background: var(--accent); border-radius: 1px; animation: bounce 1s infinite ease-in-out; }
    .island-wave span:nth-child(1) { height: 6px; animation-delay: 0.1s; }
    .island-wave span:nth-child(2) { height: 12px; animation-delay: 0.3s; }
    .island-wave span:nth-child(3) { height: 8px; animation-delay: 0.2s; }
    @keyframes bounce { 0%, 100% { height: 4px; } 50% { height: 12px; } }
    
    .status-icons { display: flex; align-items: center; gap: 6px; font-size: 12px; }
    
    /* Scrollable Content */
    .ios-scroll-content {
      flex: 1; overflow-y: auto; overflow-x: hidden; -webkit-overflow-scrolling: touch;
      padding-bottom: 100px;
    }
    .ios-scroll-content::-webkit-scrollbar { display: none; }
    
    /* Home Indicator */
    .ios-home-bar {
      position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%);
      width: 140px; height: 5px; background: rgba(255,255,255,0.4); border-radius: 10px;
      pointer-events: none; z-index: 110;
    }
    
    /* Common utility badges */
    .badge {
      display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .badge-tech { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
    .badge-health { background: rgba(244, 63, 94, 0.15); color: #f43f5e; }
    .badge-deep { background: rgba(168, 85, 247, 0.15); color: #c084fc; }
    
    /* Native Haptics simulation */
    .btn-press:active { transform: scale(0.96); opacity: 0.85; transition: transform 0.1s ease; }
  </style>
"""

# Let's define the 5 HTML mock generators
