// Product facts come from design/product.json, shared with the macOS app, whose
// LicenseStoreTests hold the app's free-tier limit to the same number.
import { expect, test } from 'vitest'
import product from '../../design/product.json'
import { FREE_FILE_LIMIT } from '../src/content.js'

test('the free file limit comes from design/product.json', () => {
  expect(FREE_FILE_LIMIT).toBe(product.freeFileLimit)
})
