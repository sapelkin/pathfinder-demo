import { useEffect, useState } from 'react'
import { Menu, MenuTrigger, MenuPopover, MenuList, MenuItem, MenuGroup, MenuGroupHeader, Button } from '@fluentui/react-components'
import { DocumentTextRegular, ChevronDownRegular } from '@fluentui/react-icons'
import { api } from '../api/client'
import type { NoteTemplate, Cohort } from '../api/types'
import { Chip } from './ui'
import { colors, cohortColor } from '../lib/theme'

const GROUPS: { cohort: Cohort; label: string }[] = [
  { cohort: 'p65', label: 'Aged 65 and over' }, { cohort: 'mh', label: 'Mental health' }, { cohort: 'other', label: 'Other' },
]

export function useTemplates(open: boolean): NoteTemplate[] | null {
  const [templates, setTemplates] = useState<NoteTemplate[] | null>(null)
  useEffect(() => {
    if (!open) return
    let cancelled = false
    api.templates().then((r) => { if (!cancelled) setTemplates(Array.isArray(r?.templates) ? r.templates : []) })
      .catch(() => { if (!cancelled) setTemplates(null) })  // an older API without /templates: the picker stays hidden
    return () => { cancelled = true }
  }, [open])
  return templates
}

/// "Insert a triage note template": fictional patients written the way nurses dictate, grouped by cohort.
export function TemplatePicker({ templates, onPick }: { templates: NoteTemplate[]; onPick: (t: NoteTemplate) => void }) {
  if (templates.length === 0) return null
  return (
    <div className="template-picker">
      <Menu positioning="below-start">
        <MenuTrigger disableButtonEnhancement>
          <Button icon={<DocumentTextRegular />} iconPosition="before" aria-label="Insert a triage note template" className="template-button">
            Insert a triage note template <ChevronDownRegular aria-hidden style={{ marginLeft: 4 }} />
          </Button>
        </MenuTrigger>
        <MenuPopover className="template-popover">
          <MenuList>
            {GROUPS.map((g) => {
              const rows = templates.filter((t) => t.cohort === g.cohort)
              if (rows.length === 0) return null
              return (
                <MenuGroup key={g.cohort}>
                  <MenuGroupHeader>{g.label}</MenuGroupHeader>
                  {rows.map((t) => (
                    <MenuItem key={t.id} onClick={() => onPick(t)} className="template-item" aria-label={`${t.title}, ${t.style}`}>
                      <span className="template-item-row">
                        <span className="template-title">{t.title}</span>
                        <Chip text={t.style} color={cohortColor(t.cohort) === colors.secondary ? colors.accent : cohortColor(t.cohort)} />
                      </span>
                    </MenuItem>
                  ))}
                </MenuGroup>
              )
            })}
          </MenuList>
        </MenuPopover>
      </Menu>
      <p className="caption" style={{ marginTop: 4 }}>Templates are fictional patients written the way nurses dictate; edit anything before confirming.</p>
    </div>
  )
}
