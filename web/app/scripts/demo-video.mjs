// Puts the films from media/ at the repository root into public/media/, so the site serves them: the clock menu plays
// pathfinder_live_demo.mp4, and the README links to the film. Skipped quietly when media/ is not there; the menu
// item then reports that the video is missing.
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcDir = path.resolve(here, '../../../media')
const outDir = path.resolve(here, '../public/media')
const films = existsSync(srcDir) ? readdirSync(srcDir).filter((f) => f.endsWith('.mp4')) : []
if (films.length) {
  mkdirSync(outDir, { recursive: true })
  let bytes = 0
  for (const f of films) {
    copyFileSync(path.join(srcDir, f), path.join(outDir, f))
    bytes += statSync(path.join(srcDir, f)).size
  }
  console.log(`${films.length} films (${(bytes / 1e6).toFixed(1)} MB) → public/media/`)
} else {
  console.log('no films in media/: the demo-video menu item will say the video is missing')
}
