// @vitest-environment jsdom
/**
 * Smoke test for the whole page.
 *
 * Renders every section the way main.js does and checks the anchors hold
 * together: section ids are unique, every in-page link (href="#x") has a
 * target, and every section in SECTIONS renders as <section id="…"> with its
 * own id. A renamed id or a link to a removed section would otherwise ship as
 * a dead nav link without any error.
 */
import { beforeAll, describe, expect, test } from 'vitest'
import { BUY_URL, FREE_FILE_LIMIT, PRICE } from '../src/content.js'
import { SECTIONS, renderPage } from '../src/page.js'

describe('rendered page', () => {
  beforeAll(() => {
    document.body.innerHTML = renderPage()
  })

  // Duplicate ids make anchors and getElementById ambiguous.
  test('every id is unique', () => {
    const ids = [...document.querySelectorAll('[id]')].map(el => el.id)
    const duplicates = ids.filter((id, i) => ids.indexOf(id) !== i)
    expect(duplicates).toEqual([])
  })

  // Each section module's exported id is the id of exactly the <section> it renders.
  test('each section renders as <section> with its exported id, in order', () => {
    const rendered = [...document.querySelectorAll('section')].map(el => el.id)
    expect(rendered).toEqual(SECTIONS.map(s => s.id))
  })

  // Every in-page link scrolls somewhere ("#" alone is the back-to-top logo link).
  test('every #anchor link has a matching id', () => {
    const targets = [...document.querySelectorAll('a[href^="#"]')]
      .map(a => a.getAttribute('href').slice(1))
      .filter(Boolean)
    expect(targets.length).toBeGreaterThan(0)
    const missing = targets.filter(id => !document.getElementById(id))
    expect(missing).toEqual([])
  })

  // Price, buy link and free limit come from content.js; a hardcoded copy left in a
  // section would show a stale value after the constant changes.
  test('every price, buy link and file limit matches content.js', () => {
    const text = document.body.textContent
    expect(new Set(text.match(/\$\d+/g))).toEqual(new Set([PRICE]))
    const limits = [...text.matchAll(/(\d+)(?:-file limit| files per)/g)].map(m => Number(m[1]))
    expect(limits.length).toBeGreaterThan(0)
    expect(new Set(limits)).toEqual(new Set([FREE_FILE_LIMIT]))
    const buyLinks = [...document.querySelectorAll('a')].filter(a => /buy/i.test(a.textContent))
    expect(buyLinks.length).toBeGreaterThan(0)
    for (const a of buyLinks) expect(['#pricing', BUY_URL]).toContain(a.getAttribute('href'))
  })
})
