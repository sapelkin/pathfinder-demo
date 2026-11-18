// Pathfinder's palette.
import type { Cohort, FollowTier, ServiceKind, TravelMode } from '../api/types'

export const colors = {
  accent: '#2a78d6',
  orange: '#eb6834',
  green: '#1baf7a',
  purple: '#7e57c2',
  slate: '#475464',
  red: '#d62e33',
  secondary: '#6b6f76',
  background: '#f2f2f7',
  card: '#ffffff',
  fill: '#e9e9ee',
  text: '#111111',
}

export const ATS_TARGET_MINUTES = [0, 10, 30, 60, 120]
export const ATS_NAMES = ['Resuscitation', 'Emergency', 'Urgent', 'Semi-urgent', 'Non-urgent']
export const ATS_WITHIN = ['Immediately', 'Within 10 minutes', 'Within 30 minutes', 'Within 60 minutes', 'Within 120 minutes']

export function atsColor(a: number): string {
  switch (a) {
    case 1: return '#d62e33'
    case 2: return '#f5851a'
    case 3: return '#219954'
    case 4: return '#2b73d6'
    default: return '#9ea3ad'
  }
}

export function tierColor(t: FollowTier): string {
  switch (t) {
    case 1: return '#d62e33'
    case 2: return colors.orange
    case 3: return colors.accent
    default: return colors.secondary
  }
}

export const TIER_TITLES: Record<FollowTier, string> = { 1: 'Call now', 2: 'Call today', 3: 'Check within 24 hours', 4: 'Automatic day-2 message' }
export const TIER_SHORT: Record<FollowTier, string> = { 1: 'Call now', 2: 'Call today', 3: 'Within 24 h', 4: 'Auto message' }
export const TIER_POLICY: Record<FollowTier, string> = {
  1: 'High risk: contact immediately (WACHS did-not-wait policy, high risk).',
  2: 'Moderate risk: contact the same day. The policy says next business hours; Pathfinder runs 7 days.',
  3: 'Check the person got the care they need: message first, call if no reply.',
  4: 'Routine: a day-2 check-in message with where to go next time.',
}

export function cohortColor(c: Cohort): string {
  switch (c) {
    case 'mh': return colors.purple
    case 'p65': return colors.green
    default: return colors.secondary
  }
}
export function cohortShort(c: Cohort): string { return c === 'mh' ? 'MH' : c === 'p65' ? '65+' : '' }

export function unitKindColor(k: 'connector' | 'store' | 'model' | 'function' | 'surface'): string {
  switch (k) {
    case 'connector': return colors.accent
    case 'store': return colors.purple
    case 'model': return colors.orange
    case 'function': return colors.green
    default: return colors.slate
  }
}

export const OUTCOME_LABEL: Record<string, string> = {
  B: 'Admitted', D: 'Discharged home', R1: 'Redirected at triage', R2: 'Did not wait', R3: 'Left at own risk',
}

export const TRAVEL_SHORT: Record<TravelMode, string> = { walk: 'on foot', bus: 'by bus', car: 'by car' }
export const TRAVEL_LABEL: Record<TravelMode, string> = { walk: 'On foot', bus: 'By bus', car: 'By car' }

export const SERVICE_KIND_LABEL: Record<ServiceKind, string> = {
  ed: 'Emergency department', urgentCare: 'Urgent care clinic', gp: 'GP', pharmacy: 'Pharmacy',
  mentalHealth: 'Mental health team', safeHaven: 'Safe Haven', virtualED: 'Virtual ED', phone: 'Phone line', homeCare: 'Care at home',
}
export const SERVICE_SHORT: Record<ServiceKind, string> = {
  ed: 'ED', urgentCare: 'UC', gp: 'GP', pharmacy: 'Rx', mentalHealth: 'MH', safeHaven: 'SH', virtualED: 'V', phone: 'Ph', homeCare: 'H',
}
export function bookable(k: ServiceKind): boolean { return k === 'gp' || k === 'mentalHealth' || k === 'homeCare' }
export function openFactor(opensIn: number, kind: ServiceKind): number {
  if (opensIn === 0) return 1
  if (bookable(kind)) return opensIn <= 2 * 1440 ? 0.8 : 0.5
  return opensIn <= 180 ? 0.6 : 0.3
}
export function travelFactor(minutes?: number | null): number {
  return minutes == null ? 0.8 : Math.exp(-minutes / 30)
}

/// Ring colours as RightDoorView.ringColor: home orange, then a blue ramp that deepens with the ring index.
export function ringColor(k: number, total: number): string {
  if (k === 0) return colors.orange
  const t = k / Math.max(1, total)
  return hsv(0.58 * 360, 0.12 + 0.75 * t, 1.0 - 0.5 * t)
}

export function hsv(h: number, s: number, v: number): string {
  const c = v * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = v - c
  let r = 0, g = 0, b = 0
  if (h < 60) [r, g, b] = [c, x, 0]
  else if (h < 120) [r, g, b] = [x, c, 0]
  else if (h < 180) [r, g, b] = [0, c, x]
  else if (h < 240) [r, g, b] = [0, x, c]
  else if (h < 300) [r, g, b] = [x, 0, c]
  else [r, g, b] = [c, 0, x]
  const to = (n: number) => Math.round((n + m) * 255).toString(16).padStart(2, '0')
  return `#${to(r)}${to(g)}${to(b)}`
}
