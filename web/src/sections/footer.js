export function renderFooter() {
  return /* html */`
    <footer class="border-t border-white/8 py-12 px-6">
      <div class="mx-auto max-w-6xl">
        <div class="flex flex-col items-center justify-between gap-6 sm:flex-row">
          <div class="flex items-center gap-2">
            <img src="/apple-touch-icon.png" width="22" height="22" alt="" aria-hidden="true" class="rounded-md">
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
