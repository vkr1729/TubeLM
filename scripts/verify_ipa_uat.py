#!/usr/bin/env python3
"""
Automated UAT Host Verification Script for TubeLM iOS IPA
Executes black-box acceptance tests SEC-01, SEC-02, SEC-06, SEC-07 from .workflow/UAT_PLAN.md
"""

import sys
import os
import zipfile
import plistlib
import tempfile
from PIL import Image

def verify_ipa(ipa_path):
    print(f"=== Running Automated UAT Verification on {ipa_path} ===")
    assert os.path.exists(ipa_path), f"IPA file does not exist: {ipa_path}"
    
    with zipfile.ZipFile(ipa_path, 'r') as z:
        namelist = z.namelist()
        
        # 1. SEC-01: Five icons inside the IPA, correct sizes
        print("\n--- SEC-01: Five icons inside IPA, correct sizes [P0] ---")
        expected_icons = {
            "Payload/TubeLM.app/AppIcon.png": (1024, 1024),
            "Payload/TubeLM.app/AppIcon60x60@2x.png": (120, 120),
            "Payload/TubeLM.app/AppIcon60x60@3x.png": (180, 180),
            "Payload/TubeLM.app/AppIcon76x76@2x.png": (152, 152),
            "Payload/TubeLM.app/AppIcon83.5x83.5@2x.png": (167, 167),
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for icon_path, (exp_w, exp_h) in expected_icons.items():
                assert icon_path in namelist, f"SEC-01 FAIL: Missing icon {icon_path} in IPA"
                z.extract(icon_path, tmpdir)
                extracted_path = os.path.join(tmpdir, icon_path)
                with Image.open(extracted_path) as img:
                    assert img.size == (exp_w, exp_h), f"SEC-01 FAIL: {icon_path} size is {img.size}, expected {(exp_w, exp_h)}"
                    assert img.mode in ("RGB", "RGBA"), f"SEC-01 FAIL: {icon_path} mode is {img.mode}"
                print(f"  ✓ {os.path.basename(icon_path)} verified: {exp_w}x{exp_h} {img.mode}")
        print("SEC-01: PASS (5/5 icons present with exact dimensions)")
        
        # 2. SEC-02 & SEC-06: Info.plist declarations and platform keys
        print("\n--- SEC-02 & SEC-06: Info.plist declarations & platform keys [P0] ---")
        plist_entry = "Payload/TubeLM.app/Info.plist"
        assert plist_entry in namelist, f"Missing {plist_entry} in IPA"
        
        plist_data = z.read(plist_entry)
        plist = plistlib.loads(plist_data)
        
        # SEC-02 checks
        assert "CFBundleIcons" in plist, "SEC-02 FAIL: CFBundleIcons missing from Info.plist"
        assert "CFBundlePrimaryIcon" in plist["CFBundleIcons"], "SEC-02 FAIL: CFBundlePrimaryIcon missing in CFBundleIcons"
        primary_files = plist["CFBundleIcons"]["CFBundlePrimaryIcon"].get("CFBundleIconFiles", [])
        assert "AppIcon60x60" in primary_files, f"SEC-02 FAIL: AppIcon60x60 not in CFBundleIconFiles: {primary_files}"
        assert plist["CFBundleIcons"]["CFBundlePrimaryIcon"].get("CFBundleIconName") == "AppIcon", "SEC-02 FAIL: CFBundleIconName != AppIcon"
        
        assert "CFBundleIcons~ipad" in plist, "SEC-02 FAIL: CFBundleIcons~ipad missing from Info.plist"
        ipad_files = plist["CFBundleIcons~ipad"]["CFBundlePrimaryIcon"].get("CFBundleIconFiles", [])
        assert "AppIcon76x76" in ipad_files and "AppIcon83.5x83.5" in ipad_files, f"SEC-02 FAIL: iPad icon files missing stems: {ipad_files}"
        
        assert plist.get("CFBundleIconFile") == "AppIcon", "SEC-02 FAIL: CFBundleIconFile != AppIcon"
        print("SEC-02: PASS (CFBundleIcons, CFBundleIcons~ipad, CFBundleIconFiles properly declared)")
        
        # SEC-06 checks
        assert plist.get("CFBundleSupportedPlatforms") == ["iPhoneOS"], f"SEC-06 FAIL: CFBundleSupportedPlatforms != ['iPhoneOS'], got {plist.get('CFBundleSupportedPlatforms')}"
        assert plist.get("MinimumOSVersion") == "17.0", f"SEC-06 FAIL: MinimumOSVersion != '17.0', got {plist.get('MinimumOSVersion')}"
        assert plist.get("CFBundlePackageType") == "APPL", f"SEC-06 FAIL: CFBundlePackageType != 'APPL'"
        assert plist.get("CFBundleSignature") == "????", f"SEC-06 FAIL: CFBundleSignature != '????'"
        assert plist.get("LSRequiresIPhoneOS") is True, f"SEC-06 FAIL: LSRequiresIPhoneOS is not true"
        assert "arm64" in plist.get("UIRequiredDeviceCapabilities", []), f"SEC-06 FAIL: arm64 missing from UIRequiredDeviceCapabilities"
        assert "audio" in plist.get("UIBackgroundModes", []), f"SEC-06 FAIL: audio missing from UIBackgroundModes"
        assert "UILaunchScreen" in plist, f"SEC-06 FAIL: UILaunchScreen missing"
        print("SEC-06: PASS (All mandatory iOS platform keys verified)")
        
        # 3. SEC-07: Mach-O binary checks
        print("\n--- SEC-07: Mach-O Binary in bundle [P0] ---")
        binary_entry = "Payload/TubeLM.app/TubeLM"
        assert binary_entry in namelist, f"SEC-07 FAIL: Missing binary {binary_entry} in IPA"
        bin_info = z.getinfo(binary_entry)
        assert bin_info.file_size > 0, "SEC-07 FAIL: TubeLM binary is 0 bytes"
        bin_header = z.read(binary_entry)[:32]
        import struct
        magic = struct.unpack("<I", bin_header[:4])[0]
        assert magic == 0xfeedfacf, f"SEC-07 FAIL: Not a 64-bit Mach-O binary (magic={hex(magic)})"
        cputype = struct.unpack("<I", bin_header[4:8])[0]
        assert cputype == 16777228, f"SEC-07 FAIL: Not an arm64 binary (cputype={cputype})"
        print(f"  ✓ Mach-O 64-bit arm64 binary verified ({bin_info.file_size:,} bytes)")
        print("SEC-07: PASS")
        
    print("\n=======================================================")
    print(f"✓ ALL AUTOMATED HOST UAT GATES PASSED FOR {ipa_path}")
    print("=======================================================")

if __name__ == "__main__":
    ipa = sys.argv[1] if len(sys.argv) > 1 else "build/TubeLM.ipa"
    verify_ipa(ipa)
