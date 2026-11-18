import { useEffect, useState } from 'react'
import { Button, Dialog, DialogSurface, DialogBody, DialogTitle, DialogContent, DialogActions } from '@fluentui/react-components'
import { PulseRegular, HistoryRegular, TextQuoteRegular, FlagCheckeredRegular, WarningFilled } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { EpisodeView, RightDoorResult, Outcome } from '../api/types'
import { useStore, useDisplayNow } from '../state/store'
import { ATSBadge, Card, CohortTag, FlowChips, LabeledRow, VitalsGrid, IconLabel } from '../components/ui'
import { ATS_NAMES, ATS_WITHIN, atsColor, colors, OUTCOME_LABEL, TRAVEL_SHORT } from '../lib/theme'
import { clockTime, duration } from '../lib/clock'

const LEAVE_REASONS = ['Wait too long', 'Felt better', 'Work or family', 'Transport home', 'Distressed', 'Not told to staff']

export function flagLabel(f: string): string {
  const map: Record<string, string> = {
    suicidalIdeation: 'Suicidal ideation', selfHarm: 'Self-harm', mentalHealthAct: 'Mental Health Act referral', drugsAlcohol: 'Drugs or alcohol',
    agitation: 'Agitated', psychosis: 'Psychotic symptoms', notLikelyToWait: 'Not likely to wait',
  }
  return map[f] ?? f
}

/// One patient in the department: what was captured, where they are, and how the episode ended.
export function PatientDetail({ episode: e }: { episode: EpisodeView }) {
  const { run, openPatient } = useStore()
  const displayNow = useDisplayNow()
  const [askReason, setAskReason] = useState(false)
  const [askService, setAskService] = useState(false)
  const [redirect, setRedirect] = useState<RightDoorResult | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!askService) return
    let cancelled = false
    setRedirect(null)
    api.rightDoor(e.id, 'redirectNow').then((r) => { if (!cancelled) setRedirect(r) }).catch(() => { if (!cancelled) setRedirect(null) })
    return () => { cancelled = true }
  }, [askService, e.id])

  const record = async (outcome: Outcome, reason?: string, service?: string) => {
    setBusy(true)
    setAskReason(false)
    setAskService(false)
    await run(() => api.outcome({ id: e.id, outcome, reason, service }))
    setBusy(false)
    if (outcome !== 'B') openPatient(null)
  }

  const status = (() => {
    switch (e.stage) {
      case 'waiting': return `Waiting ${duration(Math.floor(displayNow - e.arrival))}${e.holdReason ? `, ${e.holdReason.toLowerCase()}` : ''}`
      case 'inCare': return `In care since ${clockTime(e.calledAt ?? displayNow)}`
      default: return e.outcomeLabel ?? (e.outcome ? OUTCOME_LABEL[e.outcome] : 'Closed')
    }
  })()

  const redirectMessage = redirect
    ? redirect.blockers.length > 0 ? `${redirect.blockers.join('. ')}. Stays in the ED.` : redirect.message || (redirect.options.length === 0 ? 'Nothing suitable is open right now.' : '')
    : 'Checking open services near home…'

  return (
    <div className="stack">
      <Card>
        <div className="detail-head">
          <ATSBadge ats={e.ats} size={46} />
          <div style={{ minWidth: 0 }}>
            <div className="hstack"><span className="title3">{e.name}</span><span className="secondary">{e.age}</span><CohortTag cohort={e.cohort} /></div>
            <div className="secondary">{e.complaint}</div>
            <div className="caption" style={{ color: atsColor(e.ats) }}>{ATS_NAMES[e.ats - 1]} · {ATS_WITHIN[e.ats - 1].toLowerCase()}</div>
          </div>
        </div>
        <hr style={{ border: 0, borderTop: `1px solid ${colors.fill}`, margin: 0 }} />
        <LabeledRow label="Arrived" value={`${clockTime(e.arrival)} ${e.arrivalModeShort}`} />
        {e.homeSuburb && <LabeledRow label="Lives in" value={e.homeSuburb} />}
        <LabeledRow label="Status" value={status} />
        {e.eta && e.stage === 'waiting' && <LabeledRow label="Expected to be seen" value={e.eta.rangeText} />}
        {e.descriptor && <LabeledRow label="Triage descriptor" value={e.descriptor} />}
      </Card>

      {e.vitals && Object.values(e.vitals).some((v) => v != null) && (
        <Card title="Observations at triage" icon={<PulseRegular />}><VitalsGrid vitals={e.vitals} /></Card>
      )}

      <Card title="Known history" icon={<HistoryRegular />}>
        <LabeledRow label="ED visits earlier this year" value={String(e.priorVisits)} />
        {e.daysSinceLast != null && <LabeledRow label="Last visit" value={`${e.daysSinceLast} days ago`} />}
        {e.priorDNW && <IconLabel icon={<WarningFilled />} color={colors.orange}>Has left before being seen on an earlier visit</IconLabel>}
        {e.flags.length > 0 && <FlowChips items={e.flags.map(flagLabel).sort()} color={colors.purple} />}
      </Card>

      {e.transcript && <Card title="Dictated triage note" icon={<TextQuoteRegular />}><p style={{ fontSize: 15 }}>{e.transcript}</p></Card>}

      {e.stage !== 'closed' ? (
        <Card title="Record how the episode ends" icon={<FlagCheckeredRegular />}>
          <div className="actions">
            {e.stage === 'waiting' ? (
              <>
                <Button disabled={busy} onClick={() => setAskReason(true)}>Left before being seen (R2)</Button>
                <Button disabled={busy} onClick={() => setAskService(true)}>Redirect to another service (R1)</Button>
              </>
            ) : (
              <>
                <Button disabled={busy} onClick={() => void record('B')}>Admitted (B)</Button>
                <Button disabled={busy} onClick={() => void record('D')}>Discharged home (D)</Button>
                <Button disabled={busy} onClick={() => void record('R3')}>Left at own risk (R3)</Button>
              </>
            )}
          </div>
        </Card>
      ) : e.outcome ? (
        <Card title="Outcome" icon={<FlagCheckeredRegular />}>
          <LabeledRow label={OUTCOME_LABEL[e.outcome]} value={clockTime(e.outcomeAt ?? displayNow)} />
          {e.leaveReason && <LabeledRow label="Reason given" value={e.leaveReason} />}
          {e.redirectService && <LabeledRow label="Sent to" value={e.redirectService} />}
          {e.followUp && <LabeledRow label="Follow-through" value={e.followUp.tierTitle} />}
        </Card>
      ) : null}

      <Dialog open={askReason} onOpenChange={(_ev, d) => setAskReason(d.open)}>
        <DialogSurface aria-describedby={undefined}>
          <DialogBody>
            <DialogTitle>Why did they leave?</DialogTitle>
            <DialogContent>
              <div className="stack">
                {LEAVE_REASONS.map((r) => <Button key={r} onClick={() => void record('R2', r === 'Not told to staff' ? undefined : r)}>{r}</Button>)}
              </div>
            </DialogContent>
            <DialogActions><Button appearance="secondary" onClick={() => setAskReason(false)}>Cancel</Button></DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      <Dialog open={askService} onOpenChange={(_ev, d) => setAskService(d.open)}>
        <DialogSurface aria-describedby={undefined}>
          <DialogBody>
            <DialogTitle>{redirect && redirect.blockers.length === 0 && redirect.options.length > 0 ? 'Redirect to' : 'No redirect'}</DialogTitle>
            <DialogContent>
              <div className="stack">
                <p className="subhead secondary">{redirectMessage}</p>
                {redirect && redirect.blockers.length === 0 && redirect.options.slice(0, 5).map((o) => (
                  <Button key={o.service.id} onClick={() => void record('R1', undefined, o.service.name)}>
                    {o.minutes != null ? `${o.service.name}, ${Math.round(o.minutes)} min ${TRAVEL_SHORT[redirect.mode]}` : o.service.name}
                  </Button>
                ))}
              </div>
            </DialogContent>
            <DialogActions><Button appearance="secondary" onClick={() => setAskService(false)}>Cancel</Button></DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  )
}
