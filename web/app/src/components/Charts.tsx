import { useMemo } from 'react'
import { ResponsiveContainer, ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid, ReferenceLine, Tooltip, BarChart } from 'recharts'
import { useStore, useDisplayNow } from '../state/store'
import { ATSBadge } from './ui'
import { colors, atsColor } from '../lib/theme'
import { hexAlpha } from './ui'
import { DAY_START, duration, hourLabel } from '../lib/clock'

/// People waiting through the day: shared by the dashboard, the impact page and the wide-screen room panel.
export function QueueChart({ points, now, height = 170 }: { points: { minute: number; waiting: number }[]; now: number; height?: number }) {
  const data = useMemo(() => points.map((p) => ({ h: (p.minute - DAY_START) / 60, waiting: p.waiting })), [points])
  const nowH = (now - DAY_START) / 60
  return (
    <div className="chart-wrap" style={{ height }} role="img" aria-label="People waiting to be seen through the day">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 14, right: 8, left: -22, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#e4e4ea" />
          <XAxis dataKey="h" type="number" domain={[0, 24]} ticks={[0, 6, 12, 18, 24]} tickFormatter={hourLabel} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
          <Tooltip formatter={(v) => [`${v} waiting`, '']} labelFormatter={(h) => hourLabel(Math.round(Number(h)))} />
          <Area type="monotone" dataKey="waiting" stroke="none" fill={hexAlpha(colors.accent, 0.18)} isAnimationActive={false} />
          <Line type="monotone" dataKey="waiting" stroke={colors.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
          <ReferenceLine x={nowH} stroke={hexAlpha(colors.orange, 0.7)} strokeDasharray="4 4" label={{ value: 'now', position: 'top', fill: colors.orange, fontSize: 10 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/// The 100 simulated futures for the next person to be called: a histogram of minutes until seen.
export function FuturesChart() {
  const { state } = useStore()
  const displayNow = useDisplayNow()
  const next = state?.nextToBeCalled
  const e = next ? state?.waiting.find((w) => w.id === next.id) : undefined
  const bins = useMemo(() => {
    const counts = new Map<number, number>()
    for (const s of next?.samples ?? []) {
      const b = Math.min(120, Math.floor(s / 10) * 10)
      counts.set(b, (counts.get(b) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => a[0] - b[0]).map(([minute, count]) => ({ minute: minute + 5, count }))
  }, [next?.samples])
  if (!next || !e) return <p className="subhead secondary">Nobody waiting to be called.</p>
  const eta = e.eta
  const first = e.name.split(' ')[0]
  return (
    <>
      <div className="hstack-nowrap">
        <ATSBadge ats={e.ats} size={30} />
        <div style={{ minWidth: 0 }}>
          <div className="subhead" style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.name}, {e.complaint}</div>
          <div className="caption">waited {duration(Math.floor(displayNow - e.arrival))}{eta ? ` · seen in ${eta.rangeText}` : ''}</div>
        </div>
      </div>
      <div className="chart-wrap" style={{ height: 150 }} role="img" aria-label={`Histogram of 100 simulated futures for ${e.name}`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={bins} margin={{ top: 16, right: 8, left: -22, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#e4e4ea" />
            <XAxis dataKey="minute" type="number" domain={[0, 130]} ticks={[0, 30, 60, 90, 120]} tickLine={false} axisLine={false} label={{ value: 'minutes from now', position: 'insideBottomRight', offset: -2, fontSize: 10, fill: colors.secondary }} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
            <Tooltip formatter={(v) => [`${v} futures`, '']} labelFormatter={(m) => `${Number(m) - 5}–${Number(m) + 5} min`} />
            <Bar dataKey="count" fill={hexAlpha(colors.orange, 0.75)} barSize={22} isAnimationActive={false} />
            {eta && <ReferenceLine x={eta.p10} stroke={colors.accent} strokeDasharray="4 3" strokeWidth={1.5} />}
            {eta && <ReferenceLine x={eta.p50} stroke={colors.accent} strokeWidth={2.5} label={{ value: `median ${eta.p50} min`, position: 'top', fill: colors.accent, fontSize: 10 }} />}
            {eta && <ReferenceLine x={eta.p90} stroke={colors.accent} strokeDasharray="4 3" strokeWidth={1.5} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="caption">Each bar: how many of the 100 futures call {first} in that ten minutes. The range sent by text is the 10th to the 90th percentile; new arrivals follow the weekly pattern.</p>
    </>
  )
}

/// Arrivals in each hour so far, with the weekly template's expectation for a Saturday.
export function ArrivalsChart({ rows, now }: { rows: { hour: number; actual: number; expected: number }[]; now: number }) {
  const nowHour = (now - DAY_START) / 60
  const data = rows.map((r) => ({ h: r.hour + 0.5, actual: r.hour < nowHour ? r.actual : null, expected: r.expected }))
  return (
    <>
      <div className="chart-wrap" style={{ height: 150 }} role="img" aria-label="Arrivals by hour against the weekly pattern">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 8, left: -22, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#e4e4ea" />
            <XAxis dataKey="h" type="number" domain={[0, 24]} ticks={[0, 6, 12, 18, 24]} tickFormatter={hourLabel} tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} />
            <Tooltip labelFormatter={(h) => hourLabel(Math.floor(Number(h)))} formatter={(v, name) => [typeof v === 'number' ? v.toFixed(1) : v, name === 'actual' ? 'arrived' : 'expected']} />
            <Bar dataKey="actual" fill={hexAlpha(colors.green, 0.75)} barSize={9} isAnimationActive={false} />
            <Line type="monotone" dataKey="expected" stroke={colors.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
            <ReferenceLine x={nowHour} stroke={hexAlpha(colors.orange, 0.7)} strokeDasharray="4 4" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="caption">Bars: arrivals so far this hour. Line: the hour-of-week template the wait model draws new arrivals from.</p>
    </>
  )
}

/// Open cases by tier.
export function TierBars({ rows }: { rows: { tier: string; open: number; color: string }[] }) {
  return (
    <div className="chart-wrap" style={{ height: 150 }} role="img" aria-label="Open follow-through cases by tier">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 30, left: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="tier" width={84} tickLine={false} axisLine={false} />
          <Bar dataKey="open" isAnimationActive={false} label={{ position: 'right', fontSize: 11, fill: colors.secondary }} shape={(p: unknown) => {
            const { x, y, width, height, payload } = p as { x: number; y: number; width: number; height: number; payload: { color: string } }
            return <rect x={x} y={y + height * 0.2} width={Math.max(2, width)} height={height * 0.6} rx={3} fill={payload.color} />
          }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export { atsColor }
