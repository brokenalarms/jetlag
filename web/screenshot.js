/**
 * Take screenshots of the Jetlag website for review after web changes.
 * Builds the site, starts a preview server, captures each section plus the
 * full page, then exits.
 *
 * Usage (from web/):
 *   npm run screenshot                        # every section + full.png → design/screenshots/
 *   npm run screenshot -- --section problem   # one section only
 *
 * Sections come from SECTIONS in src/page.js, so a new section is captured
 * as <id>.png without touching this file. A full run also deletes any PNG in
 * design/screenshots/ that it no longer produces.
 *
 * Requires: npm install has been run in web/, and a Chromium browser is available.
 * If Playwright's bundled browser is missing, install it: npx playwright install chromium
 */

import { chromium } from 'playwright'
import { spawn, execSync } from 'child_process'
import { fileURLToPath } from 'url'
import { dirname, join, relative } from 'path'
import { mkdirSync, readdirSync, rmSync } from 'fs'
import { SECTIONS } from './src/page.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const screenshotsDir = join(__dirname, '..', 'design', 'screenshots')
mkdirSync(screenshotsDir, { recursive: true })

const FULL_PAGE = 'full'
const sectionIds = SECTIONS.map(section => section.id)

const sectionArg = process.argv.includes('--section')
  ? process.argv[process.argv.indexOf('--section') + 1]
  : null
if (sectionArg && !sectionIds.includes(sectionArg)) {
  console.error(`Unknown section "${sectionArg}". Sections: ${sectionIds.join(', ')}`)
  process.exit(1)
}

// Build
console.log('Building…')
execSync('npm run build', { cwd: __dirname, stdio: 'inherit' })

// Start preview server. Run vite's own entry point rather than `npx vite`, so
// server.kill() stops the server itself and the script can exit.
const viteBin = join(__dirname, 'node_modules', 'vite', 'bin', 'vite.js')
const server = spawn(process.execPath, [viteBin, 'preview', '--port', '4173', '--strictPort'], {
  cwd: __dirname,
  stdio: ['ignore', 'pipe', 'pipe'],
})

await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error('Preview server did not start in time')), 10_000)
  server.stdout.on('data', (data) => {
    if (data.toString().includes('4173')) { clearTimeout(timeout); resolve() }
  })
  server.stderr.on('data', (data) => {
    if (data.toString().includes('4173')) { clearTimeout(timeout); resolve() }
  })
  server.on('error', reject)
})

const browser = await chromium.launch()
const page = await browser.newPage()
await page.setViewportSize({ width: 1440, height: 900 })
await page.goto('http://localhost:4173')
await page.waitForLoadState('networkidle')

// Dismiss any animations so screenshots are stable
await page.addStyleTag({ content: '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; opacity: 1 !important; }' })
await page.waitForTimeout(300)

const saved = []

for (const id of sectionArg ? [sectionArg] : sectionIds) {
  await page.locator(`#${id}`).scrollIntoViewIfNeeded()
  await page.waitForTimeout(100)
  const outPath = join(screenshotsDir, `${id}.png`)
  await page.screenshot({ path: outPath })
  saved.push(outPath)
  console.log(`  saved: ${outPath}`)
}

// Full page last (slow), then drop PNGs this script no longer produces
if (!sectionArg) {
  const fullPath = join(screenshotsDir, `${FULL_PAGE}.png`)
  await page.screenshot({ path: fullPath, fullPage: true })
  saved.push(fullPath)
  console.log(`  saved: ${fullPath}`)

  const expected = new Set([...sectionIds, FULL_PAGE].map(name => `${name}.png`))
  for (const file of readdirSync(screenshotsDir)) {
    if (file.endsWith('.png') && !expected.has(file)) {
      rmSync(join(screenshotsDir, file))
      console.log(`  removed stale: ${file}`)
    }
  }
}

await browser.close()
server.kill()

console.log(`\nDone — ${saved.length} screenshot(s) in ${relative(process.cwd(), screenshotsDir) || '.'}/`)
