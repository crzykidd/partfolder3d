/**
 * MoveToLibrary — "Move to library →" control for a single item (issue #25).
 *
 * Relocates the item's on-disk directory to another library mount (copy →
 * verify-hash → remove, server-side) and updates library_id + dir_path. Only
 * rendered when two or more *enabled* libraries exist; the current library is
 * excluded from the target list.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FolderInput } from 'lucide-react'

import * as api from '@/lib/api'
import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY, AURORA_INPUT } from './styles'

interface MoveToLibraryProps {
  itemKey: string
  currentLibraryId: number
}

export function MoveToLibrary({ itemKey, currentLibraryId }: MoveToLibraryProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [targetId, setTargetId] = useState<number | ''>('')

  const { data: libraries } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
  })

  const enabled = (libraries ?? []).filter((l) => l.enabled)
  const targets = enabled.filter((l) => l.id !== currentLibraryId)

  const moveMutation = useMutation({
    mutationFn: (libraryId: number) => api.moveItem(itemKey, libraryId),
    onSuccess: (updated) => {
      queryClient.setQueryData(['item', itemKey], updated)
      void queryClient.invalidateQueries({ queryKey: ['item', itemKey] })
      void queryClient.invalidateQueries({ queryKey: ['items'] })
      void queryClient.invalidateQueries({ queryKey: ['libraries'] })
      setOpen(false)
      setTargetId('')
    },
  })

  // Show only when there is at least one other enabled library to move into.
  if (enabled.length < 2 || targets.length === 0) return null

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Move this item to a different library"
        style={{
          ...AURORA_BTN_GHOST,
          fontSize: 11,
          padding: '4px 10px',
          display: 'flex',
          alignItems: 'center',
          gap: 5,
        }}
      >
        <FolderInput size={12} />
        Move to library
      </button>
    )
  }

  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <select
        aria-label="Target library"
        value={targetId}
        onChange={(e) => setTargetId(e.target.value ? Number(e.target.value) : '')}
        disabled={moveMutation.isPending}
        style={{ ...AURORA_INPUT, width: 'auto', fontSize: 11, padding: '4px 8px' }}
      >
        <option value="">Select library…</option>
        {targets.map((l) => (
          <option key={l.id} value={l.id}>
            {l.name}
          </option>
        ))}
      </select>
      <button
        onClick={() => typeof targetId === 'number' && moveMutation.mutate(targetId)}
        disabled={moveMutation.isPending || typeof targetId !== 'number'}
        style={{
          ...AURORA_BTN_PRIMARY,
          fontSize: 11,
          padding: '4px 10px',
          opacity: moveMutation.isPending || typeof targetId !== 'number' ? 0.6 : 1,
          cursor:
            moveMutation.isPending || typeof targetId !== 'number'
              ? 'not-allowed'
              : 'pointer',
        }}
      >
        {moveMutation.isPending ? 'Moving…' : 'Move'}
      </button>
      <button
        onClick={() => {
          setOpen(false)
          setTargetId('')
        }}
        disabled={moveMutation.isPending}
        style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '4px 10px' }}
      >
        Cancel
      </button>
      {moveMutation.isError && (
        <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>Move failed</span>
      )}
    </span>
  )
}
