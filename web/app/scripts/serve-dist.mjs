// A static server for dist/ under a base path, as GitHub Pages serves it: node scripts/serve-dist.mjs [port] [base]
import http from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const port = Number(process.argv[2] || 4173)
const base = (process.argv[3] || process.env.VITE_BASE || '/').replace(/\/?$/, '/')
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.zip': 'application/zip', '.whl': 'application/octet-stream', '.py': 'text/x-python', '.png': 'image/png', '.svg': 'image/svg+xml', '.map': 'application/json' }
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x')
  if (!url.pathname.startsWith(base)) { res.writeHead(404); res.end(`not under ${base}`); return }
  let rel = decodeURIComponent(url.pathname.slice(base.length))
  let file = path.join(root, rel)
  if (!existsSync(file) || statSync(file).isDirectory()) file = path.join(root, 'index.html')
  // Like GitHub Pages: validators and a short max-age, so the runtime's second request for the wasm is served from cache.
  const st = statSync(file)
  const etag = `"${st.size}-${Number(st.mtimeMs).toString(36)}"`
  if (req.headers['if-none-match'] === etag) { res.writeHead(304, { ETag: etag }); res.end(); return }
  res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Content-Length': st.size, 'Cache-Control': 'public, max-age=600', ETag: etag, 'Last-Modified': st.mtime.toUTCString() })
  createReadStream(file).pipe(res)
}).listen(port, () => console.log(`dist served at http://localhost:${port}${base}`))
