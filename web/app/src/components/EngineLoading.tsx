import { useEffect, useState } from 'react'
import { ProgressBar, Button } from '@fluentui/react-components'
import { getEngineStatus, startEngine, subscribeEngine, type EngineStatus } from '../api/local'

/// The backend-free build's start: Pyodide and the engine wheel load from the site's own files, once (then cached).
export function EngineLoading({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<EngineStatus>(getEngineStatus())
  useEffect(() => { startEngine(); return subscribeEngine(setStatus) }, [])
  if (status.phase === 'ready') return <>{children}</>
  const pct = status.total && status.loaded ? status.loaded / status.total : undefined
  return (
    <div className="engine-loading" role="status" aria-live="polite">
      <div className="engine-card">
        <div className="title3">Pathfinder</div>
        <p className="subhead">{status.phase === 'failed' ? status.stage : 'Loading the engine… 10 MB, once'}</p>
        <ProgressBar value={pct} max={1} thickness="large" />
        <p className="caption">
          {status.phase === 'failed'
            ? status.error
            : `${status.stage}${pct != null ? ` · ${Math.round(pct * 100)}%` : ''}`}
        </p>
        <p className="caption2">The Python engine runs in this browser tab; nothing is sent to a server. Your demo state stays in this browser.</p>
        {status.phase === 'failed' && <Button appearance="primary" onClick={() => window.location.reload()}>Try again</Button>}
      </div>
    </div>
  )
}
