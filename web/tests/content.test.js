// Product facts come from design/product.json, shared with the macOS app. The
// site must name the macOS version the app actually requires, and refuse a
// version it has no marketing name for rather than print a wrong one.
import { describe, expect, test } from 'vitest'
import product from '../../design/product.json'
import { FREE_FILE_LIMIT, MIN_MACOS, macOSLabel } from '../src/content.js'

describe('content', () => {
  test('free file limit and minimum macOS come from design/product.json', () => {
    expect(FREE_FILE_LIMIT).toBe(product.freeFileLimit)
    expect(MIN_MACOS).toBe(macOSLabel(product.minimumMacOS))
  })

  test('macOS versions get their marketing names', () => {
    expect(macOSLabel('14.0')).toBe('macOS 14 Sonoma')
    expect(macOSLabel('15')).toBe('macOS 15 Sequoia')
    expect(() => macOSLabel('99.0')).toThrow()
  })
})
