export function renderNav() {
  return /* html */`
    <nav class="fixed top-0 z-50 w-full border-b border-white/6 bg-neutral-950/80 backdrop-blur-xl">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <a href="#" class="flex items-center gap-2 text-white no-underline">
          <img src="/apple-touch-icon.png" width="28" height="28" alt="" aria-hidden="true" class="rounded-md">
          <span class="text-base font-bold tracking-tight">Jetlag</span>
        </a>

        <div class="hidden items-center gap-8 text-sm text-white/60 sm:flex">
          <a href="#features" class="transition-colors hover:text-white">Features</a>
          <a href="#how-it-works" class="transition-colors hover:text-white">How it works</a>
          <a href="#pricing" class="transition-colors hover:text-white">Pricing</a>
        </div>

        <div class="flex items-center gap-3">
          <a href="#pricing" class="btn-secondary hidden text-sm sm:inline-flex">Buy License</a>
          <a href="#download" class="btn-primary text-sm">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <path d="M7 1v8M3.5 6l3.5 3.5L10.5 6M2 12h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Download
          </a>
          <!-- Mobile hamburger -->
          <button class="sm:hidden flex items-center justify-center w-9 h-9 rounded-lg border border-white/10 text-white/60 hover:text-white hover:border-white/20 transition-colors" id="nav-toggle" aria-label="Toggle menu">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="nav-icon-open">
              <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="nav-icon-close hidden">
              <path d="M5 5l8 8M13 5l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Mobile menu -->
      <div id="nav-mobile-menu" class="hidden sm:hidden border-t border-white/6 bg-neutral-950/95 backdrop-blur-xl">
        <div class="flex flex-col gap-1 px-6 py-4">
          <a href="#features" class="nav-mobile-link rounded-lg px-4 py-3 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-all">Features</a>
          <a href="#how-it-works" class="nav-mobile-link rounded-lg px-4 py-3 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-all">How it works</a>
          <a href="#pricing" class="nav-mobile-link rounded-lg px-4 py-3 text-sm text-white/60 hover:text-white hover:bg-white/5 transition-all">Pricing</a>
          <div class="mt-2 pt-3 border-t border-white/6">
            <a href="#pricing" class="btn-secondary w-full justify-center text-sm">Buy License</a>
          </div>
        </div>
      </div>
    </nav>
  `
}
