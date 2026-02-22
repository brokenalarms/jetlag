/**
 * Shared timeline component used by all problem-section scenarios.
 *
 * Clips supply { time: 'HH:MM', day: 0|1|2, tz, file, color, correct }.
 * Bar positions are derived automatically — no manual offset/width needed.
 * A time-axis with hour ticks is rendered below the clips so each card
 * shows the true relative spacing of the footage.
 */

const colorMap = {
  blue:   { bar: 'bg-blue-500/30 border-blue-400/20',   text: 'text-blue-300/70' },
  green:  { bar: 'bg-green-500/30 border-green-400/20', text: 'text-green-300/70' },
  purple: { bar: 'bg-purple-500/30 border-purple-400/20', text: 'text-purple-300/70' },
}

// Width of each clip bar (px). The bar area is PAD…(BAR_AREA - CLIP_WIDTH + PAD)
// so both the first and last clip fit fully within the card.
const CLIP_WIDTH    = 100
const BAR_AREA      = 290   // px available from label-column edge to card edge
const PAD_MINUTES   = 70    // breathing room on each side of the time scale

function toMinutes({ time, day = 0 }) {
  const [h, m] = time.split(':').map(Number)
  return day * 1440 + h * 60 + m
}

// Build a scale object from a set of clips.
// pxPerMin maps the inner bar area [0 … BAR_AREA - CLIP_WIDTH] to the time range.
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

// Generate hour-tick marks visible within the scale.
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

function renderClip(clip, scale, multiDay) {
  const c       = colorMap[clip.color]
  const tzClass = clip.correct ? 'text-white/25' : 'text-red-400/70'
  const offset  = clipOffset(clip, scale)
  const dayTag  = multiDay
    ? `<div class="text-[9px] text-white/20 mb-0.5">Day ${(clip.day ?? 0) + 1}</div>`
    : ''
  return /* html */`
    <div class="flex items-center gap-3">
      <div class="w-28 text-right font-mono leading-tight flex-shrink-0">
        ${dayTag}
        <div class="text-xs text-white/35">${clip.time}</div>
        <div class="text-[10px] ${tzClass}">${clip.tz}</div>
      </div>
      <div class="h-7 rounded ${c.bar} ${c.text} border flex items-center px-2.5 text-[11px] overflow-hidden flex-shrink-0"
           style="width:${CLIP_WIDTH}px; margin-left:${offset}px">${clip.file}</div>
    </div>
  `
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

function renderCard(card, isAfter, scale) {
  const dot        = isAfter ? 'bg-neon-pink'              : 'bg-red-400'
  const labelClass = isAfter ? 'text-neon-pink/80'         : 'text-red-400/80'
  const label      = isAfter ? 'After Jetlag'              : 'Before Jetlag'
  const cardClass  = isAfter ? 'card border-neon-pink/20 bg-neon-pink/5' : 'card'
  const capClass   = isAfter ? 'text-neon-pink/60'         : 'text-white/30'

  // Show "Day N" labels when this card's clips span multiple days.
  const days     = new Set(card.clips.map(c => c.day ?? 0))
  const multiDay = days.size > 1

  return /* html */`
    <div class="${cardClass}">
      <div class="mb-3 flex items-center gap-2">
        <div class="h-2 w-2 rounded-full ${dot}"></div>
        <span class="text-xs font-semibold uppercase tracking-widest ${labelClass}">${label}</span>
      </div>
      <div class="space-y-2">
        ${card.clips.map(clip => renderClip(clip, scale, multiDay)).join('')}
      </div>
      ${renderAxis(scale)}
      <p class="mt-3 text-xs ${capClass}">${card.caption}</p>
    </div>
  `
}

// Render both cards for a scenario sharing one scale derived from all clips
// combined. This ensures clip positions are comparable across before/after:
// Amsterdam lands at the same x in both cards; only Seoul's bar moves.
export function renderScenarioCards(before, after) {
  const sharedScale = buildScale([...before.clips, ...after.clips])
  return `
    ${renderCard(before, false, sharedScale)}
    ${renderCard(after,  true,  sharedScale)}
  `
}
