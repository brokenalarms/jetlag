# Web — Marketing Site

## Design intent

The site uses an 80s neon/retro aesthetic — spray-paint headline effects, VHS scanlines, CRT screen boxes, dark backgrounds with neon accent colors. This is intentional; don't "clean it up" or modernize the visual style.

Vanilla JS with template literals (no framework) — each section is a self-contained render function. This is deliberate; don't introduce React/Vue/etc.

## Color pipeline

`design/tokens.json` is the single source of truth for colors, shared between web and the macOS app. Don't define colors in CSS or Tailwind config directly — always go through tokens. The pipeline:

- Web: `design/tokens.json` → `tailwind.config.js` reads tokens at build time
- macOS app: `design/tokens.json` → `design/generate-colorsets.py` → `Assets.xcassets` color sets

Changing a color in `tokens.json` updates both the website and the app.

## Screenshot protocol

Mandatory for every change to files under `web/`:

1. Run screenshots before committing: `npm run screenshot --prefix web`
2. Read and share each saved screenshot image with the user using the Read tool before committing, so they can review the rendered output
3. Screenshots overwrite PNGs in `design/screenshots/` with fixed names so each commit shows a visual diff

If the Playwright browser is missing: `npx playwright install chromium` inside `web/`.
