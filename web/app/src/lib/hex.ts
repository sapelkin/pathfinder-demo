// HexGrid, as in the engine's hexgrid.py: a pointy-top hexagonal grid in axial coordinates over the metro's local
// plane (x east, y north, km). Circumradius 0.5 km, so neighbouring centres are 866 m apart.
import type { Hex } from '../api/types'

export const HEX_SIZE = 0.5
export const HEX_STEP = HEX_SIZE * Math.sqrt(3)
const S3 = Math.sqrt(3)

export function hexCenter(h: Hex, size = HEX_SIZE): { x: number; y: number } {
  return { x: size * (S3 * h.q + (S3 / 2) * h.r), y: size * 1.5 * h.r }
}

export function hexCorners(h: Hex, size = HEX_SIZE): { x: number; y: number }[] {
  const c = hexCenter(h, size)
  const out: { x: number; y: number }[] = []
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 180) * (60 * i - 30)
    out.push({ x: c.x + size * Math.cos(a), y: c.y + size * Math.sin(a) })
  }
  return out
}

export function hexAt(x: number, y: number, size = HEX_SIZE): Hex {
  const q = ((S3 / 3) * x - y / 3) / size
  const r = ((2 / 3) * y) / size
  const s = -q - r
  let rq = Math.round(q), rr = Math.round(r)
  const rs = Math.round(s)
  const dq = Math.abs(rq - q), dr = Math.abs(rr - r), ds = Math.abs(rs - s)
  if (dq > dr && dq > ds) rq = -rr - rs
  else if (dr > ds) rr = -rq - rs
  return { q: rq, r: rr }
}

export function hexKey(h: Hex): string { return `${h.q},${h.r}` }

export function hexDistance(a: Hex, b: Hex): number {
  const as = -a.q - a.r, bs = -b.q - b.r
  return (Math.abs(a.q - b.q) + Math.abs(a.r - b.r) + Math.abs(as - bs)) / 2
}

// The demo metro's local plane (the engine's network.py, `Metro`).
export const METRO = { lat: -31.929, lon: 115.902, kmPerDegLat: 110.57, kmPerDegLon: 111.32 * Math.cos((-31.929 * Math.PI) / 180) }

export function metroXY(lat: number, lon: number): { x: number; y: number } {
  return { x: (lon - METRO.lon) * METRO.kmPerDegLon, y: (lat - METRO.lat) * METRO.kmPerDegLat }
}

/// `homeCoord` from the API may be [x, y] km or [lat, lon]; both are accepted.
export function coordToXY(c: [number, number] | undefined, fallback: { x: number; y: number }): { x: number; y: number } {
  if (!c) return fallback
  const [a, b] = c
  if (Math.abs(a) > 50 || Math.abs(b) > 50) return metroXY(a, b)
  return { x: a, y: b }
}
