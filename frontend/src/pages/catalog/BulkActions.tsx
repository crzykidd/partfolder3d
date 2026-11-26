/**
 * BulkActions — sticky bottom action bar + dialogs for catalog multi-select.
 *
 * Actions: Log print, Tags, Move, More ▾ (Rescan, Delete). Each dialog shows an
 * inline succeeded/failed summary after completion (no toast library). Failed
 * items stay selected for retry; succeeded items are dropped from the selection
 * after delete/move.
 *
 * Modals are hand-rolled portals (role="dialog") matching the item-page
 * print-record modal — Radix Dialog is not a dependency of this project.
 */

import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, FolderInput, MoreHorizontal, Printer, Tags, X } from 'lucide-react'

import * as api from '@/lib/api'
import { addConfirmedTag, removeConfirmedTag } from '@/lib/import-utils'
import {
  PrintRecordFields,
  blankPrintRecord,
  normalizePrintRecord,
} from '@/pages/item/PrintRecordFields'
import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY, AURORA_INPUT } from '@/pages/item/styles'
import type { CatalogSelection, SelectableItem } from './useCatalogSelection'

type DialogKind = 'print' | 'tags' | 'move' | 'rescan' | 'delete'

/** Normalised per-item outcome shared by every bulk action. */
interface Outcome {
  succeeded: string[]
  failed: { key: string; error: string }[]
}

// ---------------------------------------------------------------------------
// Modal shell
// ---------------------------------------------------------------------------

function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return createPortal(
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
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
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{
          background: 'var(--aurora-palette-bg)',
          border: '1px solid var(--aurora-palette-border)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
          width: '100%',
          maxWidth: 520,
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 18px',
            borderBottom: '1px solid var(--aurora-divider)',
          }}
        >
          <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
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
            <X size={14} />
          </button>
        </div>
        <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  )
}

const SUB_LABEL: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  display: 'block',
  marginBottom: 5,
}

function TitleList({ titles }: { titles: string[] }) {
  return (
    <ul
      aria-label="Selected items"
      style={{
        margin: 0,
        padding: '6px 12px 6px 26px',
        maxHeight: 110,
        overflowY: 'auto',
        fontSize: 12,
        color: 'var(--aurora-text-dim)',
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 8,
      }}
    >
      {titles.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </ul>
  )
}

function ResultSummary({
  outcome,
  verb,
  titleOf,
}: {
  outcome: Outcome
  verb: string
  titleOf: (key: string) => string
}) {
  return (
    <div role="status" style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12 }}>
      <p style={{ margin: 0, color: 'var(--aurora-text)', fontWeight: 600 }}>
        {outcome.succeeded.length} {verb}
        {outcome.failed.length > 0 && `, ${outcome.failed.length} failed`}
      </p>
      {outcome.failed.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--aurora-danger)' }}>
          {outcome.failed.map((f) => (
            <li key={f.key}>
              {titleOf(f.key)}: {f.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Footer({
  done,
  onClose,
  submitLabel,
  pending,
  disabled,
  danger,
  onSubmit,
}: {
  done: boolean
  onClose: () => void
  submitLabel: string
  pending: boolean
  disabled?: boolean
  danger?: boolean
  onSubmit: () => void
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 4 }}>
      <button type="button" onClick={onClose} style={AURORA_BTN_GHOST}>
        {done ? 'Done' : 'Cancel'}
      </button>
      {!done && (
        <button
          type="button"
          onClick={onSubmit}
          disabled={pending || disabled}
          style={{
            ...AURORA_BTN_PRIMARY,
            ...(danger ? { background: 'var(--aurora-danger)', boxShadow: 'none', color: '#fff' } : {}),
            opacity: pending || disabled ? 0.5 : 1,
            cursor: pending || disabled ? 'not-allowed' : 'pointer',
          }}
        >
          {pending ? 'Working…' : submitLabel}
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dialog plumbing
// ---------------------------------------------------------------------------

interface DialogProps {
  keys: string[]
  titleOf: (key: string) => string
  onClose: () => void
  /** Report finished outcome so the bar can update the selection. */
  onOutcome: (o: Outcome, dropSucceeded: boolean) => void
}

function useInvalidateAfterBulk() {
  const qc = useQueryClient()
  return () => {
    for (const k of ['items', 'item', 'print-records', 'tags', 'libraries']) {
      void qc.invalidateQueries({ queryKey: [k] })
    }
  }
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Request failed.'
}

// --- Log print --------------------------------------------------------------

function PrintDialog({ keys, titleOf, onClose, onOutcome }: DialogProps) {
  const invalidate = useInvalidateAfterBulk()
  const [form, setForm] = useState<api.PrintRecordIn>(blankPrintRecord)
  const m = useMutation({
    mutationFn: () => api.bulkCreatePrintRecords(keys, normalizePrintRecord(form)),
    onSuccess: () => {
      invalidate()
      onOutcome({ succeeded: keys, failed: [] }, false)
    },
  })
  return (
    <Modal title={`Log print for ${keys.length} item${keys.length === 1 ? '' : 's'}`} onClose={onClose}>
      <TitleList titles={keys.map(titleOf)} />
      {m.isSuccess ? (
        <p role="status" style={{ margin: 0, fontSize: 12, color: 'var(--aurora-text)', fontWeight: 600 }}>
          Logged {m.data.created} print record{m.data.created === 1 ? '' : 's'}.
        </p>
      ) : (
        <>
          <PrintRecordFields form={form} setForm={setForm} applyDefaultProfile />
          <p style={{ margin: 0, fontSize: 11, color: 'var(--aurora-muted)' }}>
            One identical record is created per item. All-or-nothing: if any item is missing, none are logged.
          </p>
          {m.isError && (
            <p role="alert" style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{errMsg(m.error)}</p>
          )}
        </>
      )}
      <Footer
        done={m.isSuccess}
        onClose={onClose}
        submitLabel="Log print"
        pending={m.isPending}
        onSubmit={() => m.mutate()}
      />
    </Modal>
  )
}

// --- Tags -------------------------------------------------------------------

function ChipInput({
  label,
  tags,
  onChange,
}: {
  label: string
  tags: string[]
  onChange: (next: string[]) => void
}) {
  const [input, setInput] = useState('')
  const add = () => {
    onChange(addConfirmedTag(tags, input))
    setInput('')
  }
  return (
    <div>
      <label style={SUB_LABEL} htmlFor={`bulk-${label}`}>{label}</label>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          id={`bulk-${label}`}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder="Type a tag, press Enter"
          style={{ ...AURORA_INPUT, flex: 1 }}
        />
        <button
          type="button"
          onClick={add}
          disabled={!input.trim()}
          aria-label={`Add to ${label.toLowerCase()}`}
          style={{ ...AURORA_BTN_GHOST, opacity: input.trim() ? 1 : 0.4 }}
        >
          Add
        </button>
      </div>
      {tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
          {tags.map((t) => (
            <span
              key={t}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'var(--aurora-pill)',
                border: '1px solid var(--aurora-pill-border)',
                borderRadius: 20,
                padding: '3px 10px',
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--aurora-accent)',
              }}
            >
              #{t}
              <button
                type="button"
                onClick={() => onChange(removeConfirmedTag(tags, t))}
                aria-label={`Remove tag ${t} from ${label.toLowerCase()}`}
                style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'inherit' }}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function TagsDialog({ keys, titleOf, onClose, onOutcome }: DialogProps) {
  const invalidate = useInvalidateAfterBulk()
  const [add, setAdd] = useState<string[]>([])
  const [remove, setRemove] = useState<string[]>([])
  const m = useMutation({
    mutationFn: () => api.bulkTagItems(keys, add, remove),
    onSuccess: (r) => {
      invalidate()
      onOutcome(r, false)
    },
  })
  return (
    <Modal title={`Edit tags on ${keys.length} item${keys.length === 1 ? '' : 's'}`} onClose={onClose}>
      {m.isSuccess ? (
        <ResultSummary outcome={m.data} verb="updated" titleOf={titleOf} />
      ) : (
        <>
          <ChipInput label="Add tags" tags={add} onChange={setAdd} />
          <ChipInput label="Remove tags" tags={remove} onChange={setRemove} />
          <p style={{ margin: 0, fontSize: 11, color: 'var(--aurora-muted)' }}>
            New tags may land pending approval before they appear in the tag cloud.
          </p>
          {m.isError && (
            <p role="alert" style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{errMsg(m.error)}</p>
          )}
        </>
      )}
      <Footer
        done={m.isSuccess}
        onClose={onClose}
        submitLabel="Apply"
        pending={m.isPending}
        disabled={add.length === 0 && remove.length === 0}
        onSubmit={() => m.mutate()}
      />
    </Modal>
  )
}

// --- Move -------------------------------------------------------------------

function MoveDialog({
  keys,
  titleOf,
  onClose,
  onOutcome,
  libraries,
}: DialogProps & { libraries: api.LibraryOut[] }) {
  const invalidate = useInvalidateAfterBulk()
  const [target, setTarget] = useState<number | ''>('')
  const m = useMutation({
    mutationFn: async (): Promise<Outcome> => {
      const r = await api.bulkMoveItems(keys, target as number)
      // Skipped (e.g. already in target) and errored items did not move.
      const failed = [...r.skipped, ...r.errors].map((f) => ({ key: f.key, error: f.reason }))
      const bad = new Set(failed.map((f) => f.key))
      return { succeeded: keys.filter((k) => !bad.has(k)), failed }
    },
    onSuccess: (o) => {
      invalidate()
      onOutcome(o, true)
    },
  })
  return (
    <Modal title={`Move ${keys.length} item${keys.length === 1 ? '' : 's'} to library`} onClose={onClose}>
      <TitleList titles={keys.map(titleOf)} />
      {m.isSuccess ? (
        <ResultSummary outcome={m.data} verb="moved" titleOf={titleOf} />
      ) : (
        <>
          <div>
            <label style={SUB_LABEL} htmlFor="bulk-move-target">Target library</label>
            <select
              id="bulk-move-target"
              value={target}
              onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : '')}
              style={AURORA_INPUT}
            >
              <option value="">Select library…</option>
              {libraries.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
          </div>
          {m.isError && (
            <p role="alert" style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{errMsg(m.error)}</p>
          )}
        </>
      )}
      <Footer
        done={m.isSuccess}
        onClose={onClose}
        submitLabel="Move"
        pending={m.isPending}
        disabled={typeof target !== 'number'}
        onSubmit={() => m.mutate()}
      />
    </Modal>
  )
}

// --- Rescan -----------------------------------------------------------------

function RescanDialog({ keys, titleOf, onClose, onOutcome }: DialogProps) {
  const invalidate = useInvalidateAfterBulk()
  const m = useMutation({
    mutationFn: () => api.bulkRescanItems(keys),
    onSuccess: (r) => {
      invalidate()
      onOutcome(r, false)
    },
  })
  return (
    <Modal title={`Rescan ${keys.length} item${keys.length === 1 ? '' : 's'}`} onClose={onClose}>
      {m.isSuccess ? (
        <ResultSummary outcome={m.data} verb="rescanned" titleOf={titleOf} />
      ) : (
        <>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-text-dim)' }}>
            Re-inventory the folders on disk and resync the sidecar files for the selected items.
          </p>
          {m.isError && (
            <p role="alert" style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{errMsg(m.error)}</p>
          )}
        </>
      )}
      <Footer
        done={m.isSuccess}
        onClose={onClose}
        submitLabel="Rescan"
        pending={m.isPending}
        onSubmit={() => m.mutate()}
      />
    </Modal>
  )
}

// --- Delete -----------------------------------------------------------------

function DeleteDialog({ keys, titleOf, onClose, onOutcome }: DialogProps) {
  const invalidate = useInvalidateAfterBulk()
  const [typed, setTyped] = useState('')
  const confirmed = typed.trim().toLowerCase() === 'delete' || typed.trim() === String(keys.length)
  const m = useMutation({
    mutationFn: () => api.bulkDeleteItems(keys),
    onSuccess: (r) => {
      invalidate()
      onOutcome(r, true)
    },
  })
  return (
    <Modal title={`Delete ${keys.length} item${keys.length === 1 ? '' : 's'}`} onClose={onClose}>
      <TitleList titles={keys.map(titleOf)} />
      {m.isSuccess ? (
        <ResultSummary outcome={m.data} verb="deleted" titleOf={titleOf} />
      ) : (
        <>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-text-dim)' }}>
            The selected items are moved to the trash and removed from the catalog. They are retained
            in the trash for about 30 days before being purged.
          </p>
          <div>
            <label style={SUB_LABEL} htmlFor="bulk-delete-confirm">
              Type {keys.length} or &quot;delete&quot; to confirm
            </label>
            <input
              id="bulk-delete-confirm"
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              style={AURORA_INPUT}
            />
          </div>
          {m.isError && (
            <p role="alert" style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{errMsg(m.error)}</p>
          )}
        </>
      )}
      <Footer
        done={m.isSuccess}
        onClose={onClose}
        submitLabel="Delete items"
        pending={m.isPending}
        disabled={!confirmed}
        danger
        onSubmit={() => m.mutate()}
      />
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Action bar
// ---------------------------------------------------------------------------

const BAR_BTN: React.CSSProperties = {
  ...AURORA_BTN_GHOST,
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  padding: '6px 12px',
  whiteSpace: 'nowrap',
}

interface BulkActionBarProps {
  selection: CatalogSelection
  pageItems: SelectableItem[]
}

export function BulkActionBar({ selection, pageItems }: BulkActionBarProps) {
  const [dialog, setDialog] = useState<DialogKind | null>(null)
  const [moreOpen, setMoreOpen] = useState(false)

  const { data: libraries } = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 5 * 60 * 1000,
  })
  const enabledLibraries = (libraries ?? []).filter((l) => l.enabled)

  if (!selection.active) return null

  const n = selection.count
  const disabled = n === 0
  const overBulk = n > api.BULK_MAX_KEYS
  const overRescan = n > api.BULK_RESCAN_MAX_KEYS
  // Snapshot of the keys the open dialog operates on (selection may change on
  // drop-succeeded; the dialog keeps its own list for the result summary).
  const titleOf = (key: string) => selection.selected.get(key)?.title ?? key

  const open = (d: DialogKind) => {
    setMoreOpen(false)
    setDialog(d)
  }

  const handleOutcome = (o: Outcome, dropSucceeded: boolean) => {
    if (dropSucceeded) selection.remove(o.succeeded)
  }

  return (
    <>
      <div
        role="toolbar"
        aria-label="Bulk actions"
        style={{
          position: 'fixed',
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 40,
          display: 'flex',
          justifyContent: 'center',
          padding: '0 12px 12px',
          pointerEvents: 'none',
        }}
      >
        <div
          style={{
            pointerEvents: 'auto',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            maxWidth: '100%',
            background: 'var(--aurora-palette-bg)',
            border: '1px solid var(--aurora-palette-border)',
            borderRadius: 16,
            boxShadow: '0 12px 40px rgba(0,0,0,0.45)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            padding: '10px 14px',
          } as React.CSSProperties}
        >
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)', marginRight: 4 }}>
            {n} selected
          </span>
          <button type="button" style={BAR_BTN} onClick={() => selection.selectAllOnPage(pageItems)}>
            Select all on this page
          </button>
          <button type="button" style={BAR_BTN} onClick={selection.clear} disabled={disabled}>
            Clear
          </button>
          <span aria-hidden style={{ width: 1, alignSelf: 'stretch', background: 'var(--aurora-divider)' }} />
          <button type="button" style={BAR_BTN} disabled={disabled || overBulk} onClick={() => open('print')}>
            <Printer size={13} /> Log print
          </button>
          <button type="button" style={BAR_BTN} disabled={disabled || overBulk} onClick={() => open('tags')}>
            <Tags size={13} /> Tags
          </button>
          <button
            type="button"
            style={BAR_BTN}
            disabled={disabled || overBulk || enabledLibraries.length < 2}
            title={enabledLibraries.length < 2 ? 'Needs at least two enabled libraries' : undefined}
            onClick={() => open('move')}
          >
            <FolderInput size={13} /> Move
          </button>
          <div style={{ position: 'relative' }}>
            <button
              type="button"
              style={BAR_BTN}
              aria-haspopup="menu"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen((v) => !v)}
            >
              <MoreHorizontal size={13} /> More <ChevronDown size={12} />
            </button>
            {moreOpen && (
              <div
                role="menu"
                style={{
                  position: 'absolute',
                  bottom: 'calc(100% + 6px)',
                  right: 0,
                  minWidth: 190,
                  background: 'var(--aurora-palette-bg)',
                  border: '1px solid var(--aurora-palette-border)',
                  borderRadius: 10,
                  boxShadow: '0 12px 30px rgba(0,0,0,0.4)',
                  padding: 4,
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <button
                  type="button"
                  role="menuitem"
                  disabled={disabled || overRescan}
                  title={overRescan ? `Rescan is limited to ${api.BULK_RESCAN_MAX_KEYS} items` : undefined}
                  onClick={() => open('rescan')}
                  style={menuItemStyle(disabled || overRescan)}
                >
                  Rescan{overRescan ? ` (max ${api.BULK_RESCAN_MAX_KEYS})` : ''}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={disabled || overBulk}
                  onClick={() => open('delete')}
                  style={{ ...menuItemStyle(disabled || overBulk), color: 'var(--aurora-danger)' }}
                >
                  Delete…
                </button>
              </div>
            )}
          </div>
          <button type="button" style={BAR_BTN} onClick={selection.exit} aria-label="Exit select mode">
            <X size={13} />
          </button>
          {overBulk && (
            <span role="alert" style={{ fontSize: 11, color: 'var(--aurora-danger)', width: '100%', textAlign: 'center' }}>
              Bulk actions are limited to {api.BULK_MAX_KEYS} items — deselect some to continue.
            </span>
          )}
        </div>
      </div>

      {dialog && (
        <DialogHost
          kind={dialog}
          keys={selection.keys}
          titleOf={titleOf}
          libraries={enabledLibraries}
          onClose={() => setDialog(null)}
          onOutcome={handleOutcome}
        />
      )}
    </>
  )
}

function menuItemStyle(disabled: boolean): React.CSSProperties {
  return {
    background: 'transparent',
    border: 'none',
    textAlign: 'left',
    fontSize: 12,
    padding: '8px 10px',
    borderRadius: 6,
    color: 'var(--aurora-text)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.45 : 1,
  }
}

/**
 * Freezes the key/title list at open time so the dialog's list and result
 * summary stay stable even after succeeded items are dropped from the selection.
 */
function DialogHost({
  kind,
  keys,
  titleOf,
  libraries,
  onClose,
  onOutcome,
}: {
  kind: DialogKind
  keys: string[]
  titleOf: (key: string) => string
  libraries: api.LibraryOut[]
  onClose: () => void
  onOutcome: (o: Outcome, dropSucceeded: boolean) => void
}) {
  const [frozenKeys] = useState(keys)
  const [titles] = useState(() => new Map(keys.map((k) => [k, titleOf(k)])))
  const props: DialogProps = {
    keys: frozenKeys,
    titleOf: (k) => titles.get(k) ?? k,
    onClose,
    onOutcome,
  }
  switch (kind) {
    case 'print':
      return <PrintDialog {...props} />
    case 'tags':
      return <TagsDialog {...props} />
    case 'move':
      return <MoveDialog {...props} libraries={libraries} />
    case 'rescan':
      return <RescanDialog {...props} />
    case 'delete':
      return <DeleteDialog {...props} />
  }
}
