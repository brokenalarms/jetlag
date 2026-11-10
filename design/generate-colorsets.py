#!/usr/bin/env python3
"""
Generate Xcode .colorset JSON files from design/tokens.json.

Usage:
    python3 design/generate-colorsets.py           # write the color sets
    python3 design/generate-colorsets.py --check   # exit 1 if any differ from tokens

Writes color sets to macos/Sources/Assets.xcassets/ so the macOS app and
website always share the same hex values from a single source of truth.

COLORSET_MAP lists every token the app reads (Theme.swift). The background
tokens are web-only: the app uses system backgrounds.
"""
import argparse
import json
import os
import sys

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


def colorset_text(hex_color: str) -> str:
    return json.dumps(make_colorset(hex_color), indent=2) + "\n"


def contents_path(colorset_name: str) -> str:
    return os.path.join(XCASSETS_PATH, f"{colorset_name}.colorset", "Contents.json")


def write(colors: dict) -> None:
    for token_key, colorset_name in COLORSET_MAP.items():
        hex_color = colors[token_key]
        path = contents_path(colorset_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(colorset_text(hex_color))
        print(f"  {colorset_name}.colorset  ({hex_color})")
    print("Done.")


def check(colors: dict) -> int:
    """Return the number of color sets that are missing or differ from tokens."""
    drifted = 0
    for token_key, colorset_name in COLORSET_MAP.items():
        path = contents_path(colorset_name)
        expected = make_colorset(colors[token_key])
        try:
            with open(path) as f:
                actual = json.load(f)
        except FileNotFoundError:
            print(f"  missing: {colorset_name}.colorset (token {token_key})")
            drifted += 1
            continue
        if actual != expected:
            print(f"  differs: {colorset_name}.colorset (token {token_key} = {colors[token_key]})")
            drifted += 1
    if drifted:
        print("Color sets are out of date. Run: python3 design/generate-colorsets.py")
    else:
        print("Color sets match design/tokens.json.")
    return drifted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare color sets with tokens without writing; exit 1 on drift")
    args = parser.parse_args()

    with open(TOKENS_PATH) as f:
        colors = json.load(f)["colors"]

    if args.check:
        sys.exit(1 if check(colors) else 0)
    write(colors)


if __name__ == "__main__":
    main()
