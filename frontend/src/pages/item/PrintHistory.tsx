import React, { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X as XIcon } from 'lucide-react'

import * as api from '@/lib/api'
import { formatPrintTime, formatFilamentLength, formatFilamentWeight, renderStars } from '@/lib/print-utils'

import { AURORA_INPUT, AURORA_BTN_PRIMARY, AURORA_BTN_GHOST } from './styles'

// ---------------------------------------------------------------------------
// Print record form (inline modal overlay)
// ---------------------------------------------------------------------------

interface PrintRecordFormProps {
  itemKey: string
  existing?: api.PrintRecord
  onClose: () => void
  onSaved: (rec: api.PrintRecord) => void
}

function PrintRecordForm({ itemKey, existing, onClose, onSaved }: PrintRecordFormProps) {
  const today = new Date().toISOString().split('T')[0]
  const [form, setForm] = useState<api.PrintRecordIn>({
    note: existing?.note ?? '',
    visibility: existing?.visibility ?? 'private',
    date: existing?.date ?? today,
    printer: existing?.printer ?? '',
    material: existing?.material ?? '',
    filament_color: existing?.filament_color ?? '',
    nozzle_diameter: existing?.nozzle_diameter ?? null,
    layer_height: existing?.layer_height ?? null,
    supports: existing?.supports ?? null,
    success: existing?.success ?? null,
    rating: existing?.rating ?? null,
  })
  const [submitError, setSubmitError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: (body: api.PrintRecordIn) => api.createPrintRecord(itemKey, body),
    onSuccess: (rec) => { onSaved(rec) },
    onError: (e) => setSubmitError(e instanceof Error ? e.message : 'Failed to save.'),
  })

  const updateMutation = useMutation({
    mutationFn: (body: api.PrintRecordPatch) =>
      api.updatePrintRecord(itemKey, existing!.id, body),
    onSuccess: (rec) => { onSaved(rec) },
    onError: (e) => setSubmitError(e instanceof Error ? e.message : 'Failed to save.'),
  })

  const isPending = createMutation.isPending || updateMutation.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    const body: api.PrintRecordIn = {
      ...form,
      printer: form.printer || null,
      material: form.material || null,
      filament_color: form.filament_color || null,
      note: form.note || null,
    }
    if (existing) {
      updateMutation.mutate(body)
    } else {
      createMutation.mutate(body)
    }
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--aurora-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    display: 'block',
    marginBottom: 5,
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(5,13,28,0.82)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        padding: 16,
      } as React.CSSProperties}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--aurora-palette-bg)',
          border: '1px solid var(--aurora-palette-border)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
          backdropFilter: 'blur(40px)',
          WebkitBackdropFilter: 'blur(40px)',
          width: '100%',
          maxWidth: 520,
          maxHeight: '90vh',
          overflowY: 'auto',
        } as React.CSSProperties}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 18px',
            borderBottom: '1px solid var(--aurora-divider)',
          }}
        >
          <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
            {existing ? 'Edit Print Record' : 'Log a Print'}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: '50%',
              width: 28,
              height: 28,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: 'var(--aurora-muted)',
            }}
          >
            <XIcon size={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
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

          {submitError && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{submitError}</p>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 4 }}>
            <button
              type="button"
              onClick={onClose}
              style={AURORA_BTN_GHOST}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              style={{ ...AURORA_BTN_PRIMARY, opacity: isPending ? 0.5 : 1 }}
            >
              {isPending ? 'Saving…' : existing ? 'Save changes' : 'Log print'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Print record card
// ---------------------------------------------------------------------------

interface PrintRecordCardProps {
  record: api.PrintRecord
  itemKey: string
  onUpdated: (rec: api.PrintRecord) => void
  onDeleted: (id: number) => void
}

function PrintRecordCard({ record, itemKey, onUpdated, onDeleted }: PrintRecordCardProps) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [gcodeInput, setGcodeInput] = useState<HTMLInputElement | null>(null)
  const [photoInput, setPhotoInput] = useState<HTMLInputElement | null>(null)
  const [uploadingGcode, setUploadingGcode] = useState(false)
  const [uploadingPhoto, setUploadingPhoto] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: () => api.deletePrintRecord(itemKey, record.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['print-records', itemKey] })
      onDeleted(record.id)
    },
  })

  async function handleGcodeUpload(file: File) {
    setUploadingGcode(true)
    setUploadError(null)
    try {
      const updated = await api.uploadGcode(itemKey, record.id, file)
      onUpdated(updated)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed.')
    } finally {
      setUploadingGcode(false)
    }
  }

  async function handlePhotoUpload(file: File) {
    setUploadingPhoto(true)
    setUploadError(null)
    try {
      const updated = await api.uploadPrintPhoto(itemKey, record.id, file)
      onUpdated(updated)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed.')
    } finally {
      setUploadingPhoto(false)
    }
  }

  return (
    <>
      {editing && (
        <PrintRecordForm
          itemKey={itemKey}
          existing={record}
          onClose={() => setEditing(false)}
          onSaved={(rec) => {
            setEditing(false)
            onUpdated(rec)
          }}
        />
      )}

      <div
        style={{
          background: 'var(--aurora-glass)',
          border: '1px solid var(--aurora-card-border)',
          borderRadius: 10,
          padding: '12px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
            {/* Visibility badge */}
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px 8px',
                borderRadius: 20,
                fontSize: 10,
                fontWeight: 700,
                background: record.visibility === 'public' ? 'rgba(34,197,94,0.15)' : 'var(--aurora-glass)',
                color: record.visibility === 'public' ? '#22C55E' : 'var(--aurora-muted)',
                border: `1px solid ${record.visibility === 'public' ? 'rgba(34,197,94,0.3)' : 'var(--aurora-glass-border)'}`,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {record.visibility}
            </span>

            {/* Outcome chip */}
            {record.success != null && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: '2px 8px',
                  borderRadius: 20,
                  fontSize: 10,
                  fontWeight: 700,
                  background: record.success ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                  color: record.success ? '#22C55E' : '#EF4444',
                  border: `1px solid ${record.success ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                }}
              >
                {record.success ? '✓ Success' : '✗ Failed'}
              </span>
            )}

            {/* Rating */}
            {record.rating != null && (
              <span style={{ fontSize: 13, color: '#F59E0B' }} title={`Rating: ${record.rating}/5`}>
                {renderStars(record.rating)}
              </span>
            )}

            {/* Date */}
            {record.date && (
              <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{record.date}</span>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
            <button
              onClick={() => setEditing(true)}
              style={{
                ...AURORA_BTN_GHOST,
                fontSize: 11,
                padding: '3px 9px',
              }}
            >
              Edit
            </button>
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                style={{
                  ...AURORA_BTN_GHOST,
                  fontSize: 11,
                  padding: '3px 9px',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'rgba(239,68,68,0.12)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = '#EF4444'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(239,68,68,0.3)'
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
                  ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text-dim)'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
                }}
              >
                Delete
              </button>
            ) : (
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                  style={{
                    background: '#EF4444',
                    border: 'none',
                    borderRadius: 20,
                    color: '#FFF',
                    fontSize: 11,
                    padding: '3px 9px',
                    cursor: 'pointer',
                    opacity: deleteMutation.isPending ? 0.5 : 1,
                  }}
                >
                  {deleteMutation.isPending ? '…' : 'Confirm'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 9px' }}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Settings row */}
        {(record.printer || record.material || record.filament_color ||
          record.nozzle_diameter != null || record.layer_height != null) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 11, color: 'var(--aurora-text-dim)' }}>
            {record.printer && <span>Printer: {record.printer}</span>}
            {record.material && <span>Material: {record.material}</span>}
            {record.filament_color && <span>Color: {record.filament_color}</span>}
            {record.nozzle_diameter != null && <span>Nozzle: {record.nozzle_diameter}mm</span>}
            {record.layer_height != null && <span>Layer: {record.layer_height}mm</span>}
            {record.supports != null && <span>Supports: {record.supports ? 'Yes' : 'No'}</span>}
          </div>
        )}

        {/* Gcode stats (parsed) */}
        {(record.filament_length_mm != null || record.filament_weight_g != null ||
          record.estimated_print_time_s != null) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 11, color: 'var(--aurora-text-dim)' }}>
            {record.filament_length_mm != null && (
              <span>Filament: {formatFilamentLength(record.filament_length_mm)}</span>
            )}
            {record.filament_weight_g != null && (
              <span>Weight: {formatFilamentWeight(record.filament_weight_g)}</span>
            )}
            {record.estimated_print_time_s != null && (
              <span>Time: {formatPrintTime(record.estimated_print_time_s)}</span>
            )}
          </div>
        )}

        {/* Note */}
        {record.note && (
          <p style={{ fontSize: 12, color: 'var(--aurora-text-dim)', lineHeight: 1.6, whiteSpace: 'pre-wrap', margin: 0 }}>
            {record.note}
          </p>
        )}

        {/* File uploads */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingTop: 2 }}>
          <button
            onClick={() => gcodeInput?.click()}
            disabled={uploadingGcode}
            style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 10px', opacity: uploadingGcode ? 0.5 : 1 }}
          >
            {uploadingGcode ? 'Uploading…' : record.gcode_file_path ? 'Replace gcode' : 'Upload gcode'}
          </button>
          <input
            ref={setGcodeInput}
            type="file"
            accept=".gcode,.bgcode,.gco"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handleGcodeUpload(file)
              e.target.value = ''
            }}
          />

          <button
            onClick={() => photoInput?.click()}
            disabled={uploadingPhoto}
            style={{ ...AURORA_BTN_GHOST, fontSize: 11, padding: '3px 10px', opacity: uploadingPhoto ? 0.5 : 1 }}
          >
            {uploadingPhoto ? 'Uploading…' : record.print_photo_path ? 'Replace photo' : 'Upload photo'}
          </button>
          <input
            ref={setPhotoInput}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handlePhotoUpload(file)
              e.target.value = ''
            }}
          />
        </div>

        {uploadError && (
          <p style={{ fontSize: 11, color: 'var(--aurora-danger)', margin: 0 }}>{uploadError}</p>
        )}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Print History section
// ---------------------------------------------------------------------------

export interface PrintHistorySectionProps {
  itemKey: string
}

export function PrintHistorySection({ itemKey }: PrintHistorySectionProps) {
  const queryClient = useQueryClient()
  const [addingRecord, setAddingRecord] = useState(false)
  const [records, setRecords] = useState<api.PrintRecord[]>([])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['print-records', itemKey],
    queryFn: () => api.listPrintRecords(itemKey),
    staleTime: 30_000,
  })

  useEffect(() => {
    if (data) setRecords(data)
  }, [data])

  function handleUpdated(updated: api.PrintRecord) {
    setRecords((prev) =>
      prev.map((r) => (r.id === updated.id ? updated : r)),
    )
    void queryClient.invalidateQueries({ queryKey: ['print-records', itemKey] })
  }

  function handleDeleted(id: number) {
    setRecords((prev) => prev.filter((r) => r.id !== id))
  }

  function handleSaved(rec: api.PrintRecord) {
    setAddingRecord(false)
    setRecords((prev) => [rec, ...prev])
    void queryClient.invalidateQueries({ queryKey: ['print-records', itemKey] })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {addingRecord && (
        <PrintRecordForm
          itemKey={itemKey}
          onClose={() => setAddingRecord(false)}
          onSaved={handleSaved}
        />
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
          {records.length > 0 ? `${records.length} record(s)` : ''}
        </span>
        <button
          onClick={() => setAddingRecord(true)}
          style={AURORA_BTN_PRIMARY}
        >
          + Log a print
        </button>
      </div>

      {isLoading && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>Loading…</p>
      )}

      {isError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>Failed to load print records.</p>
      )}

      {!isLoading && !isError && records.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
          No print records yet. Log your first print above.
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {records.map((rec) => (
          <PrintRecordCard
            key={rec.id}
            record={rec}
            itemKey={itemKey}
            onUpdated={handleUpdated}
            onDeleted={handleDeleted}
          />
        ))}
      </div>
    </div>
  )
}
