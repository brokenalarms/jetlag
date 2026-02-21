export function renderNav() {
  return /* html */`
    <nav class="fixed top-0 z-50 w-full border-b border-white/6 bg-neutral-950/80 backdrop-blur-xl">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <a href="#" class="flex items-center gap-2 text-white no-underline">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect width="28" height="28" rx="8" fill="#f59e0b"/>
            <path d="M8 9l4.5 4.5L8 18M14 18h6" stroke="#0a0a0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
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
        </div>
      </div>
    </nav>
  `
}
