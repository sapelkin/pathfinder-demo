import { Suspense, lazy } from 'react'
import { Spinner } from '@fluentui/react-components'
import { DoorArrowRightRegular, DoorArrowRightFilled, ArrowSyncRegular, ArrowSyncFilled, MapRegular, MapFilled, DataBarVerticalRegular, DataBarVerticalFilled, PulseRegular, PulseFilled } from '@fluentui/react-icons'
import { TAB_LABEL, tabsFor, useStore, type Tab } from './state/store'
import { ClockControl } from './components/ClockControl'
import { BannerView, CaptionView } from './components/Overlays'
import { FrontDoor } from './screens/FrontDoor'
import { FollowThrough } from './screens/FollowThrough'
import { SettingsSheet } from './screens/Settings'
import { UnitsSheet } from './screens/Units'
import { IntakeSheet } from './screens/Intake'
import { IS_LOCAL } from './api/mode'
import { EngineLoading } from './components/EngineLoading'

const RightDoor = lazy(() => import('./screens/RightDoor').then((m) => ({ default: m.RightDoor })))
const Impact = lazy(() => import('./screens/Impact').then((m) => ({ default: m.Impact })))
const Live = lazy(() => import('./screens/Live').then((m) => ({ default: m.Live })))

function tabIcon(t: Tab, selected: boolean) {
  switch (t) {
    case 'frontDoor': return selected ? <DoorArrowRightFilled /> : <DoorArrowRightRegular />
    case 'followThrough': return selected ? <ArrowSyncFilled /> : <ArrowSyncRegular />
    case 'rightDoor': return selected ? <MapFilled /> : <MapRegular />
    case 'impact': return selected ? <DataBarVerticalFilled /> : <DataBarVerticalRegular />
    case 'dashboard': return selected ? <PulseFilled /> : <PulseRegular />
  }
}

function TabButtons({ tabs }: { tabs: Tab[] }) {
  const { nav, setTab, state } = useStore()
  return (
    <>
      {tabs.map((t) => {
        const selected = nav.tab === t
        const badge = t === 'followThrough' ? state?.openActionCount ?? 0 : 0
        return (
          <button key={t} type="button" role="tab" className="tab" aria-selected={selected} aria-controls="main" onClick={() => setTab(t)}>
            {tabIcon(t, selected)}
            <span>{TAB_LABEL[t]}</span>
            {badge > 0 && <span className="tab-badge" aria-label={`${badge} open actions`}>{badge}</span>}
          </button>
        )
      })}
    </>
  )
}

export default function App() {
  if (IS_LOCAL) return <EngineLoading><Shell /></EngineLoading>
  return <Shell />
}

function Shell() {
  const { state, nav, error, connected } = useStore()
  const tabs = tabsFor(state?.deployment ?? 'full')
  const fallback = <div className="empty"><Spinner label="Loading…" /></div>
  const screen = (() => {
    switch (nav.tab) {
      case 'frontDoor': return <FrontDoor />
      case 'followThrough': return <FollowThrough />
      case 'rightDoor': return <Suspense fallback={fallback}><RightDoor /></Suspense>
      case 'impact': return <Suspense fallback={fallback}><Impact /></Suspense>
      case 'dashboard': return <Suspense fallback={fallback}><Live /></Suspense>
    }
  })()
  return (
    <div className="shell">
      <nav className="rail" role="tablist" aria-label="Screens">
        <div className="rail-brand">Pathfinder</div>
        <TabButtons tabs={tabs} />
      </nav>
      <header className="topbar">
        <div className="topbar-title">
          <span>{TAB_LABEL[nav.tab]}</span>
          <span className="ed-name">{state?.ed.name ?? ''}</span>
        </div>
        <ClockControl />
      </header>
      <main className="main" id="main" role="tabpanel">
        {!connected && error && <div className="connection" role="status">{IS_LOCAL ? `The engine reported an error (${error}).` : `Not connected to the API (${error}). Retrying every 2 s.`}</div>}
        {screen}
      </main>
      {tabs.length > 1 && (
        <nav className="tabbar" role="tablist" aria-label="Screens">
          <TabButtons tabs={tabs} />
        </nav>
      )}
      <BannerView />
      <CaptionView />
      <IntakeSheet />
      <SettingsSheet />
      <UnitsSheet />
    </div>
  )
}
