const freeFeatures = [
  'Full pipeline: import, tag, fix timestamps, organize',
  'All camera profiles (GoPro, iPhone, DJI, Insta360…)',
  'Dry-run preview mode',
  'Date-based folder organization',
  'Up to 50 files per run',
]

const proFeatures = [
  'Everything in Free',
  'Unlimited files per run',
  'Priority support',
  'All future updates included',
]

function checkIcon(color = 'pink') {
  const colors = {
    pink:  'text-neon-pink',
    white: 'text-white/60',
  }
  return /* html */`
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" class="${colors[color]}" aria-hidden="true">
      <path d="M3 8l3.5 3.5 7-7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  `
}

export function renderPricing() {
  return /* html */`
    <section id="pricing" class="py-24 px-6 bg-white/[0.02]">
      <div class="mx-auto max-w-5xl">
        <div class="text-center mb-14">
          <span class="section-label">Pricing</span>
          <h2 class="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
            Simple, honest pricing
          </h2>
          <p class="mt-4 mx-auto max-w-md text-base text-white/50">
            One-time purchase. No subscription. Use Jetlag forever.
          </p>
        </div>

        <div class="grid gap-6 lg:grid-cols-2 max-w-3xl mx-auto">
          <!-- Free tier -->
          <div class="card flex flex-col">
            <div class="mb-6">
              <h3 class="text-lg font-bold text-white">Jetlag</h3>
              <div class="mt-3 flex items-baseline gap-1">
                <span class="text-4xl font-bold text-white">Free</span>
              </div>
              <p class="mt-2 text-sm text-white/45">Start using Jetlag today, no purchase required.</p>
            </div>

            <ul class="flex-1 space-y-3 mb-8">
              ${freeFeatures.map(f => /* html */`
                <li class="flex items-start gap-3 text-sm text-white/60">
                  ${checkIcon('white')}
                  <span>${f}</span>
                </li>
              `).join('')}
              <li class="flex items-start gap-3 text-sm text-white/35 mt-2 pt-2 border-t border-white/8">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" class="text-white/25 flex-shrink-0 mt-0.5" aria-hidden="true">
                  <path d="M4 8h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
                <span>50-file limit per run</span>
              </li>
            </ul>

            <a id="download" href="#download" class="btn-secondary w-full justify-center">
              Download free
            </a>
          </div>

          <!-- Pro tier -->
          <div class="relative rounded-2xl border border-neon-pink/30 bg-gradient-to-b from-neon-pink/8 to-transparent p-6 flex flex-col glow-amber">
            <div class="absolute -top-3 left-6">
              <span class="rounded-full bg-neon-pink px-3 py-1 text-xs font-bold text-white uppercase tracking-wide">Most popular</span>
            </div>

            <div class="mb-6 mt-2">
              <h3 class="text-lg font-bold text-white">Jetlag Pro</h3>
              <div class="mt-3 flex items-baseline gap-1">
                <span class="text-4xl font-bold text-white">$29</span>
                <span class="text-sm text-white/40">one time</span>
              </div>
              <p class="mt-2 text-sm text-white/45">Unlock unlimited processing, forever.</p>
            </div>

            <ul class="flex-1 space-y-3 mb-8">
              ${proFeatures.map(f => /* html */`
                <li class="flex items-start gap-3 text-sm text-white/75">
                  ${checkIcon('pink')}
                  <span>${f}</span>
                </li>
              `).join('')}
            </ul>

            <a href="https://jetlag.app/buy" class="btn-primary w-full justify-center">
              Buy Jetlag Pro — $29
            </a>
            <p class="mt-3 text-center text-xs text-white/30">Secure checkout via Paddle. Instant license delivery.</p>
          </div>
        </div>

        <!-- License key entry -->
        <div class="mt-10 mx-auto max-w-md text-center">
          <p class="text-sm text-white/40 mb-4">Already purchased? Activate your license in the app via <strong class="text-white/60">Preferences → License</strong>, or enter your key directly when prompted on first use.</p>
        </div>

        <!-- FAQ -->
        <div class="mt-16 grid gap-4 sm:grid-cols-2 max-w-3xl mx-auto">
          ${[
            ['What is the 50-file limit?', 'The free version processes up to 50 files per pipeline run. For most day trips with one or two cameras, that\'s plenty. Pro removes the limit entirely.'],
            ['Is it really a one-time purchase?', 'Yes. Pay once, use Jetlag Pro forever. No monthly fee, no annual renewal.'],
            ['What macOS version do I need?', 'macOS 13 Ventura or later. Jetlag is a native SwiftUI app — no Electron, no web runtime.'],
            ['Can I try it before buying?', 'Yes. Download the free version and run it on your footage. The full pipeline works — you\'re only limited to 50 files per run.'],
          ].map(([q, a]) => /* html */`
            <div class="card">
              <h4 class="text-sm font-semibold text-white mb-2">${q}</h4>
              <p class="text-sm text-white/45 leading-relaxed">${a}</p>
            </div>
          `).join('')}
        </div>
      </div>
    </section>
  `
}
