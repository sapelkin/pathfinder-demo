// Prepares the backend-free build: copies Pyodide's runtime files from node_modules into public/pyodide/ and puts the
// engine wheel into public/engine/. The wheel comes from web/engine/dist/pathfinder_engine-*.whl when the engine
// author has built one; otherwise it is zipped here from web/engine/pathfinder_engine (pure Python, no dependencies),
// and if the engine has no dispatch.py yet, scripts/dispatch_stub.py is injected as pathfinder_engine/dispatch.py.
// Runs before `vite dev` and `vite build`; it is quick and idempotent.
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync, rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import zlib from 'node:zlib'

const here = path.dirname(fileURLToPath(import.meta.url))
// Only the backend-free build needs these 12 MB; the HTTP build removes them so dist/ stays small.
if (process.env.VITE_API_MODE === 'http' && !process.argv.includes('--force')) {
  for (const d of ['pyodide', 'engine']) rmSync(path.join(here, '..', 'public', d), { recursive: true, force: true })
  console.log('VITE_API_MODE is http: public/pyodide and public/engine removed (unset it or pass --force to prepare them)')
  process.exit(0)
}
const app = path.join(here, '..')
const engineDir = path.join(app, '..', 'engine')
const pyodideSrc = path.join(app, 'node_modules', 'pyodide')
const pyodideOut = path.join(app, 'public', 'pyodide')
const engineOut = path.join(app, 'public', 'engine')

// 1. Pyodide runtime: only the files loadPyodide reads for a pure-Python package (no micropip, no CDN).
const PYODIDE_FILES = ['pyodide.mjs', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']
mkdirSync(pyodideOut, { recursive: true })
let pyodideBytes = 0
for (const f of PYODIDE_FILES) {
  const src = path.join(pyodideSrc, f)
  if (!existsSync(src)) throw new Error(`pyodide file missing: ${src} (npm install pyodide)`)
  cpSync(src, path.join(pyodideOut, f))
  pyodideBytes += statSync(src).size
}
const pyodideVersion = JSON.parse(readFileSync(path.join(pyodideSrc, 'package.json'), 'utf8')).version

// 2. The engine wheel.
mkdirSync(engineOut, { recursive: true })
for (const f of readdirSync(engineOut)) rmSync(path.join(engineOut, f))
const distDir = path.join(engineDir, 'dist')
const built = existsSync(distDir) ? readdirSync(distDir).filter((f) => /^pathfinder_engine-.*\.whl$/.test(f)).sort().pop() : undefined
const pkgDir = path.join(engineDir, 'pathfinder_engine')
const hasDispatch = existsSync(path.join(pkgDir, 'dispatch.py'))
let wheelName, wheelBytes, source
if (built) {
  wheelName = built
  cpSync(path.join(distDir, built), path.join(engineOut, built))
  wheelBytes = statSync(path.join(engineOut, built)).size
  source = `web/engine/dist/${built}`
  // A built wheel without dispatch.py still gets the stub, as a sidecar module installed next to it.
} else {
  if (!existsSync(pkgDir)) throw new Error(`engine package missing: ${pkgDir}`)
  const version = readFileSync(path.join(engineDir, 'pyproject.toml'), 'utf8').match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? '0.1.0'
  wheelName = `pathfinder_engine-${version}-py3-none-any.whl`
  const entries = []
  const walk = (dir, rel) => {
    for (const f of readdirSync(dir)) {
      if (f === '__pycache__' || f.endsWith('.pyc') || f.startsWith('.')) continue
      const p = path.join(dir, f), r = `${rel}/${f}`
      if (statSync(p).isDirectory()) walk(p, r)
      else entries.push({ name: r, data: readFileSync(p) })
    }
  }
  walk(pkgDir, 'pathfinder_engine')
  if (!hasDispatch) entries.push({ name: 'pathfinder_engine/dispatch.py', data: readFileSync(path.join(here, 'dispatch_stub.py')) })
  const info = `pathfinder_engine-${version}.dist-info`
  entries.push({ name: `${info}/METADATA`, data: Buffer.from(`Metadata-Version: 2.1\nName: pathfinder_engine\nVersion: ${version}\nSummary: Pathfinder's simulation engine (browser build)\nRequires-Python: >=3.11\n`) })
  entries.push({ name: `${info}/WHEEL`, data: Buffer.from('Wheel-Version: 1.0\nGenerator: pathfinder-web\nRoot-Is-Purelib: true\nTag: py3-none-any\n') })
  entries.push({ name: `${info}/top_level.txt`, data: Buffer.from('pathfinder_engine\n') })
  entries.push({ name: `${info}/RECORD`, data: Buffer.from(entries.map((e) => `${e.name},,`).join('\n') + `\n${info}/RECORD,,\n`) })
  const zip = buildZip(entries)
  writeFileSync(path.join(engineOut, wheelName), zip)
  wheelBytes = zip.length
  source = `zipped from web/engine/pathfinder_engine${hasDispatch ? '' : ' + scripts/dispatch_stub.py'}`
}
if (built && !hasDispatch) writeFileSync(path.join(engineOut, 'dispatch.py'), readFileSync(path.join(here, 'dispatch_stub.py')))
writeFileSync(path.join(engineOut, 'manifest.json'), JSON.stringify({
  wheel: wheelName, stubDispatch: !hasDispatch, pyodide: pyodideVersion, builtAt: new Date().toISOString(),
}, null, 2))
console.log(`pyodide ${pyodideVersion}: ${PYODIDE_FILES.length} files, ${(pyodideBytes / 1e6).toFixed(1)} MB → public/pyodide/`)
console.log(`engine wheel ${wheelName} (${(wheelBytes / 1e3).toFixed(0)} kB, ${source}${hasDispatch ? ', engine dispatch.py' : ', stub dispatch.py'}) → public/engine/`)

/// A minimal ZIP writer: stored entries (no compression) with CRC-32, which is all a wheel needs.
function buildZip(entries) {
  const locals = [], centrals = []
  let offset = 0
  const dosTime = 0, dosDate = (1 << 5) | 1 | ((2024 - 1980) << 9)
  for (const e of entries) {
    const name = Buffer.from(e.name, 'utf8')
    const crc = zlib.crc32(e.data) >>> 0
    const lh = Buffer.alloc(30)
    lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0x0800, 6); lh.writeUInt16LE(0, 8)
    lh.writeUInt16LE(dosTime, 10); lh.writeUInt16LE(dosDate, 12); lh.writeUInt32LE(crc, 14)
    lh.writeUInt32LE(e.data.length, 18); lh.writeUInt32LE(e.data.length, 22); lh.writeUInt16LE(name.length, 26); lh.writeUInt16LE(0, 28)
    const ch = Buffer.alloc(46)
    ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(0x0800, 8); ch.writeUInt16LE(0, 10)
    ch.writeUInt16LE(dosTime, 12); ch.writeUInt16LE(dosDate, 14); ch.writeUInt32LE(crc, 16)
    ch.writeUInt32LE(e.data.length, 20); ch.writeUInt32LE(e.data.length, 24); ch.writeUInt16LE(name.length, 28)
    ch.writeUInt16LE(0, 30); ch.writeUInt16LE(0, 32); ch.writeUInt16LE(0, 34); ch.writeUInt16LE(0, 36); ch.writeUInt32LE(0, 38); ch.writeUInt32LE(offset, 42)
    locals.push(lh, name, e.data)
    centrals.push(ch, name)
    offset += lh.length + name.length + e.data.length
  }
  const central = Buffer.concat(centrals)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(0, 4); end.writeUInt16LE(0, 6)
  end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10); end.writeUInt32LE(central.length, 12); end.writeUInt32LE(offset, 16); end.writeUInt16LE(0, 20)
  return Buffer.concat([...locals, central, end])
}
