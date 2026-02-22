const features = [
  {
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 2v4M10 14v4M2 10h4M14 10h4M4.93 4.93l2.83 2.83M12.24 12.24l2.83 2.83M4.93 15.07l2.83-2.83M12.24 7.76l2.83-2.83" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
    title: 'Camera-aware timestamp fixing',
    description: 'Understands GoPro FAT quirks, iPhone UTC offsets, DJI timezone handling, and Insta360 INSV files. Reads EXIF DateTimeOriginal as the source of truth — never overwrites it.',
  },
  {
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="5" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M6 5V4a1 1 0 011-1h6a1 1 0 011 1v1" stroke="currentColor" stroke-width="1.5"/><path d="M10 9v4M8 11h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
    title: '"Content Created" sync',
    description: 'Sets both the EXIF Keys:CreationDate field and the macOS file birth time — the two timestamps that populate "Content Created" on import and in the media browser.',
  },
  {
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4 4h4v4H4zM12 4h4v4h-4zM4 12h4v4H4zM12 12h4v4h-4z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>`,
    title: 'Camera profiles',
    description: 'Save per-camera settings: file extensions, import directory, EXIF make/model filters, Gyroflow presets. Switch between GoPro, iPhone, drone, and cinema with one click.',
  },
  {
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 10l4 4 10-10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    title: 'Smart date-based organization',
    description: 'Moves files into YYYY/GROUP/YYYY-MM-DD folders automatically. Cleans up empty source directories. Processes files alphabetically so interrupted runs are safely resumable.',
  },
  {
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.5"/><path d="M10 6v4l3 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
    title: 'Dry-run mode',
    description: 'Preview every change before it happens. See exactly which fields will be written, which files will move, and what the final timestamps will be — without touching a single file.',
  },
  {
    icon: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 10h10M5 6h10M5 14h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
    title: 'Gyroflow project generation',
    description: 'Automatically creates .gyroflow project files for the Gyroflow Toolbox plugin on footage with embedded gyro data. Non-fatal when gyro data is absent.',
  },
]

export function renderFeatures() {
  return /* html */`
    <section id="features" class="py-24 px-6 bg-white/[0.02]">
      <div class="mx-auto max-w-6xl">
        <div class="text-center mb-14">
          <span class="section-label">Features</span>
          <h2 class="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
            Everything your pipeline needs
          </h2>
          <p class="mt-4 mx-auto max-w-xl text-base text-white/50">
            Built for working filmmakers who shoot with multiple cameras and need footage
            to cut together without the manual timestamp headache.
          </p>
        </div>

        <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          ${features.map(f => /* html */`
            <div class="card group transition-all hover:border-white/15 hover:bg-white/6">
              <div class="feature-icon mb-4">${f.icon}</div>
              <h3 class="text-base font-semibold text-white mb-2">${f.title}</h3>
              <p class="text-sm leading-relaxed text-white/50">${f.description}</p>
            </div>
          `).join('')}
        </div>

        <!-- Camera logos strip -->
        <div class="mt-14 text-center">
          <p class="text-xs uppercase tracking-widest text-white/25 font-medium mb-6">Works with footage from</p>
          <div class="flex flex-wrap items-center justify-center gap-8">
            ${['GoPro', 'iPhone', 'DJI', 'Insta360', 'Sony', 'Canon'].map(cam => /* html */`
              <span class="text-sm font-semibold text-white/30">${cam}</span>
            `).join('')}
          </div>
        </div>

        <!-- Import by reference callout -->
        <div class="mt-10 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6">
          <div class="flex gap-4 items-start">
            <div class="feature-icon flex-shrink-0">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path d="M10 6v4M10 14h.01" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="1.5"/>
              </svg>
            </div>
            <div>
              <h3 class="text-base font-semibold text-white mb-1.5">Always import by reference in your video editor</h3>
              <p class="text-sm leading-relaxed text-white/50">
                Jetlag only writes timestamp metadata — it never re-encodes your video. Keep it that way
                in your editor too: some editors, including Final Cut Pro with Sony MP4s, re-encode footage
                during a standard library import, silently stripping embedded gyro stabilisation data and
                lens metadata that Gyroflow Toolbox and other plugins depend on. Import by reference instead
                (uncheck <span class="text-white/70 font-medium">"Copy to Library"</span> in FCP's import
                dialog) to keep your files exactly as shot, with all metadata intact.
              </p>
            </div>
          </div>
        </div>

      </div>
    </section>
  `
}
