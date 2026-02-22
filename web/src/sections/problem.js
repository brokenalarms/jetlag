export function renderProblem() {
  const colorMap = {
    blue:   { bar: 'bg-blue-500/30 border-blue-400/20',   text: 'text-blue-300/70' },
    green:  { bar: 'bg-green-500/30 border-green-400/20', text: 'text-green-300/70' },
    purple: { bar: 'bg-purple-500/30 border-purple-400/20', text: 'text-purple-300/70' },
  }

  const renderClip = (clip) => {
    const c = colorMap[clip.color]
    const tzClass = clip.correct ? 'text-white/25' : 'text-red-400/70'
    return /* html */`
      <div class="flex items-center gap-3">
        <div class="w-28 text-right font-mono leading-tight flex-shrink-0">
          <div class="text-xs text-white/35">${clip.time}</div>
          <div class="text-[10px] ${tzClass}">${clip.tz}</div>
        </div>
        <div class="h-7 rounded ${c.bar} ${c.text} border flex items-center px-2.5 text-[11px] overflow-hidden"
             style="width:${clip.width}px; margin-left:${clip.offset}px; flex-shrink:0">${clip.file}</div>
      </div>
    `
  }

  const renderCard = (card, isAfter) => {
    const dot        = isAfter ? 'bg-amber-400'      : 'bg-red-400'
    const labelClass = isAfter ? 'text-amber-400/80' : 'text-red-400/80'
    const label      = isAfter ? 'After Jetlag'      : 'Before Jetlag'
    const cardClass  = isAfter ? 'card border-amber-500/20 bg-amber-500/5' : 'card'
    const capClass   = isAfter ? 'text-amber-400/60' : 'text-white/30'
    return /* html */`
      <div class="${cardClass}">
        <div class="mb-3 flex items-center gap-2">
          <div class="h-2 w-2 rounded-full ${dot}"></div>
          <span class="text-xs font-semibold uppercase tracking-widest ${labelClass}">${label}</span>
        </div>
        <div class="space-y-3">
          ${card.clips.map(renderClip).join('')}
        </div>
        <p class="mt-3 text-xs ${capClass}">${card.caption}</p>
      </div>
    `
  }

  // Timeline uses a 24-hour scale mapped to ~250px usable width.
  // offset = Math.round((h*60+m) / 1440 * 250)
  const scenarios = [
    {
      num: '01',
      title: 'Crossed a timezone, forgot to update the camera',
      body: `Flying from Amsterdam (+02:00) to Seoul (+09:00) for the next leg of a food trip, you forget to update the GoPro. Day two footage shot at 09:07am Seoul time reads as 02:07am in your editor — appearing to have been shot in the middle of the previous night, before clips from the day before.`,
      before: {
        clips: [
          { time: '14:12', tz: '[+02:00]',    correct: true,  file: 'amsterdam_day1.MP4', color: 'blue',  width: 130, offset: 148 },
          { time: '02:07', tz: '[+02:00  ✗]', correct: false, file: 'seoul_day2.MP4',     color: 'green', width: 110, offset: 22  },
        ],
        caption: 'Seoul footage appears at 2am — camera clock never left Amsterdam',
      },
      after: {
        clips: [
          { time: '14:12', tz: '[+02:00]', correct: true, file: 'amsterdam_day1.MP4', color: 'blue',  width: 130, offset: 148 },
          { time: '09:07', tz: '[+09:00]', correct: true, file: 'seoul_day2.MP4',     color: 'green', width: 110, offset: 95  },
        ],
        caption: 'Jetlag applies +09:00 — Seoul footage correctly placed in the morning',
      },
    },
    {
      num: '02',
      title: 'GoPro shot ten minutes after iPhone — appearing seven hours later',
      body: `You shoot a market stall on your iPhone at 08:00, then pull out the GoPro ten minutes later. GoPro doesn't embed a timezone in DateTimeOriginal. Your editor falls back to the file's birth time, which gets set to whenever you copied the SD card — hours after the fact. The right time is in the file; it just needs pairing with your timezone.`,
      before: {
        clips: [
          { time: '08:00', tz: '[+08:00]',  correct: true,  file: 'IMG_0812.MOV', color: 'green', width: 115, offset: 83  },
          { time: '15:43', tz: '[no tz  ✗]', correct: false, file: 'GH012345.MP4', color: 'blue',  width: 115, offset: 164 },
        ],
        caption: '7h 43m gap — GoPro birth time set at copy, not at capture',
      },
      after: {
        clips: [
          { time: '08:00', tz: '[+08:00]', correct: true, file: 'IMG_0812.MOV', color: 'green', width: 115, offset: 83 },
          { time: '08:10', tz: '[+08:00]', correct: true, file: 'GH012345.MP4', color: 'blue',  width: 115, offset: 85 },
        ],
        caption: 'GoPro lands 10 minutes after iPhone, exactly as shot',
      },
    },
    {
      num: '03',
      title: 'Drone footage offset by an entire timezone',
      body: `DJI drones store MediaCreateDate in UTC. Many editors read that integer field and treat it as local time. Shoot at sunset (18:07) in Tokyo (+09:00) and the clip lands at 09:07 — nine hours early, as if filmed before dawn. The same issue affects any camera that correctly stores UTC but whose timezone context is then lost on import.`,
      before: {
        clips: [
          { time: '18:07', tz: '[+09:00]',       correct: true,  file: 'iphone_sunset.MOV', color: 'green',  width: 115, offset: 189 },
          { time: '09:07', tz: '[UTC→local  ✗]', correct: false, file: 'DJI_0011.MP4',       color: 'purple', width: 100, offset: 95  },
        ],
        caption: 'Drone appears 9 hours early — UTC timestamp misread as local time',
      },
      after: {
        clips: [
          { time: '18:07', tz: '[+09:00]', correct: true, file: 'iphone_sunset.MOV', color: 'green',  width: 115, offset: 189 },
          { time: '18:09', tz: '[+09:00]', correct: true, file: 'DJI_0011.MP4',      color: 'purple', width: 100, offset: 191 },
        ],
        caption: 'Drone and iPhone land at the same sunset moment',
      },
    },
  ]

  return /* html */`
    <section class="py-24 px-6">
      <div class="mx-auto max-w-5xl">

        <!-- Section header -->
        <div class="mb-16 text-center">
          <span class="section-label">The Problem</span>
          <h2 class="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
            Cameras lie about time
          </h2>
          <p class="mt-4 mx-auto max-w-2xl text-base leading-relaxed text-white/55">
            Every camera stores timestamps differently — different fields, different timezone handling,
            different filesystem quirks. The result is always the same: footage from the same shoot
            scattered hours apart in your editor's timeline.
          </p>
        </div>

        <!-- Scenarios -->
        <div class="space-y-14">
          ${scenarios.map(s => /* html */`
            <div>
              <div class="mb-5 flex gap-3 items-start">
                <span class="mt-0.5 flex-shrink-0 font-mono text-xs font-bold text-amber-500/60 border border-amber-500/20 rounded px-1.5 py-0.5 leading-tight">${s.num}</span>
                <div>
                  <h3 class="text-base font-semibold text-white mb-1.5">${s.title}</h3>
                  <p class="text-sm leading-relaxed text-white/50 max-w-2xl">${s.body}</p>
                </div>
              </div>
              <div class="grid gap-4 sm:grid-cols-2 overflow-x-auto">
                ${renderCard(s.before, false)}
                ${renderCard(s.after, true)}
              </div>
            </div>
          `).join('')}
        </div>

        <!-- What Jetlag actually fixes -->
        <div class="mt-14 rounded-2xl border border-white/8 bg-white/3 px-6 py-5 space-y-2">
          <p class="text-sm leading-relaxed text-white/45">
            <span class="font-semibold text-white/70">What actually gets corrected.</span>
            Jetlag fixes timezone labelling relative to UTC — a clip shot at 10am in Seoul is stamped
            10:00+09:00 (01:00 UTC). It will display as 10am in Seoul, 2am in Berlin, 6pm the day before
            in New York — wherever your editor's timezone is set. Clips slot into the timeline at the
            moment they were captured, correctly relative to each other.
          </p>
          <p class="text-sm leading-relaxed text-white/35">
            What can't be fixed: if your device clock was set to the wrong hour — not just the wrong
            timezone — there's no metadata to recover the true capture time from.
          </p>
        </div>

      </div>
    </section>
  `
}
