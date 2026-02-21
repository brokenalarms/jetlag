export function renderFooter() {
  return /* html */`
    <footer class="border-t border-white/8 py-12 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="flex flex-col items-center justify-between gap-6 sm:flex-row">
          <div class="flex items-center gap-2">
            <svg width="22" height="22" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <rect width="28" height="28" rx="8" fill="#f59e0b"/>
              <path d="M8 9l4.5 4.5L8 18M14 18h6" stroke="#0a0a0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span class="text-sm font-bold text-white">Jetlag</span>
          </div>

          <div class="flex items-center gap-8 text-sm text-white/35">
            <a href="#features" class="hover:text-white/70 transition-colors">Features</a>
            <a href="#pricing" class="hover:text-white/70 transition-colors">Pricing</a>
            <a href="https://github.com/brokenalarms/Jetlag" target="_blank" rel="noopener noreferrer" class="hover:text-white/70 transition-colors">GitHub</a>
            <a href="https://github.com/brokenalarms/Jetlag/issues" target="_blank" rel="noopener noreferrer" class="hover:text-white/70 transition-colors">Support</a>
          </div>

          <p class="text-xs text-white/25">
            &copy; ${new Date().getFullYear()} Jetlag. Made for filmmakers.
          </p>
        </div>
      </div>
    </footer>
  `
}
