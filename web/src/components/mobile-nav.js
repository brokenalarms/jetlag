/**
 * Mobile navigation: a hamburger toggle in the nav bar and a drop-down menu
 * under it, shown below the `sm` breakpoint only.
 *
 * render*() return markup; initMobileNav() wires the toggle once it is in the DOM.
 */
const TOGGLE_ID = 'nav-toggle'
const MENU_ID = 'nav-mobile-menu'

export function renderMobileNavToggle() {
  return /* html */`
    <button class="sm:hidden flex items-center justify-center w-9 h-9 rounded-lg border border-white/10 text-white/60 hover:text-white hover:border-white/20 transition-colors" id="${TOGGLE_ID}" aria-label="Toggle menu">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="nav-icon-open">
        <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="nav-icon-close hidden">
        <path d="M5 5l8 8M13 5l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>
  `
}

/** links: [{ href, label }] */
export function renderMobileNavMenu(links) {
  return /* html */`
    <div id="${MENU_ID}" class="hidden sm:hidden border-t border-white/6 bg-neutral-950/95 backdrop-blur-xl">
      <div class="flex flex-col gap-1 px-6 py-4">
        ${links.map(({ href, label }) => /* html */`
          <a href="${href}" class="nav-mobile-link rounded-lg px-4 py-3 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-all">${label}</a>
        `).join('')}
        <div class="mt-2 pt-3 border-t border-white/6">
          <a href="#pricing" class="btn-secondary w-full justify-center text-sm">Buy License</a>
        </div>
      </div>
    </div>
  `
}

export function initMobileNav() {
  const toggle = document.getElementById(TOGGLE_ID)
  const menu = document.getElementById(MENU_ID)
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
