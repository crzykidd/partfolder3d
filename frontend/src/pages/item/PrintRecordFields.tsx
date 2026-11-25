/**
 * PrintRecordFields — the shared print-record form fields (visibility, date,
 * outcome, rating, printer, material, filament, supports, nozzle, layer height,
 * note). Used by the item-page "Log a Print" modal and the catalog bulk
 * "Log print" dialog. Renders a fragment: the parent supplies the flex-column
 * (gap 14) container.
 */

import React from 'react'

import type * as api from '@/lib/api'
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

interface PrintRecordFieldsProps {
  form: api.PrintRecordIn
  setForm: React.Dispatch<React.SetStateAction<api.PrintRecordIn>>
}

export function PrintRecordFields({ form, setForm }: PrintRecordFieldsProps) {
  const labelStyle = PRINT_FIELD_LABEL_STYLE
  return (
    <>
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
