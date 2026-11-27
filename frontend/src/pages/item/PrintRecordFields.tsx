/**
 * PrintRecordFields — the shared print-record form fields (visibility, date,
 * outcome, rating, printer, material, filament, supports, nozzle, layer height,
 * note). Used by the item-page "Log a Print" modal and the catalog bulk
 * "Log print" dialog. Renders a fragment: the parent supplies the flex-column
 * (gap 14) container.
 */

import React, { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Save } from 'lucide-react'

import * as api from '@/lib/api'
import { renderStars } from '@/lib/print-utils'

import { AURORA_INPUT } from './styles'

export const PRINT_FIELD_LABEL_STYLE: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  display: 'block',
  marginBottom: 5,
}

/** Blank form state for a new record (today's date, private). */
export function blankPrintRecord(): api.PrintRecordIn {
  return {
    note: '',
    visibility: 'private',
    date: new Date().toISOString().split('T')[0],
    printer: '',
    material: '',
    filament_color: '',
    nozzle_diameter: null,
    layer_height: null,
    supports: null,
    success: null,
    rating: null,
  }
}

/** Convert form state to the request body (empty strings become null). */
export function normalizePrintRecord(form: api.PrintRecordIn): api.PrintRecordIn {
  return {
    ...form,
    printer: form.printer || null,
    material: form.material || null,
    filament_color: form.filament_color || null,
    note: form.note || null,
  }
}

/** Copy a profile's non-null settings into the form (null fields leave the form alone). */
export function applyPrinterProfile(
  form: api.PrintRecordIn,
  profile: api.PrinterProfile,
): api.PrintRecordIn {
  const next = { ...form }
  if (profile.printer != null) next.printer = profile.printer
  if (profile.material != null) next.material = profile.material
  if (profile.filament_color != null) next.filament_color = profile.filament_color
  if (profile.nozzle_diameter != null) next.nozzle_diameter = profile.nozzle_diameter
  if (profile.layer_height != null) next.layer_height = profile.layer_height
  if (profile.supports != null) next.supports = profile.supports
  return next
}

/** True when none of the six profile-controlled settings fields has a value. */
function settingsAreBlank(f: api.PrintRecordIn): boolean {
  return (
    !f.printer &&
    !f.material &&
    !f.filament_color &&
    f.nozzle_diameter == null &&
    f.layer_height == null &&
    f.supports == null
  )
}

interface PrintRecordFieldsProps {
  form: api.PrintRecordIn
  setForm: React.Dispatch<React.SetStateAction<api.PrintRecordIn>>
  /**
   * When true (new-record forms only), pre-fill the settings from the user's
   * default printer profile once, if the settings fields are still blank.
   */
  applyDefaultProfile?: boolean
}

export function PrintRecordFields({
  form,
  setForm,
  applyDefaultProfile = false,
}: PrintRecordFieldsProps) {
  const labelStyle = PRINT_FIELD_LABEL_STYLE
  const profilesQ = useQuery({
    queryKey: ['printer-profiles'],
    queryFn: api.listPrinterProfiles,
    staleTime: 60_000,
  })
  const profiles = profilesQ.data ?? []
  const [selectedId, setSelectedId] = useState('')
  const autoApplied = useRef(false)
  const qc = useQueryClient()
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveDefault, setSaveDefault] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [savedNote, setSavedNote] = useState(false)
  const nothingToSave = settingsAreBlank(form)

  function openSave() {
    setSaveName(form.printer ?? '')
    setSaveDefault(false)
    setSaveError(null)
    setSavedNote(false)
    setSaveOpen(true)
  }

  async function handleSaveProfile() {
    const name = saveName.trim()
    if (!name || nothingToSave || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      const created = await api.createPrinterProfile({
        name,
        printer: form.printer || null,
        material: form.material || null,
        filament_color: form.filament_color || null,
        nozzle_diameter: form.nozzle_diameter ?? null,
        layer_height: form.layer_height ?? null,
        supports: form.supports ?? null,
        is_default: saveDefault,
      })
      qc.setQueryData<api.PrinterProfile[]>(['printer-profiles'], (old) => [
        ...(old ?? []).map((p) => (saveDefault ? { ...p, is_default: false } : p)),
        created,
      ])
      void qc.invalidateQueries({ queryKey: ['printer-profiles'] })
      setSelectedId(String(created.id))
      setSaveOpen(false)
      setSavedNote(true)
    } catch (err) {
      const status = (err as { status?: number } | null)?.status
      const msg = err instanceof Error ? err.message : ''
      setSaveError(
        status === 409 || /409|already exists/i.test(msg)
          ? 'A profile with that name already exists.'
          : 'Could not save the profile. Please try again.',
      )
    } finally {
      setSaving(false)
    }
  }

  // Apply the default profile once, only if the user hasn't typed anything yet
  // (handles the profiles query resolving after the form opened).
  useEffect(() => {
    if (!applyDefaultProfile || autoApplied.current || !profilesQ.data) return
    autoApplied.current = true
    const def = profilesQ.data.find((p) => p.is_default)
    if (!def) return
    setSelectedId(String(def.id))
    setForm((f) => (settingsAreBlank(f) ? applyPrinterProfile(f, def) : f))
  }, [applyDefaultProfile, profilesQ.data, setForm])

  function handleProfileChange(v: string) {
    setSelectedId(v)
    const profile = profiles.find((p) => String(p.id) === v)
    if (profile) setForm((f) => applyPrinterProfile(f, profile))
  }

  return (
    <>
      {/* Load from printer profile / save as profile */}
      <div>
        {profiles.length > 0 && (
          <>
            <label style={labelStyle} htmlFor="print-profile-select">Load from profile</label>
            <select
              id="print-profile-select"
              value={selectedId}
              onChange={(e) => handleProfileChange(e.target.value)}
              style={AURORA_INPUT}
            >
              <option value="">Select a printer profile…</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.is_default ? ' (default)' : ''}
                </option>
              ))}
            </select>
          </>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: profiles.length > 0 ? 6 : 0 }}>
          <button
            type="button"
            onClick={() => (saveOpen ? setSaveOpen(false) : openSave())}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12,
              padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
              background: 'transparent', color: 'var(--aurora-muted)',
              border: '1px solid var(--aurora-border, currentColor)',
            }}
          >
            <Save size={13} aria-hidden="true" />
            Save as profile
          </button>
          {savedNote && !saveOpen && (
            <span role="status" style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Saved</span>
          )}
        </div>
        {saveOpen && (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input
              type="text"
              aria-label="New profile name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void handleSaveProfile()
                }
              }}
              placeholder="Profile name"
              maxLength={100}
              style={AURORA_INPUT}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={saveDefault}
                onChange={(e) => setSaveDefault(e.target.checked)}
              />
              Make default
            </label>
            {nothingToSave && (
              <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>
                Fill in at least one printer setting to save a profile.
              </span>
            )}
            {saveError && (
              <span role="alert" style={{ fontSize: 12, color: 'var(--aurora-danger, #e5484d)' }}>
                {saveError}
              </span>
            )}
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                disabled={!saveName.trim() || nothingToSave || saving}
                onClick={() => void handleSaveProfile()}
                style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, cursor: 'pointer' }}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button
                type="button"
                onClick={() => setSaveOpen(false)}
                style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, cursor: 'pointer' }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Visibility + Date */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>Visibility</label>
          <select
            value={form.visibility}
            onChange={(e) => setForm((f) => ({ ...f, visibility: e.target.value }))}
            style={AURORA_INPUT}
          >
            <option value="private">Private</option>
            <option value="public">Public</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Date</label>
          <input
            type="date"
            value={form.date ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, date: e.target.value || null }))}
            style={AURORA_INPUT}
          />
        </div>
      </div>

      {/* Outcome + Rating */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>Outcome</label>
          <select
            value={form.success == null ? '' : form.success ? 'true' : 'false'}
            onChange={(e) => {
              const v = e.target.value
              setForm((f) => ({
                ...f,
                success: v === '' ? null : v === 'true',
              }))
            }}
            style={AURORA_INPUT}
          >
            <option value="">Not recorded</option>
            <option value="true">Success</option>
            <option value="false">Failed</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Rating (1–5)</label>
          <select
            value={form.rating ?? ''}
            onChange={(e) => {
              const v = e.target.value
              setForm((f) => ({ ...f, rating: v === '' ? null : Number(v) }))
            }}
            style={AURORA_INPUT}
          >
            <option value="">None</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>{n} — {renderStars(n)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Printer + Material */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>Printer</label>
          <input
            type="text"
            value={form.printer ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, printer: e.target.value }))}
            placeholder="e.g. Bambu X1C"
            style={AURORA_INPUT}
          />
        </div>
        <div>
          <label style={labelStyle}>Material</label>
          <input
            type="text"
            value={form.material ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
            placeholder="e.g. PLA"
            style={AURORA_INPUT}
          />
        </div>
      </div>

      {/* Filament color + Supports */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>Filament color</label>
          <input
            type="text"
            value={form.filament_color ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, filament_color: e.target.value }))}
            placeholder="e.g. Black"
            style={AURORA_INPUT}
          />
        </div>
        <div>
          <label style={labelStyle}>Supports</label>
          <select
            value={form.supports == null ? '' : form.supports ? 'true' : 'false'}
            onChange={(e) => {
              const v = e.target.value
              setForm((f) => ({
                ...f,
                supports: v === '' ? null : v === 'true',
              }))
            }}
            style={AURORA_INPUT}
          >
            <option value="">Not recorded</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </div>
      </div>

      {/* Nozzle + Layer height */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={labelStyle}>Nozzle (mm)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={form.nozzle_diameter ?? ''}
            onChange={(e) => {
              const v = e.target.value
              setForm((f) => ({ ...f, nozzle_diameter: v === '' ? null : Number(v) }))
            }}
            placeholder="0.4"
            style={AURORA_INPUT}
          />
        </div>
        <div>
          <label style={labelStyle}>Layer height (mm)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.layer_height ?? ''}
            onChange={(e) => {
              const v = e.target.value
              setForm((f) => ({ ...f, layer_height: v === '' ? null : Number(v) }))
            }}
            placeholder="0.20"
            style={AURORA_INPUT}
          />
        </div>
      </div>

      {/* Note */}
      <div>
        <label style={labelStyle}>Note</label>
        <textarea
          rows={3}
          value={form.note ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
          placeholder="Any notes about this print…"
          style={{ ...AURORA_INPUT, resize: 'none', lineHeight: 1.5 }}
        />
      </div>
    </>
  )
}
