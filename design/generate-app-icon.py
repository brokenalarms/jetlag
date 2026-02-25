#!/usr/bin/env python3
"""
Generate the Jetlag app icon as a 1024×1024 PNG.

Renders the Amsterdam vs Seoul 'before Jetlag' timeline: two clip rows
(blue 'jet', green 'lag') on a shared time axis, showing the 7-hour
misalignment. 'jet' and 'lag' sit inside the bars exactly as file labels
appear in the web timeline component.

Usage:
    python3 design/generate-app-icon.py

Outputs:
    macos/Sources/Assets.xcassets/AppIcon.appiconset/AppIcon.png
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    import subprocess
    import tempfile

    venv_dir = Path(tempfile.mkdtemp(prefix="jetlag-icon-"))
    print(f"  Pillow not found — creating temporary venv at {venv_dir}")
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    venv_python = str(venv_dir / "bin" / "python3")
    subprocess.check_call([venv_python, "-m", "pip", "install", "Pillow", "-q"])
    raise SystemExit(subprocess.call([venv_python] + sys.argv))


# ── Design tokens ──────────────────────────────────────────────────────────────

SIZE = 1024
BG_COLOR = (10, 10, 11)                # #0a0a0b

BLUE_FILL    = (59,  130, 246,  90)    # blue-500  ~35 %
BLUE_BORDER  = (96,  165, 250,  70)    # blue-400  ~27 %
BLUE_TEXT    = (147, 197, 253, 180)    # blue-300  ~70 %

GREEN_FILL   = (34,  197,  94,  90)   # green-500 ~35 %
GREEN_BORDER = (74,  222, 128,  70)   # green-400 ~27 %
GREEN_TEXT   = (134, 239, 172, 180)   # green-300 ~70 %

LABEL_COLOR  = (255, 255, 255,  90)   # white / 35  — time digits
TZ_CORRECT   = (134, 239, 172, 180)   # green-300 / 70
TZ_WRONG     = (248, 113, 113, 180)   # red-400 / 70


# ── Timeline data (Amsterdam vs Seoul, before Jetlag) ─────────────────────────

CLIPS = [
    {
        'time': '02:00', 'tz': '+04:00',
        'label': 'jet', 'correct': False,
    },
    {
        'time': '07:00', 'tz': '+09:00',
        'label': 'lag', 'correct': True,
    },
]


# ── Layout fractions  (these are the only design knobs) ───────────────────────
#
# All pixel dimensions are derived from SIZE × a named fraction so that the
# composition stays proportional at any resolution.

# Canvas margins
CANVAS_PAD_FRAC    = 1 / 16    # outer margin each side  → 64 px at 1024

# Horizontal split: label-column : gap : bar-area
LABEL_COL_FRAC     = 7 / 32    # label col / content_w   ≈ 21.9 %
LABEL_GAP_FRAC     = 3 / 128   # label↔bar gap / content_w ≈ 2.3 %

# Vertical fill: how much of the canvas height the content block occupies
CONTENT_FILL_FRAC  = 9 / 16    # content_h / SIZE         = 56.25 %
ROW_GAP_OF_CONTENT = 1 / 9     # inter-row gap / content_h ≈ 11.1 %

# Bar proportions
BAR_H_FRAC         = 1 / 2     # bar height / row height
BAR_R_FRAC         = 1 / 8     # bar corner-radius / bar height
CARD_R_FRAC        = 1 / 14    # card corner-radius / row height

# Font sizes as fractions of BAR_H
FONT_BAR_FRAC      = 0.65      # bar label ('jet' / 'lag')
FONT_TIME_FRAC     = 0.38      # time digits ('14:12')
FONT_TZ_FRAC       = 0.25      # tz label

# Glow effect as fractions of BAR_H
GLOW_EXPAND_FRAC   = 0.17      # rect expansion before Gaussian blur
GLOW_RADIUS_FRAC   = 0.31      # Gaussian blur radius

# Label-column line spacing as fraction of ROW_H
LABEL_LINE_GAP_FRAC = 1 / 16

# Clip-bar width ratio comes from the web timeline component — the only
# "artistic" constant that is fixed to the original visual rather than derived
# from the icon canvas.
CLIP_W_RATIO        = 100 / 290


# ── Derived layout constants ──────────────────────────────────────────────────

PAD       = round(SIZE * CANVAS_PAD_FRAC)
CONTENT_W = SIZE - 2 * PAD
LABEL_W   = round(CONTENT_W * LABEL_COL_FRAC)
LABEL_GAP = round(CONTENT_W * LABEL_GAP_FRAC)
BAR_X     = PAD + LABEL_W + LABEL_GAP
BAR_END   = SIZE - PAD
BAR_AREA  = BAR_END - BAR_X
CLIP_W    = round(BAR_AREA * CLIP_W_RATIO)

CONTENT_H = round(SIZE * CONTENT_FILL_FRAC)
ROW_GAP   = round(CONTENT_H * ROW_GAP_OF_CONTENT)
ROW_H     = (CONTENT_H - ROW_GAP) // 2

BAR_H     = round(ROW_H  * BAR_H_FRAC)
BAR_R     = round(BAR_H  * BAR_R_FRAC)
CARD_R    = round(ROW_H  * CARD_R_FRAC)

GLOW_EXPAND = round(BAR_H * GLOW_EXPAND_FRAC)
GLOW_RADIUS = round(BAR_H * GLOW_RADIUS_FRAC)

# Staircase bar positioning: the two clip bars are placed as an adjacent pair
# centred in the bar area, with the right edge of 'jet' flush with the left
# edge of 'lag'.
STAIRCASE_H_PAD = (BAR_AREA - 2 * CLIP_W) // 2
BAR_OFFSETS     = [STAIRCASE_H_PAD, STAIRCASE_H_PAD + CLIP_W]

FONT_BAR_SZ  = round(BAR_H * FONT_BAR_FRAC)
FONT_TIME_SZ = round(BAR_H * FONT_TIME_FRAC)
FONT_TZ_SZ   = round(BAR_H * FONT_TZ_FRAC)

LABEL_LINE_GAP = round(ROW_H * LABEL_LINE_GAP_FRAC)

# Row positions — centred vertically in the canvas
TOP_Y  = (SIZE - CONTENT_H) // 2
ROW1_Y = TOP_Y
ROW2_Y = ROW1_Y + ROW_H + ROW_GAP


# ── Font loading ──────────────────────────────────────────────────────────────

_FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
]

_FONT_REGULAR_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
]



def _load(candidates, size):
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_bold(size):    return _load(_FONT_BOLD_CANDIDATES, size)
def load_regular(size): return _load(_FONT_REGULAR_CANDIDATES, size)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def composite(base, overlay):
    return Image.alpha_composite(base, overlay)


def glow_layer(canvas_size, x0, y0, x1, y1, color_rgb):
    """Return a blurred rectangle glow as an RGBA image."""
    layer = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([x0, y0, x1, y1], fill=(*color_rgb, 60))
    return layer.filter(ImageFilter.GaussianBlur(GLOW_RADIUS))


def draw_row_card(img, row_y):
    """Faint card background spanning the full content width behind each row."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(
        [PAD, row_y, SIZE - PAD, row_y + ROW_H],
        radius=CARD_R,
        fill=(255, 255, 255, 10),     # white / ~4 %
        outline=(255, 255, 255, 18),  # white / ~7 %
        width=1,
    )
    return composite(img, overlay)


def draw_clip_row(img, clip, row_y, bar_offset, fill, border, text_color, glow_rgb, fonts):
    """Render one clip row: glow behind bar, bar rect, 'jet'/'lag' label centred inside."""
    font_bar = fonts[0]
    bx0 = BAR_X + bar_offset
    bx1 = bx0 + CLIP_W
    by0 = row_y + (ROW_H - BAR_H) // 2
    by1 = by0 + BAR_H

    gl = glow_layer(img.size,
                    bx0 - GLOW_EXPAND, by0 - GLOW_EXPAND,
                    bx1 + GLOW_EXPAND, by1 + GLOW_EXPAND,
                    glow_rgb)
    img = composite(img, gl)

    bar = Image.new('RGBA', img.size, (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    bd.rounded_rectangle([bx0, by0, bx1, by1],
                         radius=BAR_R, fill=fill, outline=border, width=2)

    label = clip['label']
    bbox  = font_bar.getbbox(label)
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]
    tx    = bx0 + (CLIP_W  - tw) // 2 - bbox[0]
    ty    = by0 + (BAR_H   - th) // 2 - bbox[1]
    bd.text((tx, ty), label, font=font_bar, fill=text_color)

    return composite(img, bar)


def draw_mark(d, cx, cy, size, correct, color):
    """Draw a ✓ or ✗ as line art centred at (cx, cy)."""
    r = size // 2
    w = max(2, size // 6)
    if correct:
        d.line([(cx - r, cy), (cx - r // 3, cy + r)], fill=color, width=w)
        d.line([(cx - r // 3, cy + r), (cx + r, cy - r)], fill=color, width=w)
    else:
        d.line([(cx - r, cy - r), (cx + r, cy + r)], fill=color, width=w)
        d.line([(cx - r, cy + r), (cx + r, cy - r)], fill=color, width=w)


def draw_time_labels(img, clip, row_y, fonts):
    """
    Draw time ('02:00') and tz ('+04:00') with a ✓/✗ mark in the label column,
    right-aligned. The mark is drawn as line art to avoid font compatibility issues.
    """
    _, font_time, font_tz = fonts
    lx = BAR_X - LABEL_GAP + 5

    time_bbox = font_time.getbbox(clip['time'])
    tz_bbox   = font_tz.getbbox(clip['tz'])
    time_h    = time_bbox[3] - time_bbox[1]
    tz_h      = tz_bbox[3]   - tz_bbox[1]

    mark_size = tz_h
    mark_gap  = mark_size // 2

    group_h = time_h + LABEL_LINE_GAP + tz_h
    group_y = row_y + (ROW_H - group_h) // 2

    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    d.text((lx, group_y - time_bbox[1]),
           clip['time'], font=font_time, fill=LABEL_COLOR, anchor='ra')

    tz_y     = group_y + time_h + LABEL_LINE_GAP
    tz_color = TZ_CORRECT if clip['correct'] else TZ_WRONG

    tz_w = font_tz.getlength(clip['tz'])
    total_w = tz_w + mark_gap + mark_size
    tz_x = lx - total_w

    d.text((tz_x, tz_y - tz_bbox[1]),
           clip['tz'], font=font_tz, fill=tz_color)

    mark_cx = round(tz_x + tz_w + mark_gap + mark_size // 2)
    mark_cy = round(tz_y + tz_h // 2)
    draw_mark(d, mark_cx, mark_cy, mark_size, clip['correct'], tz_color)

    return composite(img, overlay)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    fonts = (
        load_bold(FONT_BAR_SZ),
        load_bold(FONT_TIME_SZ),
        load_regular(FONT_TZ_SZ),
    )

    img = Image.new('RGBA', (SIZE, SIZE), (*BG_COLOR, 255))

    img = draw_row_card(img, ROW1_Y)
    img = draw_clip_row(img, CLIPS[0], ROW1_Y, BAR_OFFSETS[0],
                        BLUE_FILL, BLUE_BORDER, BLUE_TEXT, (59, 130, 246), fonts)
    img = draw_time_labels(img, CLIPS[0], ROW1_Y, fonts)

    img = draw_row_card(img, ROW2_Y)
    img = draw_clip_row(img, CLIPS[1], ROW2_Y, BAR_OFFSETS[1],
                        GREEN_FILL, GREEN_BORDER, GREEN_TEXT, (34, 197, 94), fonts)
    img = draw_time_labels(img, CLIPS[1], ROW2_Y, fonts)

    script_dir = Path(__file__).parent
    out_dir    = (script_dir.parent
                  / "macos/Sources/Assets.xcassets/AppIcon.appiconset")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "AppIcon.png"
    img.convert('RGB').save(str(out_path), 'PNG')
    print(f"  AppIcon.png  (1024×1024)  →  {out_path}")


if __name__ == '__main__':
    main()
