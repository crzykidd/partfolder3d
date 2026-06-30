/**
 * AiTextPreview — shared panel that shows an AI-generated text suggestion
 * with "Use this" / "Discard" actions.
 */

import { SECTION_LABEL, AURORA_BTN_PRIMARY, AURORA_BTN_GHOST } from './styles'

interface AiTextPreviewProps {
  text: string
  onUse: () => void
  onDiscard: () => void
}

export function AiTextPreview({ text, onUse, onDiscard }: AiTextPreviewProps) {
  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 10,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <span style={SECTION_LABEL}>AI suggestion — preview</span>
      <p
        style={{
          fontSize: 13,
          color: 'var(--aurora-text)',
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          margin: 0,
        }}
      >
        {text}
      </p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          onClick={onUse}
          style={AURORA_BTN_PRIMARY}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
        >
          Use this
        </button>
        <button
          type="button"
          onClick={onDiscard}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Discard
        </button>
      </div>
    </div>
  )
}
