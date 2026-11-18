/// The same `api` surface as the HTTP client, served by the Python engine in a Web Worker (Pyodide). Selected at
/// build time with VITE_API_MODE=local. The document comes back after every POST and is kept in localStorage.
import type { WorkerRequest, WorkerResponse } from '../worker/protocol'
import { ApiError } from './errors'

export const DOCUMENT_KEY = 'pathfinder.document.v1'

export interface EngineStatus { phase: 'idle' | 'loading' | 'ready' | 'failed'; stage: string; loaded?: number; total?: number; engine?: string; stubDispatch?: boolean; restored?: boolean; error?: string }

let worker: Worker | null = null
let seq = 0
const pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>()
const exports = new Map<number, (text: string) => void>()
const imports = new Map<number, (r: { ok: boolean; error?: string }) => void>()
let status: EngineStatus = { phase: 'idle', stage: '' }
const listeners = new Set<(s: EngineStatus) => void>()
let saveTimer: number | null = null
let latestDocument: string | null = null
let suppressSavesUntil = 0
let readyResolve: (() => void) | null = null
const readyPromise = new Promise<void>((r) => { readyResolve = r })

function setStatus(s: EngineStatus) { status = s; listeners.forEach((l) => l(s)) }
export function getEngineStatus(): EngineStatus { return status }
export function subscribeEngine(l: (s: EngineStatus) => void): () => void { listeners.add(l); l(status); return () => { listeners.delete(l) } }

function readStored(): string | null {
  try { return localStorage.getItem(DOCUMENT_KEY) } catch { return null }
}
function scheduleSave(text: string) {
  if (Date.now() < suppressSavesUntil) return
  latestDocument = text
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    saveTimer = null
    try { if (latestDocument) localStorage.setItem(DOCUMENT_KEY, latestDocument) } catch (e) { console.warn('Could not save the document', e) }
  }, 500)
}
/// Forgets the saved document; saves stay off for a moment so the reset's own response is not written back
/// (the next mutating call, e.g. the next tick, saves the fresh demo again).
export function clearStoredDocument(quietMs = 1500) {
  latestDocument = null
  suppressSavesUntil = Date.now() + quietMs
  if (saveTimer) { window.clearTimeout(saveTimer); saveTimer = null }
  try { localStorage.removeItem(DOCUMENT_KEY) } catch { /* ignore */ }
}

export function startEngine(): void {
  if (worker) return
  setStatus({ phase: 'loading', stage: 'Loading the engine… 10 MB, once' })
  worker = new Worker(new URL('../worker/engine.worker.ts', import.meta.url), { type: 'module', name: 'pathfinder-engine' })
  worker.onmessage = (ev: MessageEvent<WorkerResponse>) => {
    const m = ev.data
    switch (m.type) {
      case 'progress': setStatus({ ...status, phase: 'loading', stage: m.stage, loaded: m.loaded, total: m.total }); break
      case 'ready': setStatus({ phase: 'ready', stage: 'Ready', engine: m.engine, stubDispatch: m.stubDispatch, restored: m.restored }); readyResolve?.(); break
      case 'fatal': setStatus({ phase: 'failed', stage: 'The engine could not start', error: m.message }); pending.forEach((p) => p.reject(new ApiError(503, m.message))); pending.clear(); break
      case 'result': { const p = pending.get(m.id); pending.delete(m.id); if (!p) break; if (m.status >= 400) p.reject(new ApiError(m.status, (m.body as { error?: string })?.error ?? `${m.status}`)); else p.resolve(m.body); break }
      case 'exported': { exports.get(m.id)?.(m.text); exports.delete(m.id); break }
      case 'imported': { imports.get(m.id)?.({ ok: m.ok, error: m.error }); imports.delete(m.id); break }
      case 'document': scheduleSave(m.text); break
    }
  }
  worker.onerror = (e) => setStatus({ phase: 'failed', stage: 'The engine could not start', error: e.message })
  const init: WorkerRequest = { type: 'init', baseURL: import.meta.env.BASE_URL, document: readStored() }
  worker.postMessage(init)
}

function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  startEngine()
  const [p, qs] = path.split('?')
  const query: Record<string, string> = {}
  if (qs) for (const [k, v] of new URLSearchParams(qs)) query[k] = v
  const id = ++seq
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve: resolve as (v: unknown) => void, reject })
    worker!.postMessage({ type: 'call', id, method, path: p, query, body } satisfies WorkerRequest)
  })
}

export function exportDocument(): Promise<string> {
  startEngine()
  const id = ++seq
  return new Promise((resolve) => { exports.set(id, resolve); worker!.postMessage({ type: 'export', id } satisfies WorkerRequest) })
}
export function importDocument(text: string): Promise<{ ok: boolean; error?: string }> {
  startEngine()
  const id = ++seq
  return new Promise((resolve) => { imports.set(id, resolve); worker!.postMessage({ type: 'import', id, text } satisfies WorkerRequest) })
}
export function whenEngineReady(): Promise<void> { startEngine(); return readyPromise }

export const localRequest = call
