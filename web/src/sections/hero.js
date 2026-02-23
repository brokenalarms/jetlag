export function renderHero() {
  return /* html */`
    <section class="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 pt-24 pb-16">
      <!-- Background glows: pink centre, green lower-left, pink upper-right -->
      <div class="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div class="h-[600px] w-[600px] rounded-full bg-neon-pink/10 blur-3xl"></div>
        <div class="absolute h-[400px] w-[400px] rounded-full bg-amber-500/10 blur-3xl -translate-x-48 translate-y-32"></div>
        <div class="absolute h-[300px] w-[300px] rounded-full bg-neon-pink/8 blur-3xl translate-x-48 -translate-y-16"></div>
      </div>

      <!-- Badge -->
      <div class="mb-6 animate-fade-up opacity-0" style="opacity:0;animation-delay:0.1s">
        <span class="section-label">macOS App</span>
      </div>

      <!-- Headline: headline-wrap IS the CRT screen (dark box, rounded, scanlines via vhs-scanlines).
           h1 stays transparent so drop-shadow glows around the text only, inside the screen. -->
      <div class="headline-wrap vhs-scanlines animate-fade-up opacity-0 mx-4 sm:mx-6" style="opacity:0;animation-delay:0.2s">
        <h1 class="spray-paint vhs-glitch relative mx-auto max-w-3xl text-center text-4xl font-bold leading-tight tracking-tight sm:text-5xl lg:text-7xl">
          Every camera.<br>
          <span class="text-gradient">One timeline.</span>
        </h1>
      </div>

      <!-- Subheadline -->
      <p class="animate-fade-up opacity-0 mx-auto mt-6 max-w-xl text-center text-lg leading-relaxed text-white/55" style="animation-delay: 0.35s">
        Jetlag fixes timestamps across GoPro, iPhone, drone, and cinema cameras so your footage lands in
        the right place in your video editor — automatically.
      </p>

      <!-- CTAs -->
      <div class="animate-fade-up opacity-0 mt-10 flex flex-wrap items-center justify-center gap-4" style="animation-delay: 0.5s">
        <a href="#download" class="btn-primary text-base px-8 py-3.5">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M8 1v9M4 7l4 4 4-4M2 14h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          Download free for macOS
        </a>
        <a href="#pricing" class="btn-secondary text-base px-8 py-3.5">
          Unlock Pro — one-time $29
        </a>
      </div>

      <!-- Trust line -->
      <p class="animate-fade-up opacity-0 mt-6 text-sm text-white/30" style="animation-delay: 0.6s">
        macOS 13 Ventura or later &nbsp;·&nbsp; No subscription &nbsp;·&nbsp; Free tier included
      </p>

      <!-- App preview / diagram -->
      <div class="animate-fade-up opacity-0 mt-16 w-full max-w-4xl" style="animation-delay: 0.75s">
        <div class="relative rounded-2xl border border-white/10 bg-neutral-900/60 p-1 shadow-2xl backdrop-blur-sm">
          <!-- Fake window chrome -->
          <div class="flex items-center gap-1.5 px-4 py-3 border-b border-white/8">
            <div class="h-3 w-3 rounded-full bg-red-500/70"></div>
            <div class="h-3 w-3 rounded-full bg-yellow-500/70"></div>
            <div class="h-3 w-3 rounded-full bg-green-500/70"></div>
            <span class="ml-3 text-xs text-white/25 font-mono">Jetlag — Workflow</span>
          </div>
          <!-- Fake app content -->
          <div class="grid grid-cols-[180px_1fr] min-h-[240px]">
            <!-- Sidebar -->
            <div class="border-r border-white/8 p-4 space-y-1">
              <div class="flex items-center gap-2 rounded-lg bg-neon-pink/15 px-3 py-2">
                <div class="h-4 w-4 rounded bg-neon-pink/50"></div>
                <span class="text-xs text-neon-pink font-medium">Workflow</span>
              </div>
              <div class="flex items-center gap-2 rounded-lg px-3 py-2">
                <div class="h-4 w-4 rounded bg-white/15"></div>
                <span class="text-xs text-white/40">Profiles</span>
              </div>
            </div>
            <!-- Main content -->
            <div class="p-5 space-y-4">
              <div class="space-y-2">
                <div class="text-xs text-white/30 uppercase tracking-widest font-medium">Profile</div>
                <div class="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70">
                  <div class="h-2 w-2 rounded-full bg-amber-400"></div>
                  GoPro HERO12
                </div>
              </div>
              <div class="space-y-2">
                <div class="text-xs text-white/30 uppercase tracking-widest font-medium">Pipeline</div>
                <div class="flex items-center gap-1">
                  ${['Import', 'Tag', 'Fix Time', 'Organize', 'Gyroflow'].map((step, i) => /* html */`
                    <div class="rounded px-2 py-1 text-xs font-medium ${i === 0 || i === 2 ? 'bg-neon-pink/20 text-neon-pink' : i < 4 ? 'bg-amber-500/20 text-amber-300' : 'bg-white/5 text-white/30'}">${step}</div>
                    ${i < 4 ? '<div class="text-white/20 text-xs">›</div>' : ''}
                  `).join('')}
                </div>
              </div>
              <div class="mt-2 rounded-xl bg-neutral-950/60 p-3 font-mono text-xs leading-relaxed text-white/40">
                <span class="text-green-400/80">✓</span> GH012345.MP4 &nbsp; birth → 2024-03-15 08:07:22 +0800<br>
                <span class="text-green-400/80">✓</span> IMG_0923.MOV &nbsp; birth → 2024-03-15 08:09:44 +0800<br>
                <span class="text-green-400/80">✓</span> DJI_0011.MP4 &nbsp; birth → 2024-03-15 08:11:03 +0800<br>
                <span class="text-neon-pink/60">→</span> 3 files processed, 0 errors
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  `
}
