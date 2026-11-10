/**
 * Product facts the site repeats in several sections. Change them here only.
 *
 * The free-file limit and minimum macOS come from design/product.json, which the
 * macOS app is also held to (LicenseStoreTests, design/tests/test_product.py).
 */
import product from '../../design/product.json'

// Marketing names for the macOS versions the app can require.
const MACOS_NAMES = { 13: 'Ventura', 14: 'Sonoma', 15: 'Sequoia', 26: 'Tahoe' }

export function macOSLabel(version) {
  const major = Number(String(version).split('.')[0])
  const name = MACOS_NAMES[major]
  if (!name) throw new Error(`No marketing name for macOS ${version}; add it to MACOS_NAMES`)
  return `macOS ${major} ${name}`
}

export const PRICE = '$29'
export const BUY_URL = 'https://jetlag.app/buy'
export const FREE_FILE_LIMIT = product.freeFileLimit
export const MIN_MACOS = macOSLabel(product.minimumMacOS)

export const REPO_URL = 'https://github.com/brokenalarms/Jetlag'
export const DOWNLOAD_URL = `${REPO_URL}/releases/latest`
export const SUPPORT_URL = `${REPO_URL}/issues`
