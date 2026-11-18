import { useEffect, useState } from 'react'
import { PersonRegular, PersonWalkingRegular, DataBarVerticalRegular } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { KPI, KPIMetro, Hospital } from '../api/types'
import { useStore, useDisplayNow } from '../state/store'
import { Card, NumberDot, hexAlpha } from '../components/ui'
import { colors } from '../lib/theme'
import { QueueChart, ArrivalsChart } from '../components/Charts'

function pct(x?: number): string { return x == null ? 'n/a' : `${(x * 100).toFixed(1)}%` }

function KPICard({ number, title, now, baseline, target }: { number: number; title: string; now: string; baseline: string; target: string }) {
  return (
    <Card>
      <div className="hstack-nowrap" style={{ alignItems: 'flex-start', gap: 10 }}>
        <NumberDot n={number} size={22} />
        <span className="subhead" style={{ fontWeight: 600 }}>{title}</span>
      </div>
      <div className="kpi-now">{now}</div>
      <div className="kpi-table">
        <span className="k">Baseline</span><span>{baseline}</span>
        <span className="k">Target</span><span style={{ color: colors.green, fontWeight: 600 }}>{target}</span>
      </div>
    </Card>
  )
}

/// The published category-4 average against the same room simulated as today and with Pathfinder's redirects.
/// Every number comes from /kpi.metro and /state.hospital; the difference is computed here from the two bars.
function MetroCard({ metro, hospital }: { metro?: KPIMetro | null; hospital?: Hospital | null }) {
  if (!metro) {
    return (
      <Card title="Published average vs this simulation" icon={<DataBarVerticalRegular />} tint={colors.accent}>
        <p className="subhead secondary">This comparison needs a metropolitan hospital: pick one under Settings → Hospital, and the room is rebuilt from WA Health's published numbers.</p>
      </Card>
    )
  }
  // The clean measure compares the same arrival stream in both arms: category-4 people who arrive within the
  // horizon. The mean over everyone *called* within the horizon is kept as a secondary line, because when the
  // gate empties the room, capacity reaches deeper into the backlog and that average can move the other way.
  const arrivals = metro.newArrivalT4WaitMin ?? metro.simulatedT4WaitMin
  const base = arrivals.baseline
  const withR = arrivals.withRedirects
  const diff = base - withR
  const pct = base > 0 ? (diff / base) * 100 : 0
  const max = Math.max(1, metro.publishedT4AvgWaitMin, base, withR)
  const bar = (label: string, value: number, color: string, note?: string) => (
    <div key={label}>
      <div className="metro-bar-label"><span>{label}</span><span className="mono" style={{ fontWeight: 700 }}>{Math.round(value)} min{note ? <span className="caption" style={{ fontWeight: 400 }}> · {note}</span> : null}</span></div>
      <div className="metro-bar" role="img" aria-label={`${label}: ${Math.round(value)} minutes`}><div className="metro-bar-fill" style={{ width: `${Math.max(2, (value / max) * 100)}%`, background: color }} /></div>
    </div>
  )
  return (
    <Card title="Published average vs this simulation" icon={<DataBarVerticalRegular />} tint={colors.accent}>
      <div className="metro-grid">
        <div>
          <div className="caption">Published cat-4 average wait{hospital ? `, ${hospital.short}` : ''}</div>
          <div className="metro-published">{metro.publishedT4AvgWaitMin} min</div>
          <div className="caption">WA Health, Emergency department live activity, {metro.takenText}{hospital?.source.url ? <> · <a href={hospital.source.url} target="_blank" rel="noreferrer">source</a></> : null}</div>
        </div>
        <div className="metro-bars">
          {bar('Published average', metro.publishedT4AvgWaitMin, hexAlpha(colors.secondary, 0.45))}
          {bar('Simulated, as today: cat-4 arriving in the next 6 h', base, colors.orange, `${metro.waitingNow.baseline} waiting at +6 h`)}
          {bar('Simulated, with Pathfinder redirects', withR, colors.green, `${metro.waitingNow.withRedirects} waiting at +6 h`)}
          <p className="subhead" style={{ fontWeight: 600, color: diff >= 0 ? colors.green : colors.orange }}>
            {diff >= 0 ? `${Math.round(diff)} min shorter (−${Math.abs(pct).toFixed(0)}%)` : `${Math.round(-diff)} min longer (+${Math.abs(pct).toFixed(0)}%)`} with redirects · {Math.round(metro.redirectedShare * 100)}% of arrivals redirected
          </p>
        </div>
      </div>
      <p className="caption">{metro.method}{metro.replicas ? ` ${metro.replicas} replicas over ${metro.horizonMinutes} minutes.` : ''}{metro.newArrivalT4WaitMin ? ` Everyone called within the horizon, including the backlog already in the room: ${Math.round(metro.simulatedT4WaitMin.baseline)} → ${Math.round(metro.simulatedT4WaitMin.withRedirects)} min.` : ''}</p>
    </Card>
  )
}

/// The six pitch KPIs: today's simulated shift against baselines from published WA and national figures.
export function Impact() {
  const { state } = useStore()
  const displayNow = useDisplayNow()
  const [kpi, setKpi] = useState<KPI | null>(null)
  const [error, setError] = useState<string | null>(null)
  const version = state?.version
  useEffect(() => {
    let cancelled = false
    api.kpi().then((k) => { if (!cancelled) { setKpi(k); setError(null) } }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [version])
  if (!state) return <div className="empty">Connecting…</div>
  if (!kpi) return <div className="empty">{error ? `Impact unavailable: ${error}` : 'Counting…'}</div>
  const b = kpi.baselines
  const ret = (cohort: string, outcome: string) => b.returns?.find((r) => r.cohort === cohort && r.outcome === outcome)?.ret28
  const capture = kpi.captureSeconds.length === 0 ? 'No intakes yet' : `${Math.round(kpi.captureSeconds.reduce((a, c) => a + c, 0) / kpi.captureSeconds.length)} s average`
  const contact = kpi.rContactShare
  const next = kpi.namedNextStepShare
  return (
    <div className="page">
      <div className="stack">
        <MetroCard metro={kpi.metro} hospital={state.hospital} />
        <Card title="Waiting room today" icon={<PersonRegular />} tint={colors.accent}>
          <QueueChart points={kpi.queueHistory ?? state.queueHistory} now={displayNow} height={150} />
          <p className="caption">People waiting to be seen, every 15 minutes, simulated Saturday.</p>
        </Card>
        <div className="kpi-grid">
          <KPICard number={1} title="Nurse time to capture the front-door record" now={capture} baseline="2 to 5 min triage, plus registration typing" target="Under 3 min, structured, no retyping" />
          <KPICard number={2} title="Waiting patients who know their expected time" now={`${Math.round(kpi.etaShareWaiting * 100)}% of people waiting`} baseline="0%: only hospital averages are public" target="Everyone who consents, updated every 10 minutes" />
          <KPICard number={3} title="Did not wait" now={`${(kpi.todayDNWRate * 100).toFixed(1)}% of today's arrivals (simulated)`} baseline={`${pct(b.dnw_rate)}: the national rate on WA's triage mix; ${pct(b.dnw_ats123_share)} of them category 1 to 3`} target="3.6% in year one" />
          <KPICard number={4} title="People who left or were redirected, contacted within 24 hours" now={contact.total === 0 ? 'None due yet' : `${contact.done} of ${contact.total} due were contacted`} baseline="Not measured; a next-business-day call for moderate or high risk only" target="95% contacted, every reason recorded" />
          <KPICard number={5} title="Mental health: back in an ED within 28 days after going home" now={kpi.returns != null ? `${(kpi.returns * 100).toFixed(1)}% so far` : 'Measured at 28 days'} baseline={`${pct(ret('mh', 'D'))}, assumed from published studies`} target="20%" />
          <KPICard number={6} title="People aged 65+ sent home with a named next step" now={`${next.done} of ${next.total} today`} baseline={`Not recorded; ${pct(ret('p65', 'D'))} are back within 28 days`} target="80% with a named service" />
        </div>
        <Card title="Arrivals today against the weekly pattern" icon={<PersonWalkingRegular />} tint={colors.green}>
          <ArrivalsChart rows={kpi.arrivalsByHour} now={displayNow} />
        </Card>
        <p className="caption" style={{ padding: '0 4px' }}>Baselines: published WA and national figures plus stated assumptions, listed in PUBLIC_FIGURES.md. The demo ED and its patients are simulated. Triage suggestions use published ATS descriptors and are not yet clinically validated.</p>
      </div>
    </div>
  )
}
