import './style.css'

import { renderNav } from './sections/nav.js'
import { renderHero } from './sections/hero.js'
import { renderProblem } from './sections/problem.js'
import { initSliders } from './components/timeline.js'
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
  ].join('')

  initSliders()

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

  document.querySelectorAll('.card, section h2, section p.text-white\\/55').forEach(el => {
    observer.observe(el)
  })

  // Mobile nav smooth close on link click
  document.querySelectorAll('nav a[href^="#"]').forEach(link => {
    link.addEventListener('click', () => {
      // Nothing needed — CSS scroll-behavior: smooth handles it
    })
  })
}

document.addEventListener('DOMContentLoaded', mount)
