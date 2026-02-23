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

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ── Design tokens ──────────────────────────────────────────────────────────────

SIZE = 1024
BG_COLOR = (10, 10, 11)                # #0a0a0b

# Bar colours match the web timeline component exactly
BLUE_FILL    = (59,  130, 246,  90)    # blue-500  ~35 %
BLUE_BORDER  = (96,  165, 250,  70)    # blue-400  ~27 %
BLUE_TEXT    = (147, 197, 253, 180)    # blue-300  ~70 %

GREEN_FILL   = (34,  197,  94,  90)   # green-500 ~35 %
GREEN_BORDER = (74,  222, 128,  70)   # green-400 ~27 %
GREEN_TEXT   = (134, 239, 172, 180)   # green-300 ~70 %

LABEL_COLOR  = (255, 255, 255,  90)   # white / 35  — time digits
TZ_CORRECT   = (255, 255, 255,  64)   # white / 25
TZ_WRONG     = (248, 113, 113, 180)   # red-400 / 70
AXIS_COLOR   = (255, 255, 255,  20)   # white /  8
TICK_COLOR   = (255, 255, 255,  26)   # white / 10
TICK_LABEL   = (255, 255, 255,  51)   # white / 20
NEWDAY_COLOR = (255, 255, 255,  51)   # white / 20


# ── Timeline data (Amsterdam vs Seoul, before Jetlag) ─────────────────────────

PAD_MINUTES = 70      # breathing room on each side of the time scale (from timeline.js)

CLIPS = [
    {
        'day': 0, 'time': '14:12', 'tz': '[+02:00]',
        'label': 'jet', 'color': 'blue', 'correct': True,
    },
    {
        'day': 1, 'time': '02:07', 'tz': '[+02:00  ✗]',
        'label': 'lag', 'color': 'green', 'correct': False,
    },
]


def to_minutes(clip):
    h, m = map(int, clip['time'].split(':'))
    return clip['day'] * 1440 + h * 60 + m


def build_scale(clips, bar_area, clip_w):
    times       = [to_minutes(c) for c in clips]
    scale_start = max(0, min(times) - PAD_MINUTES)
    scale_end   = max(times) + PAD_MINUTES
    px_per_min  = (bar_area - clip_w) / (scale_end - scale_start)
    return {'start': scale_start, 'end': scale_end, 'ppm': px_per_min}


def clip_offset_px(clip, scale):
    return round((to_minutes(clip) - scale['start']) * scale['ppm'])


def build_ticks(scale, bar_area):
    """Hour-tick marks visible within the scale window."""
    start, end, ppm = scale['start'], scale['end'], scale['ppm']
    duration = end - start
    # Use 6-hour intervals when the span exceeds 8 hours (avoids label crowding)
    interval = 6 if duration > 8 * 60 else 3 if duration > 6 * 60 else 2
    ticks = []
    for h in range(math.ceil(start / 60), math.floor(end / 60) + 1):
        if h % interval != 0:
            continue
        px = round((h * 60 - start) * ppm)
        if px < 0 or px > bar_area:
            continue
        disp_h    = h % 24
        is_newday = (h % 24 == 0) and (h > 0)
        ticks.append({'px': px, 'label': f'{disp_h:02d}:00', 'new_day': is_newday})
    return ticks


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
FONT_TZ_FRAC       = 0.25      # tz label and axis tick labels

# Glow effect as fractions of BAR_H
GLOW_EXPAND_FRAC   = 0.17      # rect expansion before Gaussian blur
GLOW_RADIUS_FRAC   = 0.31      # Gaussian blur radius

# Axis geometry as fractions of BAR_H
TICK_H_FRAC        = 0.10      # tick-mark height
TICK_GAP_FRAC      = 0.13      # gap between tick bottom and label top

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

# AXIS_H is defined as BAR_H * (TICK_H_FRAC + TICK_GAP_FRAC + FONT_TZ_FRAC).
# Since BAR_H = ROW_H * BAR_H_FRAC and ROW_H is what we want to derive, solve:
#   CONTENT_H = 2 * ROW_H + ROW_GAP + BAR_H_FRAC * (TICK_H + TICK_GAP + FONT_TZ) * ROW_H
#             = ROW_H * (2 + BAR_H_FRAC * AXIS_BAR_FRAC) + ROW_GAP
AXIS_BAR_FRAC = TICK_H_FRAC + TICK_GAP_FRAC + FONT_TZ_FRAC
ROW_H         = int((CONTENT_H - ROW_GAP) / (2 + BAR_H_FRAC * AXIS_BAR_FRAC))

BAR_H     = round(ROW_H  * BAR_H_FRAC)
BAR_R     = round(BAR_H  * BAR_R_FRAC)
CARD_R    = round(ROW_H  * CARD_R_FRAC)
AXIS_H    = round(BAR_H  * AXIS_BAR_FRAC)   # exactly fits tick + gap + label

GLOW_EXPAND = round(BAR_H * GLOW_EXPAND_FRAC)
GLOW_RADIUS = round(BAR_H * GLOW_RADIUS_FRAC)

TICK_H    = round(BAR_H * TICK_H_FRAC)
TICK_GAP  = round(BAR_H * TICK_GAP_FRAC)

FONT_BAR_SZ  = round(BAR_H * FONT_BAR_FRAC)
FONT_TIME_SZ = round(BAR_H * FONT_TIME_FRAC)
FONT_TZ_SZ   = round(BAR_H * FONT_TZ_FRAC)

LABEL_LINE_GAP = round(ROW_H * LABEL_LINE_GAP_FRAC)

# Row positions — centred vertically in the canvas
TOP_Y  = (SIZE - CONTENT_H) // 2
ROW1_Y = TOP_Y
ROW2_Y = ROW1_Y + ROW_H + ROW_GAP
AXIS_Y = ROW2_Y + ROW_H


# ── Font loading ──────────────────────────────────────────────────────────────

_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
]

_FONT_REGULAR_CANDIDATES = [
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


def draw_clip_row(img, clip, row_y, scale, fill, border, text_color, glow_rgb, fonts):
    """Render one clip row: glow behind bar, bar rect, 'jet'/'lag' label centred inside."""
    font_bar, _, _ = fonts
    offset = clip_offset_px(clip, scale)
    bx0 = BAR_X + offset
    bx1 = bx0 + CLIP_W
    by0 = row_y + (ROW_H - BAR_H) // 2
    by1 = by0 + BAR_H

    # Glow: expanded rect blurred outward
    gl = glow_layer(img.size,
                    bx0 - GLOW_EXPAND, by0 - GLOW_EXPAND,
                    bx1 + GLOW_EXPAND, by1 + GLOW_EXPAND,
                    glow_rgb)
    img = composite(img, gl)

    # Bar fill + border
    bar = Image.new('RGBA', img.size, (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    bd.rounded_rectangle([bx0, by0, bx1, by1],
                         radius=BAR_R, fill=fill, outline=border, width=2)

    # Label centred inside bar using exact bbox metrics
    label = clip['label']
    bbox  = font_bar.getbbox(label)
    tw    = bbox[2] - bbox[0]
    th    = bbox[3] - bbox[1]
    tx    = bx0 + (CLIP_W  - tw) // 2 - bbox[0]
    ty    = by0 + (BAR_H   - th) // 2 - bbox[1]
    bd.text((tx, ty), label, font=font_bar, fill=text_color)

    return composite(img, bar)


def draw_time_labels(img, clip, row_y, fonts):
    """
    Draw time ('14:12') and tz ('[+02:00]') in the label column, right-aligned.
    The two-line group is centred vertically within the row using font bbox metrics.
    """
    _, font_time, font_tz = fonts
    lx = BAR_X - LABEL_GAP   # right edge of label column

    # Measure actual text heights
    time_bbox = font_time.getbbox(clip['time'])
    tz_bbox   = font_tz.getbbox(clip['tz'])
    time_h    = time_bbox[3] - time_bbox[1]
    tz_h      = tz_bbox[3]   - tz_bbox[1]

    # Centre the two-line group in the row
    group_h = time_h + LABEL_LINE_GAP + tz_h
    group_y = row_y + (ROW_H - group_h) // 2

    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Time text — adjust y so the bounding box top sits at group_y
    d.text((lx, group_y - time_bbox[1]),
           clip['time'], font=font_time, fill=LABEL_COLOR, anchor='ra')

    # TZ text — below time, red if incorrect timezone
    tz_y     = group_y + time_h + LABEL_LINE_GAP
    tz_color = TZ_CORRECT if clip['correct'] else TZ_WRONG
    d.text((lx, tz_y - tz_bbox[1]),
           clip['tz'], font=font_tz, fill=tz_color, anchor='ra')

    return composite(img, overlay)


def draw_axis(img, scale, fonts):
    """Horizontal axis line with hour-tick marks and labels below the last row."""
    _, _, font_tick = fonts
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    d.line([(BAR_X, AXIS_Y), (BAR_END, AXIS_Y)], fill=AXIS_COLOR, width=1)

    for tick in build_ticks(scale, BAR_AREA):
        tx     = BAR_X + tick['px']
        is_new = tick['new_day']
        t_col  = NEWDAY_COLOR if is_new else TICK_COLOR
        l_col  = (255, 255, 255, 77) if is_new else TICK_LABEL

        d.line([(tx, AXIS_Y), (tx, AXIS_Y + TICK_H)], fill=t_col, width=1)
        d.text((tx, AXIS_Y + TICK_H + TICK_GAP), tick['label'],
               font=font_tick, fill=l_col, anchor='mt')

    return composite(img, overlay)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    scale = build_scale(CLIPS, BAR_AREA, CLIP_W)

    fonts = (
        load_bold(FONT_BAR_SZ),      # bar label ('jet' / 'lag')
        load_bold(FONT_TIME_SZ),     # time digits ('14:12')
        load_regular(FONT_TZ_SZ),    # tz label and axis tick labels
    )

    img = Image.new('RGBA', (SIZE, SIZE), (*BG_COLOR, 255))

    # Row 1 — Amsterdam (blue, 'jet')
    img = draw_row_card(img, ROW1_Y)
    img = draw_clip_row(img, CLIPS[0], ROW1_Y, scale,
                        BLUE_FILL, BLUE_BORDER, BLUE_TEXT, (59, 130, 246), fonts)
    img = draw_time_labels(img, CLIPS[0], ROW1_Y, fonts)

    # Row 2 — Seoul before Jetlag (green, 'lag', wrong timezone)
    img = draw_row_card(img, ROW2_Y)
    img = draw_clip_row(img, CLIPS[1], ROW2_Y, scale,
                        GREEN_FILL, GREEN_BORDER, GREEN_TEXT, (34, 197, 94), fonts)
    img = draw_time_labels(img, CLIPS[1], ROW2_Y, fonts)

    # Time axis
    img = draw_axis(img, scale, fonts)

    # Save
    script_dir = Path(__file__).parent
    out_dir    = (script_dir.parent
                  / "macos/Sources/Assets.xcassets/AppIcon.appiconset")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "AppIcon.png"
    img.convert('RGB').save(str(out_path), 'PNG')
    print(f"  AppIcon.png  (1024×1024)  →  {out_path}")


if __name__ == '__main__':
    main()
