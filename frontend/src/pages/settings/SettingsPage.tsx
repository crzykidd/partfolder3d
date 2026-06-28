/**
 * SettingsPage — instance settings (admin) + per-user theme.
 *
 * Instance settings (admin only):
 *   GET /api/settings → list key/value pairs
 *   PUT /api/settings/{key} → upsert a setting
 *
 * Per-user theme is handled by ThemeProvider + AuthContext (server-sync);
 * this page just renders the current ThemeToggle for context.
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/components/ThemeProvider'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Card, SectionHeader,
  Button,
  Field, AuroraInput,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Path prefix section
// ---------------------------------------------------------------------------

function PathPrefixSection() {
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ['path-prefix'],
    queryFn: api.getPathPrefix,
  })

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  // Sync draft when data arrives or editing is reset
  useEffect(() => {
    if (!editing) {
      setDraft(data?.path_prefix ?? '')
    }
  }, [data, editing])

  const mutation = useMutation({
    mutationFn: () => api.setPathPrefix(draft.trim() || null),
    onSuccess: () => {
      setEditing(false)
      void queryClient.invalidateQueries({ queryKey: ['path-prefix'] })
    },
  })

  const currentValue = data?.path_prefix ?? ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
        Path display
      </div>
      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--aurora-text)' }}>Path prefix</div>
          <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.6 }}>
            Prefix prepended to the item directory path on item pages — useful when
            your library is mounted at a different path locally (e.g.{' '}
            <code style={{ background: 'var(--aurora-glass)', borderRadius: 4, padding: '1px 5px', fontFamily: 'monospace', fontSize: 11 }}>C:\prints\</code>{' '}
            or{' '}
            <code style={{ background: 'var(--aurora-glass)', borderRadius: 4, padding: '1px 5px', fontFamily: 'monospace', fontSize: 11 }}>/mnt/nas/</code>).
          </div>
          {!editing && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
              <span style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--aurora-muted)' }}>
                {currentValue || <em>not set</em>}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft(currentValue)
                  setEditing(true)
                }}
              >
                Edit
              </Button>
            </div>
          )}
          {editing && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
              <AuroraInput
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="e.g. C:\prints\ or /mnt/nas/"
                style={{ flex: 1, fontFamily: 'monospace' }}
                autoFocus
              />
              <Button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                size="sm"
              >
                {mutation.isPending ? 'Saving…' : 'Save'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setEditing(false)
                  setDraft(currentValue)
                }}
              >
                Cancel
              </Button>
              {mutation.isError && (
                <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>Save failed</span>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Known instance settings
// ---------------------------------------------------------------------------

const KNOWN_SETTINGS: { key: string; label: string; description: string }[] = [
  {
    key: 'instance.name',
    label: 'Instance name',
    description: 'The display name for this PartFolder 3D instance.',
  },
  {
    key: 'instance.external_url',
    label: 'External URL',
    description: 'The public URL this instance is reachable at (used in share links).',
  },
  {
    key: 'instance.timezone',
    label: 'Timezone',
    description: 'Default timezone for scheduled jobs and display.',
  },
]

function SettingRow({
  settingKey,
  label,
  description,
  currentValue,
}: {
  settingKey: string
  label: string
  description: string
  currentValue: string
}) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(currentValue)

  // Sync draft when currentValue changes (e.g. after refetch).
  useEffect(() => {
    if (!editing) setDraft(currentValue)
  }, [currentValue, editing])

  const mutation = useMutation({
    mutationFn: () => api.upsertSetting(settingKey, draft),
    onSuccess: () => {
      setEditing(false)
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        paddingTop: 14,
        paddingBottom: 14,
        borderTop: '1px solid var(--aurora-divider)',
      }}
      className="first-of-type:border-t-0"
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)', marginBottom: 2 }}>{label}</div>
          <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.5 }}>{description}</div>
        </div>
        {!editing && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            <span style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--aurora-muted)' }}>
              {currentValue || <em>not set</em>}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(currentValue)
                setEditing(true)
              }}
            >
              Edit
            </Button>
          </div>
        )}
      </div>

      {editing && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
          <AuroraInput
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            style={{ flex: 1 }}
            autoFocus
          />
          <Button
            size="sm"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Saving…' : 'Save'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setEditing(false)
              setDraft(currentValue)
            }}
          >
            Cancel
          </Button>
          {mutation.isError && (
            <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
              {mutation.error instanceof api.ApiError
                ? mutation.error.message
                : 'Save failed'}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function SettingsPage() {
  const { user } = useAuth()
  const { theme } = useTheme()
  const isAdmin = user?.role === 'admin'

  const { data: settings = [], isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: api.listSettings,
    enabled: isAdmin,
  })

  // Build a key → string value map.
  const settingMap = new Map(
    settings.map((s) => [s.key, String(s.value ?? '')]),
  )

  return (
    <AdminPage>
      <PageHeader
        title="Settings"
        description="Configure your instance and personal preferences."
      />

      {/* Per-user theme */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
          Appearance
        </div>
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)', marginBottom: 2 }}>Theme</div>
              <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.5 }}>
                Current: <strong style={{ color: 'var(--aurora-text-dim)' }}>{theme}</strong>. Use the toggle in the header to change.
                When signed in, your preference is saved to the server.
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Per-user path prefix */}
      <PathPrefixSection />

      {/* Instance settings (admin only) */}
      {isAdmin && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
            Instance settings
          </div>
          {isLoading ? (
            <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
          ) : (
            <Card>
              {KNOWN_SETTINGS.map((s) => (
                <SettingRow
                  key={s.key}
                  settingKey={s.key}
                  label={s.label}
                  description={s.description}
                  currentValue={settingMap.get(s.key) ?? ''}
                />
              ))}
            </Card>
          )}
        </div>
      )}
    </AdminPage>
  )
}
