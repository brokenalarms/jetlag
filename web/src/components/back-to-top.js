/**
 * Floating back-to-top button, shown once the page is scrolled past SHOW_AFTER_PX.
 *
 * renderBackToTop() returns markup; initBackToTop() wires scroll and click.
 */
const BUTTON_ID = 'back-to-top'
export const SHOW_AFTER_PX = 600

export function renderBackToTop() {
  return /* html */`
    <button id="${BUTTON_ID}" class="fixed bottom-6 right-6 z-40 hidden h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-neutral-950/80 text-white/50 backdrop-blur-sm transition-all hover:border-white/20 hover:text-white hover:bg-neutral-900/90" aria-label="Back to top">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M9 14V4M5 8l4-4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
  `
}

export function initBackToTop() {
  const btn = document.getElementById(BUTTON_ID)
  if (!btn) return

  window.addEventListener('scroll', () => {
    const show = window.scrollY > SHOW_AFTER_PX
    btn.classList.toggle('hidden', !show)
    btn.classList.toggle('flex', show)
  }, { passive: true })

  btn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  })
}
