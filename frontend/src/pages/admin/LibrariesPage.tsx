/**
 * LibrariesPage — Admin: list, add, and disable library mounts.
 *
 * A library is a directory mounted into the container from the host.
 * The mount path must be an absolute path inside the container (e.g. /library).
 * Items are stored under the library's mount path on disk.
 *
 * Styling: Aurora aesthetic — glass cards, --aurora-* CSS vars, no Mantine, no toast.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { HardDrive, Plus, Trash2, AlertCircle } from 'lucide-react'

import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 12,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

const INPUT_STYLE: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '8px 12px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}

const BTN_PRIMARY_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  background: 'var(--aurora-accent)',
  color: '#fff',
  border: 'none',
  borderRadius: 8,
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

const BTN_GHOST_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 8,
  color: 'var(--aurora-text-dim)',
  padding: '6px 12px',
  fontSize: 12,
  cursor: 'pointer',
  transition: 'background 0.15s, color 0.15s',
}

// ---------------------------------------------------------------------------
// Add Library form
// ---------------------------------------------------------------------------

interface AddLibraryFormProps {
  onSuccess: () => void
}

function AddLibraryForm({ onSuccess }: AddLibraryFormProps) {
  const [name, setName] = useState('')
  const [mountPath, setMountPath] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => api.createLibrary({ name: name.trim(), mount_path: mountPath.trim() }),
    onSuccess: () => {
      setName('')
      setMountPath('')
      setError(null)
      onSuccess()
    },
    onError: (err) => {
      setError(err instanceof api.ApiError ? err.message : 'Failed to create library.')
    },
  })

  const canSubmit = name.trim().length > 0 && mountPath.trim().length > 0 && !mutation.isPending

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (canSubmit) mutation.mutate()
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          Library name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Main Library"
          style={INPUT_STYLE}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = 'var(--aurora-accent)'
            e.currentTarget.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = 'var(--aurora-input-border)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          Mount path
        </label>
        <input
          type="text"
          value={mountPath}
          onChange={(e) => setMountPath(e.target.value)}
          placeholder="/library"
          style={INPUT_STYLE}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = 'var(--aurora-accent)'
            e.currentTarget.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = 'var(--aurora-input-border)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        />
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
          Absolute path inside the container, mounted from your host — e.g.{' '}
          <code style={{ background: 'var(--aurora-glass)', borderRadius: 4, padding: '1px 5px', fontSize: 11 }}>/library/main</code>
        </p>
      </div>

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 12px' }}>
          <AlertCircle size={14} style={{ color: '#EF4444', flexShrink: 0 }} />
          <span style={{ fontSize: 12, color: '#EF4444' }}>{error}</span>
        </div>
      )}

      <div>
        <button
          type="submit"
          disabled={!canSubmit}
          style={{ ...BTN_PRIMARY_STYLE, opacity: canSubmit ? 1 : 0.5, cursor: canSubmit ? 'pointer' : 'default' }}
        >
          <Plus size={14} />
          {mutation.isPending ? 'Adding…' : 'Add library'}
        </button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Library row
// ---------------------------------------------------------------------------

interface LibraryRowProps {
  library: api.LibraryOut
  onDisable: (id: number) => void
  isDisabling: boolean
  isLast?: boolean
}

function LibraryRow({ library, onDisable, isDisabling, isLast = false }: LibraryRowProps) {
  const handleDisable = () => {
    if (!window.confirm(`Disable library "${library.name}"? Items are not deleted.`)) return
    onDisable(library.id)
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '14px 18px',
        borderBottom: isLast ? 'none' : '1px solid var(--aurora-divider)',
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 8,
          background: library.enabled ? 'rgba(15,164,171,0.12)' : 'var(--aurora-glass)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <HardDrive
          size={17}
          style={{ color: library.enabled ? 'var(--aurora-accent)' : 'var(--aurora-muted)' }}
        />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--aurora-text)' }}>
            {library.name}
          </span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 20,
              letterSpacing: '0.06em',
              background: library.enabled ? 'rgba(15,164,171,0.12)' : 'var(--aurora-glass)',
              color: library.enabled ? 'var(--aurora-accent)' : 'var(--aurora-muted)',
              border: `1px solid ${library.enabled ? 'rgba(15,164,171,0.3)' : 'var(--aurora-glass-border)'}`,
            }}
          >
            {library.enabled ? 'enabled' : 'disabled'}
          </span>
        </div>
        <div
          style={{
            marginTop: 2,
            fontSize: 12,
            color: 'var(--aurora-muted)',
            fontFamily: 'monospace',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {library.mount_path}
        </div>
      </div>

      {library.enabled && (
        <button
          onClick={handleDisable}
          disabled={isDisabling}
          title="Disable library"
          style={{
            ...BTN_GHOST_STYLE,
            color: isDisabling ? 'var(--aurora-muted)' : '#EF4444',
            borderColor: isDisabling ? 'var(--aurora-glass-border)' : 'rgba(239,68,68,0.3)',
            opacity: isDisabling ? 0.5 : 1,
          }}
          onMouseEnter={(e) => {
            if (!isDisabling) {
              (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.08)'
            }
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
          }}
        >
          <Trash2 size={13} />
          Disable
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function LibrariesPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [disablingId, setDisablingId] = useState<number | null>(null)

  const { data: libraries = [], isLoading } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
  })

  const disableMutation = useMutation({
    mutationFn: (id: number) => api.disableLibrary(id),
    onMutate: (id) => setDisablingId(id),
    onSettled: () => {
      setDisablingId(null)
      void queryClient.invalidateQueries({ queryKey: ['libraries'] })
    },
  })

  const handleDisable = (id: number) => {
    disableMutation.mutate(id)
  }

  const handleAddSuccess = () => {
    setShowForm(false)
    void queryClient.invalidateQueries({ queryKey: ['libraries'] })
  }

  const enabledCount = libraries.filter((l) => l.enabled).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, color: 'var(--aurora-text)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--aurora-text)', letterSpacing: '-0.02em', margin: 0 }}>
            Libraries
          </h1>
          <p style={{ marginTop: 4, fontSize: 12, color: 'var(--aurora-muted)', margin: '4px 0 0' }}>
            {isLoading
              ? 'Loading…'
              : `${libraries.length} registered${enabledCount !== libraries.length ? ` (${enabledCount} enabled)` : ''}`}
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          style={{
            ...BTN_PRIMARY_STYLE,
            opacity: showForm ? 0.7 : 1,
          }}
        >
          <Plus size={14} />
          Add library
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div style={{ ...CARD_STYLE, padding: '20px 22px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)', marginBottom: 16 }}>
            Register a new library
          </div>
          <AddLibraryForm onSuccess={handleAddSuccess} />
        </div>
      )}

      {/* Library list */}
      <div style={CARD_STYLE}>
        {isLoading ? (
          <div style={{ padding: '36px 18px', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
            Loading…
          </div>
        ) : libraries.length === 0 ? (
          <div style={{ padding: '48px 18px', textAlign: 'center' }}>
            <HardDrive size={32} style={{ color: 'var(--aurora-muted)', margin: '0 auto 12px' }} />
            <p style={{ fontSize: 14, color: 'var(--aurora-text)', fontWeight: 600, margin: '0 0 6px' }}>
              No libraries yet
            </p>
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
              Add a library to start storing items. Make sure the path is mounted as a volume
              in both your backend and worker containers.
            </p>
          </div>
        ) : (
          <div>
            {libraries.map((lib, i) => (
              <LibraryRow
                key={lib.id}
                library={lib}
                onDisable={handleDisable}
                isDisabling={disablingId === lib.id}
                isLast={i === libraries.length - 1}
              />
            ))}
          </div>
        )}
      </div>

      {/* Help text */}
      <div
        style={{
          ...CARD_STYLE,
          padding: '14px 18px',
          borderColor: 'rgba(15,164,171,0.2)',
          background: 'rgba(15,164,171,0.04)',
        }}
      >
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--aurora-text-dim)' }}>How libraries work:</strong>{' '}
          Each library is a directory mounted into the container from your host (or a NAS/network share).
          The mount path you register here must be the absolute path <em>inside the container</em> — e.g.{' '}
          <code style={{ background: 'var(--aurora-glass)', borderRadius: 4, padding: '1px 5px' }}>/library</code>.
          Both the backend and worker containers must have the same volume mounted at the same path.
          Disabling a library hides it from the UI but does not delete any files.
        </p>
      </div>
    </div>
  )
}
