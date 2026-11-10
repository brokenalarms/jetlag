/**
 * Design tokens for the site, read from design/tokens.json (the single source
 * shared with the macOS app).
 *
 * Every token colour is exposed as a CSS variable holding an `r g b` triplet,
 * so style.css can write `rgb(var(--neon-pink))` or `rgb(var(--neon-pink) / 0.3)`.
 */
import { createRequire } from 'module'
import plugin from 'tailwindcss/plugin'

const require = createRequire(import.meta.url)
export const tokens = require('../design/tokens.json')

/** '#ff2d78' → '255 45 120' */
export function hexToTriplet(hex) {
  const match = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!match) throw new Error(`Not a #rrggbb colour: ${hex}`)
  const n = parseInt(match[1], 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}

/** { 'neon-pink': '#ff2d78' } → { '--neon-pink': '255 45 120' } */
export function cssVariables(colors) {
  return Object.fromEntries(
    Object.entries(colors).map(([name, hex]) => [`--${name}`, hexToTriplet(hex)])
  )
}

/** Tailwind plugin that writes every token colour onto :root. */
export const tokenVariables = plugin(({ addBase }) => {
  addBase({ ':root': cssVariables(tokens.colors) })
})
