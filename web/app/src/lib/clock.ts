// SimClock, as in the engine's clock.py: simulated minutes since Monday 00:00 of the demo week.
export const WEEK = 10_080
export const START_MINUTE = 5 * 1440 + 14 * 60 + 30 // Saturday 2:30 pm
export const DAY_START = 5 * 1440 // Saturday 00:00
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function minuteOfDay(t: number): number { return ((t % 1440) + 1440) % 1440 }
export function dayOfWeek(t: number): number { return Math.floor((((t % WEEK) + WEEK) % WEEK) / 1440) }
export function hourOfWeek(t: number): number { return Math.floor((((t % WEEK) + WEEK) % WEEK) / 60) }

export function clockTime(t: number): string {
  const m = minuteOfDay(Math.floor(t))
  const h = Math.floor(m / 60)
  const mm = m % 60
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${String(mm).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`
}

export function clockText(t: number): string { return `${DAYS[dayOfWeek(Math.floor(t))]} ${clockTime(t)}` }

export function duration(minutes: number): string {
  const m = Math.max(0, Math.floor(minutes))
  if (m < 60) return `${m} min`
  return m % 60 === 0 ? `${Math.floor(m / 60)} h` : `${Math.floor(m / 60)} h ${m % 60} m`
}

export function round5(m: number): number { return Math.max(0, Math.round(m / 5) * 5) }

export function hourLabel(h: number): string {
  if (h === 0 || h === 24) return '12am'
  if (h === 12) return '12pm'
  return h < 12 ? `${h}am` : `${h - 12}pm`
}
