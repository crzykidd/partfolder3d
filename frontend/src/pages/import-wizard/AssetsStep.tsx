/**
 * AssetsStep — Manyfold connector Part 3: file-selection step.
 *
 * Only shown when the session has staged files (ImportWizardPage checks
 * session.files.length > 0). Lists each staged file (name, role, human
 * size) with a checkbox bound to `selected`, checked by default (the
 * backend defaults selected=true). Unchecking calls the file-selection
 * PATCH endpoint immediately (optimistic — matches ImagesStep/SummaryStep's
 * pattern of writing through on every toggle rather than batching at Next).
 *
 * Benefits any session with staged files, not just Manyfold imports — a
 * plain multi-file upload gets the same review-before-commit affordance.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  AURORA_CARD,
  AURORA_BTN_GHOST,
  AURORA_BTN_PRIMARY,
} from './styles'

export interface AssetsStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

/** Human-readable byte size, e.g. "1.4 MB". */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

function FileRow({ sessionId, file }: { sessionId: string; file: api.ImportSessionFile }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const toggleMutation = useMutation({
    mutationFn: (selected: boolean) =>
      api.patchSessionFileSelection(sessionId, file.id, selected),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', sessionId], updated)
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to update selection.'),
  })

  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 14px',
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 8,
        cursor: toggleMutation.isPending ? 'wait' : 'pointer',
        opacity: file.selected ? 1 : 0.6,
        transition: 'opacity 0.15s',
      }}
    >
      <input
        type="checkbox"
        checked={file.selected}
        disabled={toggleMutation.isPending}
        onChange={(e) => {
          setError(null)
          toggleMutation.mutate(e.target.checked)
        }}
        style={{ accentColor: 'var(--aurora-accent)', width: 16, height: 16, cursor: 'pointer', flexShrink: 0 }}
      />
      <span
        style={{
          fontSize: 13,
          color: 'var(--aurora-text)',
          minWidth: 0,
          flex: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {file.original_name}
      </span>
      <span
        style={{
          fontSize: 11,
          color: 'var(--aurora-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          flexShrink: 0,
        }}
      >
        {file.role}
      </span>
      <span style={{ fontSize: 12, color: 'var(--aurora-muted)', flexShrink: 0, minWidth: 56, textAlign: 'right' }}>
        {formatSize(file.size)}
      </span>
      {error && (
        <span style={{ fontSize: 11, color: 'var(--aurora-danger)', flexBasis: '100%' }}>{error}</span>
      )}
    </label>
  )
}

export function AssetsStep({ session, onNext, onPrev }: AssetsStepProps) {
  const selectedCount = session.files.filter((f) => f.selected).length
  const totalCount = session.files.length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <p style={{ fontSize: 13, color: 'var(--aurora-text-dim)', margin: '0 0 4px' }}>
          Choose which staged files become part of this item. Deselected files stay
          out of the committed item but aren't deleted here — go back to the Summary
          step to remove them entirely.
        </p>
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
          {selectedCount} of {totalCount} file{totalCount === 1 ? '' : 's'} selected
        </p>
      </div>

      <div style={{ ...AURORA_CARD, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {session.files.map((f) => (
          <FileRow key={f.id} sessionId={session.id} file={f} />
        ))}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4 }}>
        <button
          type="button"
          onClick={onPrev}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={onNext}
          style={AURORA_BTN_PRIMARY}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
        >
          Next →
        </button>
      </div>
    </div>
  )
}
