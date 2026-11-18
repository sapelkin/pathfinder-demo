/// The Python engine in the browser: Pyodide loaded from the site's own files (no CDN), the engine wheel unpacked
/// into the virtual file system (no micropip), one Dispatcher serving the API routes in order, and the document
/// sent back after every mutating call so the main thread can keep it in localStorage.
import type { WorkerRequest, WorkerResponse } from './protocol'

type PyProxy = { (...args: unknown[]): unknown; destroy?: () => void }
interface Pyodide {
  unpackArchive(buffer: ArrayBuffer, format: string, options?: { extractDir?: string }): void
  runPythonAsync(code: string): Promise<unknown>
  globals: { get(name: string): PyProxy }
}
type LoadPyodide = (opts: { indexURL: string; stdLibURL?: string; lockFileURL?: string }) => Promise<Pyodide>

const post = (m: WorkerResponse) => (self as unknown as Worker).postMessage(m)
const queue: WorkerRequest[] = []
let ready = false
let handle: PyProxy | null = null
let exportDoc: PyProxy | null = null
let importDoc: PyProxy | null = null

async function fetchWithProgress(url: string, stage: string): Promise<ArrayBuffer> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${stage}: ${res.status} ${res.statusText} for ${url}`)
  const total = Number(res.headers.get('content-length') || 0)
  if (!res.body || !total) return res.arrayBuffer()
  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let loaded = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    loaded += value.length
    post({ type: 'progress', stage, loaded, total })
  }
  const out = new Uint8Array(loaded)
  let o = 0
  for (const c of chunks) { out.set(c, o); o += c.length }
  return out.buffer
}

async function boot(baseURL: string, document: string | null) {
  const origin = self.location.origin
  const base = new URL(baseURL, origin).href
  const indexURL = new URL('pyodide/', base).href
  post({ type: 'progress', stage: 'Loading the engine… 10 MB, once' })
  // Warm the browser cache with progress for the big file, then let Pyodide load it (from cache) itself.
  await fetchWithProgress(new URL('pyodide.asm.wasm', indexURL).href, 'Python runtime')
  const mod = (await import(/* @vite-ignore */ new URL('pyodide.mjs', indexURL).href)) as { loadPyodide: LoadPyodide }
  post({ type: 'progress', stage: 'Starting Python' })
  const py = await mod.loadPyodide({ indexURL })
  post({ type: 'progress', stage: 'Installing the engine' })
  const manifest = (await (await fetch(new URL('engine/manifest.json', base).href, { cache: 'no-cache' })).json()) as { wheel: string; stubDispatch: boolean }
  const wheel = await fetchWithProgress(new URL(`engine/${manifest.wheel}`, base).href, 'Engine')
  py.unpackArchive(wheel, 'whl')
  if (manifest.stubDispatch) {
    // A built wheel without its own dispatch.py: install the sidecar module next to it.
    try {
      const stub = await (await fetch(new URL('engine/dispatch.py', base).href)).text()
      await py.runPythonAsync(`import importlib.util, pathlib, pathfinder_engine
_p = pathlib.Path(pathfinder_engine.__file__).parent / "dispatch.py"
if not _p.exists():
    _p.write_text(${JSON.stringify(stub)})`)
    } catch { /* the wheel ships its own */ }
  }
  await py.runPythonAsync(`
import json
from pathfinder_engine import __version__ as _engine_version
from pathfinder_engine.dispatch import Dispatcher
_dispatcher = Dispatcher()

def _handle(method, path, query_json, body_json):
    r = _dispatcher.handle(method, path, json.loads(query_json), json.loads(body_json) if body_json else None)
    return json.dumps(r, separators=(",", ":"))

def _export():
    return _dispatcher.export_document()

def _import(text):
    try:
        _dispatcher.import_document(text)
        return ""
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
`)
  handle = py.globals.get('_handle')
  exportDoc = py.globals.get('_export')
  importDoc = py.globals.get('_import')
  let restored = false
  if (document) {
    const err = importDoc(document) as string
    restored = !err
    if (err) console.warn('Stored document not restored:', err)
  }
  const engine = (await py.runPythonAsync('_engine_version')) as string
  ready = true
  post({ type: 'ready', engine: String(engine), stubDispatch: manifest.stubDispatch, restored })
  while (queue.length) await serve(queue.shift()!)
}

async function serve(m: WorkerRequest) {
  if (!handle || !exportDoc || !importDoc) return
  if (m.type === 'call') {
    const raw = handle(m.method, m.path, JSON.stringify(m.query), m.body === undefined ? '' : JSON.stringify(m.body)) as string
    const r = JSON.parse(raw) as { status: number; body: unknown }
    post({ type: 'result', id: m.id, status: r.status, body: r.body })
    if (m.method === 'POST' && r.status < 400) post({ type: 'document', text: exportDoc() as string })
  } else if (m.type === 'export') {
    post({ type: 'exported', id: m.id, text: exportDoc() as string })
  } else if (m.type === 'import') {
    const err = importDoc(m.text) as string
    post({ type: 'imported', id: m.id, ok: !err, error: err || undefined })
    if (!err) post({ type: 'document', text: exportDoc() as string })
  }
}

let chain: Promise<void> = Promise.resolve()
self.onmessage = (ev: MessageEvent<WorkerRequest>) => {
  const m = ev.data
  if (m.type === 'init') {
    boot(m.baseURL, m.document).catch((e) => post({ type: 'fatal', message: e instanceof Error ? e.message : String(e) }))
    return
  }
  if (!ready) { queue.push(m); return }
  chain = chain.then(() => serve(m)).catch((e) => {
    if (m.type === 'call') post({ type: 'result', id: m.id, status: 500, body: { error: e instanceof Error ? e.message : String(e) } })
  })
}
