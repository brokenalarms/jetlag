import { renderScenarioCards } from '../components/timeline.js'

export function renderProblem() {
  // Clip fields: time (HH:MM), day (0-based, 0=same day as first clip),
  // tz (display string), correct (bool), file (label), color (blue|green|purple).
  // Bar positions are derived automatically by the timeline component.
  const scenarios = [
    {
      num: '01',
      title: 'Filmed in Amsterdam, flew to Seoul, shot the next morning',
      body: `You film in Amsterdam at 2pm (+02:00), fly overnight to Seoul (+09:00), and shoot the next morning at 9am — but the GoPro was never updated. Seoul's 9am stores as 02:07 Amsterdam time: it lands on the right day but 7 hours too early, as if you filmed in the middle of the night.`,
      before: {
        // GoPro still on +02:00: Seoul 09:07 local = 02:07 Amsterdam time, day 1 (next day)
        clips: [
          { day: 0, time: '14:12', tz: '[+02:00]',    correct: true,  file: 'amsterdam_day1.MP4', color: 'blue'  },
          { day: 1, time: '02:07', tz: '[+02:00  ✗]', correct: false, file: 'seoul_day2.MP4',     color: 'green' },
        ],
        caption: 'Seoul appears 7 hours too early — camera clock never left +02:00',
      },
      after: {
        // Corrected: Seoul day 1 (next day), 09:07 +09:00
        clips: [
          { day: 0, time: '14:12', tz: '[+02:00]', correct: true, file: 'amsterdam_day1.MP4', color: 'blue'  },
          { day: 1, time: '09:07', tz: '[+09:00]', correct: true, file: 'seoul_day2.MP4',     color: 'green' },
        ],
        caption: 'Seoul correctly placed: 9am the next morning, after Amsterdam',
      },
    },
    {
      num: '02',
      title: 'GoPro shot ten minutes after iPhone — appearing seven hours later',
      body: `You shoot a market stall on your iPhone at 08:00, then pull out the GoPro ten minutes later. GoPro doesn't embed a timezone in DateTimeOriginal. Your editor falls back to the file's birth time, which gets set to whenever you copied the SD card — hours after the fact. The right time is in the file; it just needs pairing with your timezone.`,
      before: {
        clips: [
          { day: 0, time: '08:00', tz: '[+08:00]',   correct: true,  file: 'IMG_0812.MOV', color: 'green' },
          { day: 0, time: '15:43', tz: '[no tz  ✗]', correct: false, file: 'GH012345.MP4', color: 'blue'  },
        ],
        caption: '7h 43m gap — GoPro birth time set at copy, not at capture',
      },
      after: {
        clips: [
          { day: 0, time: '08:00', tz: '[+08:00]', correct: true, file: 'IMG_0812.MOV', color: 'green' },
          { day: 0, time: '08:10', tz: '[+08:00]', correct: true, file: 'GH012345.MP4', color: 'blue'  },
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
          { day: 0, time: '18:07', tz: '[+09:00]',       correct: true,  file: 'iphone_sunset.MOV', color: 'green'  },
          { day: 0, time: '09:07', tz: '[UTC→local  ✗]', correct: false, file: 'DJI_0011.MP4',       color: 'purple' },
        ],
        caption: 'Drone appears 9 hours early — UTC timestamp misread as local time',
      },
      after: {
        clips: [
          { day: 0, time: '18:07', tz: '[+09:00]', correct: true, file: 'iphone_sunset.MOV', color: 'green'  },
          { day: 0, time: '18:09', tz: '[+09:00]', correct: true, file: 'DJI_0011.MP4',      color: 'purple' },
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
          <h2 class="vhs-scanlines mt-5 text-3xl font-bold tracking-tight sm:text-4xl">
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
                <span class="mt-0.5 flex-shrink-0 font-mono text-xs font-bold text-amber-400/80 border border-amber-500/25 rounded px-1.5 py-0.5 leading-tight">${s.num}</span>
                <div>
                  <h3 class="text-base font-semibold text-white mb-1.5">${s.title}</h3>
                  <p class="text-sm leading-relaxed text-white/50 max-w-2xl">${s.body}</p>
                </div>
              </div>
              <div class="grid gap-4 sm:grid-cols-2 overflow-x-auto">
                ${renderScenarioCards(s.before, s.after)}
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
