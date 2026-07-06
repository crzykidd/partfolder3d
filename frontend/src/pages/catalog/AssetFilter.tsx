/**
 * AssetFilter — catalog toolbar three-state control to filter by print-asset presence.
 *
 * States:
 *   null  → All items (default, no filter sent to API)
 *   true  → "With files" (has_asset=true — items that have model or gcode files)
 *   false → "Without files" (has_asset=false — items with no model/gcode files)
 *
 * Styled as a button-segment group matching the Compact/Full grid-mode toggle.
 * No new deps.
 */

import { Box } from 'lucide-react'

interface AssetFilterProps {
  /** Current filter state: null = All, true = With files, false = Without files. */
  value: boolean | null
  /** Called with the new value when the user selects an option. */
  onChange: (value: boolean | null) => void
}

type Option = { label: string; value: boolean | null }

const OPTIONS: Option[] = [
  { label: 'All', value: null },
  { label: 'With files', value: true },
  { label: 'Without files', value: false },
]

export function AssetFilter({ value, onChange }: AssetFilterProps) {
  return (
    <div
      title="Filter by print assets"
      style={{
        display: 'flex',
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 10,
        overflow: 'hidden',
      }}
    >
      {OPTIONS.map((opt, idx) => {
        const active = value === opt.value
        return (
          <button
            key={String(opt.value)}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(opt.value)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: opt.value === true ? 4 : 0,
              padding: '5px 10px',
              fontSize: 12,
              border: 'none',
              borderRight: idx < OPTIONS.length - 1 ? '1px solid var(--aurora-glass-border)' : 'none',
              cursor: 'pointer',
              background: active ? 'var(--aurora-pill)' : 'transparent',
              color: active ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
              fontWeight: active ? 700 : 400,
              boxShadow: active ? 'var(--aurora-glow)' : 'none',
              transition: 'all 0.15s',
              whiteSpace: 'nowrap',
            }}
          >
            {opt.value === true && (
              <Box size={11} aria-hidden="true" style={{ color: active ? 'var(--aurora-accent)' : 'var(--aurora-muted)' }} />
            )}
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
