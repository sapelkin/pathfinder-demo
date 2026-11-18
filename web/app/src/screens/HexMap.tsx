import { useMemo, useRef, useState, type PointerEvent as RPointerEvent, type WheelEvent as RWheelEvent } from 'react'
import type { Network, RightDoorOption, RightDoorResult, Hex } from '../api/types'
import { coordToXY, hexCenter, hexCorners, hexKey, hexDistance, HEX_STEP } from '../lib/hex'
import { colors, ringColor, atsColor, SERVICE_SHORT } from '../lib/theme'

/// The demo metro drawn in SVG: suburbs, arterial roads with bus
/// corridors, the rings as they spread, the travel-time field, the routes and the pins. Drag to pan, wheel to zoom.
export function HexMap({ plan, network, shownRings, settled, selected, routes, firstName, onSelect }: {
  plan: RightDoorResult; network: Network | null; shownRings: number; settled: boolean; selected: string | null
  routes: RightDoorOption[]; firstName: string; onSelect: (serviceId: string) => void
}) {
  const [size, setSize] = useState({ w: 600, h: 330 })
  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)
  const ref = useRef<SVGSVGElement>(null)

  const home = useMemo(() => (plan.homeXY ? { x: plan.homeXY[0], y: plan.homeXY[1] } : coordToXY(plan.homeCoord, hexCenter(plan.home))), [plan.homeXY, plan.homeCoord, plan.home])
  const kMax = plan.search.rings.length - 1
  const spanKm = (kMax + 3) * HEX_STEP * 2 + 1.2
  const ppk = (size.w / spanKm) * scale
  const cx = size.w / 2 + pan.x
  const cy = size.h / 2 + pan.y
  const px = (x: number, y: number) => ({ x: cx + (x - home.x) * ppk, y: cy - (y - home.y) * ppk })
  const path = (pts: { x: number; y: number }[]) => pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

  const serviceById = useMemo(() => new Map((network?.services ?? []).map((s) => [s.id, s])), [network])
  const found = plan.search.rings.slice(0, shownRings).flatMap((r) => r.found)
  const optionById = useMemo(() => new Map(plan.options.map((o) => [o.service.id, o])), [plan.options])
  const fieldMax = Math.max(1, ...plan.field.map((f) => f.minutes))
  const fieldByHex = useMemo(() => new Map(plan.field.map((f) => [hexKey(f.hex), f.minutes])), [plan.field])

  const measure = (el: SVGSVGElement | null) => {
    if (!el) return
    const r = el.getBoundingClientRect()
    if (Math.abs(r.width - size.w) > 1 || Math.abs(r.height - size.h) > 1) setSize({ w: r.width, h: r.height })
  }
  const onPointerDown = (e: RPointerEvent<SVGSVGElement>) => { drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }; e.currentTarget.setPointerCapture(e.pointerId) }
  const onPointerMove = (e: RPointerEvent<SVGSVGElement>) => { if (drag.current) setPan({ x: drag.current.px + e.clientX - drag.current.x, y: drag.current.py + e.clientY - drag.current.y }) }
  const onPointerUp = () => { drag.current = null }
  const onWheel = (e: RWheelEvent<SVGSVGElement>) => { setScale((s) => Math.min(4, Math.max(0.5, s * (e.deltaY > 0 ? 0.9 : 1.1)))) }

  const ringHexes: { hex: Hex; k: number }[] = plan.search.rings.slice(0, shownRings).flatMap((r) => r.hexes.map((hex) => ({ hex, k: r.k })))
  const corridors = network?.corridors ?? []
  const roads = network?.roads ?? []

  return (
    <svg
      ref={(el) => { (ref as { current: SVGSVGElement | null }).current = el; measure(el) }}
      className="hexmap" viewBox={`0 0 ${size.w} ${size.h}`} role="img"
      aria-label={`Hexagon map: ${shownRings} of ${plan.search.rings.length} rings searched from ${firstName}'s home, ${found.length} services found`}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onWheel={onWheel}
    >
      <rect width={size.w} height={size.h} fill="#edefe6" />
      {/* Suburbs as soft patches with their names. */}
      {(network?.suburbs ?? []).map((s) => { const c = px(s.x, s.y); return <circle key={s.name} cx={c.x} cy={c.y} r={(s.spread ?? 1) * 1.6 * ppk} fill="#e3e7db" /> })}
      {/* Arterial roads and bus corridors. */}
      {[...roads, ...corridors].map((line, i) => (
        <g key={`road-${i}`}>
          <path d={path(line.map(([x, y]) => px(x, y)))} stroke="#d6d8cf" strokeWidth={7 * Math.min(scale, 1.5)} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          <path d={path(line.map(([x, y]) => px(x, y)))} stroke="#ffffff" strokeWidth={4.5 * Math.min(scale, 1.5)} fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      ))}
      {corridors.map((line, i) => (
        <path key={`bus-${i}`} d={path(line.map(([x, y]) => px(x, y)))} stroke="#9aa3ae" strokeWidth={1.2} strokeDasharray="6 5" fill="none" opacity={0.8} />
      ))}
      {(network?.suburbs ?? []).map((s) => { const c = px(s.x, s.y); return <text key={`l-${s.name}`} x={c.x} y={c.y} textAnchor="middle" dominantBaseline="middle" fontSize={11} fontWeight={500} fill="#7a7f86">{s.name}</text> })}
      {/* The travel-time field, once settled: lighter is nearer. */}
      {settled && plan.field.filter((f) => hexDistance(f.hex, plan.home) <= kMax + 1).map((f) => {
        const t = f.minutes / fieldMax
        return <path key={`f-${hexKey(f.hex)}`} d={path(hexCorners(f.hex).map((p) => px(p.x, p.y))) + 'Z'} fill={colors.accent} opacity={0.05 + 0.3 * (1 - t)} />
      })}
      {/* The rings, as far as the search has spread. */}
      {ringHexes.map(({ hex, k }) => (
        <path key={`r-${hexKey(hex)}`} d={path(hexCorners(hex).map((p) => px(p.x, p.y))) + 'Z'} fill={ringColor(k, kMax)} fillOpacity={0.55} stroke="rgba(255,255,255,0.75)" strokeWidth={0.7}>
          {fieldByHex.has(hexKey(hex)) && <title>{`ring ${k}: ${Math.round(fieldByHex.get(hexKey(hex)) ?? 0)} min`}</title>}
        </path>
      ))}
      {/* The routes, once the travel field has settled. */}
      {settled && routes.map((o) => {
        if (!o.route || o.route.length < 2) return null
        const faded = selected != null && selected !== o.service.id
        return <path key={`route-${o.service.id}`} d={path(o.route.map((h) => { const c = hexCenter(h); return px(c.x, c.y) }))} stroke={colors.accent} strokeOpacity={faded ? 0.3 : 1} strokeWidth={3.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      })}
      {/* Service pins found so far. */}
      {found.map((sid) => {
        const s = serviceById.get(sid) ?? optionById.get(sid)?.service
        if (!s || s.x == null || s.y == null) return null
        const p = px(s.x, s.y)
        const o = optionById.get(sid)
        const open = o ? o.opensIn === 0 : true
        const fill = s.kind === 'ed' ? atsColor(1) : open ? colors.green : '#9ea3ad'
        const r = 14
        const isSel = selected === sid
        return (
          <g key={`pin-${sid}`} style={{ cursor: 'pointer' }} onClick={(ev) => { ev.stopPropagation(); onSelect(sid) }} onPointerDown={(ev) => ev.stopPropagation()} tabIndex={0} role="button"
            aria-label={`${s.name}${o && o.minutes != null ? `, ${Math.round(o.minutes)} min` : ''}`} onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(sid) } }}>
            <circle cx={p.x} cy={p.y - r} r={r} fill={fill} stroke={isSel ? colors.accent : '#fff'} strokeWidth={isSel ? 3 : 2} />
            <text x={p.x} y={p.y - r} textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700} fill="#fff">{SERVICE_SHORT[s.kind]}</text>
            {settled && o && o.minutes != null && (() => {
              const label = size.w >= 600 ? `${s.name.length > 22 ? s.name.slice(0, 21) + '…' : s.name} · ${Math.round(o.minutes)} min` : `${Math.round(o.minutes)} min`
              const w = label.length * 6.2 + 12
              return (
                <g>
                  <rect x={p.x - w / 2} y={p.y - 2 * r - 20} width={w} height={17} rx={8.5} fill="#fff" opacity={0.95} />
                  <text x={p.x} y={p.y - 2 * r - 11.5} textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700} fill="#111">{label}</text>
                </g>
              )
            })()}
          </g>
        )
      })}
      {/* Home. */}
      {(() => {
        const p = px(home.x, home.y)
        const s = 32
        return (
          <g>
            <rect x={p.x - s / 2} y={p.y - s / 2} width={s} height={s} rx={9} fill={colors.orange} stroke="#fff" strokeWidth={2} />
            <path d={`M${p.x - 8} ${p.y + 1} L${p.x} ${p.y - 7} L${p.x + 8} ${p.y + 1} V${p.y + 8} H${p.x - 8} Z`} fill="#fff" />
            <text x={p.x} y={p.y + s / 2 + 12} textAnchor="middle" fontSize={11} fontWeight={600} fill="#111">{firstName}'s home</text>
          </g>
        )
      })()}
      <text x={10} y={16} fontSize={11} fill="#7a7f86">ring {Math.min(shownRings, kMax)} of {kMax} · {plan.search.hexCount} hexagons searched · {found.length} services found</text>
    </svg>
  )
}
