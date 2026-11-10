// @vitest-environment jsdom
/**
 * Behaviour tests for the interactive page chrome in components/.
 *
 * The mobile menu and back-to-top button are wired by init functions after the
 * markup is mounted. These tests mount each component's own markup and drive
 * it the way a visitor would, so moving or renaming ids between render and
 * init cannot silently leave a dead button.
 */
import { afterEach, describe, expect, test, vi } from 'vitest'
import { initMobileNav, renderMobileNavMenu, renderMobileNavToggle } from '../src/components/mobile-nav.js'
import { SHOW_AFTER_PX, initBackToTop, renderBackToTop } from '../src/components/back-to-top.js'
import { NAV_LINKS } from '../src/sections/nav.js'

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('mobile nav', () => {
  const mount = () => {
    document.body.innerHTML = renderMobileNavToggle() + renderMobileNavMenu(NAV_LINKS)
    initMobileNav()
    const toggle = document.getElementById('nav-toggle')
    return {
      toggle,
      menu: document.getElementById('nav-mobile-menu'),
      openIcon: toggle.querySelector('.nav-icon-open'),
      closeIcon: toggle.querySelector('.nav-icon-close'),
    }
  }

  // The menu lists every nav link, the same ones the desktop bar shows.
  test('lists every NAV_LINKS entry', () => {
    const { menu } = mount()
    const links = [...menu.querySelectorAll('.nav-mobile-link')].map(a => [a.getAttribute('href'), a.textContent])
    expect(links).toEqual(NAV_LINKS.map(l => [l.href, l.label]))
  })

  // Toggle opens the menu and swaps the hamburger for a close icon; again closes it.
  test('toggle opens and closes the menu', () => {
    const { toggle, menu, openIcon, closeIcon } = mount()
    expect(menu.classList.contains('hidden')).toBe(true)
    toggle.click()
    expect(menu.classList.contains('hidden')).toBe(false)
    expect([openIcon.classList.contains('hidden'), closeIcon.classList.contains('hidden')]).toEqual([true, false])
    toggle.click()
    expect(menu.classList.contains('hidden')).toBe(true)
    expect([openIcon.classList.contains('hidden'), closeIcon.classList.contains('hidden')]).toEqual([false, true])
  })

  // Following a link closes the menu so the target section is not covered.
  test('clicking a link closes the menu', () => {
    const { toggle, menu, openIcon } = mount()
    toggle.click()
    menu.querySelector('a[href="#features"]').click()
    expect(menu.classList.contains('hidden')).toBe(true)
    expect(openIcon.classList.contains('hidden')).toBe(false)
  })
})

describe('back to top', () => {
  const scrollTo = y => {
    Object.defineProperty(window, 'scrollY', { value: y, configurable: true })
    window.dispatchEvent(new Event('scroll'))
  }

  // Hidden near the top, shown once scrolled past the threshold, hidden again on return.
  test('shows only after scrolling past the threshold', () => {
    document.body.innerHTML = renderBackToTop()
    initBackToTop()
    const btn = document.getElementById('back-to-top')
    scrollTo(SHOW_AFTER_PX)
    expect(btn.classList.contains('hidden')).toBe(true)
    scrollTo(SHOW_AFTER_PX + 1)
    expect([btn.classList.contains('hidden'), btn.classList.contains('flex')]).toEqual([false, true])
    scrollTo(0)
    expect(btn.classList.contains('hidden')).toBe(true)
  })

  // Clicking scrolls smoothly to the very top.
  test('click scrolls to the top', () => {
    const spy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    document.body.innerHTML = renderBackToTop()
    initBackToTop()
    document.getElementById('back-to-top').click()
    expect(spy).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })
})
