/**
 * SettingsPage — instance settings (admin) + per-user theme + per-library paths.
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
  type RenderMode,
  RENDER_MODE_LABELS,
  IMPORT_DEFAULT_LIBRARY_KEY,
  setRenderMode,
  setDefaultImportLibrary,
} from '@/lib/api/settings'
import { detectOS, rewriteLocalPath } from '@/lib/catalog-utils'
import {
  AdminPage, PageHeader,
  Card,
  Button, FilterPill,
  AuroraInput,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// OS override — stored in localStorage so it survives page reloads.
// Values: 'windows' | 'posix' | 'auto'  (default 'auto')
// ---------------------------------------------------------------------------

const OS_OVERRIDE_KEY = 'pf3d_os_override'

type OSOverride = 'windows' | 'posix' | 'auto'

function readOSOverride(): OSOverride {
  try {
    const v = localStorage.getItem(OS_OVERRIDE_KEY)
    if (v === 'windows' || v === 'posix' || v === 'auto') return v
  } catch { /* ignore */ }
  return 'auto'
}

function writeOSOverride(v: OSOverride): void {
  try { localStorage.setItem(OS_OVERRIDE_KEY, v) } catch { /* ignore */ }
}

function getEffectiveOS(override: OSOverride): 'windows' | 'posix' {
  return override === 'auto' ? detectOS() : override
}

// ---------------------------------------------------------------------------
// Per-library path prefixes section
// ---------------------------------------------------------------------------

const INLINE_CODE: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  borderRadius: 4,
  padding: '1px 5px',
  fontFamily: 'monospace',
  fontSize: 11,
}

const PREVIEW_BOX: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 6,
  padding: '6px 10px',
}

/** Build a sample container path for a library — used for live preview. */
function sampleContainerPath(mountPath: string): string {
  return `${mountPath}/Sample-Creator/Cool-Thing-abc123`
}

interface LibraryRowDraft {
  windows: string
  posix: string
}

function PathPrefixesSection() {
  const queryClient = useQueryClient()

  const librariesQ = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 60_000,
  })

  const prefixesQ = useQuery({
    queryKey: ['path-prefixes'],
    queryFn: api.getPathPrefixes,
    staleTime: 60_000,
  })

  const [osOverride, setOSOverride] = useState<OSOverride>(readOSOverride)
  const [editing, setEditing] = useState(false)
  // draft: library_id (string) → {windows, posix}
  const [draft, setDraft] = useState<Record<string, LibraryRowDraft>>({})

  const libraries = librariesQ.data ?? []
  const savedPrefixes = prefixesQ.data?.path_prefixes ?? {}

  // When data arrives (or editing is cancelled), reset draft to saved state.
  useEffect(() => {
    if (!editing) {
      const next: Record<string, LibraryRowDraft> = {}
      for (const lib of libraries) {
        const entry = savedPrefixes[String(lib.id)]
        next[String(lib.id)] = {
          windows: entry?.windows ?? '',
          posix: entry?.posix ?? '',
        }
      }
      setDraft(next)
    }
  }, [savedPrefixes, libraries, editing])

  const mutation = useMutation({
    mutationFn: () => {
      // Convert draft to PathPrefixMap, treating '' as null
      const map: api.PathPrefixMap = {}
      for (const lib of libraries) {
        const row = draft[String(lib.id)] ?? { windows: '', posix: '' }
        map[String(lib.id)] = {
          windows: row.windows.trim() || null,
          posix: row.posix.trim() || null,
        }
      }
      return api.setPathPrefixes(map)
    },
    onSuccess: () => {
      setEditing(false)
      void queryClient.invalidateQueries({ queryKey: ['path-prefixes'] })
    },
  })

  function handleOSOverride(v: OSOverride) {
    setOSOverride(v)
    writeOSOverride(v)
  }

  function startEdit() {
    // Seed draft from saved data before entering edit mode.
    const next: Record<string, LibraryRowDraft> = {}
    for (const lib of libraries) {
      const entry = savedPrefixes[String(lib.id)]
      next[String(lib.id)] = {
        windows: entry?.windows ?? '',
        posix: entry?.posix ?? '',
      }
    }
    setDraft(next)
    setEditing(true)
  }

  function cancelEdit() {
    setEditing(false)
    // draft will be reset by the useEffect above
  }

  const effectiveOS = getEffectiveOS(osOverride)
  const isLoading = librariesQ.isLoading || prefixesQ.isLoading

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
        Path display
      </div>
      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Description */}
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--aurora-text)', marginBottom: 4 }}>
              Per-library path prefixes
            </div>
            <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.7 }}>
              Maps each library's stored paths to where <em>you</em> open the files on your
              machine or NAS. Set a prefix per library so different mounts work independently.
              PartFolder 3D auto-detects whether you are on Windows or Mac/Linux and applies
              the right separator style.
            </div>
            <div style={{ fontSize: 12, color: 'var(--aurora-muted)', marginTop: 4, lineHeight: 1.7 }}>
              Windows example:{' '}
              <code style={INLINE_CODE}>Z:\3dprints\</code>.{' '}
              Mac / Linux example:{' '}
              <code style={INLINE_CODE}>/mnt/nas/3dprints/</code>.
            </div>
          </div>

          {/* This-browser OS override */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--aurora-text-dim)', marginBottom: 6 }}>
              This browser
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <FilterPill active={osOverride === 'auto'} onClick={() => handleOSOverride('auto')}>
                Auto-detect
              </FilterPill>
              <FilterPill active={osOverride === 'windows'} onClick={() => handleOSOverride('windows')}>
                Windows <code style={{ fontFamily: 'monospace', fontSize: 11 }}>\</code>
              </FilterPill>
              <FilterPill active={osOverride === 'posix'} onClick={() => handleOSOverride('posix')}>
                Mac / Linux <code style={{ fontFamily: 'monospace', fontSize: 11 }}>/</code>
              </FilterPill>
            </div>
            <div style={{ fontSize: 11, color: 'var(--aurora-muted)', marginTop: 5 }}>
              Detected OS: <strong>{effectiveOS === 'windows' ? 'Windows' : 'Mac / Linux'}</strong>
              {osOverride !== 'auto' && ' (manual override — stored in this browser)'}
            </div>
          </div>

          {/* Library table */}
          {isLoading ? (
            <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
          ) : libraries.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
              No libraries configured yet. Add a library first.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {libraries.map((lib) => {
                const libIdStr = String(lib.id)
                const row = editing
                  ? (draft[libIdStr] ?? { windows: '', posix: '' })
                  : {
                      windows: savedPrefixes[libIdStr]?.windows ?? '',
                      posix: savedPrefixes[libIdStr]?.posix ?? '',
                    }
                const currentPrefix = effectiveOS === 'windows' ? row.windows : row.posix
                const sample = sampleContainerPath(lib.mount_path)
                const preview = rewriteLocalPath(
                  sample,
                  lib.mount_path,
                  currentPrefix || null,
                  effectiveOS,
                )

                function setRow(field: 'windows' | 'posix', value: string) {
                  setDraft((prev) => ({
                    ...prev,
                    [libIdStr]: { ...(prev[libIdStr] ?? { windows: '', posix: '' }), [field]: value },
                  }))
                }

                return (
                  <div
                    key={lib.id}
                    style={{
                      borderTop: '1px solid var(--aurora-divider)',
                      paddingTop: 12,
                    }}
                  >
                    {/* Library name + mount */}
                    <div style={{ marginBottom: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)' }}>
                        {lib.name}
                      </span>
                      <code
                        style={{
                          marginLeft: 8,
                          fontSize: 11,
                          color: 'var(--aurora-muted)',
                          fontFamily: 'monospace',
                        }}
                      >
                        {lib.mount_path}
                      </code>
                      {!lib.enabled && (
                        <span
                          style={{
                            marginLeft: 6,
                            fontSize: 10,
                            fontWeight: 600,
                            background: 'var(--aurora-glass)',
                            border: '1px solid var(--aurora-glass-border)',
                            borderRadius: 20,
                            padding: '1px 7px',
                            color: 'var(--aurora-muted)',
                          }}
                        >
                          disabled
                        </span>
                      )}
                    </div>

                    {/* Path inputs */}
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      <div style={{ flex: 1, minWidth: 180 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--aurora-text-dim)', marginBottom: 4 }}>
                          Windows path <code style={INLINE_CODE}>\</code>
                        </div>
                        {editing ? (
                          <AuroraInput
                            type="text"
                            value={row.windows}
                            onChange={(e) => setRow('windows', e.target.value)}
                            placeholder="e.g. Z:\3dprints\"
                            style={{ fontFamily: 'monospace', fontSize: 12 }}
                          />
                        ) : (
                          <span style={{ fontFamily: 'monospace', fontSize: 12, color: row.windows ? 'var(--aurora-text-dim)' : 'var(--aurora-muted)' }}>
                            {row.windows || <em>not set</em>}
                          </span>
                        )}
                      </div>

                      <div style={{ flex: 1, minWidth: 180 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--aurora-text-dim)', marginBottom: 4 }}>
                          Mac / Linux path <code style={INLINE_CODE}>/</code>
                        </div>
                        {editing ? (
                          <AuroraInput
                            type="text"
                            value={row.posix}
                            onChange={(e) => setRow('posix', e.target.value)}
                            placeholder="e.g. /mnt/nas/3dprints/"
                            style={{ fontFamily: 'monospace', fontSize: 12 }}
                          />
                        ) : (
                          <span style={{ fontFamily: 'monospace', fontSize: 12, color: row.posix ? 'var(--aurora-text-dim)' : 'var(--aurora-muted)' }}>
                            {row.posix || <em>not set</em>}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Live preview for this row */}
                    <div style={{ ...PREVIEW_BOX, marginTop: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--aurora-text-dim)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Preview ({effectiveOS === 'windows' ? 'Windows' : 'Mac / Linux'})
                      </div>
                      <code style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--aurora-text)', wordBreak: 'break-all' }}>
                        {preview}
                      </code>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Action buttons */}
          {libraries.length > 0 && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingTop: 4 }}>
              {!editing ? (
                <Button size="sm" onClick={startEdit}>
                  Edit
                </Button>
              ) : (
                <>
                  <Button
                    size="sm"
                    onClick={() => mutation.mutate()}
                    disabled={mutation.isPending}
                  >
                    {mutation.isPending ? 'Saving…' : 'Save'}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={cancelEdit}>
                    Cancel
                  </Button>
                  {mutation.isError && (
                    <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>Save failed</span>
                  )}
                </>
              )}
            </div>
          )}

        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Render mode setting (select control, admin only)
// ---------------------------------------------------------------------------

const RENDER_MODE_SETTING_KEY = 'render.mode'

function RenderModeRow({ currentValue }: { currentValue: string }) {
  const queryClient = useQueryClient()
  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: (value: RenderMode) => setRenderMode(value),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  // Normalise the stored value; fall back to 'all' if absent or unrecognised.
  const safeValue: RenderMode =
    currentValue === 'all' || currentValue === 'no_images' || currentValue === 'off'
      ? currentValue
      : 'all'

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
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)', marginBottom: 2 }}>
            Background render mode
          </div>
          <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.5 }}>
            Controls when mesh thumbnails are automatically rendered.
            Overrides the server's <code style={{ fontFamily: 'monospace', fontSize: 11 }}>RENDER_MODE</code> env variable.
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {saved && (
            <span style={{ fontSize: 12, color: 'var(--aurora-accent)' }}>Saved</span>
          )}
          {mutation.isError && (
            <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>Save failed</span>
          )}
          <select
            value={safeValue}
            disabled={mutation.isPending}
            onChange={(e) => mutation.mutate(e.target.value as RenderMode)}
            style={{
              fontSize: 13,
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid var(--aurora-glass-border)',
              background: 'var(--aurora-glass)',
              color: 'var(--aurora-text)',
              cursor: 'pointer',
            }}
          >
            {(Object.entries(RENDER_MODE_LABELS) as [RenderMode, string][]).map(
              ([value, label]) => (
                <option key={value} value={value}>{label}</option>
              )
            )}
          </select>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Default import library setting (select + clear, admin only)
// ---------------------------------------------------------------------------

function DefaultImportLibraryRow({ currentValue }: { currentValue: string }) {
  const queryClient = useQueryClient()
  const [saved, setSaved] = useState(false)

  const { data: libraries = [] } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 60_000,
  })

  const enabledLibraries = (libraries as api.LibraryOut[]).filter((l) => l.enabled)

  const mutation = useMutation({
    mutationFn: (libId: number | null) => setDefaultImportLibrary(libId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  // Parse the stored value (JSON-encoded int or null)
  const currentLibId = currentValue !== '' ? Number(currentValue) : null

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
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)', marginBottom: 2 }}>
            Default import library
          </div>
          <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.5 }}>
            Library used automatically during bulk commit and inbox scanning when a session
            has no explicit library set.  When unset, the sole enabled library is used
            (if only one exists).
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          {saved && (
            <span style={{ fontSize: 12, color: 'var(--aurora-accent)' }}>Saved</span>
          )}
          {mutation.isError && (
            <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>Save failed</span>
          )}
          <select
            value={currentLibId ?? ''}
            disabled={mutation.isPending}
            onChange={(e) => {
              const val = e.target.value === '' ? null : Number(e.target.value)
              mutation.mutate(val)
            }}
            style={{
              fontSize: 13,
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid var(--aurora-glass-border)',
              background: 'var(--aurora-glass)',
              color: 'var(--aurora-text)',
              cursor: 'pointer',
              minWidth: 160,
            }}
          >
            <option value="">— None (auto) —</option>
            {enabledLibraries.map((lib) => (
              <option key={lib.id} value={lib.id}>
                {lib.name}
              </option>
            ))}
          </select>
        </div>
      </div>
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

      {/* Per-library × per-OS path prefixes */}
      <PathPrefixesSection />

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
              <RenderModeRow
                currentValue={settingMap.get(RENDER_MODE_SETTING_KEY) ?? ''}
              />
              <DefaultImportLibraryRow
                currentValue={settingMap.get(IMPORT_DEFAULT_LIBRARY_KEY) ?? ''}
              />
            </Card>
          )}
        </div>
      )}
    </AdminPage>
  )
}
