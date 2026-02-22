const steps = [
  {
    number: '01',
    title: 'Connect your SD card',
    description: 'Plug in your memory card or point Jetlag at any folder of raw footage. It reads your camera profile to know which file extensions to look for.',
  },
  {
    number: '02',
    title: 'Pick a profile & timezone',
    description: 'Select the camera profile you set up once. Set the timezone where you shot (the offset that goes with DateTimeOriginal). That\'s it.',
  },
  {
    number: '03',
    title: 'Dry run, then apply',
    description: 'Preview every timestamp change and file move before committing. When you\'re satisfied, hit Apply. Jetlag processes one file at a time — safe to interrupt.',
  },
  {
    number: '04',
    title: 'Import to your editor',
    description: 'Drag your organized folder into your video editor. The "Content Created" column shows the corrected shoot times and your multi-camera timeline just… works.',
  },
]

export function renderHowItWorks() {
  return /* html */`
    <section id="how-it-works" class="py-24 px-6">
      <div class="mx-auto max-w-5xl">
        <div class="text-center mb-14">
          <span class="section-label">How it works</span>
          <h2 class="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
            From card to cut in four steps
          </h2>
        </div>

        <div class="relative">
          <!-- Connecting line -->
          <div class="absolute left-[26px] top-12 bottom-12 w-px bg-gradient-to-b from-neon-pink/50 via-amber-500/30 to-transparent hidden sm:block"></div>

          <div class="space-y-8">
            ${steps.map((step, i) => /* html */`
              <div class="flex gap-6 group">
                <div class="relative flex-shrink-0 z-10">
                  <div class="flex h-[52px] w-[52px] items-center justify-center rounded-xl border font-mono text-sm font-bold bg-neutral-950
                    ${i % 2 === 0
                      ? 'border-neon-pink/50 text-neon-pink'
                      : 'border-amber-500/50 text-amber-400'}">
                    ${step.number}
                  </div>
                </div>
                <div class="pt-3 pb-2">
                  <h3 class="text-base font-semibold text-white mb-1.5">${step.title}</h3>
                  <p class="text-sm leading-relaxed text-white/50 max-w-lg">${step.description}</p>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Workflow diagram note -->
        <div class="mt-14 rounded-2xl border border-white/8 bg-white/4 p-6">
          <p class="text-xs uppercase tracking-widest text-white/30 font-medium mb-4">Pipeline overview</p>
          <div class="flex flex-wrap items-center gap-2 text-sm">
            ${['Import from card', 'Tag', 'Fix timestamps', 'Organize by date', 'Generate Gyroflow'].map((step, i, arr) => /* html */`
              <span class="rounded-lg border px-3 py-1.5 text-xs font-medium
                ${i % 2 === 0
                  ? 'border-neon-pink/20 bg-neon-pink/8 text-neon-pink/80'
                  : 'border-amber-500/20 bg-amber-500/8 text-amber-300/80'}">${step}</span>
              ${i < arr.length - 1 ? '<span class="text-white/20 text-xs">→</span>' : ''}
            `).join('')}
          </div>
          <p class="mt-4 text-xs text-white/35">
            Each step is independently toggleable. Run just timestamp fixing on existing footage,
            or run the full import → organize → gyroflow pipeline from a memory card.
          </p>
        </div>
      </div>
    </section>
  `
}
