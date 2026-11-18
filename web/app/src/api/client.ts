import type {
  HospitalsResponse, IntakeResult, TemplatesResponse, IntakeSubmit, KPI, Network, Persona, RightDoorResult, Settings, State, Unit, Vitals, ETA, TravelMode, Outcome,
} from './types'

import { ApiError } from './errors'
import { IS_LOCAL } from './mode'
import { localRequest } from './local'

export { ApiError }
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || 'http://localhost:8000'

let tokenProvider: (() => Promise<string | null>) | null = null
/// MSAL installs this when sign-in is on; otherwise requests go out bare (AUTH_DISABLED=1 on the API).
export function setTokenProvider(p: (() => Promise<string | null>) | null) { tokenProvider = p }

async function httpRequest<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (tokenProvider) {
    const t = await tokenProvider()
    if (t) headers.Authorization = `Bearer ${t}`
  }
  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try { const j = await res.json(); if (j && typeof j.error === 'string') message = j.error } catch { /* no body */ }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/// One transport for every screen: the HTTP API, or the engine in a Web Worker when VITE_API_MODE=local.
const request: <T>(method: 'GET' | 'POST', path: string, body?: unknown) => Promise<T> = IS_LOCAL ? localRequest : httpRequest

export const api = {
  speechToken: () => request<{ token: string; region: string; expiresIn: number }>('GET', '/speech/token'),
  health: () => request<{ ok: boolean; version?: string }>('GET', '/health'),
  state: () => request<State>('GET', '/state'),
  tick: (clientNow: string) => request<State>('POST', '/tick', { clientNow }),
  settings: (s: Settings) => request<State>('POST', '/settings', s),
  reset: (keepDemo = false) => request<State>('POST', '/reset', { keepDemo }),
  jump: (minutes: number) => request<State>('POST', '/jump', { minutes }),
  parse: (b: { transcript: string; typed: string; monitorVitals?: Vitals; recordLookedUp?: boolean }) => request<IntakeResult>('POST', '/parse', b),
  eta: (ats: number) => request<{ eta: ETA; samples: number[] }>('POST', '/eta', { ats }),
  intakeFinish: (b: IntakeSubmit) => request<State>('POST', '/intake/finish', b),
  intakeRedirect: (b: IntakeSubmit) => request<State>('POST', '/intake/redirect', b),
  outcome: (b: { id: number; outcome: Outcome; reason?: string; service?: string }) => request<State>('POST', '/outcome', b),
  contact: (b: { id: number; reached: boolean; result: string; nextStep?: string; reason?: string }) => request<State>('POST', '/contact', b),
  message: (id: number) => request<State>('POST', '/message', { id }),
  alo: (id: number) => request<State>('POST', '/alo', { id }),
  rightDoor: (id: number, purpose: 'redirectNow' | 'nextTime', mode?: TravelMode) =>
    request<RightDoorResult>('GET', `/rightdoor?id=${id}&purpose=${purpose}${mode ? `&mode=${mode}` : ''}`),
  kpi: () => request<KPI>('GET', '/kpi'),
  units: () => request<Unit[]>('GET', '/units'),
  personas: () => request<Persona[]>('GET', '/personas'),
  network: () => request<Network>('GET', '/network'),
  hospitals: () => request<HospitalsResponse>('GET', '/hospitals'),
  templates: () => request<TemplatesResponse>('GET', '/templates'),
  demoStart: (narrated = false) => request<State>('POST', '/demo/start', { narrated }),
  demoStop: () => request<State>('POST', '/demo/stop'),
}
