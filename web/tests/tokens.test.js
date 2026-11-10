/**
 * Tests for the colour token pipeline (web/tokens.js and src/style.css).
 *
 * design/tokens.json is the only place colours are defined. tokens.js turns
 * them into `r g b` CSS variables; style.css must use those variables rather
 * than copying a token's hex or rgba() value, or a token change would leave
 * the copy behind.
 */
import { readFileSync } from 'fs'
import { describe, expect, test } from 'vitest'
import { cssVariables, hexToTriplet, tokens } from '../tokens.js'

describe('hexToTriplet', () => {
  // Triplets are space-separated so `rgb(var(--x) / alpha)` works.
  test('converts #rrggbb to "r g b"', () => {
    expect(hexToTriplet('#ff2d78')).toBe('255 45 120')
    expect(hexToTriplet('#0A0A0B')).toBe('10 10 11')
  })

  // A malformed token should fail the build rather than emit a broken variable.
  test('rejects anything but #rrggbb', () => {
    expect(() => hexToTriplet('#fff')).toThrow()
    expect(() => hexToTriplet('red')).toThrow()
  })
})

describe('cssVariables', () => {
  // Every token becomes a --name variable.
  test('emits one variable per token', () => {
    const vars = cssVariables(tokens.colors)
    expect(Object.keys(vars)).toEqual(Object.keys(tokens.colors).map(name => `--${name}`))
    expect(vars['--neon-pink']).toBe('255 45 120')
  })
})

describe('style.css', () => {
  const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8').toLowerCase()

  // No token colour may be hand-copied into the stylesheet, as hex or as rgb(a) numbers.
  test('does not copy token colours', () => {
    const copies = Object.entries(tokens.colors).flatMap(([name, hex]) => {
      const [r, g, b] = hexToTriplet(hex).split(' ')
      const asRgb = new RegExp(`rgba?\\(\\s*${r}\\s*,\\s*${g}\\s*,\\s*${b}\\b`)
      return css.includes(hex.toLowerCase()) || asRgb.test(css) ? [name] : []
    })
    expect(copies).toEqual([])
  })
})
