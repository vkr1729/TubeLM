#!/usr/bin/env python3
"""
Generate graceful, high-fidelity iOS app icons for TubeLM directly from Resources/AppIcon.svg
inspired by Health_Span and StriveRing-ios.
Outputs standard iOS dimensions:
  - 1024x1024 (AppStore / Master / LiveContainer high-res)
  - 180x180   (iPhone 60pt @3x)
  - 120x120   (iPhone 60pt @2x)
  - 167x167   (iPad Pro 83.5pt @2x)
  - 152x152   (iPad 76pt @2x)
"""

import os
import subprocess
import tempfile
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SVG_PATH = os.path.join(REPO_ROOT, "Resources/AppIcon.svg")
TARGET_DIR = os.path.join(REPO_ROOT, "ios/TubeLM")

def render_svg_to_master_png(svg_path, size=1024):
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ width: {size}px; height: {size}px; overflow: hidden; background: #102521; }}
  img {{ width: {size}px; height: {size}px; display: block; }}
</style>
</head>
<body>
  <img src="file://{os.path.abspath(svg_path)}" />
</body>
</html>"""

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
        f.write(html_content)
        tmp_html = f.name

    tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name

    try:
        subprocess.run([
            "/usr/bin/google-chrome",
            "--headless",
            "--disable-gpu",
            "--force-device-scale-factor=1",
            f"--window-size={size},{size}",
            f"--screenshot={tmp_png}",
            f"file://{tmp_html}"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        img = Image.open(tmp_png)
        # Ensure RGB format
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img
    finally:
        if os.path.exists(tmp_html):
            os.remove(tmp_html)
        if os.path.exists(tmp_png):
            os.remove(tmp_png)

def main():
    os.makedirs(TARGET_DIR, exist_ok=True)
    print(f"Rendering graceful master icon from {SVG_PATH}...")
    master = render_svg_to_master_png(SVG_PATH, size=1024)

    sizes = {
        "AppIcon.png": (1024, 1024),
        "AppIcon60x60@2x.png": (120, 120),
        "AppIcon60x60@3x.png": (180, 180),
        "AppIcon76x76@2x.png": (152, 152),
        "AppIcon83.5x83.5@2x.png": (167, 167),
    }

    print(f"Generating iOS icon set in {TARGET_DIR}...")
    for filename, (w, h) in sizes.items():
        out_path = os.path.join(TARGET_DIR, filename)
        if (w, h) == (1024, 1024):
            master.save(out_path, format="PNG", optimize=True)
        else:
            resized = master.resize((w, h), Image.Resampling.LANCZOS)
            resized.save(out_path, format="PNG", optimize=True)
        print(f"  ✓ Created {filename} ({w}x{h})")

    print("All graceful icons successfully generated!")

if __name__ == "__main__":
    main()
