/**
 * CommitReadyPanel — bulk-commit all pending_wizard sessions, with an
 * optional target-library picker; shows a BulkResultSummary when done.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { IMPORT_DEFAULT_LIBRARY_KEY } from '@/lib/api/settings'
import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY } from './styles'
import { BulkResultSummary } from './BulkResultSummary'

interface CommitReadyPanelProps {
  pendingCount: number
  libraries: api.LibraryOut[]
  settings: api.SettingOut[]
}

export function CommitReadyPanel({ pendingCount, libraries, settings }: CommitReadyPanelProps) {
  const queryClient = useQueryClient()
  const [showLibraryPicker, setShowLibraryPicker] = useState(false)
  const [pickedLibraryId, setPickedLibraryId] = useState<number | null>(null)
  const [result, setResult] = useState<api.BulkCommitResponse | null>(null)
  const [commitError, setCommitError] = useState<string | null>(null)

  const enabledLibraries = libraries.filter((l) => l.enabled)

  // Is a default library already configured?
  const defaultLibSetting = settings.find((s) => s.key === IMPORT_DEFAULT_LIBRARY_KEY)
  const defaultLibId = typeof defaultLibSetting?.value === 'number'
    ? (defaultLibSetting.value as number)
    : null

  const bulkMutation = useMutation({
    mutationFn: (libraryId: number | null) =>
      api.bulkCommitImportSessions({ session_ids: null, library_id: libraryId ?? undefined }),
    onSuccess: (data) => {
      setResult(data)
      setShowLibraryPicker(false)
      void queryClient.invalidateQueries({ queryKey: ['import-sessions'] })
    },
    onError: (e) => {
      setCommitError(e instanceof Error ? e.message : 'Bulk commit failed.')
      setShowLibraryPicker(false)
    },
  })

  if (result) {
    return (
      <BulkResultSummary
        result={result}
        onClose={() => { setResult(null) }}
      />
    )
  }

  const handleCommitReady = () => {
    setCommitError(null)
    // Need library picker if: multiple libraries AND no default configured
    const needsPicker = enabledLibraries.length > 1 && defaultLibId === null
    if (needsPicker) {
      setShowLibraryPicker(true)
    } else {
      bulkMutation.mutate(null)
    }
  }

  if (showLibraryPicker) {
    return (
      <div
        style={{
          background: 'var(--aurora-glass)',
          border: '1px solid var(--aurora-glass-border)',
          borderRadius: 12,
          padding: '16px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          minWidth: 280,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
            Choose target library
          </p>
          <button
            onClick={() => { setShowLibraryPicker(false) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--aurora-muted)', fontSize: 15, lineHeight: 1, padding: 2 }}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
          Multiple libraries exist and no default is configured. Pick one for this batch.
        </p>

        <select
          value={pickedLibraryId ?? ''}
          onChange={(e) => setPickedLibraryId(e.target.value === '' ? null : Number(e.target.value))}
          style={{
            background: 'var(--aurora-input-bg)',
            border: '1px solid var(--aurora-input-border)',
            borderRadius: 8,
            color: 'var(--aurora-text)',
            padding: '7px 11px',
            fontSize: 13,
            outline: 'none',
            width: '100%',
          }}
        >
          <option value="">Select a library…</option>
          {enabledLibraries.map((lib) => (
            <option key={lib.id} value={lib.id}>
              {lib.name}
            </option>
          ))}
        </select>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            onClick={() => { if (pickedLibraryId != null) bulkMutation.mutate(pickedLibraryId) }}
            disabled={pickedLibraryId === null || bulkMutation.isPending}
            style={{
              ...AURORA_BTN_PRIMARY,
              opacity: pickedLibraryId === null || bulkMutation.isPending ? 0.5 : 1,
              cursor: pickedLibraryId === null || bulkMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {bulkMutation.isPending ? 'Committing…' : 'Commit ready'}
          </button>
          <button
            type="button"
            onClick={() => { setShowLibraryPicker(false) }}
            style={AURORA_BTN_GHOST}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
      <button
        type="button"
        onClick={handleCommitReady}
        disabled={pendingCount === 0 || bulkMutation.isPending}
        style={{
          ...AURORA_BTN_PRIMARY,
          opacity: pendingCount === 0 || bulkMutation.isPending ? 0.5 : 1,
          cursor: pendingCount === 0 || bulkMutation.isPending ? 'not-allowed' : 'pointer',
        }}
        title={pendingCount === 0 ? 'No pending sessions to commit' : `Commit all ${pendingCount} ready sessions`}
        onMouseEnter={(e) => {
          if (pendingCount > 0 && !bulkMutation.isPending)
            (e.currentTarget as HTMLButtonElement).style.opacity = '0.85'
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.opacity =
            pendingCount === 0 || bulkMutation.isPending ? '0.5' : '1'
        }}
      >
        {bulkMutation.isPending
          ? 'Committing…'
          : `Commit ready${pendingCount > 0 ? ` (${pendingCount})` : ''}`}
      </button>
      {commitError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{commitError}</p>
      )}
    </div>
  )
}
