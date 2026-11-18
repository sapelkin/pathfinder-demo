import { BriefcaseMedicalFilled, PulseRegular, PersonRegular, ArrowSyncRegular } from '@fluentui/react-icons'
import { useStore, useDisplayNow } from '../state/store'
import { Card, Chip } from '../components/ui'
import { colors, atsColor, TIER_SHORT, tierColor } from '../lib/theme'
import { clockText, duration } from '../lib/clock'
import { QueueChart, FuturesChart, TierBars } from '../components/Charts'
import { contactShare } from './FollowThrough'
import { PublishedChip } from '../components/Published'

/// The department live: the room now, the wait model's working, follow-through. Everything redraws as the clock runs.
export function Live() {
  const { state } = useStore()
  const displayNow = useDisplayNow()
  if (!state) return <div className="empty">Connecting…</div>
  const contact = contactShare(state.followCases, state.now)
  const todayDNW = (() => {
    const today = state.followCases.filter((e) => e.arrival >= 5 * 1440)
    const left = today.filter((e) => e.outcome === 'R2').length
    const arrivals = today.length + state.waiting.length + state.counters.inCare
    return arrivals === 0 ? 0 : left / arrivals
  })()
  const etaShare = state.waiting.length === 0 ? 0 : state.waiting.filter((e) => e.etaSentAt != null).length / state.waiting.length
  const tile = (value: string, label: string, color: string) => (
    <div className="stat" key={label}><div className="stat-value" style={{ color, fontSize: 24 }}>{value}</div><div className="stat-label">{label}</div></div>
  )
  const tiers = ([1, 2, 3, 4] as const).map((t) => ({ tier: TIER_SHORT[t], open: state.followCases.filter((e) => e.followUp?.tier === t && e.followUp.status !== 'closed').length, color: tierColor(t) }))
  return (
    <div className="page">
      <div className="stack">
        <Card>
          <div className="hstack-nowrap">
            <BriefcaseMedicalFilled style={{ color: colors.accent, fontSize: 18 }} />
            <span className="headline">{state.hospital?.name ?? state.ed.name}</span>
            <span className="caption mono">{clockText(displayNow)}</span>
            <span className="spacer" />
            <Chip text="Simulated" icon={<PulseRegular />} />
            <PublishedChip hospital={state.hospital} />
          </div>
          <div className="stats live-stats">
            {tile(String(state.counters.waiting), 'waiting', colors.accent)}
            {tile(String(state.counters.inCare), 'in care', colors.green)}
            {tile(duration(state.counters.longestWait), 'longest wait', colors.orange)}
            {tile(String(state.counters.mayLeave), 'may leave', atsColor(1))}
            {tile(`${(todayDNW * 100).toFixed(1)}%`, 'did not wait today', colors.orange)}
            {tile(`${Math.round(etaShare * 100)}%`, 'know their wait', colors.accent)}
            {tile(`${contact.done}/${contact.total}`, 'reached, of those due', colors.purple)}
          </div>
        </Card>
        <div className="grid-2">
          <Card title="Waiting room today" icon={<PersonRegular />} tint={colors.accent}>
            <QueueChart points={state.queueHistory} now={displayNow} />
            <p className="caption">People waiting to be seen, every 15 minutes, simulated Saturday. Live.</p>
          </Card>
          <Card title="The wait model, live: 100 futures for the next person" icon={<PulseRegular />} tint={colors.orange}>
            <FuturesChart />
          </Card>
          <Card title="In care" icon={<BriefcaseMedicalFilled />} tint={colors.green}>
            <div className="stat-value" style={{ color: colors.green, fontSize: 40 }}>{state.counters.inCare}</div>
            <p className="caption">People called in and being treated right now; {state.counters.waiting} still waiting to be seen.</p>
          </Card>
          <Card title="Follow-through" icon={<ArrowSyncRegular />} tint={colors.purple}>
            <TierBars rows={tiers} />
            <div className="stats">
              {tile(String(state.followCases.filter((e) => e.followUp?.status === 'closed' && e.followUp.tier !== 4).length), 'loops closed in 24 h', colors.green)}
              {tile(`${contact.done} of ${contact.total}`, 'reached when due', colors.purple)}
              {tile(String(contact.notYetDue), 'not yet due', colors.secondary)}
            </div>
          </Card>
        </div>
        <p className="caption" style={{ padding: '0 4px' }}>Simulated ED, calibrated to published WA figures; patients are fictional. Every panel updates as the clock runs.</p>
      </div>
    </div>
  )
}
