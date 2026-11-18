import { useEffect, useMemo, useState } from 'react'
import { Button } from '@fluentui/react-components'
import { CheckmarkCircleFilled, HexagonRegular } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { Deployment, Unit } from '../api/types'
import { useStore } from '../state/store'
import { Chip, Row, Section, Sheet } from '../components/ui'
import { colors, unitKindColor } from '../lib/theme'
import { DEPLOYMENTS, Segmented } from './Settings'

const KINDS: Unit['kind'][] = ['connector', 'store', 'model', 'function', 'surface']
const RANK: Record<Deployment, number> = { minimum: 0, standard: 1, full: 2 }
const SUMMARY: Record<Deployment, string> = {
  minimum: "Seven units, one interface: the ED system's own messages. Everyone who consents knows their wait; no new screen for staff.",
  standard: 'Adds the front door: voice intake, the triage rules, history, the nurse app and an audit log.',
  full: 'Adds follow-through and the right door: alerts, the directory, travel times, the ranker, the search, the worklist, the six measures and write-back.',
}
const LAYER_TITLE: Record<Deployment, string> = { minimum: 'The foundation: minimum, 7 units', standard: 'Second layer: standard, adds 6', full: 'Third layer: full, adds 13' }
const LAYER_BLURB: Record<Deployment, string> = {
  minimum: "One interface, the ED system's own messages. Every patient who consents knows their wait; no new screen for staff.",
  standard: 'The front door: the nurse speaks, the rules suggest, the nurse confirms, the message goes.',
  full: 'Follow-through and the right door, the six measures, and write-back to the record.',
}
function singular(k: Unit['kind']): string { return k === 'surface' ? 'screen' : k }

/// The architecture as a stack: the foundation first, then each layer added on top of it. Every unit shows its kind,
/// what it plugs into and what it gives. Changing the deployment changes what the app shows.
export function UnitsSheet() {
  const { state, nav, setShowUnits, settings } = useStore()
  const [units, setUnits] = useState<Unit[]>([])
  const open = nav.showUnits
  useEffect(() => { if (open) api.units().then(setUnits).catch(() => setUnits([])) }, [open])
  const deployment = state?.deployment ?? 'full'
  const on = useMemo(() => new Set(units.filter((u) => RANK[u.tier] <= RANK[deployment]).map((u) => u.id)), [units, deployment])
  if (!state) return null
  return (
    <Sheet open={open} onClose={() => setShowUnits(false)} title="Units" trailing={<Button appearance="primary" onClick={() => setShowUnits(false)}>Done</Button>}>
      <Section footer="Different hospitals run different systems: EDIS at metro sites, the webPAS ED module in the country, vendors' own systems at contracted sites, the state EMR from 2028. Each connector speaks one message standard, never one hospital's system. Pathfinder sits beside them and replaces nothing.">
        <Row><Segmented label="Deployment" options={DEPLOYMENTS} value={deployment} onChange={(d) => void settings({ deployment: d })} /></Row>
        <Row>
          <div>
            <div className="title3" style={{ color: colors.accent }}>{on.size} of {units.length} units</div>
            <div className="caption">{SUMMARY[deployment]}</div>
          </div>
        </Row>
        <Row>
          <div className="kind-legend">
            {KINDS.map((k) => <span key={k}><span className="tier-dot" style={{ background: unitKindColor(k) }} />{singular(k)}</span>)}
          </div>
        </Row>
      </Section>
      {(['minimum', 'standard', 'full'] as Deployment[]).map((tier) => {
        const layer = units.filter((u) => u.tier === tier).sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind))
        return (
          <Section key={tier} header={LAYER_TITLE[tier]} footer={LAYER_BLURB[tier]}>
            {layer.length === 0 && <Row><span className="caption">Loading the catalogue…</span></Row>}
            {layer.map((u) => {
              const isOn = on.has(u.id)
              return (
                <Row key={u.id}>
                  <div className="unit-row">
                    <span style={{ color: isOn ? unitKindColor(u.kind) : 'rgba(107,111,118,0.4)', display: 'inline-flex', width: 26, justifyContent: 'center' }}>{isOn ? <CheckmarkCircleFilled /> : <HexagonRegular />}</span>
                    <div>
                      <div className="hstack">
                        <span className="subhead" style={{ fontWeight: 600, color: isOn ? colors.text : colors.secondary }}>{u.name}</span>
                        <Chip text={singular(u.kind)} color={unitKindColor(u.kind)} />
                      </div>
                      <div className="caption">{u.plugsInto}</div>
                      <div className="caption" style={{ color: isOn ? colors.green : colors.secondary }}>{u.gives}</div>
                    </div>
                  </div>
                </Row>
              )
            })}
          </Section>
        )
      })}
    </Sheet>
  )
}
