/**
 * The page, top to bottom.
 *
 * SECTIONS is the single list of content sections in page order. Each section
 * module exports its anchor `id` and a `render()` that returns
 * `<section id="${id}">…</section>`. screenshot.js reads the same list.
 */
import { renderNav } from './sections/nav.js'
import * as hero from './sections/hero.js'
import * as problem from './sections/problem.js'
import * as features from './sections/features.js'
import * as audience from './sections/audience.js'
import * as howItWorks from './sections/how-it-works.js'
import * as pricing from './sections/pricing.js'
import * as download from './sections/download.js'
import { renderFooter } from './sections/footer.js'
import { renderBackToTop, initBackToTop } from './components/back-to-top.js'
import { initMobileNav } from './components/mobile-nav.js'
import { initTimelineSliders } from './components/timeline.js'

export const SECTIONS = [hero, problem, features, audience, howItWorks, pricing, download]

export function renderPage() {
  return [
    renderNav(),
    ...SECTIONS.map(section => section.render()),
    renderFooter(),
    renderBackToTop(),
  ].join('')
}

export function initPage() {
  // Intersection Observer for scroll-triggered fade-in
  const observer = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view')
          observer.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.1 }
  )

  document.querySelectorAll('.card, section h2, section p.text-white\\/55, .fade-on-scroll').forEach(el => {
    observer.observe(el)
  })

  initTimelineSliders()
  initMobileNav()
  initBackToTop()
}
