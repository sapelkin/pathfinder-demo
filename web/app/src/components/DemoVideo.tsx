import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@fluentui/react-components'
import { DismissRegular, FullScreenMaximizeRegular } from '@fluentui/react-icons'

export const DEMO_VIDEO_URL = `${import.meta.env.BASE_URL}media/pathfinder_live_demo.mp4`

/// The silent screen recording of the live demo, over the whole page. Esc or Close returns to the app.
export function DemoVideo({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const [missing, setMissing] = useState(false)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !document.fullscreenElement) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const fullscreen = () => { void box.current?.requestFullscreen?.().catch(() => undefined) }
  return createPortal(
    <div ref={box} className="demo-video" role="dialog" aria-modal="true" aria-label="Live demo video">
      <div className="demo-video-bar">
        <span>Pathfinder · live demo · 3:28 · no sound: the speech is given live</span>
        <span className="demo-video-actions">
          <Button appearance="subtle" icon={<FullScreenMaximizeRegular />} onClick={fullscreen}>Full screen</Button>
          <Button appearance="primary" icon={<DismissRegular />} onClick={onClose}>Close</Button>
        </span>
      </div>
      {missing
        ? <p className="demo-video-missing">The demo video is not part of this build.</p>
        : <video src={DEMO_VIDEO_URL} controls autoPlay muted playsInline preload="auto" onError={() => setMissing(true)} />}
    </div>,
    document.body,
  )
}
