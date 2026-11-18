import { type ReactNode, type CSSProperties } from 'react'
import { Dialog, DialogSurface, DialogBody, Button } from '@fluentui/react-components'
import { ChevronRightRegular, LockClosedRegular, ChatFilled } from '@fluentui/react-icons'
import type { Cohort, Vitals } from '../api/types'
import { ATS_TARGET_MINUTES, atsColor, cohortColor, cohortShort, colors } from '../lib/theme'

export function ATSBadge({ ats, size = 34 }: { ats: number; size?: number }) {
  return (
    <span
      className="ats-badge"
      role="img"
      aria-label={`Triage category ${ats}`}
      style={{ width: size, height: size, borderRadius: size * 0.3, fontSize: size * 0.52, background: atsColor(ats) }}
    >
      {ats}
    </span>
  )
}

export function Chip({ text, color = colors.secondary, icon, filled = false, title }: { text: string; color?: string; icon?: ReactNode; filled?: boolean; title?: string }) {
  return (
    <span className="chip" title={title} style={filled ? { background: color, color: '#fff' } : { background: hexAlpha(color, 0.13), color }}>
      {icon}
      {text}
    </span>
  )
}

export function CohortTag({ cohort }: { cohort: Cohort }) {
  if (cohort === 'other') return null
  return <Chip text={cohortShort(cohort)} color={cohortColor(cohort)} />
}

export function Card({ title, icon, tint = colors.secondary, children, className, style, id }: {
  title?: string; icon?: ReactNode; tint?: string; children: ReactNode; className?: string; style?: CSSProperties; id?: string
}) {
  return (
    <section className={`card ${className ?? ''}`} style={style} id={id} aria-label={title}>
      {title && (
        <h3 className="card-title" style={{ color: tint }}>
          {icon}
          <span>{title}</span>
        </h3>
      )}
      {children}
    </section>
  )
}

/// A grouped-list section: a header, a card of divided rows, a footer.
export function Section({ header, footer, children, className }: { header?: ReactNode; footer?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`section ${className ?? ''}`}>
      {header && <div className="section-header">{header}</div>}
      <div className="section-card">{children}</div>
      {footer && <div className="section-footer">{footer}</div>}
    </div>
  )
}

export function Row({ children, onClick, chevron, selected, ariaLabel, className }: {
  children: ReactNode; onClick?: () => void; chevron?: boolean; selected?: boolean; ariaLabel?: string; className?: string
}) {
  const showChevron = chevron ?? Boolean(onClick)
  if (onClick) {
    return (
      <button type="button" className={`row row-button ${selected ? 'row-selected' : ''} ${className ?? ''}`} onClick={onClick} aria-label={ariaLabel} aria-pressed={selected}>
        <div className="row-content">{children}</div>
        {showChevron && <ChevronRightRegular className="row-chevron" aria-hidden />}
      </button>
    )
  }
  return (
    <div className={`row ${className ?? ''}`}>
      <div className="row-content">{children}</div>
    </div>
  )
}

export function LabeledRow({ label, value, valueColor }: { label: string; value: ReactNode; valueColor?: string }) {
  return (
    <div className="labeled">
      <span className="labeled-label">{label}</span>
      <span className="labeled-value" style={valueColor ? { color: valueColor } : undefined}>{value}</span>
    </div>
  )
}

export function IconLabel({ icon, children, color, size = 'sub', weight }: { icon: ReactNode; children: ReactNode; color?: string; size?: 'sub' | 'caption' | 'caption2'; weight?: number }) {
  return (
    <div className={`icon-label icon-label-${size}`} style={{ color, fontWeight: weight }}>
      <span className="icon-label-icon" aria-hidden>{icon}</span>
      <span>{children}</span>
    </div>
  )
}

/// Minutes waited against the category's target: the bar fills over three targets, the tick marks the target itself.
export function WaitBar({ waited, ats }: { waited: number; ats: number }) {
  const target = Math.max(1, ATS_TARGET_MINUTES[ats - 1])
  const share = Math.min(1, waited / (target * 3))
  const over = waited > target
  return (
    <div className="waitbar" role="img" aria-label={`Waited ${waited} minutes, target ${target}`}>
      <div className="waitbar-fill" style={{ width: `max(4px, ${share * 100}%)`, background: over ? colors.orange : hexAlpha(atsColor(ats), 0.85) }} />
      <div className="waitbar-tick" />
    </div>
  )
}

export function FlowChips({ items, color }: { items: string[]; color: string }) {
  return (
    <div className="flow-chips">
      {items.map((t) => <Chip key={t} text={t} color={color} />)}
    </div>
  )
}

export function Stat({ value, label, color, big }: { value: string; label: string; color: string; big?: boolean }) {
  return (
    <div className={`stat ${big ? 'stat-big' : ''}`}>
      <div className="stat-value" style={{ color }}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export function VitalsGrid({ vitals }: { vitals: Vitals }) {
  const tile = (name: string, value: string | undefined, unit: string, abnormal: boolean) => (
    <div className={`vital ${value == null ? 'vital-empty' : ''}`} key={name}>
      <div className="vital-name">{name}</div>
      <div className="vital-value" style={{ color: value == null ? colors.secondary : abnormal ? colors.orange : colors.text }}>
        {value ?? '—'}
        {value != null && <span className="vital-unit">{unit}</span>}
      </div>
    </div>
  )
  const v = vitals
  return (
    <div className="vitals-grid">
      {tile('Pulse', v.pulse?.toString(), 'bpm', v.pulse != null && (v.pulse < 50 || v.pulse > 100))}
      {tile('BP', v.systolic != null ? `${v.systolic}/${v.diastolic ?? '–'}` : undefined, '', v.systolic != null && (v.systolic < 90 || v.systolic > 160))}
      {tile('SpO₂', v.spo2?.toString(), '%', v.spo2 != null && v.spo2 < 94)}
      {tile('Resp', v.resp?.toString(), '/min', v.resp != null && (v.resp < 10 || v.resp > 24))}
      {tile('Temp', v.temp != null ? v.temp.toFixed(1) : undefined, '°C', v.temp != null && v.temp >= 38)}
      {tile('Pain', v.pain?.toString(), '/10', v.pain != null && v.pain >= 7)}
    </div>
  )
}

export function NumberDot({ n, size = 20 }: { n: number; size?: number }) {
  return <span className="number-dot" style={{ width: size, height: size, fontSize: size * 0.55 }}>{n}</span>
}

/// A full-screen sheet on a phone, a large centred panel on a wide screen. Fluent's Dialog gives the focus trap and Escape.
export function Sheet({ open, onClose, title, leading, trailing, children, wide, footer }: {
  open: boolean; onClose: () => void; title: string; leading?: ReactNode; trailing?: ReactNode; children: ReactNode; wide?: boolean; footer?: ReactNode
}) {
  return (
    <Dialog open={open} modalType="modal" onOpenChange={(_e, d) => { if (!d.open) onClose() }}>
      <DialogSurface className={`sheet ${wide ? 'sheet-wide' : ''}`} aria-label={title}>
        <DialogBody className="sheet-body">
          <header className="sheet-bar">
            <div className="sheet-leading">{leading}</div>
            <h2 className="sheet-title">{title}</h2>
            <div className="sheet-trailing">{trailing}</div>
          </header>
          <div className="sheet-content">{children}</div>
          {footer}
        </DialogBody>
      </DialogSurface>
    </Dialog>
  )
}

/// What the patient sees on their phone. Nothing is actually sent in the demo.
export function MessagePreview({ to, text, sentAt, open, onClose }: { to: string; text: string; sentAt: string; open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} modalType="modal" onOpenChange={(_e, d) => { if (!d.open) onClose() }}>
      <DialogSurface className="message-sheet" aria-label={`Text message to ${to}`}>
          <div className="message-preview">
            <div className="grabber" />
            <div className="message-head">
              <ChatFilled style={{ color: colors.green }} />
              <strong>Text message to {to}</strong>
              <span className="caption">{sentAt}</span>
            </div>
            <div className="message-bubble-row"><div className="message-bubble">{text}</div></div>
            <IconLabel icon={<LockClosedRegular />} size="caption" color={colors.secondary}>
              Simulated. No message leaves this device in the demo, and messages never carry clinical details.
            </IconLabel>
            <div style={{ marginTop: 12 }}><Button appearance="secondary" onClick={onClose}>Done</Button></div>
          </div>
      </DialogSurface>
    </Dialog>
  )
}

export function hexAlpha(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}
