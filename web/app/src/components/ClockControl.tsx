import { Menu, MenuTrigger, MenuPopover, MenuList, MenuItem, MenuDivider, MenuItemRadio, Menu as SubMenu, type MenuProps } from '@fluentui/react-components'
import { useState } from 'react'
import { ClockFilled, PauseCircleFilled, PauseFilled, PlayFilled, SkipForward30Regular, PlayCircleRegular, SettingsRegular, VideoClipRegular } from '@fluentui/react-icons'
import { api } from '../api/client'
import { SPEEDS, useStore, useDisplayNow } from '../state/store'
import { clockText } from '../lib/clock'
import { DemoVideo } from './DemoVideo'

export function speedLabel(s: number): string { return s === 1 ? 'Real time' : `×${s}` }

export function ClockControl() {
  const { state, run, settings, setShowSettings } = useStore()
  const displayNow = useDisplayNow()
  const [video, setVideo] = useState(false)
  if (!state) return <span className="clock-pill clock-pill-empty">Connecting…</span>
  const onSpeed: MenuProps['onCheckedValueChange'] = (_e, d) => {
    const s = Number(d.checkedItems[0])
    if (s) void settings({ speed: s })
  }
  return (
    <>
    <Menu>
      <MenuTrigger disableButtonEnhancement>
        <button type="button" className="clock-pill" aria-label={`Clock ${clockText(displayNow)}, ${state.running ? 'running' : 'paused'}, speed ${speedLabel(state.speed)}`}>
          {state.running ? <ClockFilled aria-hidden /> : <PauseCircleFilled aria-hidden />}
          <span className="clock-text">{clockText(displayNow)}</span>
          {state.speed > 1 && <span className="speed-badge">×{state.speed}</span>}
        </button>
      </MenuTrigger>
      <MenuPopover>
        <MenuList>
          <MenuItem icon={state.running ? <PauseFilled /> : <PlayFilled />} onClick={() => void settings({ running: !state.running })}>
            {state.running ? 'Pause' : 'Resume'}
          </MenuItem>
          <SubMenu checkedValues={{ speed: [String(state.speed)] }} onCheckedValueChange={onSpeed}>
            <MenuTrigger disableButtonEnhancement>
              <MenuItem>Speed</MenuItem>
            </MenuTrigger>
            <MenuPopover>
              <MenuList>
                {SPEEDS.map((s) => <MenuItemRadio key={s} name="speed" value={String(s)}>{speedLabel(s)}</MenuItemRadio>)}
              </MenuList>
            </MenuPopover>
          </SubMenu>
          <MenuItem icon={<SkipForward30Regular />} onClick={() => void run(() => api.jump(30))}>Jump 30 minutes</MenuItem>
          <MenuDivider />
          <MenuItem icon={<PlayCircleRegular />} onClick={() => void run(() => api.demoStart(false))}>Guided demo</MenuItem>
          <MenuItem icon={<SettingsRegular />} onClick={() => setShowSettings(true)}>Settings</MenuItem>
          <MenuDivider />
          <MenuItem icon={<VideoClipRegular />} onClick={() => setVideo(true)}>Watch the demo video</MenuItem>
        </MenuList>
      </MenuPopover>
    </Menu>
    {video && <DemoVideo onClose={() => setVideo(false)} />}
    </>
  )
}
