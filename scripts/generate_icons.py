#!/usr/bin/env python3
"""
Generate high-fidelity iOS app icons for TubeLM adhering to the Executive Briefing
design system (rich emerald green, dark contrast, lime accent #d9ff63, crisp monogram).
Outputs standard iOS dimensions:
  - 1024x1024 (AppStore / Master / LiveContainer high-res)
  - 180x180   (iPhone 60pt @3x)
  - 120x120   (iPhone 60pt @2x)
  - 167x167   (iPad Pro 83.5pt @2x)
  - 152x152   (iPad 76pt @2x)
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_icon_master(size=2048):
    # Render at 2x master resolution (2048x2048) with supersampling for crisp edges
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background gradient: Emerald green (#15803d to #0f3e1f)
    top_color = (21, 128, 61, 255)     # #15803d
    bot_color = (15, 62, 31, 255)      # #0f3e1f
    for y in range(size):
        factor = y / size
        r = int(top_color[0] * (1 - factor) + bot_color[0] * factor)
        g = int(top_color[1] * (1 - factor) + bot_color[1] * factor)
        b = int(top_color[2] * (1 - factor) + bot_color[2] * factor)
        draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

    # 2. Subtle radial glow at upper-center
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    center_x, center_y = size // 2, int(size * 0.35)
    glow_radius = int(size * 0.45)
    glow_draw.ellipse(
        [center_x - glow_radius, center_y - glow_radius, center_x + glow_radius, center_y + glow_radius],
        fill=(34, 197, 94, 60) # #22c55e with alpha
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=int(size * 0.12)))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # 3. Inner Card / Badge Plate (subtle rounded rect plate)
    plate_margin = int(size * 0.16)
    plate_radius = int(size * 0.18)
    plate_bbox = [plate_margin, plate_margin, size - plate_margin, size - plate_margin]
    
    # Plate drop shadow
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [plate_margin, plate_margin + int(size * 0.02), size - plate_margin, size - plate_margin + int(size * 0.02)],
        radius=plate_radius,
        fill=(5, 25, 12, 120)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(size * 0.04)))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    # Plate body
    draw.rounded_rectangle(
        plate_bbox,
        radius=plate_radius,
        fill=(18, 24, 20, 245), # Deep charcoal slate (#121814)
        outline=(52, 211, 153, 90), # Subtle emerald rim (#34d399)
        width=int(size * 0.008)
    )

    # 4. Central Monogram & Icon Graphics
    # Monogram: "TL"
    # Try finding a bold system font, fallback to drawn geometric shapes if not present
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"
    ]
    font = None
    for p in font_paths:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, int(size * 0.38))
                break
            except Exception:
                continue

    # Center coordinates
    cx = size // 2
    cy = int(size * 0.48)

    if font:
        text = "TL"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = cx - tw // 2 - bbox[0]
        ty = cy - th // 2 - bbox[1]

        # Draw text with crisp lime color (#d9ff63)
        draw.text((tx, ty), text, font=font, fill=(217, 255, 99, 255))
    else:
        # Crisp geometric fallback for TL
        # Letter T
        t_left = int(size * 0.28)
        t_right = int(size * 0.48)
        t_top = int(size * 0.32)
        t_bar_h = int(size * 0.07)
        t_stem_w = int(size * 0.07)
        t_bot = int(size * 0.68)
        draw.rectangle([t_left, t_top, t_right, t_top + t_bar_h], fill=(217, 255, 99, 255))
        draw.rectangle([(t_left + t_right - t_stem_w) // 2, t_top, (t_left + t_right + t_stem_w) // 2, t_bot], fill=(217, 255, 99, 255))

        # Letter L
        l_left = int(size * 0.52)
        l_right = int(size * 0.72)
        l_top = int(size * 0.32)
        l_stem_w = int(size * 0.07)
        l_bar_h = int(size * 0.07)
        l_bot = int(size * 0.68)
        draw.rectangle([l_left, l_top, l_left + l_stem_w, l_bot], fill=(217, 255, 99, 255))
        draw.rectangle([l_left, l_bot - l_bar_h, l_right, l_bot], fill=(217, 255, 99, 255))

    # 5. Signal dot / badge (lime accent dot at bottom center indicating audio/stream)
    dot_y = int(size * 0.74)
    dot_r = int(size * 0.032)
    draw.ellipse(
        [cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
        fill=(34, 197, 94, 255) # Green #22c55e
    )
    # Inner bright dot
    inner_r = int(dot_r * 0.5)
    draw.ellipse(
        [cx - inner_r, dot_y - inner_r, cx + inner_r, dot_y + inner_r],
        fill=(217, 255, 99, 255) # Lime #d9ff63
    )

    return img

def main():
    target_dir = os.path.join(os.path.dirname(__file__), "../ios/TubeLM")
    os.makedirs(target_dir, exist_ok=True)

    master = create_icon_master(size=2048)

    sizes = {
        "AppIcon.png": (1024, 1024),
        "AppIcon60x60@2x.png": (120, 120),
        "AppIcon60x60@3x.png": (180, 180),
        "AppIcon76x76@2x.png": (152, 152),
        "AppIcon83.5x83.5@2x.png": (167, 167),
    }

    print(f"Generating iOS icon set in {target_dir}...")
    for filename, (w, h) in sizes.items():
        out_path = os.path.join(target_dir, filename)
        resized = master.resize((w, h), Image.Resampling.LANCZOS)
        # Convert to RGB (iOS icons should not have an alpha channel)
        rgb_img = Image.new("RGB", (w, h), (15, 62, 31))
        rgb_img.paste(resized, mask=resized.split()[3])
        rgb_img.save(out_path, format="PNG", optimize=True)
        print(f"  ✓ Created {filename} ({w}x{h})")

    print("All icons successfully generated!")

if __name__ == "__main__":
    main()
