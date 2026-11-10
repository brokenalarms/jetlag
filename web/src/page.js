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

function initMobileNav() {
  const toggle = document.getElementById('nav-toggle')
  const menu = document.getElementById('nav-mobile-menu')
  if (!toggle || !menu) return

  const iconOpen = toggle.querySelector('.nav-icon-open')
  const iconClose = toggle.querySelector('.nav-icon-close')

  toggle.addEventListener('click', () => {
    const isOpen = !menu.classList.contains('hidden')
    menu.classList.toggle('hidden', isOpen)
    iconOpen.classList.toggle('hidden', !isOpen)
    iconClose.classList.toggle('hidden', isOpen)
  })

  // Close menu on link click
  menu.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', () => {
      menu.classList.add('hidden')
      iconOpen.classList.remove('hidden')
      iconClose.classList.add('hidden')
    })
  })
}

function renderBackToTop() {
  return /* html */`
    <button id="back-to-top" class="fixed bottom-6 right-6 z-40 hidden h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-neutral-950/80 text-white/50 backdrop-blur-sm transition-all hover:border-white/20 hover:text-white hover:bg-neutral-900/90" aria-label="Back to top">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M9 14V4M5 8l4-4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
  `
}

function initBackToTop() {
  const btn = document.getElementById('back-to-top')
  if (!btn) return

  window.addEventListener('scroll', () => {
    const show = window.scrollY > 600
    btn.classList.toggle('hidden', !show)
    btn.classList.toggle('flex', show)
  }, { passive: true })

  btn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  })
}
