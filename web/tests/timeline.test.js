/**
 * Unit tests for the timeline maths in components/timeline.js.
 *
 * The problem section's interactive timelines place each clip bar, the hour
 * ticks and the live time readout from these functions. If they drift, clips
 * land in the wrong place or the slider shows wrong times, and nothing else
 * would catch it short of eyeballing the page.
 */
import { describe, expect, test } from 'vitest'
import {
  CLIP_WIDTH_PCT,
  PAD_MINUTES,
  buildScale,
  buildTicks,
  clipOffset,
  formatMinutes,
  toMinutes,
} from '../src/components/timeline.js'

describe('toMinutes', () => {
  // Clips on later days sit a whole day (1440 min) further along the axis.
  test('counts minutes from midnight of day 0', () => {
    expect(toMinutes({ time: '00:00' })).toBe(0)
    expect(toMinutes({ time: '14:12', day: 0 })).toBe(852)
    expect(toMinutes({ time: '02:07', day: 1 })).toBe(1440 + 127)
  })
})

describe('buildScale', () => {
  // The axis is padded either side so the first and last clips are not flush with the edges.
  test('pads the earliest and latest clip', () => {
    const scale = buildScale([{ time: '08:00' }, { time: '15:43' }])
    expect(scale).toEqual({ scaleStart: 480 - PAD_MINUTES, scaleEnd: 943 + PAD_MINUTES })
  })

  // A clip just after midnight on day 0 must not push the axis to negative minutes.
  test('never starts before midnight of day 0', () => {
    expect(buildScale([{ time: '00:30' }, { time: '02:00' }]).scaleStart).toBe(0)
  })
})

describe('clipOffset', () => {
  // The earliest clip starts one pad in; the latest still leaves room for a full-width bar.
  test('maps the scale onto 0 … 100 - clip width', () => {
    const clips = [{ time: '08:00' }, { time: '15:43' }]
    const scale = buildScale(clips)
    const range = scale.scaleEnd - scale.scaleStart
    const usable = 100 - CLIP_WIDTH_PCT
    expect(clipOffset(clips[0], scale)).toBeCloseTo((PAD_MINUTES / range) * usable)
    expect(clipOffset(clips[1], scale)).toBeCloseTo(((range - PAD_MINUTES) / range) * usable)
    expect(clipOffset(clips[1], scale) + CLIP_WIDTH_PCT).toBeLessThanOrEqual(100)
  })

  // A zero-length scale would divide by zero; the clip sits at the left edge instead.
  test('returns 0 for an empty range', () => {
    expect(clipOffset({ time: '10:00' }, { scaleStart: 600, scaleEnd: 600 })).toBe(0)
  })
})

describe('buildTicks', () => {
  const labels = scale => buildTicks(scale).map(t => t.label)

  // Short spans (≤ 6 h) tick every 2 hours.
  test('ticks every 2 hours on a short span', () => {
    expect(labels(buildScale([{ time: '10:00' }, { time: '11:00' }]))).toEqual(['10:00', '12:00'])
  })

  // Medium spans (6–15 h) tick every 3 hours.
  test('ticks every 3 hours on a medium span', () => {
    expect(labels(buildScale([{ time: '08:00' }, { time: '15:43' }]))).toEqual(['09:00', '12:00', '15:00'])
  })

  // Long spans tick every 6 hours; hours wrap at 24 and midnight is flagged as a new day.
  test('ticks every 6 hours across midnight and marks the new day', () => {
    const scale = buildScale([{ time: '14:12', day: 0 }, { time: '09:07', day: 1 }])
    const ticks = buildTicks(scale)
    expect(ticks.map(t => t.label)).toEqual(['18:00', '00:00', '06:00'])
    expect(ticks.map(t => t.isNewDay)).toEqual([false, true, false])
  })

  // Ticks are positioned on the same 0 … 100 - clip width scale as the clip bars.
  test('positions ticks on the clip scale', () => {
    const scale = buildScale([{ time: '14:12', day: 0 }, { time: '09:07', day: 1 }])
    const midnight = buildTicks(scale)[1]
    expect(midnight.pct).toBeCloseTo(clipOffset({ time: '00:00', day: 1 }, scale))
  })
})

describe('formatMinutes', () => {
  // The slider readout rounds interpolated minutes and rolls over into the next day.
  test('formats day and HH:MM', () => {
    expect(formatMinutes(852)).toEqual({ day: 0, time: '14:12' })
    expect(formatMinutes(1440 + 127)).toEqual({ day: 1, time: '02:07' })
    expect(formatMinutes(1439.6)).toEqual({ day: 1, time: '00:00' })
    expect(formatMinutes(65.4)).toEqual({ day: 0, time: '01:05' })
  })
})
