# Web — Marketing Site

## Design intent

The site uses an 80s neon/retro aesthetic — spray-paint headline effects, VHS scanlines, CRT screen boxes, dark backgrounds with neon accent colors. This is intentional; don't "clean it up" or modernize the visual style.

Vanilla JS with template literals (no framework) — each section is a self-contained render function. This is deliberate; don't introduce React/Vue/etc.

## Color pipeline

`design/tokens.json` is the single source of truth for colors, shared between web and the macOS app. Don't define colors in CSS or Tailwind config directly — always go through tokens. The pipeline:

- Web: `design/tokens.json` → `web/tokens.js` → `tailwind.config.js` at build time. Tokens become Tailwind colours (`neon-*`, `amber-*` for the accent shades, `neutral-850/925/950` for the backgrounds) and `:root` CSS variables holding `r g b` triplets. In `style.css` write `rgb(var(--neon-pink))` or `rgb(var(--neon-pink) / 0.3)`, never a hex or `rgba(...)` of a token colour.
- macOS app: `design/tokens.json` → `design/generate-colorsets.py` → `Assets.xcassets` color sets. `python3 design/generate-colorsets.py --check` exits 1 if the colour sets have drifted from the tokens.
- App icon and favicons: `design/generate-app-icon.py` reads the background from `tokens.json`.

Changing a color in `tokens.json` updates the website at the next build; re-run `generate-colorsets.py` for the app.

## Screenshot protocol

Mandatory for every change to files under `web/`:

1. Run screenshots before committing: `npm run screenshot --prefix web`
2. Read and share each saved screenshot image with the user using the Read tool before committing, so they can review the rendered output
3. Screenshots overwrite PNGs in `design/screenshots/` with fixed names so each commit shows a visual diff

If the Playwright browser is missing: `npx playwright install chromium` inside `web/`.
