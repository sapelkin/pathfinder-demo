import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Textarea } from '@fluentui/react-components'
import { MicFilled, PulseRegular, PersonRegular, StethoscopeRegular, LightbulbRegular, CheckmarkCircleFilled, HourglassRegular, ShieldCheckmarkRegular, ChatFilled, ArrowDownloadRegular, TrayItemAddRegular, LockClosedRegular, InfoRegular, TextQuoteRegular, SparkleRegular, ArrowTurnRightRegular, ShieldPersonRegular, CheckmarkCircleRegular, MicPulseRegular } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { ETA, IntakeResult, Vitals } from '../api/types'
import { useStore, useDisplayNow } from '../state/store'
import { ATSBadge, Card, Chip, FlowChips, IconLabel, LabeledRow, MessagePreview, Sheet, VitalsGrid } from '../components/ui'
import { ATS_NAMES, ATS_WITHIN, atsColor, colors } from '../lib/theme'
import { clockTime, round5 } from '../lib/clock'
import { Dictation, speechConfigured, SPEECH_OFF_STATUS } from '../speech/dictation'
import { TemplatePicker, useTemplates } from '../components/TemplatePicker'
import type { NoteTemplate } from '../api/types'

const EMPTY: IntakeResult = { form: { redFlags: [], mh: [], vitals: {}, redFlagLabels: [], mhLabels: [] }, hits: [], commands: [] }

const EXAMPLE = 'Tap the microphone and speak as you assess. For example: “72 year old man, chest pain for 2 hours, pulse 104, BP 150 over 90, sats 95 percent, pain 6 out of 10.” Then say “confirm category 2” and “send the message”.'

function isMentalHealth(r: IntakeResult): boolean {
  return r.form.mh.length > 0 || ['suicidal', 'self_harm', 'anxiety', 'psychosis', 'agitation', 'low_mood', 'crisis', 'intox'].includes(r.form.complaintKey ?? '')
}

/// TriageRules.safetyActions and .stream, mirrored for the Safety card.
function safetyActions(ats: number, r: IntakeResult): string[] {
  const out: string[] = []
  const f = r.form
  const mh = isMentalHealth(r)
  if (mh) {
    if (f.mh.includes('suicidal') || f.mh.includes('self_harm_act')) out.push('Keep in line of sight while waiting')
    if (ats <= 2) out.push('Alert the mental health team now; a staff member stays with the patient')
    else if (ats === 3) out.push('Do not leave in the waiting room without a support person; alert the mental health team')
    else if (ats === 4) out.push('Regular observation while waiting; discuss with the mental health team')
    else out.push('Routine waiting-room checks')
    out.push('If under Mental Health Act forms or in police custody, consider escalation')
  }
  if (ats <= 2 && !mh) out.push('Notify the medical officer now')
  if ((f.age ?? 0) >= 65 && (f.complaintKey === 'fall' || f.complaintKey === 'confusion')) out.push('Falls and delirium screen; check for a carer or aged-care contact')
  out.push('Offer an Aboriginal Liaison Officer if the patient identifies as Aboriginal')
  return out
}
function stream(ats: number, r: IntakeResult): string {
  if (isMentalHealth(r)) return ats <= 3 ? 'Mental health team review' : 'Mental health liaison, then main ED'
  if (ats <= 2) return 'Resuscitation or acute area'
  if (ats === 3) return 'Main ED'
  if (ats === 4) return r.form.complaintKey === 'limb' || r.form.complaintKey === 'laceration' ? 'Fast track' : 'Main ED'
  return 'Fast track, or redirect to an urgent care clinic'
}

const ARRIVAL_SHORT: Record<string, string> = {
  'By car': 'by car', 'Walked in': 'on foot', 'By bus or train': 'by bus', 'By taxi': 'by taxi', 'By ambulance': 'by ambulance', 'With police': 'with police',
}

/// The field cards of still 02_speech: one per thing heard, coloured by what it is.
function FieldCards({ r }: { r: IntakeResult }) {
  const f = r.form
  const v = f.vitals
  const rec = r.record
  const cells: { label: string; value?: string; tone: 'blue' | 'green' | 'orange' | 'purple' }[] = [
    { label: 'Known record', value: rec ? `${rec.priorVisits} visits${rec.daysSinceLast != null ? ` · last ${rec.daysSinceLast} days ago` : ''}` : f.name ? 'New patient' : undefined, tone: 'green' },
    { label: 'Age', value: f.age != null ? String(f.age) : undefined, tone: 'blue' },
    { label: 'Sex', value: f.sex ? (f.sex === 'F' ? 'Female' : 'Male') : undefined, tone: 'blue' },
    { label: 'Problem', value: f.complaint, tone: 'blue' },
    { label: 'Duration', value: f.duration, tone: 'blue' },
    ...(f.redFlagLabels.length > 0
      ? f.redFlagLabels.map((l) => ({ label: 'Red flag', value: l, tone: 'orange' as const }))
      : [{ label: 'Red flag', value: undefined, tone: 'orange' as const }]),
    { label: 'Arrival', value: f.arrivalMode, tone: 'blue' },
    { label: 'Pulse', value: v.pulse != null ? String(v.pulse) : undefined, tone: 'blue' },
    { label: 'Blood pressure', value: v.systolic != null ? `${v.systolic}/${v.diastolic ?? '–'}` : undefined, tone: 'blue' },
    { label: 'SpO₂', value: v.spo2 != null ? `${v.spo2}%` : undefined, tone: 'blue' },
    { label: 'Pain', value: v.pain != null ? `${v.pain} / 10` : undefined, tone: 'blue' },
    ...(v.resp != null ? [{ label: 'Resp rate', value: String(v.resp), tone: 'blue' as const }] : []),
    ...(v.temp != null ? [{ label: 'Temperature', value: `${v.temp.toFixed(1)} °C`, tone: 'blue' as const }] : []),
    ...f.mhLabels.map((l) => ({ label: 'Mental health', value: l, tone: 'purple' as const })),
  ]
  return (
    <div className="field-grid" aria-label="Fields heard">
      {cells.map((c, i) => (
        <div key={`${c.label}-${i}`} className={`field ${c.value ? `field-${c.tone}` : 'field-empty'}`}>
          <div className="field-label">{c.label}</div>
          <div className="field-value">{c.value ?? 'not heard yet'}</div>
        </div>
      ))}
    </div>
  )
}

export function IntakeSheet() {
  const { state, nav, setShowIntake, run } = useStore()
  const displayNow = useDisplayNow()
  const open = nav.showIntake
  const [transcript, setTranscript] = useState('')
  const [typed, setTyped] = useState('')
  const [showTyping, setShowTyping] = useState(false)
  const [result, setResult] = useState<IntakeResult>(EMPTY)
  const [monitor, setMonitor] = useState<Vitals | undefined>(undefined)
  const [confirmed, setConfirmed] = useState<number | null>(null)
  const [eta, setEta] = useState<ETA | null>(null)
  const [messageSent, setMessageSent] = useState(false)
  const [showMessage, setShowMessage] = useState(false)
  const [status, setStatus] = useState('')
  const [listening, setListening] = useState(false)
  const [startedAt, setStartedAt] = useState(() => Date.now())
  const [seconds, setSeconds] = useState(0)
  const [busy, setBusy] = useState(false)
  const commandsRun = useRef(0)
  const dictation = useRef<Dictation | null>(null)
  const recordLookedUp = useRef(false)
  const debounce = useRef<number | null>(null)
  const triageRef = useRef<HTMLDivElement>(null)
  const etaRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const templates = useTemplates(open)
  const [undo, setUndo] = useState<{ previous: string; title: string } | null>(null)
  const undoTimer = useRef<number | null>(null)

  /// A template replaces whatever was typed (with a one-click Undo for 10 s), parses as usual and hands focus back.
  const pickTemplate = (t: NoteTemplate) => {
    if (undoTimer.current) window.clearTimeout(undoTimer.current)
    const previous = typed
    setTyped(t.text)
    setShowTyping(true)
    setUndo(previous.trim() ? { previous, title: t.title } : null)
    if (previous.trim()) undoTimer.current = window.setTimeout(() => setUndo(null), 10000)
    window.setTimeout(() => { const el = textareaRef.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length) } }, 50)
  }
  const undoTemplate = () => {
    if (!undo) return
    setTyped(undo.previous)
    setUndo(null)
    if (undoTimer.current) window.clearTimeout(undoTimer.current)
    window.setTimeout(() => textareaRef.current?.focus(), 50)
  }

  const demo = state?.demo?.running ? state.demo : null
  const demoIntake = demo?.intake ?? null
  const scripted = Boolean(demo && (demoIntake?.open || demo.transcriptSoFar != null))
  const scriptedListening = Boolean(scripted && demo?.listening)
  const edName = state?.ed.name ?? 'the ED'

  const reset = useCallback(() => {
    setTranscript(''); setTyped(''); setShowTyping(false); setResult(EMPTY); setMonitor(undefined); setConfirmed(null)
    setEta(null); setMessageSent(false); setShowMessage(false); setStatus(speechConfigured ? '' : SPEECH_OFF_STATUS); setListening(false)
    setStartedAt(Date.now()); setSeconds(0); commandsRun.current = 0; recordLookedUp.current = false
    setUndo(null)
  }, [])

  useEffect(() => { if (open) reset() }, [open, reset])

  useEffect(() => {
    if (!open) return
    const id = window.setInterval(() => setSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => window.clearInterval(id)
  }, [open, startedAt])

  // The guided demo dictates through the same path as live dictation.
  useEffect(() => {
    if (scripted && demo?.transcriptSoFar != null) setTranscript(demo.transcriptSoFar)
  }, [scripted, demo?.transcriptSoFar])
  const dConfirmed = demoIntake?.confirmed ?? null
  const dEta = demoIntake?.eta ?? null
  const dSent = demoIntake?.messageSent ?? false
  const dShow = demoIntake?.showMessage ?? false
  useEffect(() => {
    if (!scripted || !demoIntake) return
    setConfirmed(dConfirmed)
    if (dEta) setEta(dEta)
    setMessageSent(dSent)
    setShowMessage(dShow)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scripted, dConfirmed, dEta?.rangeText, dSent, dShow])

  const confirmATS = useCallback(async (a: number) => {
    setConfirmed(a)
    try {
      const r = await api.eta(a)
      setEta(r.eta)
    } catch { setEta(null) }
  }, [])

  const sendMessage = useCallback(() => {
    setMessageSent(true)
    setShowMessage(true)
  }, [])

  const submit = useCallback(async (kind: 'finish' | 'redirect', ats: number | null) => {
    if (busy) return
    setBusy(true)
    dictation.current?.stop()
    const body = { transcript, typed, confirmed: ats ?? undefined, messageSent, startedAt: new Date(startedAt).toISOString(), monitorVitals: monitor }
    const s = await run(() => (kind === 'finish' ? api.intakeFinish(body) : api.intakeRedirect(body)))
    setBusy(false)
    if (s) setShowIntake(false)
  }, [busy, transcript, typed, messageSent, startedAt, monitor, run, setShowIntake])

  const suggested = result.suggested ?? null
  const handlers = useRef({ confirmATS, sendMessage, submit, confirmed, suggested, scripted })
  handlers.current = { confirmATS, sendMessage, submit, confirmed, suggested, scripted }

  // POST /parse on every change, 300 ms debounced; voice commands run once each, in the order spoken.
  useEffect(() => {
    if (!open) return
    if (!transcript && !typed && !monitor) { setResult(EMPTY); return }
    if (debounce.current) window.clearTimeout(debounce.current)
    debounce.current = window.setTimeout(async () => {
      try {
        const r = await api.parse({ transcript, typed, monitorVitals: monitor, recordLookedUp: recordLookedUp.current })
        if (r.record) recordLookedUp.current = true
        setResult(r)
        const cmds = r.commands ?? []
        if (cmds.length > commandsRun.current) {
          const fresh = cmds.slice(commandsRun.current)
          commandsRun.current = cmds.length
          const h = handlers.current
          for (const c of fresh) {
            if (c.startsWith('confirm:')) await h.confirmATS(Number(c.split(':')[1]))
            else if (c === 'send') h.sendMessage()
            else if (c === 'fromMonitor') setMonitor(r.monitorVitals ?? { pulse: 104, systolic: 150, diastolic: 90, spo2: 95, resp: 20, temp: 36.9, gcs: 15 })
            else if (c === 'finish') { if (!h.scripted) void h.submit('finish', handlers.current.confirmed ?? r.suggested ?? null) }
            else if (c === 'redirect') { if (!h.scripted) void h.submit('redirect', handlers.current.confirmed ?? r.suggested ?? null) }
          }
        }
      } catch (e) {
        setStatus(`Parser unavailable: ${e instanceof Error ? e.message : String(e)}`)
      }
    }, 300)
    return () => { if (debounce.current) window.clearTimeout(debounce.current) }
  }, [open, transcript, typed, monitor])

  useEffect(() => { if (suggested != null) triageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [suggested])
  useEffect(() => { if (confirmed != null) etaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [confirmed])

  const toggleListening = () => {
    if (!dictation.current) {
      const d = new Dictation()
      d.onText = (t) => setTranscript(t)
      d.onStatus = (s) => setStatus(s)
      d.onListening = (l) => setListening(l)
      dictation.current = d
    }
    dictation.current.toggle(transcript)
  }
  useEffect(() => () => dictation.current?.stop(), [])

  const isListening = listening || scriptedListening
  const f = result.form
  const rec = result.record
  const shown = confirmed ?? suggested ?? 3
  const first = (rec?.name ?? f.name ?? '').split(' ')[0]
  const template = state?.intakeMessageTemplate ?? "Hi {first}, you're checked in at {ed}. Expected time to be seen: {eta}. We'll text you if that changes. If you feel worse, tell the triage nurse straight away. If you decide to leave, please tell us first."
  const message = useMemo(() => {
    const hello = first ? `Hi ${first}` : 'Hi'
    return template.replace(/Hi \{first\}/, hello).replace('{first}', first).replace('{eta}', eta?.rangeText ?? 'soon').replace('{ed}', edName)
  }, [template, first, eta, edName])

  const close = () => { dictation.current?.stop(); setShowIntake(false) }

  const captureCards = (
    <>
      <Card title={isListening ? 'Listening' : 'Triage note'} icon={isListening ? <MicPulseRegular /> : <TextQuoteRegular />} tint={isListening ? colors.orange : colors.secondary}>
        {!transcript && !typed ? <p className="subhead secondary">{EXAMPLE}</p> : <p className="transcript">{transcript}</p>}
        {templates && templates.length > 0 && !scripted && <TemplatePicker templates={templates} onPick={pickTemplate} />}
        {showTyping || typed ? (
          <Textarea ref={textareaRef} value={typed} onChange={(_e, d) => setTyped(d.value)} placeholder="Type instead" resize="vertical" aria-label="Type the triage note" />
        ) : !isListening ? (
          <button type="button" className="link-button" style={{ fontSize: 12.5 }} onClick={() => setShowTyping(true)}>Type instead</button>
        ) : null}
        {undo && (
          <div className="undo-line caption" role="status">
            <span>Replaced your note with “{undo.title}”.</span>
            <Button size="small" appearance="secondary" onClick={undoTemplate}>Undo</Button>
          </div>
        )}
        {status && <IconLabel icon={speechConfigured ? <InfoRegular /> : <LockClosedRegular />} size="caption" color={colors.secondary}>{status}</IconLabel>}
      </Card>
      <Card title="Patient" icon={<PersonRegular />} tint={colors.accent}>
        <div className="hstack-nowrap">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="headline" style={{ color: !f.name && !rec ? colors.secondary : colors.text }}>{f.name ?? rec?.name ?? 'Name not given yet'}</div>
            <div className="subhead secondary">{[f.age != null ? String(f.age) : null, f.sex ? (f.sex === 'F' ? 'female' : 'male') : null, f.arrivalMode ? ARRIVAL_SHORT[f.arrivalMode] ?? f.arrivalMode : null].filter(Boolean).join(' · ')}</div>
          </div>
          {(f.age ?? 0) >= 65 && <Chip text="65+" color={colors.green} />}
          {isMentalHealth(result) && <Chip text="MH" color={colors.purple} />}
        </div>
        {rec ? (
          <>
            <hr style={{ border: 0, borderTop: `1px solid ${colors.fill}`, margin: 0 }} />
            <IconLabel icon={<CheckmarkCircleFilled />} color={colors.green} weight={600}>Known record found</IconLabel>
            <div className="stats">
              <div><div className="subhead" style={{ fontWeight: 700 }}>{rec.priorVisits}</div><div className="caption2">ED visits this year</div></div>
              {rec.daysSinceLast != null && <div><div className="subhead" style={{ fontWeight: 700 }}>{rec.daysSinceLast} d</div><div className="caption2">since last visit</div></div>}
              {rec.lastOutcome && <div><div className="subhead" style={{ fontWeight: 700 }}>{rec.lastOutcome}</div><div className="caption2">last time</div></div>}
            </div>
            <p className="caption">{rec.note}</p>
          </>
        ) : f.name ? <p className="caption">No earlier record found: new patient.</p> : null}
      </Card>
      <FieldCards r={result} />
      <Card title="Immediate: observations" icon={<PulseRegular />} tint={colors.accent}>
        <VitalsGrid vitals={f.vitals} />
        <button type="button" className="link-button" onClick={() => setMonitor({ pulse: 104, systolic: 150, diastolic: 90, spo2: 95, resp: 20, temp: 36.9, gcs: 15 })}>
          <ArrowDownloadRegular /> Take observations from the monitor
        </button>
      </Card>
    </>
  )

  const answerCards = (
    <>
      <Card title="Symptoms" icon={<StethoscopeRegular />} tint={colors.accent}>
        <div className="hstack">
          <span className="headline" style={{ color: f.complaint ? colors.text : colors.secondary }}>{f.complaint ?? 'Presenting problem not heard yet'}</span>
          {f.duration && <span className="secondary">for {f.duration}</span>}
        </div>
        {f.redFlagLabels.length > 0 && <FlowChips items={[...f.redFlagLabels].sort()} color={colors.orange} />}
        {f.mhLabels.length > 0 && <FlowChips items={[...f.mhLabels].sort()} color={colors.purple} />}
      </Card>
      {(suggested != null || confirmed != null) && (
        <div ref={triageRef}>
          <Card title={confirmed == null ? 'Suggested triage category' : 'Triage category confirmed'} icon={confirmed == null ? <LightbulbRegular /> : <CheckmarkCircleFilled />} tint={confirmed == null ? colors.accent : colors.green}>
            <div className="hstack-nowrap" style={{ gap: 14 }}>
              <ATSBadge ats={shown} size={56} />
              <div>
                <div className="title3">{ATS_NAMES[shown - 1]}</div>
                <div className="secondary">Seen {ATS_WITHIN[shown - 1].toLowerCase()}</div>
              </div>
            </div>
            {result.hits.slice(0, 4).map((h) => (
              <div className="hit" key={`${h.ats}-${h.text}`}>
                <ATSBadge ats={h.ats} size={20} />
                <div>
                  <div className="subhead">{h.text}</div>
                  <div className="caption2" style={{ color: h.source === 'Demo threshold' ? colors.orange : colors.secondary }}>{h.source}</div>
                </div>
              </div>
            ))}
            <div className="ats-buttons" role="group" aria-label="Confirm the triage category">
              {[1, 2, 3, 4, 5].map((a) => {
                const sel = confirmed === a
                const sug = suggested === a && confirmed == null
                return (
                  <button key={a} type="button" className="ats-button" aria-pressed={sel} aria-label={`Confirm category ${a}${sug ? ' (suggested)' : ''}`}
                    style={{ background: sel ? atsColor(a) : `${atsColor(a)}1f`, color: sel ? '#fff' : atsColor(a), borderColor: sug ? atsColor(a) : 'transparent' }}
                    onClick={() => void confirmATS(a)}>{a}</button>
                )
              })}
            </div>
            <IconLabel icon={<ShieldPersonRegular />} size="caption" color={colors.secondary}>The nurse decides. Rules follow the published ATS descriptors; items marked “demo threshold” are not yet clinically validated.</IconLabel>
          </Card>
        </div>
      )}
      {confirmed != null && (
        <div ref={etaRef} className="stack">
          <Card title="Expected time to be seen" icon={<HourglassRegular />} tint={colors.accent}>
            {confirmed === 1 ? (
              <div className="eta-big" style={{ fontSize: 30 }}>Now: resuscitation team</div>
            ) : eta ? (
              <>
                <div className="eta-big">{eta.rangeText}</div>
                <p className="subhead secondary">Most likely about {round5(eta.p50)} min · {eta.ahead} {eta.ahead === 1 ? 'person' : 'people'} ahead with the same or more urgent need</p>
                <p className="caption">In 8 of 10 simulated futures of this waiting room the patient is seen within this range. New arrivals follow the weekly pattern for a Saturday afternoon.</p>
              </>
            ) : <p className="subhead secondary">Working out the expected time…</p>}
            <Button appearance="primary" icon={messageSent ? <CheckmarkCircleFilled /> : <ChatFilled />} disabled={messageSent} onClick={sendMessage}
              style={messageSent ? { background: colors.green, color: '#fff' } : undefined}>
              {messageSent ? `Sent by text at ${clockTime(displayNow)}` : 'Send by text message'}
            </Button>
            {messageSent && <button type="button" className="link-button" style={{ fontSize: 12.5 }} onClick={() => setShowMessage(true)}>Show the message</button>}
          </Card>
          <Card title="Safety and stream" icon={<ShieldCheckmarkRegular />} tint={colors.accent}>
            <LabeledRow label="Stream" value={stream(confirmed, result)} />
            {safetyActions(confirmed, result).map((s) => <IconLabel key={s} icon={<CheckmarkCircleRegular />}>{s}</IconLabel>)}
            {confirmed >= 4 && (
              <div><Button icon={<ArrowTurnRightRegular />} disabled={busy} onClick={() => void submit('redirect', confirmed)}>Redirect to an urgent care clinic instead</Button></div>
            )}
          </Card>
          <div className="actions">
            <Button appearance="primary" icon={<ChatFilled />} disabled={messageSent} onClick={sendMessage}>Send the message</Button>
            <Button appearance="primary" icon={<TrayItemAddRegular />} disabled={busy} onClick={() => void submit('finish', confirmed)}>Add to the waiting room</Button>
            <Button icon={<ArrowTurnRightRegular />} disabled={busy} onClick={() => void submit('redirect', confirmed)}>Redirect</Button>
            <Button icon={<ArrowDownloadRegular />} onClick={() => setMonitor({ pulse: 104, systolic: 150, diastolic: 90, spo2: 95, resp: 20, temp: 36.9, gcs: 15 })}>Obs from the monitor</Button>
            <Button appearance="subtle" onClick={close}>Cancel</Button>
          </div>
        </div>
      )}
      {suggested == null && confirmed == null && (
        <Card title="As the nurse speaks" icon={<SparkleRegular />} tint={colors.secondary}>
          <p className="subhead secondary">The category and its published descriptor appear here as soon as the rules match something; the expected time follows the confirmation.</p>
        </Card>
      )}
    </>
  )

  const micBar = (
    <div className="mic-bar">
      <div className="capture-time">
        <div className="headline">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</div>
        <div className="caption2">capture time</div>
      </div>
      <button type="button" className={`mic-button ${isListening ? 'listening' : ''}`} onClick={toggleListening}
        aria-label={isListening ? 'Stop listening' : speechConfigured ? 'Start dictation' : 'Dictation is off; type instead'}
        title={speechConfigured ? undefined : SPEECH_OFF_STATUS}>
        {isListening ? <MicPulseRegular /> : <MicFilled />}
      </button>
      <button type="button" className="add-button" disabled={confirmed == null || busy} onClick={() => void submit('finish', confirmed)}>
        <TrayItemAddRegular />
        <span>Add</span>
      </button>
    </div>
  )

  return (
    <Sheet open={open} onClose={close} title="New arrival" wide footer={micBar}
      leading={<Button appearance="subtle" onClick={close}>Cancel</Button>}
      trailing={<Button appearance="primary" disabled={confirmed == null || busy} onClick={() => void submit('finish', confirmed)}>Add</Button>}>
      <div className="intake-layout">
        <div className="stack">{captureCards}</div>
        <div className="stack">{answerCards}</div>
      </div>
      <div style={{ height: 24 }} />
      <MessagePreview open={showMessage} onClose={() => setShowMessage(false)} to={rec?.name ?? f.name ?? 'the patient'} text={message} sentAt={clockTime(displayNow)} />
    </Sheet>
  )
}
