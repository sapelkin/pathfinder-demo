import { useEffect, useState } from 'react'
import { Button, Dialog, DialogSurface, DialogBody, DialogTitle, DialogContent, DialogActions } from '@fluentui/react-components'
import { PhoneFilled, ChatFilled, PeopleFilled, CheckmarkCircleFilled, FlagFilled, ArrowCircleRightRegular, HistoryRegular, ChatBubblesQuestionRegular, QuestionCircleRegular, ArrowTurnRightRegular, ArrowUndoRegular, MapRegular, WarningFilled, ShieldRegular, PersonCallRegular, ArrowSyncRegular, DataBarVerticalRegular } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { EpisodeView, FollowTier, RightDoorResult } from '../api/types'
import { useStore, useDisplayNow } from '../state/store'
import { ATSBadge, Card, Chip, CohortTag, FlowChips, IconLabel, LabeledRow, NumberDot, Row, Section } from '../components/ui'
import { colors, TIER_SHORT, TIER_TITLES, TIER_POLICY, tierColor, OUTCOME_LABEL, atsColor, TRAVEL_SHORT } from '../lib/theme'
import { clockTime, duration } from '../lib/clock'
import { flagLabel } from './PatientDetail'
import { TierBars } from '../components/Charts'
import { ServiceIcon } from './RightDoor'
import { useWide } from '../lib/useWide'

const TIERS: FollowTier[] = [1, 2, 3, 4]

function openCases(cases: EpisodeView[], tier: FollowTier) {
  return cases.filter((e) => e.followUp?.tier === tier && e.followUp.status !== 'closed')
}
function closedCases(cases: EpisodeView[]) {
  return cases.filter((e) => e.followUp?.status === 'closed' && e.followUp.tier !== 4).sort((a, b) => (b.followUp?.closedAt ?? 0) - (a.followUp?.closedAt ?? 0))
}
/// People who left or were redirected in the last 24 hours: contacted, of those due, plus how many are not yet due.
export function contactShare(cases: EpisodeView[], now: number) {
  const r = cases.filter((e) => e.outcome === 'R2' || e.outcome === 'R3' || e.outcome === 'R1')
  const contacted = (e: EpisodeView) => (e.followUp?.attempts ?? 0) > 0 || e.followUp?.status === 'closed'
  const due = r.filter((e) => contacted(e) || (e.outcomeAt ?? 0) + (e.followUp?.dueMinutes ?? 0) <= now)
  return { done: due.filter(contacted).length, total: due.length, notYetDue: r.length - due.length }
}

function TierSummary() {
  const { state } = useStore()
  if (!state) return null
  const contact = contactShare(state.followCases, state.now)
  return (
    <Card>
      <div className="stats">
        {TIERS.map((t) => (
          <div className="stat" key={t}>
            <div className="stat-value" style={{ color: tierColor(t), fontSize: 22 }}>{openCases(state.followCases, t).length}</div>
            <div className="stat-label" style={{ fontSize: 11 }}>{TIER_SHORT[t]}</div>
          </div>
        ))}
      </div>
      <hr style={{ border: 0, borderTop: `1px solid ${colors.fill}`, margin: 0 }} />
      <IconLabel icon={<PersonCallRegular />} size="caption" color={colors.secondary}>
        Left or redirected in the last 24 hours: {contact.done} of {contact.total} due a contact have been reached or tried; {contact.notYetDue} more are not yet due.
      </IconLabel>
    </Card>
  )
}

function TierHeader({ tier, count }: { tier: FollowTier; count: number }) {
  return (
    <>
      <span className="tier-dot" style={{ background: tierColor(tier) }} />
      <span>{TIER_TITLES[tier]}</span>
      <span style={{ opacity: 0.7 }}>{count}</span>
    </>
  )
}

export function CaseRow({ episode: e }: { episode: EpisodeView }) {
  const f = e.followUp
  const due = e.dueText ?? ''
  const overdue = due.startsWith('Overdue') || due.startsWith('Try again now')
  return (
    <div className="queue-row">
      <span className="tier-bar" style={{ background: tierColor(f?.tier ?? 4) }} />
      <div className="queue-body" style={{ gap: 4 }}>
        <div className="queue-name">
          <span className="headline">{e.name}</span>
          <span className="secondary">{e.age}</span>
          <CohortTag cohort={e.cohort} />
          <span className="spacer" />
          {e.outcome && <Chip text={e.outcome} color={e.outcome === 'D' ? colors.green : colors.orange} />}
        </div>
        <div className="subhead secondary" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{f?.reasons?.[0] ?? e.complaint}</div>
        <div className="queue-foot">
          <span>{f?.risk7 != null ? `${Math.round(f.risk7 * 100)} in 100 back within 7 days` : ''}</span>
          <span style={{ color: overdue ? colors.orange : undefined }}>{due}</span>
        </div>
        {f?.result && f.status !== 'open' && (
          <IconLabel icon={f.status === 'closed' ? <CheckmarkCircleFilled /> : <PhoneFilled />} size="caption" color={f.status === 'closed' ? colors.green : colors.orange}>{f.result}</IconLabel>
        )}
      </div>
    </div>
  )
}

export function FollowThrough() {
  const { state, nav, openCase } = useStore()
  const [autoOpen, setAutoOpen] = useState(false)
  const wide = useWide()
  if (!state) return <div className="empty">Connecting…</div>
  const cases = state.followCases
  const selected = nav.followCase != null ? cases.find((e) => e.id === nav.followCase) : undefined
  const auto = openCases(cases, 4)
  const done = closedCases(cases)
  const list = (
    <div>
      <div className="section" style={{ marginBottom: 14 }}><TierSummary /></div>
      {([1, 2, 3] as FollowTier[]).map((tier) => {
        const rows = openCases(cases, tier)
        if (rows.length === 0) return null
        return (
          <Section key={tier} header={<TierHeader tier={tier} count={rows.length} />}>
            {rows.map((e) => <Row key={e.id} onClick={() => openCase(e.id)} selected={nav.followCase === e.id} ariaLabel={`${e.name}, ${TIER_TITLES[tier]}`}><CaseRow episode={e} /></Row>)}
          </Section>
        )
      })}
      <Section header={<TierHeader tier={4} count={auto.length} />}>
        <Row onClick={() => setAutoOpen((v) => !v)} chevron={false}>
          <div className="hstack-nowrap"><span style={{ flex: 1 }}>{auto.length} people discharged home</span><span aria-hidden>{autoOpen ? '▾' : '▸'}</span></div>
        </Row>
        {autoOpen && auto.slice(0, 30).map((e) => <Row key={e.id} onClick={() => openCase(e.id)} selected={nav.followCase === e.id}><CaseRow episode={e} /></Row>)}
      </Section>
      {done.length > 0 && (
        <Section header="Loop closed in the last 24 hours">
          {done.slice(0, 12).map((e) => <Row key={e.id} onClick={() => openCase(e.id)} selected={nav.followCase === e.id}><CaseRow episode={e} /></Row>)}
        </Section>
      )}
    </div>
  )
  return (
    <div className="page">
      <div className="split">
        <div className="split-list">{list}</div>
        <div className="split-detail">
          {selected ? (
            <div className="stack detail-stack">
              <div className="hstack">
                <Button appearance="subtle" onClick={() => openCase(null)} icon={<span aria-hidden>‹</span>}>Follow-through</Button>
                <span className="headline">{selected.name}</span>
              </div>
              <CaseView episode={selected} />
            </div>
          ) : wide ? <ListPanel /> : null}
        </div>
      </div>
    </div>
  )
}

function ListPanel() {
  const { state } = useStore()
  if (!state) return null
  const contact = contactShare(state.followCases, state.now)
  const rows = TIERS.map((t) => ({ tier: TIER_SHORT[t], open: openCases(state.followCases, t).length, color: tierColor(t) }))
  return (
    <div className="stack room-panel">
      <Card title="Follow-through" icon={<ArrowSyncRegular />} tint={colors.purple}>
        <TierBars rows={rows} />
        <div className="stats">
          <div className="stat"><div className="stat-value" style={{ color: colors.green }}>{closedCases(state.followCases).length}</div><div className="stat-label">loops closed in 24 h</div></div>
          <div className="stat"><div className="stat-value" style={{ color: colors.purple }}>{contact.done} of {contact.total}</div><div className="stat-label" style={{ whiteSpace: 'normal' }}>left or redirected, reached when due</div></div>
          <div className="stat"><div className="stat-value" style={{ color: colors.secondary }}>{contact.notYetDue}</div><div className="stat-label">not yet due</div></div>
        </div>
      </Card>
      <Card title="The six measures, today" icon={<DataBarVerticalRegular />} tint={colors.accent}>
        <p className="caption">Open the Impact tab for today's six measures against their baselines.</p>
      </Card>
      <p className="caption">Select a case on the left: the outcome of the contact, why they are on the list, the right door next time, and the script.</p>
    </div>
  )
}

/// One follow-through case: the outcome of the contact first, then why it is on the list, the right door next time,
/// the risk, and the script.
export function CaseView({ episode: e }: { episode: EpisodeView }) {
  const { run, openRightDoor, state } = useStore()
  const displayNow = useDisplayNow()
  const f = e.followUp
  const [showOutcomes, setShowOutcomes] = useState(false)
  const [calling, setCalling] = useState(false)
  const [plan, setPlan] = useState<RightDoorResult | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.rightDoor(e.id, 'nextTime').then((r) => { if (!cancelled) setPlan(r) }).catch(() => { if (!cancelled) setPlan(null) })
    return () => { cancelled = true }
  }, [e.id, e.outcome])

  const contact = async (reached: boolean, result: string, nextStep?: string) => {
    setBusy(true)
    setShowOutcomes(false)
    setCalling(false)
    await run(() => api.contact({ id: e.id, reached, result, nextStep }))
    setBusy(false)
  }
  const call = () => {
    setCalling(true)
    window.setTimeout(() => { setCalling(false); setShowOutcomes(true) }, 1600)
  }

  const left = e.outcome === 'R2' || e.outcome === 'R3'
  const demoCalling = state?.demo?.running && state.demo.callingId != null && String(state.demo.callingId) === String(e.id)
  const edFirst = plan ? plan.edFirst ?? plan.options.some((o) => o.pinned000) : false
  const ed = plan?.options.find((o) => o.service.kind === 'ed')
  const places = plan ? plan.options.filter((o) => o.minutes != null && !(edFirst && o.service.kind === 'ed')).slice(0, 3) : []
  const where = e.homeSuburb || 'home'
  const mode = plan?.mode ?? e.travel

  return (
    <div className="stack">
      <Card>
        <div className="detail-head">
          <ATSBadge ats={e.ats} size={44} />
          <div style={{ minWidth: 0 }}>
            <div className="hstack"><span className="title3">{e.name}</span><span className="secondary">{e.age}</span><CohortTag cohort={e.cohort} /></div>
            <div className="secondary">{e.complaint}</div>
            {e.outcome && (
              <div className="subhead" style={{ fontWeight: 600, color: e.outcome === 'D' ? colors.green : colors.orange }}>
                {OUTCOME_LABEL[e.outcome]} at {clockTime(e.outcomeAt ?? 0)} after {duration((e.outcomeAt ?? 0) - e.arrival)} in the ED
              </div>
            )}
          </div>
        </div>
      </Card>

      {f && f.status === 'closed' ? (
        <Card title={`Loop closed at ${clockTime(f.closedAt ?? displayNow)}`} icon={<CheckmarkCircleFilled />} tint={colors.green}>
          <p className="subhead">{f.result ?? ''}</p>
          {f.nextStep && <IconLabel icon={<ArrowTurnRightRegular />} weight={600}>{f.nextStep}</IconLabel>}
          {e.leaveReason && left && <IconLabel icon={<CheckmarkCircleFilled />} size="caption" color={colors.secondary}>Reason for leaving recorded: {e.leaveReason.toLowerCase()}</IconLabel>}
        </Card>
      ) : (
        <>
          <div className="actions-3">
            <Button appearance="primary" icon={<PhoneFilled />} as="a" href={`tel:0400000000`} onClick={(ev) => { ev.preventDefault(); call() }} disabled={busy}>Call</Button>
            <Button icon={<ChatFilled />} disabled={busy || f?.messageSent} onClick={() => void run(() => api.message(e.id))}>{f?.messageSent ? 'Sent' : 'Message'}</Button>
            <Button icon={<PeopleFilled />} disabled={busy} onClick={() => void run(() => api.alo(e.id))} aria-pressed={f?.aloOffered}>{f?.aloOffered ? 'ALO asked' : 'Ask an Aboriginal Liaison Officer'}</Button>
          </div>
          {f?.result && f.status === 'noAnswer' && <IconLabel icon={<PhoneFilled />} size="caption" color={colors.orange}>{f.result}</IconLabel>}
        </>
      )}

      {f && (
        <Card title={f.tierTitle || TIER_TITLES[f.tier]} icon={<FlagFilled />} tint={tierColor(f.tier)}>
          {(f.reasons ?? []).map((r) => <IconLabel key={r} icon={<ArrowCircleRightRegular />}>{r}</IconLabel>)}
          <p className="caption">{f.policy || TIER_POLICY[f.tier]}</p>
          <p className="caption" style={{ fontWeight: 600, color: tierColor(f.tier) }}>{e.dueText}</p>
        </Card>
      )}

      <Card title={edFirst ? 'Next steps' : 'The right door next time'} icon={<MapRegular />} tint={colors.accent}>
        {edFirst ? (
          <>
            <IconLabel icon={<WarningFilled />} color={atsColor(1)} weight={600}>{e.problem} can be time-critical: if it comes back, call 000. The ED is the right door.</IconLabel>
            {ed && <p className="caption">Nearest ED from home: {ed.service.name}, {ed.minutesText}.</p>}
            <p className="caption">For follow-up and a check-up, from {where} {TRAVEL_SHORT[mode]}:</p>
          </>
        ) : (
          <p className="caption">From {where}, {TRAVEL_SHORT[mode]}, at this time:</p>
        )}
        {!plan && <p className="caption">Searching from home…</p>}
        {places.map((o) => (
          <div className="option-row" key={o.service.id}>
            <span style={{ color: colors.accent, width: 24, display: 'inline-flex', justifyContent: 'center' }}><ServiceIcon kind={o.service.kind} /></span>
            <div>
              <div className="subhead" style={{ fontWeight: 600 }}>{o.service.name}</div>
              <div className="caption">{o.service.goodFor}</div>
              <div className="hstack" style={{ marginTop: 2 }}>
                <Chip text={o.openText} color={o.opensIn === 0 ? colors.green : colors.secondary} />
                <span className="caption">{o.minutesText}</span>
              </div>
            </div>
          </div>
        ))}
        <button type="button" className="link-button" onClick={() => openRightDoor(e.id)}><MapRegular /> Show the search on the map</button>
      </Card>

      {f && f.risk7 != null && f.risk28 != null && (
        <Card title="Chance of coming back to an ED" icon={<ArrowUndoRegular />} tint={colors.accent}>
          <div className="stats" style={{ gap: 20 }}>
            <div><div className="title3" style={{ color: colors.accent }}>{Math.round(f.risk7 * 100)} in 100</div><div className="caption">within 7 days</div></div>
            <div><div className="title3" style={{ color: colors.accent }}>{Math.round(f.risk28 * 100)} in 100</div><div className="caption">within 28 days</div></div>
          </div>
          <p className="caption">{f.riskBasis}{f.riskN != null ? `, ${f.riskN.toLocaleString()} episodes` : ''}. Rates assumed from published studies, see PUBLIC_FIGURES.md.</p>
        </Card>
      )}

      {left && f?.status !== 'closed' && (
        <Card title="Why they left" icon={<QuestionCircleRegular />}>
          <p className="subhead">{e.leaveReason ?? 'Not told to staff. Ask on the call and record it: no system records this today.'}</p>
        </Card>
      )}
      {e.outcome === 'R1' && e.redirectService && (
        <Card title="Redirected at triage" icon={<ArrowTurnRightRegular />}>
          <p className="subhead">Sent to {e.redirectService}. Check they got there and were seen.</p>
        </Card>
      )}

      <Card title="Call script" icon={<ChatBubblesQuestionRegular />} tint={colors.accent}>
        <div className="script-line"><NumberDot n={1} /><span>Are you safe right now, and how are you feeling?</span></div>
        <div className="script-line"><NumberDot n={2} /><span>{e.outcome === 'D' ? 'Do you have what you need: medicines, appointments, a GP visit?' : 'Did you get care somewhere else? Where?'}</span></div>
        <div className="script-line"><NumberDot n={3} /><span>{e.outcome === 'D' ? 'If this happens again, here is where to go first.' : 'What would have helped you stay? What would help next time?'}</span></div>
        {e.cohort === 'mh' && <IconLabel icon={<ShieldRegular />} size="caption" color={atsColor(1)} weight={600}>If not safe: call 000, or the Mental Health Emergency Response Line on 1300 555 788.</IconLabel>}
      </Card>

      {e.transcript && <Card title="Dictated triage note" icon={<ChatBubblesQuestionRegular />}><p style={{ fontSize: 15 }}>{e.transcript}</p></Card>}

      <Card title="History" icon={<HistoryRegular />}>
        <LabeledRow label="ED visits earlier this year" value={String(e.priorVisits)} />
        {e.daysSinceLast != null && <LabeledRow label="Last visit" value={`${e.daysSinceLast} days ago`} />}
        {e.priorDNW && <LabeledRow label="Left before being seen before" value="Yes" />}
        {e.flags.length > 0 && <FlowChips items={e.flags.map(flagLabel).sort()} color={colors.purple} />}
      </Card>
      <div style={{ height: 40 }} />

      {(calling || demoCalling) && (
        <div className="calling" role="status">
          <div className="calling-card">
            <div className="calling-icon"><PhoneFilled /></div>
            <div className="title3">Calling {e.name}</div>
            <div className="caption">Script open. The outcome is recorded when the call ends.</div>
            <a className="link-button" href={`tel:0400000000`} onClick={(ev) => ev.stopPropagation()}>Dial from this device</a>
          </div>
        </div>
      )}

      <Dialog open={showOutcomes} onOpenChange={(_ev, d) => setShowOutcomes(d.open)}>
        <DialogSurface aria-describedby={undefined}>
          <DialogBody>
            <DialogTitle>Call outcome</DialogTitle>
            <DialogContent>
              <div className="stack">
                <div className="caption">Reached</div>
                <Button onClick={() => void contact(true, 'Safe, got care elsewhere')}>Reached: safe, got care elsewhere</Button>
                <Button onClick={() => void contact(true, 'Safe at home, will see own GP', 'GP within 48 hours')}>Reached: safe at home, will see GP</Button>
                <Button onClick={() => void contact(true, 'Coming back to the ED now')}>Reached: coming back to the ED</Button>
                {e.cohort === 'mh' && <Button onClick={() => void contact(true, 'Safe; referred to the community mental health team', 'Community mental health team')}>Reached: referred to community team</Button>}
                <div className="caption">Not reached</div>
                <Button onClick={() => void contact(false, '')}>No answer: send a message</Button>
              </div>
            </DialogContent>
            <DialogActions><Button appearance="secondary" onClick={() => setShowOutcomes(false)}>Cancel</Button></DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
      <span className="sr-only">{state?.clockText}</span>
    </div>
  )
}
