#!/usr/bin/env python3
"""
Generate Xcode .colorset JSON files from design/tokens.json.

Usage:
    python3 design/generate-colorsets.py

Writes color sets to macos/Sources/Assets.xcassets/ so the macOS app and
website always share the same hex values from a single source of truth.
"""
import json
import os

COLORSET_MAP = {
    "accent":       "AccentColor",
    "neon-pink":    "NeonPink",
    "neon-yellow":  "NeonYellow",
    "neon-cyan":    "NeonCyan",
    "neon-purple":  "NeonPurple",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENS_PATH = os.path.join(SCRIPT_DIR, "tokens.json")
XCASSETS_PATH = os.path.join(SCRIPT_DIR, "../macos/Sources/Assets.xcassets")


def hex_to_rgb_float(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0


def make_colorset(hex_color: str) -> dict:
    r, g, b = hex_to_rgb_float(hex_color)
    return {
        "colors": [
            {
                "color": {
                    "color-space": "srgb",
                    "components": {
                        "alpha": "1.000",
                        "red":   f"{r:.3f}",
                        "green": f"{g:.3f}",
                        "blue":  f"{b:.3f}",
                    },
                },
                "idiom": "universal",
            }
        ],
        "info": {"author": "xcode", "version": 1},
    }


with open(TOKENS_PATH) as f:
    tokens = json.load(f)

colors = tokens["colors"]

for token_key, colorset_name in COLORSET_MAP.items():
    hex_color = colors[token_key]
    colorset_dir = os.path.join(XCASSETS_PATH, f"{colorset_name}.colorset")
    os.makedirs(colorset_dir, exist_ok=True)
    contents_path = os.path.join(colorset_dir, "Contents.json")
    with open(contents_path, "w") as f:
        json.dump(make_colorset(hex_color), f, indent=2)
        f.write("\n")
    print(f"  {colorset_name}.colorset  ({hex_color})")

print("Done.")
