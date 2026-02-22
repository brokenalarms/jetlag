const audiences = [
  {
    cardClasses: 'border-neon-pink/15 bg-neon-pink/5 hover:border-neon-pink/25 hover:bg-neon-pink/8',
    iconClasses: 'bg-neon-pink/15 text-neon-pink',
    taglineClass: 'text-neon-pink',
    icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
      <path d="M12 3C9.5 5.5 8 8.5 8 12C8 15.5 9.5 18.5 12 21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M12 3C14.5 5.5 16 8.5 16 12C16 15.5 14.5 18.5 12 21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M3 12h18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M4.5 8h15M4.5 16h15" stroke="currentColor" stroke-width="1" stroke-linecap="round" opacity="0.5"/>
    </svg>`,
    title: 'Digital nomads',
    tagline: 'A new city every few weeks, a new timezone every few days',
    description: "You work from wherever you want. Your footage should follow suit. Jetlag re-anchors your clips to the right timezone automatically, so that Lisbon Monday and Bangkok Thursday both land exactly where they belong in your edit.",
  },
  {
    cardClasses: 'border-neon-cyan/15 bg-neon-cyan/5 hover:border-neon-cyan/25 hover:bg-neon-cyan/8',
    iconClasses: 'bg-neon-cyan/15 text-neon-cyan',
    taglineClass: 'text-neon-cyan',
    icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="6.5" cy="15.5" r="3.5" stroke="currentColor" stroke-width="1.5"/>
      <circle cx="17.5" cy="15.5" r="3.5" stroke="currentColor" stroke-width="1.5"/>
      <path d="M6.5 15.5L10 8.5L14 15.5L17.5 15.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M10 8.5L12 6.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M14.5 8.5H17.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    title: 'Bikepackers & adventurers',
    tagline: 'Weeks in the saddle across borders',
    description: "GoPro on the bars, phone in the hip pack. Multi-week routes cross timezones every few days, and your editor won't know that unless Jetlag tells it. Cross a border, and your footage stays true to the ride.",
  },
  {
    cardClasses: 'border-amber-500/20 bg-amber-500/5 hover:border-amber-500/35 hover:bg-amber-500/8',
    iconClasses: 'bg-amber-500/15 text-amber-400',
    taglineClass: 'text-amber-400',
    icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="5" y="8" width="12" height="13" rx="2.5" stroke="currentColor" stroke-width="1.5"/>
      <path d="M9 8V5C9 4 10 3 12 3C14 3 15 4 15 5V8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <rect x="7.5" y="13.5" width="7" height="4.5" rx="1" stroke="currentColor" stroke-width="1.5"/>
      <path d="M9.5 11H14.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,
    title: 'Backpackers & gap-year travelers',
    tagline: 'Months abroad, a dozen countries, one chaotic camera roll',
    description: "A year away means timestamps scattered across every timezone you passed through. When you sit down to cut the highlights, Jetlag has already untangled the timeline so your story plays in order.",
  },
  {
    cardClasses: 'border-neon-purple/15 bg-neon-purple/5 hover:border-neon-purple/25 hover:bg-neon-purple/8',
    iconClasses: 'bg-neon-purple/15 text-neon-purple',
    taglineClass: 'text-neon-purple',
    icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="2" y="6" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M16 10L22 7V17L16 14V10Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,
    title: 'Travel content creators',
    tagline: 'Multi-camera workflow, weekly uploads, no time to waste',
    description: "Three cameras, daily vlogs, and a drive that fills faster than your upload queue. Jetlag automates the intake so footage is organised and timestamped the moment it lands — ready to cut, not to fix.",
  },
]

export function renderAudience() {
  return /* html */`
    <section id="audience" class="py-24 px-6">
      <div class="mx-auto max-w-6xl">

        <div class="text-center mb-14">
          <span class="section-label">Who it's for</span>
          <h2 class="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
            Made for people who don't stop moving
          </h2>
          <p class="mt-4 mx-auto max-w-2xl text-base leading-relaxed text-white/55">
            Whether it's a dream gap year, a cross-continent bikepacking route, or life as a full-time
            digital nomad — if you film your journey and cross timezones doing it, Jetlag was built for you.
          </p>
        </div>

        <div class="grid gap-6 sm:grid-cols-2">
          ${audiences.map(a => /* html */`
            <div class="rounded-2xl border ${a.cardClasses} p-7 backdrop-blur-sm transition-all group">
              <div class="flex h-12 w-12 items-center justify-center rounded-xl ${a.iconClasses} mb-5">
                ${a.icon}
              </div>
              <h3 class="text-base font-semibold text-white mb-1">${a.title}</h3>
              <p class="text-xs font-semibold uppercase tracking-wide ${a.taglineClass} mb-3 opacity-80">${a.tagline}</p>
              <p class="text-sm leading-relaxed text-white/50">${a.description}</p>
            </div>
          `).join('')}
        </div>

        <div class="mt-10 rounded-2xl border border-white/8 bg-white/[0.03] p-8 text-center">
          <p class="text-base leading-relaxed text-white/60 max-w-2xl mx-auto">
            If you shoot across timezones and edit video, an automatic intake workflow sets you up
            to <span class="text-white font-semibold">tell the story</span> rather than
            <span class="text-white font-semibold">fix the timestamps</span>.
          </p>
        </div>

      </div>
    </section>
  `
}
