import { speechConfigured } from '../speech/dictation'
import { useEffect, useRef, useState } from 'react'
import { Button, Switch, Dropdown, Option } from '@fluentui/react-components'
import { PlayCircleRegular, StopFilled, ArrowCounterclockwiseRegular, HexagonRegular, ArrowDownloadRegular, ArrowUploadRegular, CheckmarkCircleFilled, BuildingFilled } from '@fluentui/react-icons'
import { IS_LOCAL } from '../api/mode'
import { clearStoredDocument, exportDocument, importDocument, getEngineStatus } from '../api/local'
import { api } from '../api/client'
import type { Deployment, Persona, HospitalsResponse } from '../api/types'
import { SPEEDS, useStore } from '../state/store'
import { IconLabel, LabeledRow, Row, Section, Sheet } from '../components/ui'
import { colors } from '../lib/theme'

export function Segmented<T extends string | number>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => <button key={String(o.value)} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>)}
    </div>
  )
}

export const DEPLOYMENTS: { value: Deployment; label: string }[] = [{ value: 'minimum', label: 'Minimum' }, { value: 'standard', label: 'Standard' }, { value: 'full', label: 'Full' }]

export function SettingsSheet() {
  const { state, nav, setShowSettings, setShowUnits, settings, run } = useStore()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [importNote, setImportNote] = useState<string>('')
  const [hospitals, setHospitals] = useState<HospitalsResponse | null>(null)
  const [hospitalsError, setHospitalsError] = useState<string | null>(null)
  const [hospitalNote, setHospitalNote] = useState<string>('')
  const [switching, setSwitching] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const open = nav.showSettings
  useEffect(() => { if (open) api.personas().then(setPersonas).catch(() => setPersonas([])) }, [open])
  useEffect(() => {
    if (!open) return
    setHospitalsError(null)
    api.hospitals().then(setHospitals).catch((e) => { setHospitals(null); setHospitalsError(e instanceof Error ? e.message : String(e)) })
  }, [open])
  if (!state) return null
  const close = () => setShowSettings(false)
  const demoRunning = Boolean(state.demo?.running)
  const personaLabel = state.personaChoice === 'random' ? 'Random each run' : personas.find((p) => p.id === state.personaChoice)?.label ?? state.persona.label
  return (
    <Sheet open={open} onClose={close} title="Settings" trailing={<Button appearance="primary" onClick={close}>Done</Button>}>
      <Section header="Hospital" footer={hospitals ? (
        <>WA Health, Emergency department live activity, {hospitals.takenText}. The page says the figures are a guide only; the average is for triage category 4. <a href={hospitals.url} target="_blank" rel="noreferrer">{hospitals.url}</a></>
      ) : hospitalsError ? `The hospital list is not available on this API yet (${hospitalsError}).` : 'Loading the published numbers…'}>
        {hospitals?.hospitals.map((h) => {
          const current = (state.hospital?.id ?? 'demo') === h.id
          return (
            <Row key={h.id} chevron={false} selected={current} ariaLabel={`${h.name}: ${h.waiting} waiting, ${h.inEd} in ED, category 4 average ${h.t4AvgWaitMin} minutes`} onClick={() => {
              if (current || switching) return
              setSwitching(h.id)
              setHospitalNote('')
              void run(() => api.settings({ hospitalId: h.id })).then((s) => {
                setSwitching(null)
                if (s) setHospitalNote(h.id === 'demo' ? `Back to ${h.name}: the simulated afternoon.` : `Rebuilt the waiting room for ${h.name} from WA Health's published numbers`)
              })
            }}>
              <div className="hospital-row">
                <span className="hospital-check">{current ? <CheckmarkCircleFilled /> : <BuildingFilled style={{ color: colors.secondary, opacity: 0.6 }} />}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="subhead" style={{ fontWeight: current ? 700 : 500 }}>{h.name}{switching === h.id ? ' · rebuilding…' : ''}</div>
                  <div className="caption">{h.id === 'demo' ? 'The simulated afternoon: Saturday 2:30 pm, calibrated to published WA figures' : `${h.waiting} waiting · ${h.inEd} in ED · cat-4 avg ${h.t4AvgWaitMin} min`}</div>
                </div>
              </div>
            </Row>
          )
        })}
        {hospitalNote && <Row><IconLabel icon={<CheckmarkCircleFilled />} color={colors.green} size="caption">{hospitalNote}</IconLabel></Row>}
      </Section>

      <Section header="Demo" footer="The guided demo takes about 80 seconds and is the same every time, so it can be recorded.">
        <Row onClick={() => { close(); void run(() => api.demoStart(false)) }} chevron={false}>
          <IconLabel icon={<PlayCircleRegular />} color={colors.accent}>Play the guided demo</IconLabel>
        </Row>
        {demoRunning && (
          <Row onClick={() => void run(() => api.demoStop())} chevron={false}>
            <IconLabel icon={<StopFilled />} color={colors.red}>Stop the guided demo</IconLabel>
          </Row>
        )}
        <Row>
          <div className="labeled">
            <span className="labeled-label">Demo patient</span>
            <Dropdown aria-label="Demo patient" value={personaLabel} selectedOptions={[state.personaChoice]} onOptionSelect={(_e, d) => { if (d.optionValue) void settings({ personaChoice: d.optionValue }) }} style={{ minWidth: 180 }}>
              <Option value="random" text="Random each run">Random each run</Option>
              {personas.map((p) => <Option key={p.id} value={p.id} text={p.label}>{p.label}</Option>)}
            </Dropdown>
          </div>
        </Row>
        {state.personaChoice === 'random' && <Row><span className="caption">Next run: {state.persona.label}. Two devices side by side tell two different stories.</span></Row>}
        <Row><Switch label="Captions during the demo" labelPosition="before" checked={state.showCaptions} onChange={(_e, d) => void settings({ showCaptions: d.checked })} style={{ width: '100%', justifyContent: 'space-between' }} /></Row>
        <Row onClick={() => { void run(() => api.reset(false)); close() }} chevron={false}>
          <IconLabel icon={<ArrowCounterclockwiseRegular />} color={colors.accent}>Reset to Saturday 2:30 pm</IconLabel>
        </Row>
      </Section>

      {IS_LOCAL && (
        <Section header="Your data" footer={`This build runs the Python engine in your browser (${getEngineStatus().engine ? `engine ${getEngineStatus().engine}` : 'Pyodide'}); the demo state is saved in this browser only. Export it to move it to another device or to keep it; import replaces what is here.`}>
          <Row onClick={() => { void exportDocument().then((text) => { const blob = new Blob([text], { type: 'application/json' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `pathfinder-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`; a.click(); URL.revokeObjectURL(a.href) }) }} chevron={false}>
            <IconLabel icon={<ArrowDownloadRegular />} color={colors.accent}>Export data (JSON)</IconLabel>
          </Row>
          <Row onClick={() => fileInput.current?.click()} chevron={false}>
            <div>
              <IconLabel icon={<ArrowUploadRegular />} color={colors.accent}>Import data (JSON)</IconLabel>
              {importNote && <div className="caption" style={{ marginTop: 4 }}>{importNote}</div>}
              <input ref={fileInput} type="file" accept="application/json,.json" style={{ display: 'none' }} aria-label="Import data (JSON)" onChange={(ev) => {
                const f = ev.target.files?.[0]
                ev.target.value = ''
                if (!f) return
                void f.text().then(async (text) => {
                  const r = await importDocument(text)
                  setImportNote(r.ok ? `Imported ${f.name}.` : `Could not import ${f.name}: ${r.error ?? 'not a Pathfinder document'}`)
                  if (r.ok) await run(() => api.state())
                })
              }} />
            </div>
          </Row>
          <Row onClick={() => { clearStoredDocument(); void run(() => api.reset(false)).then(() => clearStoredDocument()) }} chevron={false}>
            <IconLabel icon={<ArrowCounterclockwiseRegular />} color={colors.red}>Reset to the demo</IconLabel>
          </Row>
        </Section>
      )}

      <Section header="Clock">
        <Row>
          <div className="stack" style={{ gap: 8 }}>
            <span>Speed</span>
            <Segmented label="Speed" options={SPEEDS.map((s) => ({ value: s, label: s === 1 ? 'Real' : `×${s}` }))} value={state.speed} onChange={(s) => void settings({ speed: s })} />
          </div>
        </Row>
        <Row><Switch label="Running" labelPosition="before" checked={state.running} onChange={(_e, d) => void settings({ running: d.checked })} style={{ width: '100%', justifyContent: 'space-between' }} /></Row>
      </Section>

      <Section header="Voice" footer="Dictation uses Azure AI Speech in Australian English when a speech key is configured for this build. Audio goes to the speech service, so it should only ever be used with demo data.">
        <Row><Switch label="Spoken confirmations" labelPosition="before" checked={state.speakFeedback} onChange={(_e, d) => void settings({ speakFeedback: d.checked })} style={{ width: '100%', justifyContent: 'space-between' }} /></Row>
        <Row><LabeledRow label="Dictation" value={speechConfigured ? `Azure AI Speech, ${import.meta.env.VITE_SPEECH_REGION || 'australiaeast'}` : 'Off: keyboard only'} /></Row>
      </Section>

      <Section header="Architecture" footer="Everything is a unit. The minimum runs on public data with no hospital integration; each further unit plugs into one message standard.">
        <Row>
          <div className="stack" style={{ gap: 8 }}>
            <span>Deployment</span>
            <Segmented label="Deployment" options={DEPLOYMENTS} value={state.deployment} onChange={(d) => void settings({ deployment: d })} />
          </div>
        </Row>
        <Row onClick={() => { close(); setShowUnits(true) }}>
          <IconLabel icon={<HexagonRegular />} color={colors.accent}>The units, and what each plugs into</IconLabel>
        </Row>
      </Section>

      <Section header="Data">
        <Row><LabeledRow label="Demo ED volume" value="70,000 a year" /></Row>
        <Row><span className="caption">A mid-sized metropolitan ED, assumed 70,000 presentations a year; WA's 24 public EDs saw 1.03 million in 2024-25</span></Row>
        <Row><LabeledRow label="Calibrated median wait" value="38 min" /></Row>
        <Row><LabeledRow label="Calibrated did-not-wait rate" value="4.4%" /></Row>
        <Row><span className="caption">Public edition: published WA and national figures plus stated assumptions (see PUBLIC_FIGURES.md). No hackathon Data. The demo ED and its patients are fictional.</span></Row>
      </Section>

      <Section header="Where the numbers come from">
        <Row>
          <p className="caption">
            Expected times come from 100 simulated futures of this waiting room, re-run every 10 simulated minutes; the queue is calibrated to a median wait of 38 min and a did-not-wait rate of 4.4% over eight simulated weeks.
            Triage suggestions follow the published ATS descriptors (ACEM G24, WA triage procedure); items marked “demo threshold” are not yet clinically validated.
            Follow-through tiers follow the WACHS did-not-wait policy; return risks are looked up in a table built from published studies, never modelled.
            The right door is a ring search over 866 m hexagons from home, then Dijkstra travel times over an invented road and bus network.
          </p>
        </Row>
      </Section>
    </Sheet>
  )
}
