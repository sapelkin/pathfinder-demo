/* global localStorage */
// The backend-free build, checked end to end with Playwright: the Alan Pierce flow, reload persistence, export and
// import. Usage: node scripts/local-check.mjs http://localhost:4173/pathfinder-demo/
import { createRequire } from 'node:module'
import { execSync } from 'node:child_process'
import path from 'node:path'
import { readdirSync, statSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const loadPlaywright = () => { try { return require('playwright') } catch { return createRequire(path.join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'x.js'))('playwright') } }
const { chromium } = loadPlaywright()
const base = process.argv[2] || 'http://localhost:4173/pathfinder-demo/'
const here = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.join(here, '..', 'screenshots')
mkdirSync(outDir, { recursive: true })
const dist = path.join(here, '..', 'dist')
const sizeOf = (dir) => !existsSync(dir) ? 0 : readdirSync(dir).reduce((n, f) => { const p = path.join(dir, f); return n + (statSync(p).isDirectory() ? sizeOf(p) : statSync(p).size) }, 0)
const mb = (n) => `${(n / 1e6).toFixed(1)} MB`
console.log(`dist total ${mb(sizeOf(dist))}: assets ${mb(sizeOf(path.join(dist, 'assets')))}, pyodide ${mb(sizeOf(path.join(dist, 'pyodide')))}, engine ${mb(sizeOf(path.join(dist, 'engine')))}`)

const browser = await chromium.launch()
const errors = []
const shot = async (page, name) => { await page.waitForTimeout(300); await page.screenshot({ path: path.join(outDir, `local_${name}.png`) }); console.log(`  local_${name}.png`) }
const context = await browser.newContext({ viewport: { width: 1024, height: 768 }, deviceScaleFactor: 1 })
const page = await context.newPage()
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)) })
let firstState = 0, transferred = 0
const seen = new Set()
page.on('response', async (r) => { try { if (seen.has(r.url()) || r.status() === 304) return; seen.add(r.url()); const b = await r.body(); transferred += b.length } catch { /* streamed */ } })

const t0 = Date.now()
await page.goto(base, { waitUntil: 'domcontentloaded' })
const tLoad = Date.now() - t0
await page.waitForSelector('.engine-loading', { timeout: 10000 }).catch(() => {})
await shot(page, '00_loading')
await page.waitForSelector('.queue-row', { timeout: 120000 })
firstState = Date.now() - t0
console.log(`first load (DOMContentLoaded) ${tLoad} ms; time to first /state rendered ${firstState} ms; unique bytes downloaded ${mb(transferred)}`)
await shot(page, '01_front_door')

// The Alan Pierce flow.
await page.locator('button[aria-label^="New arrival"]').click()
await page.locator('button', { hasText: 'Type instead' }).click()
await page.locator('textarea').fill('Name is Alan Pierce, 72 year old man, chest pain for 2 hours, worse when breathing in. Came by car. Pulse 104, BP 150 over 90, sats 95 percent, pain 6 out of 10.')
await page.waitForSelector('button[aria-label^="Confirm category 2 (suggested)"]', { timeout: 20000 })
await shot(page, '02_intake_parsed')
await page.locator('button[aria-label^="Confirm category 2"]').click()
await page.waitForSelector('.eta-big', { timeout: 20000 })
await page.locator('button', { hasText: 'Send by text message' }).click()
await page.waitForTimeout(400)
await shot(page, '03_intake_message')
await page.locator('button', { hasText: 'Done' }).last().click()
await page.locator('button', { hasText: 'Add to the waiting room' }).click()
await page.waitForSelector('.queue-row:has-text("Alan P.")', { timeout: 20000 })
await shot(page, '04_front_door_added')
// Record D for Alan: open him, he is waiting, so first jump the clock until he is in care? Use outcome via patient detail when in care.
await page.locator('.row-button').filter({ hasText: 'Alan P.' }).first().click()
await page.waitForTimeout(400)
await shot(page, '05_patient_detail')
await page.locator('button', { hasText: 'Front door' }).first().click()
// Pause the simulated clock so the queue stays put for the persistence, export and import comparisons.
await page.locator('.clock-pill').click()
await page.locator('[role="menuitem"]', { hasText: 'Pause' }).click()
await page.waitForTimeout(600)
// Persistence: reload and check Alan is still in the queue.
await page.waitForTimeout(1200) // the 500 ms debounced save
const t1 = Date.now()
await page.reload({ waitUntil: 'domcontentloaded' })
await page.waitForSelector('.queue-row', { timeout: 120000 })
console.log(`reload: engine ready again in ${Date.now() - t1} ms`)
const stillThere = await page.locator('.queue-row:has-text("Alan P.")').count()
console.log(`reload persistence: Alan P. ${stillThere > 0 ? 'still in the queue' : 'MISSING'}`)
await shot(page, '06_after_reload')

// Follow-through, case, right door.
await page.locator('[role="tab"]:visible', { hasText: 'Follow-through' }).first().click()
await page.waitForSelector('.tier-bar', { timeout: 20000 })
await page.locator('.row-button').filter({ has: page.locator('.tier-bar') }).first().click()
await page.waitForSelector('.script-line', { timeout: 20000 })
await shot(page, '07_case')
await page.locator('button', { hasText: 'Show the search on the map' }).click()
await page.waitForSelector('.hexmap path', { timeout: 30000 })
await page.waitForTimeout(3500)
await shot(page, '08_right_door')
await page.locator('[role="tab"]:visible', { hasText: 'Impact' }).first().click()
await page.waitForSelector('.kpi-grid', { timeout: 20000 })
await shot(page, '09_impact')
await page.locator('[role="tab"]:visible', { hasText: 'Live' }).first().click()
await page.waitForSelector('.live-stats', { timeout: 20000 })
await shot(page, '10_live')

// Export, reset, import.
await page.locator('.clock-pill').click()
await page.locator('[role="menuitem"]', { hasText: 'Settings' }).click()
await page.waitForSelector('text=Export data (JSON)')
await shot(page, '11_settings')
const [download] = await Promise.all([page.waitForEvent('download'), page.locator('button', { hasText: 'Export data (JSON)' }).click()])
const exported = path.join(outDir, 'local_export.json')
await download.saveAs(exported)
const doc = JSON.parse(readFileSync(exported, 'utf8'))
console.log(`export: ${download.suggestedFilename()} ${mb(statSync(exported).size)}, version ${doc.version}, keys ${Object.keys(doc).slice(0, 6).join(',')}…`)
await page.locator('button', { hasText: 'Reset to the demo' }).click()
await page.waitForTimeout(1500)
const afterReset = await page.evaluate(() => localStorage.getItem('pathfinder.document.v1'))
await page.locator('button', { hasText: 'Done' }).last().click()
await page.locator('[role="tab"]:visible', { hasText: 'Front door' }).first().click()
await page.waitForSelector('.queue-row', { timeout: 20000 })
const gone = await page.locator('.queue-row:has-text("Alan P.")').count()
console.log(`reset: localStorage ${afterReset == null ? 'cleared' : 'still set (' + mb(afterReset.length) + ')'}; Alan ${gone === 0 ? 'gone' : 'still there'}`)
await page.locator('.clock-pill').click()
await page.locator('[role="menuitem"]', { hasText: 'Settings' }).click()
const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.locator('button', { hasText: 'Import data (JSON)' }).click()])
await chooser.setFiles(exported)
await page.waitForTimeout(2500)
await page.locator('button', { hasText: 'Done' }).last().click()
await page.waitForTimeout(800)
await page.locator('[role="tab"]:visible', { hasText: 'Front door' }).first().click()
await page.waitForSelector('.queue-row', { timeout: 20000 })
const back = await page.locator('.queue-row:has-text("Alan P.")').count()
console.log(`import: Alan ${back > 0 ? 'back in the queue' : 'MISSING'}`)
await shot(page, '12_after_import')

// Metro mode: switch to Joondalup, the header and the waiting count must equal the published numbers, Impact has the card.
const hospitals = await page.evaluate(async (b) => { try { const r = await fetch(new URL('hospitals', b)); return r.ok ? await r.json() : null } catch { return null } }, base).catch(() => null)
await page.locator('.clock-pill').click()
await page.locator('[role="menuitem"]', { hasText: 'Settings' }).click()
await page.waitForTimeout(1500)
const hasPicker = await page.locator('.row-button', { hasText: 'Joondalup Health Campus' }).count()
if (!hasPicker) {
  console.log('metro: /hospitals not available on this build yet (Settings shows the notice); skipped')
  await page.locator('button', { hasText: 'Done' }).last().click()
} else {
  await page.locator('.row-button', { hasText: 'Joondalup Health Campus' }).click()
  await page.waitForSelector('text=Rebuilt the waiting room for Joondalup Health Campus', { timeout: 60000 })
  const rowText = await page.locator('.row-button', { hasText: 'Joondalup Health Campus' }).locator('.caption').textContent()
  const published = Number((rowText.match(/(\d+) waiting/) || [])[1])
  await page.locator('button', { hasText: 'Done' }).last().click()
  await page.locator('[role="tab"]:visible', { hasText: 'Front door' }).first().click()
  await page.waitForSelector('.queue-row', { timeout: 20000 })
  await page.waitForTimeout(800)
  const header = await page.locator('.card .headline').first().textContent()
  const waitingTile = await page.locator('.stats .stat').first().locator('.stat-value').textContent()
  const chip = await page.locator('text=From published numbers').count()
  console.log(`metro: header "${header}" ${header.includes('Joondalup') ? 'OK' : 'WRONG'}; waiting ${waitingTile} vs published ${published} ${Number(waitingTile) === published ? 'OK' : 'DIFFERENT'}; chip ${chip ? 'shown' : 'MISSING'}`)
  await page.waitForTimeout(1200)
  const stored = await page.evaluate(() => { try { return JSON.parse(localStorage.getItem('pathfinder.document.v1') || 'null') } catch { return null } })
  console.log(`metro: document saved after the switch: ${stored ? 'yes' : 'NO'}${stored && stored.hospital ? ` (hospital ${stored.hospital.id ?? stored.hospital})` : ''}`)
  await page.locator('[role="tab"]:visible', { hasText: 'Impact' }).first().click()
  await page.waitForSelector('text=Published average vs this simulation', { timeout: 20000 })
  const metroCard = await page.locator('text=Simulated, with Pathfinder redirects').count()
  console.log(`metro: Impact card ${metroCard ? 'present with the two bars' : 'present but without metro numbers'}`)
  await shot(page, '14_metro_impact')
  void hospitals
}

// Templates: the first aged-care template parses to its expected category; the elbow case is category 4 and can be redirected.
const templatesResp = await page.evaluate(async (b) => { try { const r = await fetch(new URL('templates', b)); return r.ok ? await r.json() : null } catch { return null } }, base).catch(() => null)
await page.locator('[role="tab"]:visible', { hasText: 'Front door' }).first().click()
await page.waitForSelector('.queue-row', { timeout: 20000 })
await page.locator('button[aria-label^="New arrival"]').click()
await page.waitForTimeout(1500)
const pickerCount = await page.locator('button[aria-label="Insert a triage note template"]').count()
if (!pickerCount) {
  console.log('templates: /templates not available on this build yet (picker hidden, instruction line kept); skipped')
  await page.locator('.sheet-bar button', { hasText: 'Cancel' }).click()
} else {
  const list = templatesResp?.templates ?? []
  const aged = list.find((t) => t.cohort === 'p65')
  const elbow = list.find((t) => /elbow/i.test(t.title) || t.id.includes('elbow'))
  const pick = async (t) => {
    await page.locator('button[aria-label="Insert a triage note template"]').click()
    await page.locator('[role="menuitem"]', { hasText: t.title }).first().click()
    await page.waitForTimeout(1500)
  }
  if (aged) {
    await pick(aged)
    const complaint = await page.locator('.field', { hasText: 'PROBLEM' }).locator('.field-value').textContent()
    const suggested = await page.locator('button[aria-label*="(suggested)"]').getAttribute('aria-label')
    const n = Number((suggested || '').match(/category (\d)/)?.[1])
    console.log(`templates: "${aged.title}" → problem "${complaint}" ${complaint && complaint !== 'not heard yet' ? 'OK' : 'MISSING'}; suggested ${n} vs expected ${aged.expect.suggested} ${n === aged.expect.suggested ? 'OK' : 'DIFFERENT'}`)
  }
  if (elbow) {
    await pick(elbow)
    const undoShown = await page.locator('.undo-line').count()
    const suggested = await page.locator('button[aria-label*="(suggested)"]').getAttribute('aria-label')
    const n = Number((suggested || '').match(/category (\d)/)?.[1])
    await page.locator(`button[aria-label^="Confirm category ${n}"]`).click()
    await page.waitForSelector('.eta-big', { timeout: 20000 })
    const redirectBtn = page.locator('button', { hasText: 'Redirect to an urgent care clinic instead' })
    const hasRedirect = await redirectBtn.count()
    console.log(`templates: "${elbow.title}" → suggested ${n} ${n === 4 ? 'OK' : 'NOT 4'}; undo offered ${undoShown ? 'yes' : 'no'}; redirect offered ${hasRedirect ? 'yes' : 'NO'}`)
    if (hasRedirect) {
      await redirectBtn.click()
      await page.waitForSelector('.banner', { timeout: 20000 })
      const bannerText = await page.locator('.banner').textContent()
      console.log(`templates: redirect → "${bannerText.trim().slice(0, 90)}" ${/redirected to/i.test(bannerText) ? 'OK (gate passed, service named)' : 'UNEXPECTED'}`)
    }
  }
  await shot(page, '15_templates_elbow')
}

// Phone width, once.
const phone = await browser.newPage({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2 })
await phone.goto(base, { waitUntil: 'domcontentloaded' })
await phone.waitForSelector('.queue-row', { timeout: 120000 })
await phone.screenshot({ path: path.join(outDir, 'local_13_front_door_phone.png') })
console.log('  local_13_front_door_phone.png')
await browser.close()
writeFileSync(path.join(outDir, 'local_report.txt'), `first load ${tLoad} ms, first state ${firstState} ms, transferred ${mb(transferred)}\n`)
if (errors.length) { console.log('\nConsole errors:'); errors.forEach((e) => console.log('  ' + e)); process.exitCode = 1 } else console.log('\nNo console errors.')
