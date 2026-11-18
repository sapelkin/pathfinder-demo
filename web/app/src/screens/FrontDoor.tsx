import { Button } from '@fluentui/react-components'
import { MicFilled, BriefcaseMedicalFilled, PulseRegular, ChatFilled, PersonWalkingFilled, ArrowSwapRegular, PersonRegular, ShieldFilled, StarEmphasisFilled } from '@fluentui/react-icons'
import { useStore, useDisplayNow } from '../state/store'
import type { EpisodeView } from '../api/types'
import { ATSBadge, Card, Chip, CohortTag, Row, Section, Stat, WaitBar } from '../components/ui'
import { colors, atsColor } from '../lib/theme'
import { duration } from '../lib/clock'
import { PatientDetail } from './PatientDetail'
import { PublishedChip, PublishedLine } from '../components/Published'
import { QueueChart, FuturesChart } from '../components/Charts'
import { useWide } from '../lib/useWide'

export function StatusHeader() {
  const { state } = useStore()
  if (!state) return null
  return (
    <Card>
      <div className="hstack" style={{ gap: 8 }}>
        <BriefcaseMedicalFilled style={{ color: colors.accent, fontSize: 18 }} />
        <span className="headline" style={{ flex: '1 1 160px', minWidth: 0 }}>{state.hospital?.name ?? state.ed.name}</span>
        <Chip text="Simulated" icon={<PulseRegular />} />
        <PublishedChip hospital={state.hospital} />
      </div>
      <PublishedLine hospital={state.hospital} />
      <div className="stats">
        <Stat value={String(state.counters.waiting)} label="waiting" color={colors.accent} />
        <Stat value={String(state.counters.inCare)} label="in care" color={colors.green} />
        <Stat value={duration(state.counters.longestWait)} label="longest wait" color={colors.orange} />
        <Stat value={String(state.counters.mayLeave)} label="may leave" color={atsColor(1)} />
      </div>
    </Card>
  )
}

function arrivalSymbol(e: EpisodeView) {
  if (e.arrivalMode === 'By ambulance') return <StarEmphasisFilled style={{ fontSize: 13, color: colors.secondary }} aria-label="by ambulance" />
  if (e.arrivalMode === 'With police') return <ShieldFilled style={{ fontSize: 13, color: colors.secondary }} aria-label="with police" />
  return null
}

export function QueueRow({ episode: e, now }: { episode: EpisodeView; now: number }) {
  const waited = Math.max(e.waitedMinutes, Math.floor(now - e.arrival))
  return (
    <div className="queue-row">
      <ATSBadge ats={e.ats} />
      <div className="queue-body">
        <div className="queue-name">
          <span className="headline">{e.name}</span>
          <span className="secondary">{e.age}</span>
          <CohortTag cohort={e.cohort} />
          {arrivalSymbol(e)}
          <span className="spacer" />
          {e.etaSentAt != null && <span className="sent-dot" title="Expected time sent by text"><ChatFilled /></span>}
        </div>
        <div className="subhead secondary" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.complaint}</div>
        <WaitBar waited={waited} ats={e.ats} />
        <div className="queue-foot">
          <span>Waited {duration(waited)}</span>
          {e.holdReason ? <span style={{ color: colors.purple }}>{e.holdReason}</span> : e.eta ? <span>Seen in {e.eta.rangeText}</span> : null}
        </div>
        {e.mayLeaveSoon && (
          <div className="hstack-nowrap" style={{ color: colors.orange, fontSize: 12, fontWeight: 600 }}>
            <PersonWalkingFilled /> May leave before being seen
          </div>
        )}
      </div>
    </div>
  )
}

export function FrontDoor() {
  const { state, nav, openPatient, setShowIntake } = useStore()
  const displayNow = useDisplayNow()
  const wide = useWide()
  if (!state) return <div className="empty">Connecting to the demo ED…</div>
  const nurseUnit = state.deployment !== 'minimum'
  const list = (
    <div>
      <div className="section" style={{ marginBottom: 14 }}><StatusHeader /></div>
      {nurseUnit ? (
        <Section>
          <Row onClick={() => setShowIntake(true)} ariaLabel="New arrival: speak the triage note; Pathfinder fills the form">
            <div className="new-arrival">
              <span className="mic-circle"><MicFilled /></span>
              <div>
                <div className="headline">New arrival</div>
                <div className="subhead secondary">Speak the triage note; Pathfinder fills the form</div>
              </div>
            </div>
          </Row>
        </Section>
      ) : (
        <Section>
          <Row>
            <div className="icon-label icon-label-sub secondary"><ArrowSwapRegular /> <span>Minimum deployment: the queue comes from the ED system's messages; expected times go out by text. No nurse screen.</span></div>
          </Row>
        </Section>
      )}
      <Section
        header="Waiting to be seen, next first"
        footer="Order follows each category's target time. Expected times come from 100 simulated futures of this waiting room. Patients are fictional."
      >
        {state.waiting.length === 0 && <Row><span className="secondary">Nobody is waiting.</span></Row>}
        {state.waiting.map((e) => (
          <Row key={e.id} onClick={() => openPatient(e.id)} selected={nav.frontPatient === e.id} ariaLabel={`${e.name}, ${e.age}, ${e.complaint}`}>
            <QueueRow episode={e} now={displayNow} />
          </Row>
        ))}
      </Section>
    </div>
  )
  const selected = nav.frontPatient != null ? state.waiting.find((e) => e.id === nav.frontPatient) ?? state.followCases.find((e) => e.id === nav.frontPatient) : undefined
  return (
    <div className="page">
      <div className="split">
        <div className="split-list">
          {list}
        </div>
        <div className="split-detail">
          {selected ? (
            <div className="stack detail-stack">
              <div className="hstack">
                <Button appearance="subtle" onClick={() => openPatient(null)} icon={<span aria-hidden>‹</span>}>Front door</Button>
                <span className="headline">{selected.name}</span>
              </div>
              <PatientDetail episode={selected} />
            </div>
          ) : wide ? (
            <RoomPanel />
          ) : null}
        </div>
      </div>
    </div>
  )
}

/// Wide screen: the room's charts beside the queue, until a patient is selected.
function RoomPanel() {
  const { state } = useStore()
  const displayNow = useDisplayNow()
  if (!state) return null
  return (
    <div className="stack room-panel">
      <Card title="Waiting room today" icon={<PersonRegular />} tint={colors.accent}>
        <QueueChart points={state.queueHistory} now={displayNow} height={190} />
      </Card>
      <Card title="The wait model, live: 100 futures for the next person" icon={<PulseRegular />} tint={colors.orange}>
        <FuturesChart />
      </Card>
      <p className="caption">Select a patient on the left to see what was captured and how the episode ends.</p>
    </div>
  )
}
