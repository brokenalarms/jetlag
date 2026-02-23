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
BLUE_GLOW    = (59,  130, 246,  25)    # diffuse glow

GREEN_FILL   = (34,  197,  94,  90)   # green-500 ~35 %
GREEN_BORDER = (74,  222, 128,  70)   # green-400 ~27 %
GREEN_TEXT   = (134, 239, 172, 180)   # green-300 ~70 %
GREEN_GLOW   = (34,  197,  94,  25)   # diffuse glow

LABEL_COLOR  = (255, 255, 255,  90)   # white / 35  — time digits
TZ_CORRECT   = (255, 255, 255,  64)   # white / 25
TZ_WRONG     = (248, 113, 113, 180)   # red-400 / 70
AXIS_COLOR   = (255, 255, 255,  20)   # white /  8
TICK_COLOR   = (255, 255, 255,  26)   # white / 10
TICK_LABEL   = (255, 255, 255,  51)   # white / 20
NEWDAY_COLOR = (255, 255, 255,  51)   # white / 20


# ── Timeline data (Amsterdam vs Seoul, before Jetlag) ─────────────────────────

PAD_MINUTES = 70

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
    min_t       = min(times)
    max_t       = max(times)
    scale_start = max(0, min_t - PAD_MINUTES)
    scale_end   = max_t + PAD_MINUTES
    px_per_min  = (bar_area - clip_w) / (scale_end - scale_start)
    return {'start': scale_start, 'end': scale_end, 'ppm': px_per_min}


def clip_offset_px(clip, scale):
    return round((to_minutes(clip) - scale['start']) * scale['ppm'])


def build_ticks(scale, bar_area):
    start, end, ppm = scale['start'], scale['end'], scale['ppm']
    duration = end - start
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


# ── Layout ────────────────────────────────────────────────────────────────────

OUTER_L   = 64
OUTER_R   = 64
LABEL_W   = 196         # width of the time-label column
LABEL_GAP = 24          # gap between label column and bar area
BAR_X     = OUTER_L + LABEL_W + LABEL_GAP   # 284 — x where bar area starts
BAR_END   = SIZE - OUTER_R                  # 960
BAR_AREA  = BAR_END - BAR_X                 # 676 px

# Clip bar width scaled from the web component ratio (100 / 290)
CLIP_W    = round(BAR_AREA * 100 / 290)     # ~233 px
BAR_H     = 108                             # bar rectangle height
BAR_R     = 12                             # corner radius

ROW_H     = 220          # total height of each clip row slot
ROW_GAP   = 72           # vertical gap between the two rows
AXIS_H    = 55           # actual rendered height of axis line + ticks + labels

CARD_R    = 16           # row card corner radius

# Centre the three-part content block vertically based on actual rendered extent.
TOTAL_H   = ROW_H + ROW_GAP + ROW_H + AXIS_H
TOP_Y     = (SIZE - TOTAL_H) // 2

ROW1_Y    = TOP_Y
ROW2_Y    = ROW1_Y + ROW_H + ROW_GAP
AXIS_Y    = ROW2_Y + ROW_H              # y of the axis line


# ── Font loading ──────────────────────────────────────────────────────────────

_FONT_CANDIDATES = [
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


def load_bold(size):
    return _load(_FONT_CANDIDATES, size)


def load_regular(size):
    return _load(_FONT_REGULAR_CANDIDATES, size)


# ── Drawing helpers ───────────────────────────────────────────────────────────

def composite(base, overlay):
    return Image.alpha_composite(base, overlay)


def glow_layer(size_px, x0, y0, x1, y1, color_rgb, radius=40):
    """Return a blurred rectangle glow as an RGBA image."""
    layer = Image.new('RGBA', size_px, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([x0, y0, x1, y1], fill=(*color_rgb, 60))
    return layer.filter(ImageFilter.GaussianBlur(radius))


def draw_row_card(img, row_y):
    """Draw a faint card background behind a clip row."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(
        [OUTER_L, row_y, SIZE - OUTER_R, row_y + ROW_H],
        radius=CARD_R,
        fill=(255, 255, 255, 10),      # white / ~4 %
        outline=(255, 255, 255, 18),   # white / ~7 %
        width=1,
    )
    return composite(img, overlay)


def draw_clip_row(img, clip, row_y, scale, fill, border, text_color, glow_rgb, fonts):
    """Render one clip row: glow + bar + 'jet'/'lag' label inside bar."""
    font_bar, _, _ = fonts
    offset = clip_offset_px(clip, scale)
    bx0 = BAR_X + offset
    bx1 = bx0 + CLIP_W
    by0 = row_y + (ROW_H - BAR_H) // 2
    by1 = by0 + BAR_H

    # Glow (blurred rectangle behind the bar)
    gl = glow_layer(img.size, bx0 - 20, by0 - 20, bx1 + 20, by1 + 20, glow_rgb, radius=36)
    img = composite(img, gl)

    # Bar fill + border
    bar = Image.new('RGBA', img.size, (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    bd.rounded_rectangle([bx0, by0, bx1, by1], radius=BAR_R, fill=fill, outline=border, width=2)

    # Text label centred inside the bar
    label = clip['label']
    bbox  = font_bar.getbbox(label)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = bx0 + (CLIP_W - tw) // 2 - bbox[0]
    ty = by0 + (BAR_H  - th) // 2 - bbox[1]
    bd.text((tx, ty), label, font=font_bar, fill=text_color)

    img = composite(img, bar)
    return img


def draw_time_labels(img, clip, row_y, fonts):
    """Draw time and tz text in the label column, right-aligned to BAR_X."""
    _, font_time, font_tz = fonts
    lx = BAR_X - LABEL_GAP          # right edge of label column

    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Time (e.g. '14:12') — vertically centred, slightly above middle
    centre_y = row_y + ROW_H // 2
    d.text((lx, centre_y - 18), clip['time'], font=font_time,
           fill=LABEL_COLOR, anchor='rs')

    # TZ (e.g. '[+02:00]' or '[+02:00  ✗]')
    tz_color = TZ_CORRECT if clip['correct'] else TZ_WRONG
    d.text((lx, centre_y + 10), clip['tz'], font=font_tz,
           fill=tz_color, anchor='rs')

    return composite(img, overlay)


def draw_axis(img, scale, fonts):
    """Draw horizontal axis line, hour ticks, and labels."""
    _, _, font_tick = fonts
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    # Axis line across bar area
    d.line([(BAR_X, AXIS_Y), (BAR_END, AXIS_Y)], fill=AXIS_COLOR, width=1)

    for tick in build_ticks(scale, BAR_AREA):
        tx     = BAR_X + tick['px']
        is_new = tick['new_day']
        t_col  = NEWDAY_COLOR if is_new else TICK_COLOR
        l_col  = (255, 255, 255, 77) if is_new else TICK_LABEL

        # Tick mark
        d.line([(tx, AXIS_Y), (tx, AXIS_Y + 12)], fill=t_col, width=1)
        # Hour label
        d.text((tx, AXIS_Y + 16), tick['label'], font=font_tick,
               fill=l_col, anchor='mt')

    return composite(img, overlay)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    scale = build_scale(CLIPS, BAR_AREA, CLIP_W)

    fonts = (
        load_bold(76),     # bar label ('jet' / 'lag')
        load_bold(44),     # time digits ('14:12')
        load_regular(26),  # tz label and axis ticks
    )

    img = Image.new('RGBA', (SIZE, SIZE), (*BG_COLOR, 255))

    # Row 1 — Amsterdam (blue, 'jet')
    img = draw_row_card(img, ROW1_Y)
    img = draw_clip_row(img, CLIPS[0], ROW1_Y, scale,
                        BLUE_FILL, BLUE_BORDER, BLUE_TEXT,
                        (59, 130, 246), fonts)
    img = draw_time_labels(img, CLIPS[0], ROW1_Y, fonts)

    # Row 2 — Seoul (green, 'lag')
    img = draw_row_card(img, ROW2_Y)
    img = draw_clip_row(img, CLIPS[1], ROW2_Y, scale,
                        GREEN_FILL, GREEN_BORDER, GREEN_TEXT,
                        (34, 197, 94), fonts)
    img = draw_time_labels(img, CLIPS[1], ROW2_Y, fonts)

    # Time axis
    img = draw_axis(img, scale, fonts)

    # Save
    script_dir = Path(__file__).parent
    out_dir = (script_dir.parent
               / "macos/Sources/Assets.xcassets/AppIcon.appiconset")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "AppIcon.png"
    img.convert('RGB').save(str(out_path), 'PNG')
    print(f"  AppIcon.png  (1024×1024)  →  {out_path}")


if __name__ == '__main__':
    main()
