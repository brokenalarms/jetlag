/**
 * Interactive timeline component for problem-section scenarios.
 *
 * Clips supply { time: 'HH:MM', day: 0|1|2, tz, file, color, correct }.
 * Bar positions are derived automatically — no manual offset/width needed.
 * A draggable slider interpolates each clip between its "before" (broken)
 * and "after" (corrected) position. The time axis uses hour ticks to show
 * the true relative spacing of the footage.
 */

const colorMap = {
  blue:   { bar: 'bg-blue-500/30 border-blue-400/20',   text: 'text-blue-300/70' },
  green:  { bar: 'bg-green-500/30 border-green-400/20', text: 'text-green-300/70' },
  purple: { bar: 'bg-purple-500/30 border-purple-400/20', text: 'text-purple-300/70' },
}

const CLIP_WIDTH    = 100
const BAR_AREA      = 290
const PAD_MINUTES   = 70

function toMinutes({ time, day = 0 }) {
  const [h, m] = time.split(':').map(Number)
  return day * 1440 + h * 60 + m
}

function buildScale(clips) {
  const times      = clips.map(toMinutes)
  const minTime    = Math.min(...times)
  const maxTime    = Math.max(...times)
  const scaleStart = Math.max(0, minTime - PAD_MINUTES)
  const scaleEnd   = maxTime + PAD_MINUTES
  const pxPerMin   = (BAR_AREA - CLIP_WIDTH) / (scaleEnd - scaleStart)
  return { scaleStart, scaleEnd, pxPerMin }
}

function clipOffset(clip, scale) {
  return Math.round((toMinutes(clip) - scale.scaleStart) * scale.pxPerMin)
}

function buildTicks(scale) {
  const { scaleStart, scaleEnd, pxPerMin } = scale
  const durationMin = scaleEnd - scaleStart
  const interval    = durationMin > 15 * 60 ? 6 : durationMin > 6 * 60 ? 3 : 2
  const ticks       = []
  const startH      = Math.ceil(scaleStart / 60)
  const endH        = Math.floor(scaleEnd   / 60)
  for (let h = startH; h <= endH; h++) {
    if (h % interval !== 0) continue
    const px = Math.round((h * 60 - scaleStart) * pxPerMin)
    if (px < 0 || px > BAR_AREA) continue
    const dispH    = h % 24
    const isNewDay = h % 24 === 0 && h > 0
    ticks.push({ px, label: `${String(dispH).padStart(2, '0')}:00`, isNewDay })
  }
  return ticks
}

// 124px = w-28 (112px) + gap-3 (12px) — aligns axis with the bar area.
const AXIS_MARGIN = 124

function renderAxis(scale) {
  const ticks = buildTicks(scale)
  return /* html */`
    <div class="relative h-5 border-t border-white/8 mt-1"
         style="margin-left:${AXIS_MARGIN}px; width:${BAR_AREA}px">
      ${ticks.map(({ px, label, isNewDay }) => /* html */`
        <div class="absolute top-0 flex flex-col items-center"
             style="left:${px}px; transform:translateX(-50%)">
          <div class="h-1.5 w-px ${isNewDay ? 'bg-white/20' : 'bg-white/10'}"></div>
          <div class="text-[9px] mt-0.5 ${isNewDay ? 'text-white/30' : 'text-white/20'}">${label}</div>
        </div>
      `).join('')}
    </div>
  `
}

// --- Interactive timeline slider ---

const scenarioStore = []

function formatMinutes(totalMin) {
  const rounded = Math.round(totalMin)
  const day     = Math.floor(rounded / 1440)
  const rem     = rounded - day * 1440
  const h       = Math.floor(rem / 60)
  const m       = rem % 60
  return {
    day,
    time: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`,
  }
}

export function renderInteractiveTimeline(before, after) {
  const sharedScale = buildScale([...before.clips, ...after.clips])
  const idx = scenarioStore.length

  const allClips = [...before.clips, ...after.clips]
  const days     = new Set(allClips.map(c => c.day ?? 0))
  const multiDay = days.size > 1

  const clipEntries = before.clips.map((bClip, i) => ({
    before:       bClip,
    after:        after.clips[i],
    beforeOffset: clipOffset(bClip, sharedScale),
    afterOffset:  clipOffset(after.clips[i], sharedScale),
    beforeMin:    toMinutes(bClip),
    afterMin:     toMinutes(after.clips[i]),
  }))

  scenarioStore.push({
    clips:         clipEntries,
    beforeCaption: before.caption,
    afterCaption:  after.caption,
  })

  return /* html */`
    <div class="timeline-interactive card" data-scenario="${idx}">
      <div class="mb-3 flex items-center gap-3">
        <div class="flex items-center gap-2 flex-shrink-0">
          <div class="h-2 w-2 rounded-full bg-red-400 tl-dot"></div>
          <span class="text-xs font-semibold uppercase tracking-widest text-red-400/80 tl-before-label">Before</span>
        </div>
        <input type="range" min="0" max="100" value="0" class="timeline-range flex-1">
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="text-xs font-semibold uppercase tracking-widest text-white/20 tl-after-label">After</span>
          <div class="h-2 w-2 rounded-full bg-neon-pink/30 tl-dot-after"></div>
        </div>
      </div>
      <div class="space-y-2">
        ${clipEntries.map(({ before: b, beforeOffset }) => {
          const c       = colorMap[b.color]
          const tzClass = b.correct ? 'text-white/25' : 'text-red-400/70'
          const dayTag  = multiDay
            ? `<div class="text-[9px] text-white/20 mb-0.5 tl-day">Day ${(b.day ?? 0) + 1}</div>`
            : ''
          return /* html */`
            <div class="flex items-center gap-3">
              <div class="w-28 text-right font-mono leading-tight flex-shrink-0">
                ${dayTag}
                <div class="text-xs text-white/35 tl-time">${b.time}</div>
                <div class="text-[10px] tl-tz ${tzClass}">${b.tz}</div>
              </div>
              <div class="h-7 rounded ${c.bar} ${c.text} border flex items-center px-2.5 text-[11px] overflow-hidden flex-shrink-0 tl-bar"
                   style="width:${CLIP_WIDTH}px; margin-left:${beforeOffset}px">${b.file}</div>
            </div>
          `
        }).join('')}
      </div>
      ${renderAxis(sharedScale)}
      <p class="mt-3 text-xs tl-caption text-white/30">${before.caption}</p>
    </div>
  `
}

export function initTimelineSliders() {
  document.querySelectorAll('.timeline-interactive').forEach(card => {
    const idx  = parseInt(card.dataset.scenario, 10)
    const data = scenarioStore[idx]
    if (!data) return

    const range       = card.querySelector('.timeline-range')
    const bars        = card.querySelectorAll('.tl-bar')
    const times       = card.querySelectorAll('.tl-time')
    const tzs         = card.querySelectorAll('.tl-tz')
    const dayLabels   = card.querySelectorAll('.tl-day')
    const caption     = card.querySelector('.tl-caption')
    const beforeLabel = card.querySelector('.tl-before-label')
    const afterLabel  = card.querySelector('.tl-after-label')
    const dotBefore   = card.querySelector('.tl-dot')
    const dotAfter    = card.querySelector('.tl-dot-after')

    range.addEventListener('input', () => {
      const t = range.value / 100

      data.clips.forEach((clip, i) => {
        const offset = Math.round(clip.beforeOffset + (clip.afterOffset - clip.beforeOffset) * t)
        bars[i].style.marginLeft = `${offset}px`

        const currentMin    = clip.beforeMin + (clip.afterMin - clip.beforeMin) * t
        const { day, time } = formatMinutes(currentMin)
        times[i].textContent = time
        if (dayLabels[i]) dayLabels[i].textContent = `Day ${day + 1}`

        const isAfter = t >= 0.5
        const src     = isAfter ? clip.after : clip.before
        tzs[i].textContent = src.tz
        tzs[i].className   = `text-[10px] tl-tz ${src.correct ? 'text-white/25' : 'text-red-400/70'}`
      })

      const isAfter = t >= 0.5
      caption.textContent = isAfter ? data.afterCaption : data.beforeCaption
      caption.className   = `mt-3 text-xs tl-caption ${isAfter ? 'text-neon-pink/60' : 'text-white/30'}`

      beforeLabel.className = `text-xs font-semibold uppercase tracking-widest tl-before-label ${t < 0.5 ? 'text-red-400/80' : 'text-red-400/30'}`
      afterLabel.className  = `text-xs font-semibold uppercase tracking-widest tl-after-label ${t >= 0.5 ? 'text-neon-pink/80' : 'text-white/20'}`

      dotBefore.className = `h-2 w-2 rounded-full tl-dot ${t < 0.5 ? 'bg-red-400' : 'bg-red-400/30'}`
      dotAfter.className  = `h-2 w-2 rounded-full tl-dot-after ${t >= 0.5 ? 'bg-neon-pink' : 'bg-neon-pink/30'}`

      card.classList.toggle('timeline-active', t >= 0.5)
    })
  })
}
