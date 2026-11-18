import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import type { Banner, Deployment, State, Settings } from '../api/types'

export type Tab = 'frontDoor' | 'followThrough' | 'rightDoor' | 'impact' | 'dashboard'
export const ALL_TABS: Tab[] = ['frontDoor', 'followThrough', 'rightDoor', 'impact', 'dashboard']
export const TAB_LABEL: Record<Tab, string> = {
  frontDoor: 'Front door', followThrough: 'Follow-through', rightDoor: 'Right door', impact: 'Impact', dashboard: 'Live',
}
/// AppTab.tabs(for:): the minimum and standard deployments have only the front door. The API may send `tabs` itself.
export function tabsFor(d: Deployment, fromApi?: string[]): Tab[] {
  if (fromApi && fromApi.length > 0) return ALL_TABS.filter((t) => fromApi.includes(t))
  return d === 'full' ? ALL_TABS : ['frontDoor']
}

export const SPEEDS = [1, 10, 60, 300, 1200]

interface Nav {
  tab: Tab
  frontPatient: number | null
  followCase: number | null
  rightDoorId: number | null
  showIntake: boolean
  showSettings: boolean
  showUnits: boolean
}

export interface Store {
  state: State | null
  error: string | null
  connected: boolean
  nav: Nav
  banner: Banner | null
  dismissBanner: () => void
  setTab: (t: Tab) => void
  openPatient: (id: number | null) => void
  openCase: (id: number | null) => void
  openRightDoor: (id: number) => void
  setRightDoorId: (id: number) => void
  setShowIntake: (v: boolean) => void
  setShowSettings: (v: boolean) => void
  setShowUnits: (v: boolean) => void
  apply: (s: State) => void
  run: (f: () => Promise<State>) => Promise<State | null>
  settings: (s: Settings) => Promise<void>
  /// The simulated minute right now, extrapolated between responses so the clock moves smoothly.
  simNow: () => number
  episode: (id: number) => State['waiting'][number] | undefined
}

const Ctx = createContext<Store | null>(null)
const ClockCtx = createContext<number>(0)

/// The simulated minute, redrawn 4× a second between polls (now + elapsed × speed / 60), for clocks and waited times.
export function useDisplayNow(): number { return useContext(ClockCtx) }

export function useStore(): Store {
  const s = useContext(Ctx)
  if (!s) throw new Error('useStore outside StoreProvider')
  return s
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)
  const [banner, setBanner] = useState<Banner | null>(null)
  const [nav, setNav] = useState<Nav>({
    tab: 'frontDoor', frontPatient: null, followCase: null, rightDoorId: null, showIntake: false, showSettings: false, showUnits: false,
  })
  const receivedAt = useRef<number>(Date.now())
  const stateRef = useRef<State | null>(null)
  const lastBannerKey = useRef<string>('')
  const bannerTimer = useRef<number | null>(null)
  const [displayNow, setDisplayNow] = useState(0)

  const apply = useCallback((s: State) => {
    stateRef.current = s
    receivedAt.current = Date.now()
    setState(s)
    setConnected(true)
    setError(null)
    // `state.banner` shows for 6 s, then goes; the same banner is not re-shown on every poll.
    if (s.banner) {
      const key = `${s.banner.text}|${s.banner.episodeId ?? ''}`
      if (key !== lastBannerKey.current) {
        lastBannerKey.current = key
        setBanner(s.banner)
        if (bannerTimer.current) window.clearTimeout(bannerTimer.current)
        bannerTimer.current = window.setTimeout(() => setBanner(null), 6000)
      }
    } else {
      lastBannerKey.current = ''
    }
  }, [])

  const run = useCallback(async (f: () => Promise<State>) => {
    try {
      const s = await f()
      apply(s)
      return s
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e))
      return null
    }
  }, [apply])

  // Polling: GET /state every 2 s while visible; the focused tab POSTs /tick instead so the simulation advances once.
  useEffect(() => {
    let stopped = false
    let inFlight = false
    const poll = async () => {
      if (stopped || inFlight || document.visibilityState !== 'visible') return
      inFlight = true
      try {
        const s = document.hasFocus() ? await api.tick(new Date().toISOString()) : await api.state()
        if (!stopped) apply(s)
      } catch (e) {
        if (!stopped) {
          setConnected(false)
          setError(e instanceof Error ? e.message : String(e))
        }
      } finally {
        inFlight = false
      }
    }
    void poll()
    const id = window.setInterval(poll, 2000)
    const onVisible = () => { if (document.visibilityState === 'visible') void poll() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { stopped = true; window.clearInterval(id); document.removeEventListener('visibilitychange', onVisible) }
  }, [apply])

  const simNow = useCallback(() => {
    const s = stateRef.current
    if (!s) return 0
    if (!s.running) return s.now
    const elapsed = (Date.now() - receivedAt.current) / 1000
    return s.now + Math.min(elapsed, 10) * s.speed / 60
  }, [])

  // The on-screen clock: redrawn 4× a second, like the app's 0.25 s timer.
  useEffect(() => {
    const id = window.setInterval(() => setDisplayNow(simNow()), 250)
    return () => window.clearInterval(id)
  }, [simNow])

  // The deployment picker hides tabs: if the current one goes, go back to the front door.
  useEffect(() => {
    if (!state) return
    if (!tabsFor(state.deployment, state.tabs).includes(nav.tab)) setNav((n) => ({ ...n, tab: 'frontDoor' }))
  }, [state, nav.tab])

  // The guided demo drives the screens like the app's script does: the intake sheet while it dictates, then the
  // follow-through case, the call, the right door and the measures. Each cue is applied once, when it changes.
  const demo = state?.demo?.running ? state.demo : null
  const demoTab = demo?.tab ?? null
  const demoFollow = demo?.followId ?? null
  const demoRightDoor = demo?.rightDoorId ?? null
  const demoIntakeOpen = demo ? Boolean(demo.intake?.open ?? (demo.transcriptSoFar != null)) : null
  const demoStep = demo?.step ?? -1
  useEffect(() => {
    if (!demo) return
    setNav((n) => {
      let next = n
      if (demoTab && ALL_TABS.includes(demoTab as Tab) && n.tab !== demoTab) next = { ...next, tab: demoTab as Tab }
      if (next.followCase !== demoFollow) next = { ...next, followCase: demoFollow }
      if (demoRightDoor != null && next.rightDoorId !== demoRightDoor) next = { ...next, rightDoorId: demoRightDoor }
      if (demoIntakeOpen != null && next.showIntake !== demoIntakeOpen) next = { ...next, showIntake: demoIntakeOpen, showSettings: false }
      return next
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoTab, demoFollow, demoRightDoor, demoIntakeOpen, demoStep, demo != null])

  const settings = useCallback(async (s: Settings) => { await run(() => api.settings(s)) }, [run])

  // Stable actions: the store value changes only when the state, the navigation or the banner does.
  const actions = useMemo(() => ({
    dismissBanner: () => setBanner(null),
    setTab: (tab: Tab) => setNav((n) => ({ ...n, tab })),
    openPatient: (id: number | null) => setNav((n) => ({ ...n, frontPatient: id, tab: 'frontDoor' })),
    openCase: (id: number | null) => setNav((n) => ({ ...n, followCase: id, tab: 'followThrough' })),
    openRightDoor: (id: number) => setNav((n) => ({ ...n, rightDoorId: id, tab: 'rightDoor', frontPatient: null, followCase: null })),
    setRightDoorId: (id: number) => setNav((n) => ({ ...n, rightDoorId: id })),
    setShowIntake: (v: boolean) => setNav((n) => ({ ...n, showIntake: v })),
    setShowSettings: (v: boolean) => setNav((n) => ({ ...n, showSettings: v })),
    setShowUnits: (v: boolean) => setNav((n) => ({ ...n, showUnits: v })),
  }), [])

  const value = useMemo<Store>(() => ({
    state, error, connected, nav, banner, ...actions,
    apply, run, settings, simNow,
    episode: (id) => state?.waiting.find((e) => e.id === id) ?? state?.followCases.find((e) => e.id === id),
  }), [state, error, connected, nav, banner, actions, apply, run, settings, simNow])

  return <Ctx.Provider value={value}><ClockCtx.Provider value={displayNow}>{children}</ClockCtx.Provider></Ctx.Provider>
}
