import { useStore } from '../state/store'
import { colors } from '../lib/theme'
import { InfoRegular, WarningFilled, CheckmarkCircleFilled, PersonWalkingFilled, HomeFilled, ArrowCircleRightRegular } from '@fluentui/react-icons'

function bannerIcon(systemImage: string) {
  if (systemImage.includes('walk')) return <PersonWalkingFilled />
  if (systemImage.includes('house')) return <HomeFilled />
  if (systemImage.includes('checkmark')) return <CheckmarkCircleFilled />
  if (systemImage.includes('uturn') || systemImage.includes('arrow')) return <ArrowCircleRightRegular />
  if (systemImage.includes('exclamation')) return <WarningFilled />
  return <InfoRegular />
}

export function BannerView() {
  const { banner, dismissBanner } = useStore()
  if (!banner) return null
  const color = banner.tone === 'info' ? colors.accent : banner.tone === 'warning' ? colors.orange : colors.green
  return (
    <div className="banner-wrap">
      <button type="button" className="banner" style={{ borderColor: color }} onClick={dismissBanner} role="status" aria-live="polite">
        <span className="banner-icon" style={{ color }}>{bannerIcon(banner.systemImage)}</span>
        <span>{banner.text}</span>
      </button>
    </div>
  )
}

export function CaptionView() {
  const { state } = useStore()
  if (!state?.demo?.running || !state.showCaptions || !state.demo.caption) return null
  return <div className="caption-bar" aria-live="polite">{state.demo.caption}</div>
}
