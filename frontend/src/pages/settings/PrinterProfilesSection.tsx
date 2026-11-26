/**
 * PrinterProfilesSection — per-user printer profiles (named presets of the
 * print-record settings fields). One may be the default; it pre-fills new
 * Log-print forms. Shown to every user on the Settings page.
 */

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { Card, Button, AuroraInput, AuroraSelect } from '@/components/ui'

const LABEL: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  display: 'block',
  marginBottom: 4,
}

interface Draft {
  name: string
  printer: string
  material: string
  filament_color: string
  nozzle_diameter: string
  layer_height: string
  supports: '' | 'true' | 'false'
}

const EMPTY_DRAFT: Draft = {
  name: '',
  printer: '',
  material: '',
  filament_color: '',
  nozzle_diameter: '',
  layer_height: '',
  supports: '',
}

function toDraft(p: api.PrinterProfile): Draft {
  return {
    name: p.name,
    printer: p.printer ?? '',
    material: p.material ?? '',
    filament_color: p.filament_color ?? '',
    nozzle_diameter: p.nozzle_diameter == null ? '' : String(p.nozzle_diameter),
    layer_height: p.layer_height == null ? '' : String(p.layer_height),
    supports: p.supports == null ? '' : p.supports ? 'true' : 'false',
  }
}

function toBody(d: Draft): api.PrinterProfileIn {
  return {
    name: d.name.trim(),
    printer: d.printer.trim() || null,
    material: d.material.trim() || null,
    filament_color: d.filament_color.trim() || null,
    nozzle_diameter: d.nozzle_diameter === '' ? null : Number(d.nozzle_diameter),
    layer_height: d.layer_height === '' ? null : Number(d.layer_height),
    supports: d.supports === '' ? null : d.supports === 'true',
  }
}

function summary(p: api.PrinterProfile): string {
  const parts = [
    p.printer,
    p.material,
    p.nozzle_diameter != null ? `${p.nozzle_diameter} mm nozzle` : null,
    p.layer_height != null ? `${p.layer_height} mm layer` : null,
  ].filter(Boolean)
  return parts.join(' · ')
}

function ProfileForm({
  initial,
  submitLabel,
  pending,
  error,
  onSubmit,
  onCancel,
}: {
  initial: Draft
  submitLabel: string
  pending: boolean
  error: string | null
  onSubmit: (d: Draft) => void
  onCancel: () => void
}) {
  const [d, setD] = useState<Draft>(initial)
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setD((x) => ({ ...x, [k]: e.target.value }))
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (d.name.trim()) onSubmit(d)
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      <div>
        <label style={LABEL} htmlFor="pp-name">Profile name</label>
        <AuroraInput
          id="pp-name"
          value={d.name}
          onChange={set('name')}
          placeholder="e.g. Bambu X1C — PLA 0.4"
          maxLength={255}
          required
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={LABEL} htmlFor="pp-printer">Printer</label>
          <AuroraInput id="pp-printer" value={d.printer} onChange={set('printer')} placeholder="e.g. Bambu X1C" />
        </div>
        <div>
          <label style={LABEL} htmlFor="pp-material">Material</label>
          <AuroraInput id="pp-material" value={d.material} onChange={set('material')} placeholder="e.g. PLA" />
        </div>
        <div>
          <label style={LABEL} htmlFor="pp-color">Filament color</label>
          <AuroraInput id="pp-color" value={d.filament_color} onChange={set('filament_color')} placeholder="e.g. Black" />
        </div>
        <div>
          <label style={LABEL} htmlFor="pp-supports">Supports</label>
          <AuroraSelect id="pp-supports" value={d.supports} onChange={set('supports')}>
            <option value="">Not set</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </AuroraSelect>
        </div>
        <div>
          <label style={LABEL} htmlFor="pp-nozzle">Nozzle (mm)</label>
          <AuroraInput id="pp-nozzle" type="number" step="0.1" min="0" value={d.nozzle_diameter} onChange={set('nozzle_diameter')} placeholder="0.4" />
        </div>
        <div>
          <label style={LABEL} htmlFor="pp-layer">Layer height (mm)</label>
          <AuroraInput id="pp-layer" type="number" step="0.01" min="0" value={d.layer_height} onChange={set('layer_height')} placeholder="0.20" />
        </div>
      </div>
      {error && (
        <p role="alert" style={{ margin: 0, fontSize: 12, color: 'var(--aurora-danger)' }}>{error}</p>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <Button type="submit" size="sm" disabled={pending || !d.name.trim()}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}

export function PrinterProfilesSection() {
  const qc = useQueryClient()
  const profilesQ = useQuery({
    queryKey: ['printer-profiles'],
    queryFn: api.listPrinterProfiles,
    staleTime: 60_000,
  })
  const profiles = profilesQ.data ?? []

  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)

  const refresh = () => qc.invalidateQueries({ queryKey: ['printer-profiles'] })
  const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed.')

  const createM = useMutation({
    mutationFn: (d: Draft) => api.createPrinterProfile(toBody(d)),
    onSuccess: () => { setAdding(false); void refresh() },
  })
  const updateM = useMutation({
    mutationFn: ({ id, d }: { id: number; d: Draft }) => api.updatePrinterProfile(id, toBody(d)),
    onSuccess: () => { setEditingId(null); void refresh() },
  })
  const defaultM = useMutation({
    mutationFn: (id: number) => api.updatePrinterProfile(id, { is_default: true }),
    onSuccess: () => void refresh(),
  })
  const deleteM = useMutation({
    mutationFn: (id: number) => api.deletePrinterProfile(id),
    onSuccess: () => { setConfirmDeleteId(null); void refresh() },
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
        Printer profiles
      </div>
      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {profilesQ.isLoading ? (
            <div style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Loading…</div>
          ) : profiles.length === 0 && !adding ? (
            <div style={{ fontSize: 12, color: 'var(--aurora-muted)', lineHeight: 1.7 }}>
              Save your printer, material, nozzle and layer settings as a profile, then load it
              into the Log-print form in one click. Mark one as the default to pre-fill every new print.
            </div>
          ) : null}

          {profiles.map((p) =>
            editingId === p.id ? (
              <ProfileForm
                key={p.id}
                initial={toDraft(p)}
                submitLabel="Save"
                pending={updateM.isPending}
                error={updateM.isError ? errMsg(updateM.error) : null}
                onSubmit={(d) => updateM.mutate({ id: p.id, d })}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div
                key={p.id}
                style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}
              >
                <div style={{ flex: 1, minWidth: 180 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)' }}>
                    {p.name}
                    {p.is_default && (
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: 10,
                          fontWeight: 700,
                          color: 'var(--aurora-accent)',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                        }}
                      >
                        Default
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{summary(p) || 'No settings'}</div>
                </div>
                {confirmDeleteId === p.id ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 12, color: 'var(--aurora-text-dim)' }}>Delete this profile?</span>
                    <Button variant="danger" size="sm" disabled={deleteM.isPending} onClick={() => deleteM.mutate(p.id)}>
                      Confirm delete
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirmDeleteId(null)}>Cancel</Button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 6 }}>
                    {!p.is_default && (
                      <Button variant="ghost" size="sm" disabled={defaultM.isPending} onClick={() => defaultM.mutate(p.id)}>
                        Set default
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => { setAdding(false); setEditingId(p.id) }}>
                      Edit
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => setConfirmDeleteId(p.id)}>
                      Delete
                    </Button>
                  </div>
                )}
              </div>
            ),
          )}

          {adding ? (
            <ProfileForm
              initial={EMPTY_DRAFT}
              submitLabel="Add profile"
              pending={createM.isPending}
              error={createM.isError ? errMsg(createM.error) : null}
              onSubmit={(d) => createM.mutate(d)}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <div>
              <Button size="sm" onClick={() => { createM.reset(); setEditingId(null); setAdding(true) }}>
                Add profile
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
