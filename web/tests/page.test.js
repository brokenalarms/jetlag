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
})
