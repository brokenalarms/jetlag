/**
 * Shared timeline component used by all problem-section scenarios.
 *
 * Clips supply { time: 'HH:MM', day: 0|1|2, tz, file, color, correct }.
 * Bar positions are derived automatically — no manual offset/width needed.
 * A time-axis with hour ticks is rendered below the clips so each card
 * shows the true relative spacing of the footage.
 *
 * Each scenario renders as a single interactive card with a draggable slider
 * that transitions clips between their broken (before) and corrected (after)
 * positions. The before state is the default; dragging right reveals the
 * corrected positions with smooth transitions.
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

function renderSliderClip(bClip, aClip, beforeOff, afterOff, multiDay) {
  const c = colorMap[bClip.color]
  const bTzClass = bClip.correct ? 'text-white/25' : 'text-red-400/70'
  const aTzClass = aClip.correct ? 'text-white/25' : 'text-red-400/70'

  const bDayTag = multiDay
    ? `<div class="text-[9px] text-white/20 mb-0.5">Day ${(bClip.day ?? 0) + 1}</div>`
    : ''
  const aDayTag = multiDay
    ? `<div class="text-[9px] text-white/20 mb-0.5">Day ${(aClip.day ?? 0) + 1}</div>`
    : ''

  const labelsMatch = bClip.time === aClip.time && bClip.tz === aClip.tz

  const labelHTML = labelsMatch
    ? /* html */`
        ${bDayTag}
        <div class="text-xs text-white/35">${bClip.time}</div>
        <div class="text-[10px] ${bTzClass}">${bClip.tz}</div>
      `
    : /* html */`
        <div class="slider-label-before transition-opacity duration-200">
          ${bDayTag}
          <div class="text-xs text-white/35">${bClip.time}</div>
          <div class="text-[10px] ${bTzClass}">${bClip.tz}</div>
        </div>
        <div class="slider-label-after absolute inset-0 text-right opacity-0 transition-opacity duration-200">
          ${aDayTag}
          <div class="text-xs text-white/35">${aClip.time}</div>
          <div class="text-[10px] ${aTzClass}">${aClip.tz}</div>
        </div>
      `

  return /* html */`
    <div class="flex items-center gap-3">
      <div class="w-28 text-right font-mono leading-tight flex-shrink-0 relative">
        ${labelHTML}
      </div>
      <div class="h-7 rounded ${c.bar} ${c.text} border flex items-center px-2.5 text-[11px] overflow-hidden flex-shrink-0"
           style="width:${CLIP_WIDTH}px; margin-left:${beforeOff}px"
           data-before="${beforeOff}"
           data-after="${afterOff}">${bClip.file}</div>
    </div>
  `
}

function renderSliderCard(before, after, scale) {
  const allClips = [...before.clips, ...after.clips]
  const days = new Set(allClips.map(c => c.day ?? 0))
  const multiDay = days.size > 1

  const clipsHTML = before.clips.map((bClip, i) => {
    const aClip = after.clips[i]
    const beforeOff = clipOffset(bClip, scale)
    const afterOff = clipOffset(aClip, scale)
    return renderSliderClip(bClip, aClip, beforeOff, afterOff, multiDay)
  }).join('')

  return /* html */`
    <div class="scenario-slider card" data-state="before">
      <div class="mb-3 flex items-center gap-2">
        <div class="slider-dot h-2 w-2 rounded-full bg-red-400 transition-colors duration-300"></div>
        <span class="slider-state-label text-xs font-semibold uppercase tracking-widest text-red-400/80 transition-colors duration-300">Before Jetlag</span>
      </div>
      <div class="space-y-2">
        ${clipsHTML}
      </div>
      ${renderAxis(scale)}
      <div class="mt-4 flex items-center gap-3">
        <span class="text-[10px] text-white/30 uppercase tracking-wider select-none">Before</span>
        <input type="range" min="0" max="100" value="0" class="slider-range flex-1" aria-label="Before/after timeline comparison" />
        <span class="text-[10px] text-white/30 uppercase tracking-wider select-none">After</span>
      </div>
      <p class="slider-caption-before mt-3 text-xs text-white/30">${before.caption}</p>
      <p class="slider-caption-after mt-3 text-xs text-neon-pink/60 hidden">${after.caption}</p>
    </div>
  `
}

export function renderScenarioCards(before, after) {
  const sharedScale = buildScale([...before.clips, ...after.clips])
  return renderSliderCard(before, after, sharedScale)
}

export function initSliders() {
  document.querySelectorAll('.scenario-slider').forEach(card => {
    const range = card.querySelector('.slider-range')
    if (!range) return

    const bars          = card.querySelectorAll('[data-before]')
    const dot           = card.querySelector('.slider-dot')
    const stateLabel    = card.querySelector('.slider-state-label')
    const captionBefore = card.querySelector('.slider-caption-before')
    const captionAfter  = card.querySelector('.slider-caption-after')
    const labelsBefore  = card.querySelectorAll('.slider-label-before')
    const labelsAfter   = card.querySelectorAll('.slider-label-after')

    let wasAfter = false

    range.addEventListener('input', () => {
      const progress = range.value / 100
      const isAfter = progress > 0.5

      bars.forEach(bar => {
        const b = parseFloat(bar.dataset.before)
        const a = parseFloat(bar.dataset.after)
        bar.style.marginLeft = `${Math.round(b + (a - b) * progress)}px`
      })

      if (isAfter === wasAfter) return
      wasAfter = isAfter

      card.dataset.state = isAfter ? 'after' : 'before'

      labelsBefore.forEach(l => { l.style.opacity = isAfter ? '0' : '1' })
      labelsAfter.forEach(l => { l.style.opacity = isAfter ? '1' : '0' })

      captionBefore.classList.toggle('hidden', isAfter)
      captionAfter.classList.toggle('hidden', !isAfter)

      dot.classList.toggle('bg-red-400', !isAfter)
      dot.classList.toggle('bg-neon-pink', isAfter)

      stateLabel.classList.toggle('text-red-400/80', !isAfter)
      stateLabel.classList.toggle('text-neon-pink/80', isAfter)
      stateLabel.textContent = isAfter ? 'After Jetlag' : 'Before Jetlag'
    })
  })
}
