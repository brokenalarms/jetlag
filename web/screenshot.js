/**
 * Take screenshots of the Jetlag website for review after web changes.
 * Builds the site, starts a preview server, captures key sections, then exits.
 *
 * Usage:
 *   node web/screenshot.js              # saves to web/screenshots/
 *   node web/screenshot.js --section problem   # specific section only
 *
 * Requires: npm install has been run in web/, and a Chromium browser is available.
 * If Playwright's bundled browser is missing, install it: npx playwright install chromium
 */

import { chromium } from 'playwright'
import { spawn, execSync } from 'child_process'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'
import { mkdirSync } from 'fs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const screenshotsDir = join(__dirname, '..', 'design', 'screenshots')
mkdirSync(screenshotsDir, { recursive: true })

const sectionArg = process.argv.includes('--section')
  ? process.argv[process.argv.indexOf('--section') + 1]
  : null

// Build
console.log('Building…')
execSync('npm run build', { cwd: __dirname, stdio: 'inherit' })

// Start preview server
const server = spawn('npx', ['vite', 'preview', '--port', '4173', '--strictPort'], {
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

// Use a pre-installed Chromium if the bundled headless shell is absent
const chromiumPath = '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch({ executablePath: chromiumPath })
const page = await browser.newPage()
await page.setViewportSize({ width: 1440, height: 900 })
await page.goto('http://localhost:4173')
await page.waitForLoadState('networkidle')

// Dismiss any animations so screenshots are stable
await page.addStyleTag({ content: '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; opacity: 1 !important; }' })
await page.waitForTimeout(300)

const saved = []

const sections = [
  { name: 'hero',         selector: 'section:nth-of-type(1)' },
  { name: 'problem',      selector: 'section:nth-of-type(2)' },
  { name: 'features',     selector: '#features' },
  { name: 'how-it-works', selector: '#how-it-works' },
]

const toCapture = sectionArg
  ? sections.filter(s => s.name === sectionArg)
  : sections

for (const { name, selector } of toCapture) {
  const el = page.locator(selector).first()
  await el.scrollIntoViewIfNeeded()
  await page.waitForTimeout(100)
  const outPath = join(screenshotsDir, `${name}.png`)
  await page.screenshot({ path: outPath })
  saved.push(outPath)
  console.log(`  saved: ${outPath}`)
}

// Full page last (slow)
if (!sectionArg) {
  const fullPath = join(screenshotsDir, 'full.png')
  await page.screenshot({ path: fullPath, fullPage: true })
  saved.push(fullPath)
  console.log(`  saved: ${fullPath}`)
}

await browser.close()
server.kill()

console.log(`\nDone — ${saved.length} screenshot(s) in web/screenshots/`)
