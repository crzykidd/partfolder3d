/**
 * SettingsPage — instance settings (admin) + per-user theme.
 *
 * Instance settings (admin only):
 *   GET /api/settings → list key/value pairs
 *   PUT /api/settings/{key} → upsert a setting
 *
 * Per-user theme is handled by ThemeProvider + AuthContext (server-sync);
 * this page just renders the current ThemeToggle for context.
 */

import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/components/ThemeProvider'
import * as api from '@/lib/api'

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
    <section>
      <h2 className="text-lg font-semibold mb-3">Path display</h2>
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-col gap-1 py-1">
          <div className="text-sm font-medium">Path prefix</div>
          <div className="text-xs text-muted-foreground">
            Prefix prepended to the item directory path on item pages — useful when
            your library is mounted at a different path locally (e.g.{' '}
            <code className="font-mono">C:\prints\</code> or{' '}
            <code className="font-mono">/mnt/nas/</code>).
          </div>
          {!editing && (
            <div className="flex items-center gap-3 mt-2">
              <span className="font-mono text-sm text-muted-foreground">
                {currentValue || <em>not set</em>}
              </span>
              <button
                onClick={() => {
                  setDraft(currentValue)
                  setEditing(true)
                }}
                className="text-xs text-primary hover:underline"
              >
                Edit
              </button>
            </div>
          )}
          {editing && (
            <div className="flex items-center gap-2 mt-2">
              <input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="e.g. C:\prints\ or /mnt/nas/"
                className="input-base flex-1 text-sm font-mono"
                autoFocus
              />
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {mutation.isPending ? 'Saving…' : 'Save'}
              </button>
              <button
                onClick={() => {
                  setEditing(false)
                  setDraft(currentValue)
                }}
                className="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
              >
                Cancel
              </button>
              {mutation.isError && (
                <span className="text-xs text-destructive">Save failed</span>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

// Known instance settings with friendly labels.
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
      queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  return (
    <div className="flex flex-col gap-1 py-3 border-t border-border first:border-t-0">
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1">
          <div className="text-sm font-medium">{label}</div>
          <div className="text-xs text-muted-foreground">{description}</div>
        </div>
        {!editing && (
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm text-muted-foreground">
              {currentValue || <em>not set</em>}
            </span>
            <button
              onClick={() => {
                setDraft(currentValue)
                setEditing(true)
              }}
              className="text-xs text-primary hover:underline"
            >
              Edit
            </button>
          </div>
        )}
      </div>

      {editing && (
        <div className="flex items-center gap-2 mt-1">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="input-base flex-1 text-sm"
            autoFocus
          />
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {mutation.isPending ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={() => {
              setEditing(false)
              setDraft(currentValue)
            }}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
          >
            Cancel
          </button>
          {mutation.isError && (
            <span className="text-xs text-destructive">
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
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure your instance and personal preferences.
        </p>
      </div>

      {/* Per-user theme */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Appearance</h2>
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Theme</div>
              <div className="text-xs text-muted-foreground">
                Current: <strong>{theme}</strong>. Use the toggle in the header to change.
                When signed in, your preference is saved to the server.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Per-user path prefix */}
      <PathPrefixSection />

      {/* Instance settings (admin only) */}
      {isAdmin && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Instance settings</h2>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="rounded-lg border border-border bg-card p-4">
              {KNOWN_SETTINGS.map((s) => (
                <SettingRow
                  key={s.key}
                  settingKey={s.key}
                  label={s.label}
                  description={s.description}
                  currentValue={settingMap.get(s.key) ?? ''}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
