import { useEffect, useMemo, useRef, useState } from 'react'
import { Menu, MenuTrigger, MenuPopover, MenuList, MenuItem, Button } from '@fluentui/react-components'
import { ChevronUpDownRegular, ArrowTurnRightRegular, CalendarRegular, PersonWalkingRegular, VehicleBusFilled, VehicleCarFilled, HexagonRegular, SearchRegular, CheckmarkCircleRegular, MathFormulaRegular, ShieldCheckmarkRegular, HandRightFilled, ArrowCircleRightRegular, WarningFilled, BuildingFilled, BriefcaseMedicalFilled, StethoscopeRegular, PillFilled, BrainRegular, DrinkCoffeeFilled, VideoFilled, CallFilled, HomeFilled } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { Network, RightDoorResult, RightDoorOption, ServiceKind, TravelMode } from '../api/types'
import { useStore } from '../state/store'
import { Chip, CohortTag, IconLabel, Row, Section } from '../components/ui'
import { colors, TRAVEL_SHORT, TRAVEL_LABEL, atsColor, openFactor, travelFactor } from '../lib/theme'
import { hourOfWeek } from '../lib/clock'
import { HexMap } from './HexMap'

export function ServiceIcon({ kind }: { kind: ServiceKind }) {
  switch (kind) {
    case 'ed': return <BuildingFilled />
    case 'urgentCare': return <BriefcaseMedicalFilled />
    case 'gp': return <StethoscopeRegular />
    case 'pharmacy': return <PillFilled />
    case 'mentalHealth': return <BrainRegular />
    case 'safeHaven': return <DrinkCoffeeFilled />
    case 'virtualED': return <VideoFilled />
    case 'phone': return <CallFilled />
    case 'homeCare': return <HomeFilled />
  }
}
export function TravelIcon({ mode }: { mode: TravelMode }) {
  return mode === 'walk' ? <PersonWalkingRegular /> : mode === 'bus' ? <VehicleBusFilled /> : <VehicleCarFilled />
}

const MAX_REDIRECT: Record<TravelMode, number> = { walk: 30, bus: 45, car: 45 }
/// Average wait for a bus: half the headway, which depends on the day and hour (Pathfinder.busWait).
function busWait(t: number): number {
  const h = hourOfWeek(t), day = Math.floor(h / 24), hour = h % 24
  if (day < 5 && hour >= 7 && hour < 19) return 5
  if (day === 5 && hour >= 8 && hour < 19) return 7.5
  return 15
}

/// The right door next time. A ride-share style search from the person's home, ring by ring over the hexagon grid,
/// then travel time by the way they get around, opening hours and fit. Every location on the map is invented.
export function RightDoor() {
  const { state, nav, setRightDoorId } = useStore()
  const [plan, setPlan] = useState<RightDoorResult | null>(null)
  const [network, setNetwork] = useState<Network | null>(null)
  const [modeOverride, setModeOverride] = useState<TravelMode | null>(null)
  const [shownRings, setShownRings] = useState(0)
  const [settled, setSettled] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const animatedKey = useRef('')

  const candidates = state?.rightDoorCandidates ?? []
  const id = nav.rightDoorId ?? candidates[0]?.id ?? null
  const episode = id != null ? (state?.waiting.find((e) => e.id === id) ?? state?.followCases.find((e) => e.id === id)) : undefined
  const candidate = candidates.find((c) => c.id === id)
  const stage = episode?.stage ?? candidate?.stage ?? (plan && plan.episode.id === id ? plan.episode.stage : undefined)
  const purpose: 'redirectNow' | 'nextTime' = stage === 'waiting' ? 'redirectNow' : 'nextTime'
  const hour = state ? hourOfWeek(state.now) : 0
  const key = `${id}|${modeOverride ?? ''}|${purpose}|${hour}`

  useEffect(() => { api.network().then(setNetwork).catch(() => setNetwork(null)) }, [])
  useEffect(() => { setModeOverride(null) }, [id])

  // The build animation: rings spread out from home, then the routes settle.
  useEffect(() => {
    if (id == null) { setPlan(null); return }
    let cancelled = false
    const timers: number[] = []
    api.rightDoor(id, purpose, modeOverride ?? undefined).then((p) => {
      if (cancelled) return
      setError(null)
      setPlan(p)
      setSelected(null)
      const thisKey = `${id}|${p.mode}|${p.purpose}`
      const animate = animatedKey.current !== thisKey
      animatedKey.current = thisKey
      if (!animate) { setShownRings(p.search.rings.length); setSettled(true); return }
      setShownRings(0)
      setSettled(false)
      let t = 0
      for (let k = 1; k <= p.search.rings.length; k++) {
        t += k === 1 ? 400 : 240
        timers.push(window.setTimeout(() => setShownRings(k), t))
      }
      timers.push(window.setTimeout(() => setSettled(true), t + 350))
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true; timers.forEach((t) => window.clearTimeout(t)) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const e = plan?.episode ?? episode
  const mode: TravelMode = plan?.mode ?? modeOverride ?? e?.travel ?? 'car'
  const edFirst = plan ? plan.edFirst ?? (plan.purpose === 'nextTime' && plan.options.some((o) => o.pinned000)) : false
  const ranked = useMemo(() => plan ? plan.options.filter((o) => o.minutes != null && !(edFirst && o.service.kind === 'ed')) : [], [plan, edFirst])
  const ed = plan?.options.find((o) => o.service.kind === 'ed')
  const remote = plan ? (plan.remote.length > 0 ? plan.remote : plan.options.filter((o) => o.minutes == null)) : []
  const where = e?.homeSuburb || 'home'

  if (!state) return <div className="empty">Connecting…</div>
  if (!e) return <div className="page"><div className="empty">No one to plan for yet.</div></div>

  const travelText = (() => {
    if (modeOverride) return `${TRAVEL_SHORT[mode]}, changed by the nurse`
    switch (e.arrivalMode) {
      case 'By ambulance': case 'With police': return 'assumes a car or taxi next time'
      case 'By taxi': return 'by car or taxi, as they came'
      default: return `${TRAVEL_SHORT[mode]}, as they came`
    }
  })()
  const listTitle = purpose === 'redirectNow'
    ? `Open now, within ${MAX_REDIRECT[mode]} min ${TRAVEL_SHORT[mode]} of ${where}`
    : edFirst ? `For follow-up, from ${where} ${TRAVEL_SHORT[mode]}` : `Where to go next time, from ${where} ${TRAVEL_SHORT[mode]}`
  const routesToShow: RightDoorOption[] = (() => {
    if (!plan) return []
    if (selected) return plan.options.filter((o) => o.service.id === selected)
    const top = ranked.slice(0, 3)
    if (edFirst && ed) top.unshift(ed)
    return top
  })()
  const search = plan?.search
  const kMax = search ? search.rings.length - 1 : 0
  const needText = search?.needs.map((n) => n.toLowerCase()).join(', ') ?? ''
  const candidateCount = search ? search.rings.reduce((n, r) => n + r.found.length, 0) : 0

  return (
    <div className="page">
      <div className="split">
        <div>
          <Section>
            <Row>
              <div className="stack" style={{ gap: 8 }}>
                <Menu>
                  <MenuTrigger disableButtonEnhancement>
                    <button type="button" className="row-button" style={{ display: 'flex', width: '100%', alignItems: 'center', gap: 8, background: 'none', border: 0, padding: 0, cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit' }} aria-label="Choose a person to plan for">
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="hstack"><span className="headline">{e.name}</span><span className="secondary">{e.age}</span><CohortTag cohort={e.cohort} /></div>
                        <div className="subhead secondary">{e.complaint} · lives in {where} · came {e.arrivalModeShort}</div>
                      </div>
                      <ChevronUpDownRegular style={{ color: colors.secondary }} />
                    </button>
                  </MenuTrigger>
                  <MenuPopover>
                    <MenuList>
                      {candidates.slice(0, 40).map((c) => (
                        <MenuItem key={c.id} onClick={() => setRightDoorId(c.id)}>
                          {c.name}, {c.age}{c.homeSuburb ? ` · ${c.homeSuburb}` : ''}{c.arrivalModeShort ? ` · came ${c.arrivalModeShort}` : ''}{c.outcome ? ` · ${c.outcome}` : ''}
                        </MenuItem>
                      ))}
                    </MenuList>
                  </MenuPopover>
                </Menu>
                <div className="hstack">
                  <Chip text={purpose === 'redirectNow' ? 'Redirect now?' : 'Next time'} color={colors.accent} filled icon={purpose === 'redirectNow' ? <ArrowTurnRightRegular /> : <CalendarRegular />} />
                  <Menu>
                    <MenuTrigger disableButtonEnhancement>
                      <button type="button" className="chip chip-button" style={{ background: 'rgba(42,120,214,0.13)', color: colors.accent, border: 0, cursor: 'pointer' }} aria-label={`Travel ${travelText}. Change the way of travelling`}>
                        <TravelIcon mode={mode} /> {travelText} <ChevronUpDownRegular />
                      </button>
                    </MenuTrigger>
                    <MenuPopover>
                      <MenuList>
                        {(['car', 'bus', 'walk'] as TravelMode[]).map((m) => <MenuItem key={m} icon={<TravelIcon mode={m} />} onClick={() => setModeOverride(m)}>{TRAVEL_LABEL[m]}</MenuItem>)}
                        <MenuItem onClick={() => setModeOverride(null)}>As they came</MenuItem>
                      </MenuList>
                    </MenuPopover>
                  </Menu>
                </div>
              </div>
            </Row>
          </Section>
          <Section footer="Demo metro: every hospital, clinic, road and bus route is invented. Travel times come from the hexagon model, not a routing service.">
            {plan ? (
              <HexMap plan={plan} network={network} shownRings={shownRings} settled={settled} selected={selected} routes={routesToShow} firstName={e.name.split(' ')[0]} onSelect={(sid) => setSelected((s) => (s === sid ? null : sid))} />
            ) : (
              <div className="hexmap" role="img" aria-label="Map loading" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: colors.secondary }}>{error ? `Right door unavailable: ${error}` : 'Searching from home…'}</div>
            )}
            {plan && (
              <div className="row"><div className="map-legend">
                <span><span className="swatch" style={{ background: colors.orange }} /> home</span>
                <span><span className="swatch" style={{ background: '#6fa3e4' }} /> rings searched</span>
                <span><span className="swatch" style={{ background: colors.accent }} /> route</span>
                <span><span className="swatch" style={{ background: colors.green, borderRadius: '50%' }} /> open</span>
                <span><span className="swatch" style={{ background: '#9ea3ad', borderRadius: '50%' }} /> closed</span>
                <span><span className="swatch" style={{ background: atsColor(1), borderRadius: '50%' }} /> ED</span>
                <span style={{ marginLeft: 'auto' }}>ring {Math.min(shownRings, kMax)} of {kMax} · {search?.hexCount ?? 0} hexagons · {candidateCount} services found</span>
              </div></div>
            )}
          </Section>
        </div>
        <div>
          {plan && search && (
            <>
              {plan.blockers.length > 0 ? (
                <Section>
                  <Row>
                    <div className="stack" style={{ gap: 6 }}>
                      <div className="alert-red">
                        <IconLabel icon={<HandRightFilled />} color="#b71c1c" weight={600}>Stays in the ED: no redirect from triage</IconLabel>
                      </div>
                      {plan.blockers.map((b) => <IconLabel key={b} icon={<ArrowCircleRightRegular />} size="caption" color={colors.secondary}>{b}</IconLabel>)}
                      <p className="caption">Once {e.name.split(' ')[0]} has been seen, the plan turns to where to go next time. The nurse can always decide otherwise.</p>
                    </div>
                  </Row>
                </Section>
              ) : (
                <>
                  {edFirst && ed && (
                    <Section>
                      <Row>
                        <div className="alert-red">
                          <IconLabel icon={<WarningFilled />} color="#b71c1c" weight={600}>{e.problem} can be time-critical: if it comes back, call 000.</IconLabel>
                          <p className="caption" style={{ fontWeight: 400, marginTop: 4 }}>Nearest ED from home: {ed.service.name}, {ed.minutesText}. An ambulance needs no search.</p>
                        </div>
                      </Row>
                    </Section>
                  )}
                  <Section header={listTitle}>
                    {ranked.length === 0 && (
                      <Row><span className="subhead secondary">{purpose === 'redirectNow' ? `Nothing suitable is open within ${MAX_REDIRECT[mode]} min ${TRAVEL_SHORT[mode]} right now.` : 'Nothing found within reach.'}</span></Row>
                    )}
                    {edFirst && ed && (
                      <Row onClick={() => setSelected((s) => (s === ed.service.id ? null : ed.service.id))} selected={selected === ed.service.id} chevron={false}>
                        <OptionRow rank={0} option={ed} plan={plan} mode={mode} />
                      </Row>
                    )}
                    {ranked.map((o, i) => (
                      <Row key={o.service.id} onClick={() => setSelected((s) => (s === o.service.id ? null : o.service.id))} selected={selected === o.service.id} chevron={false} ariaLabel={`${i + 1}. ${o.service.name}, ${o.minutesText}, ${o.openText}`}>
                        <OptionRow rank={i + 1} option={o} plan={plan} mode={mode} />
                      </Row>
                    ))}
                  </Section>
                  {remote.length > 0 && (
                    <Section header="Without travelling">
                      {remote.map((o) => (
                        <Row key={o.service.id}>
                          <div className="option-row">
                            <span className="remote-icon" style={{ background: o.opensIn === 0 ? colors.green : '#9ea3ad' }}><ServiceIcon kind={o.service.kind} /></span>
                            <div>
                              <div className="headline">{o.service.name}</div>
                              <div className="subhead secondary">{o.service.goodFor}</div>
                              <div className="caption">{o.service.hoursText} · {o.service.contact}</div>
                              <div style={{ marginTop: 3 }}><Chip text={o.openText} color={o.opensIn === 0 ? colors.green : colors.secondary} /></div>
                            </div>
                          </div>
                        </Row>
                      ))}
                    </Section>
                  )}
                </>
              )}
              <Section header="How the model got there">
                <Row>
                  <div className="stack" style={{ gap: 7, color: colors.secondary }}>
                    <IconLabel icon={<HexagonRegular />} size="caption">Home is hexagon {plan.home.q}, {plan.home.r}: 866 m cells, like a ride-share app's H3 index</IconLabel>
                    <IconLabel icon={<SearchRegular />} size="caption">Searched outward ring by ring: {kMax} rings, {search.hexCount} hexagons, {candidateCount} candidates</IconLabel>
                    <IconLabel icon={<CheckmarkCircleRegular />} size="caption">{search.complete === false ? 'Ring limit reached before every need was met' : `Stopped once every need was met: ${needText}`}</IconLabel>
                    <IconLabel icon={<TravelIcon mode={mode} />} size="caption">
                      Travel time {TRAVEL_SHORT[mode]}: Dijkstra over the hexagon lattice with the road and bus model
                      {mode === 'bus' ? `, average bus wait ${Math.round(plan.busWait ?? busWait(state.now))} min` : ''}
                    </IconLabel>
                    <IconLabel icon={<MathFormulaRegular />} size="caption">
                      {mode === 'car' ? 'Cost per hexagon by car: 1.3 min on arterials, 2.2 min on local streets, plus 2 min to the car and parking' : mode === 'bus' ? 'Cost per hexagon by bus: 2.4 min riding along a corridor, 10.8 min walking, plus the wait to board' : 'Cost per hexagon on foot: 10.8 min (4.8 km/h)'}
                    </IconLabel>
                    <IconLabel icon={<MathFormulaRegular />} size="caption">Score = fit × open × e^(−minutes / 30)</IconLabel>
                    {plan.purpose === 'redirectNow' && (
                      <IconLabel icon={<ShieldCheckmarkRegular />} size="caption">
                        {plan.blockers.length === 0 ? 'Redirect gate passed: category 4 or 5, nothing time-critical or high risk, came by own transport' : `Redirect gate: ${plan.blockers.join('; ').toLowerCase()}`}
                      </IconLabel>
                    )}
                  </div>
                </Row>
              </Section>
            </>
          )}
          {selected && <div style={{ padding: '0 16px' }}><Button appearance="subtle" onClick={() => setSelected(null)}>Show the top routes again</Button></div>}
        </div>
      </div>
    </div>
  )
}

function OptionRow({ rank, option: o, plan, mode }: { rank: number; option: RightDoorOption; plan: RightDoorResult; mode: TravelMode }) {
  const ring = plan.search.rings.find((r) => r.found.includes(o.service.id))?.k
  const of = openFactor(o.opensIn, o.service.kind)
  const tf = travelFactor(o.minutes)
  const maxScore = Math.max(0.01, ...plan.options.map((x) => x.score))
  return (
    <div className="option-row" style={{ width: '100%' }}>
      <span className={`rank ${rank === 0 ? 'rank-000' : rank === 1 ? 'rank-1' : ''}`}>{rank === 0 ? '000' : rank}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="hstack-nowrap"><span style={{ color: colors.accent, display: 'inline-flex' }}><ServiceIcon kind={o.service.kind} /></span><span className="headline">{o.service.name}</span></div>
        <div className="subhead secondary">{o.service.goodFor}</div>
        <div className="hstack" style={{ marginTop: 3 }}>
          <Chip text={o.openText} color={o.opensIn === 0 ? colors.green : colors.secondary} />
          <Chip text={o.minutesText} color={colors.accent} icon={<TravelIcon mode={mode} />} />
          {ring != null && <span className="caption">ring {ring}</span>}
        </div>
        <div className="score-bar" aria-hidden><div className="score-fill" style={{ width: `${Math.max(3, (o.score / maxScore) * 100)}%` }} /></div>
        <div className="caption2 mono">fit {o.fit.toFixed(2)} × open {of.toFixed(1)} × travel {tf.toFixed(2)} = {o.score.toFixed(2)}</div>
      </div>
    </div>
  )
}
