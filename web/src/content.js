/**
 * Product facts the site repeats in several sections. Change them here only.
 *
 * The free-file limit comes from design/product.json, which the macOS app is
 * also held to (LicenseStoreTests).
 */
import product from '../../design/product.json'

export const PRICE = '$29'
export const BUY_URL = 'https://jetlag.app/buy'
export const FREE_FILE_LIMIT = product.freeFileLimit

export const REPO_URL = 'https://github.com/brokenalarms/Jetlag'
export const DOWNLOAD_URL = `${REPO_URL}/releases/latest`
export const SUPPORT_URL = `${REPO_URL}/issues`
