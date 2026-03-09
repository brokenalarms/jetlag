import './style.css'

import { renderNav } from './sections/nav.js'
import { renderHero } from './sections/hero.js'
import { renderProblem } from './sections/problem.js'
import { initTimelineSliders } from './components/timeline.js'
import { renderFeatures } from './sections/features.js'
import { renderAudience } from './sections/audience.js'
import { renderHowItWorks } from './sections/how-it-works.js'
import { renderPricing } from './sections/pricing.js'
import { renderDownload } from './sections/download.js'
import { renderFooter } from './sections/footer.js'

function mount() {
  const app = document.getElementById('app')
  if (!app) return

  app.innerHTML = [
    renderNav(),
    renderHero(),
    renderProblem(),
    renderFeatures(),
    renderAudience(),
    renderHowItWorks(),
    renderPricing(),
    renderDownload(),
    renderFooter(),
    renderBackToTop(),
  ].join('')

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

document.addEventListener('DOMContentLoaded', mount)
