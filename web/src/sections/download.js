export function renderDownload() {
  return /* html */`
    <section id="download" class="py-24 px-6">
      <div class="mx-auto max-w-2xl text-center">
        <div class="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-neon-pink/15 text-neon-pink mb-6">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 4v16M8 13l8 8 8-8M6 26h20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>

        <h2 class="text-3xl font-bold tracking-tight sm:text-4xl">
          Download Jetlag
        </h2>
        <p class="mt-4 text-base text-white/50 leading-relaxed">
          Free to download and use. Upgrade to Pro for unlimited files whenever you need it.
        </p>

        <div class="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="https://github.com/brokenalarms/Jetlag/releases/latest"
            class="btn-primary text-base px-8 py-4 w-full sm:w-auto justify-center"
            target="_blank"
            rel="noopener noreferrer"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <path d="M9 1.5v11M4.5 8.5l4.5 4.5 4.5-4.5M2 15.5h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Download for macOS
          </a>
          <a
            href="https://jetlag.app/buy"
            class="btn-secondary text-base px-8 py-4 w-full sm:w-auto justify-center"
          >
            Buy Jetlag Pro — $29
          </a>
        </div>

        <p class="mt-6 text-xs text-white/25">
          macOS 13 Ventura or later &nbsp;·&nbsp; Apple Silicon & Intel &nbsp;·&nbsp; ~8 MB download
        </p>
      </div>
    </section>
  `
}
