import { Tooltip } from '@fluentui/react-components'
import { DataBarVerticalRegular } from '@fluentui/react-icons'
import type { Hospital } from '../api/types'
import { Chip } from './ui'
import { colors } from '../lib/theme'

export function publishedTriple(h: Hospital): string {
  return `${h.published.waiting} waiting · ${h.published.inEd} in ED · cat-4 avg ${h.published.t4AvgWaitMin} min`
}

/// "From published numbers": shown next to "Simulated" when the ED is a real metropolitan hospital rebuilt from
/// WA Health's live-activity page. The tooltip carries the published triple and when it was taken.
export function PublishedChip({ hospital }: { hospital?: Hospital | null }) {
  if (!hospital || hospital.id === 'demo') return null
  const text = `${publishedTriple(hospital)} · ${hospital.source.takenText}`
  return (
    <Tooltip content={text} relationship="description" withArrow>
      <span tabIndex={0} style={{ display: 'inline-flex' }} aria-label={`From published numbers: ${text}`}>
        <Chip text="From published numbers" color={colors.accent} icon={<DataBarVerticalRegular />} />
      </span>
    </Tooltip>
  )
}

export function PublishedLine({ hospital }: { hospital?: Hospital | null }) {
  if (!hospital || hospital.id === 'demo') return null
  return <p className="caption published-line">Published: {publishedTriple(hospital)} · {hospital.source.takenText}</p>
}
