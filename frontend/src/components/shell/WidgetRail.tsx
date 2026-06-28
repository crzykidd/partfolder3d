/**
 * WidgetRail — customizable right-rail panel driven by the widget registry.
 *
 * Features:
 *   - Collapse/expand (state persisted via useDashboardLayout)
 *   - Add / remove / reorder panel widgets (move up/down)
 *   - Default: Quick Import widget for all roles
 *   - Edit mode triggered by a small "Customize" button
 *   - Hidden on narrow viewports (< 900 px) via aurora-rail CSS class
 */

import React, { useState } from 'react'
import { ChevronsRight, ChevronsLeft, Settings2, ChevronUp, ChevronDown, X, Plus, Check } from 'lucide-react'

import { useAuth } from '@/context/AuthContext'
import { useDashboardLayout } from '@/hooks/useDashboardLayout'
import { getWidgets, resolveWidgets } from '@/lib/widgets/registry'
import type { PanelWidgetDef } from '@/lib/widgets/types'

// ---------------------------------------------------------------------------
// Add-widget picker
// ---------------------------------------------------------------------------

interface AddWidgetPickerProps {
  available: PanelWidgetDef[]
  activeIds: string[]
  onAdd: (id: string) => void
  onClose: () => void
}

function AddWidgetPicker({ available, activeIds, onAdd, onClose }: AddWidgetPickerProps) {
  const unadded = available.filter((w) => !activeIds.includes(w.id))

  return (
    <div
      style={{
        position: 'absolute',
        top: '100%',
        left: 0,
        right: 0,
        zIndex: 200,
        background: 'var(--aurora-palette-bg)',
        border: '1px solid var(--aurora-palette-border)',
        borderRadius: 10,
        padding: '6px',
        boxShadow: '0 8px 30px rgba(0,0,0,0.25)',
        backdropFilter: 'blur(30px)',
        WebkitBackdropFilter: 'blur(30px)',
        marginTop: 4,
      } as React.CSSProperties}
    >
      <div style={{ padding: '4px 8px', marginBottom: 4 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--aurora-muted)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          Add panel widget
        </span>
      </div>
      {unadded.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', padding: '4px 8px', margin: 0 }}>
          All widgets added
        </p>
      ) : (
        unadded.map((widget) => {
          const Icon = widget.icon
          return (
            <button
              key={widget.id}
              onClick={() => { onAdd(widget.id); onClose() }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '7px 10px',
                background: 'transparent',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
                color: 'var(--aurora-text-dim)',
                textAlign: 'left',
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.background =
                  'var(--aurora-palette-hover)'
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.background = 'transparent'
              }}
            >
              <Icon size={13} style={{ color: 'var(--aurora-accent)' }} />
              {widget.title}
            </button>
          )
        })
      )}
      <div style={{ borderTop: '1px solid var(--aurora-divider)', marginTop: 4, paddingTop: 4 }}>
        <button
          onClick={onClose}
          style={{
            width: '100%',
            padding: '6px 10px',
            background: 'transparent',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontSize: 12,
            color: 'var(--aurora-muted)',
            textAlign: 'left',
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Panel widget header (in edit mode)
// ---------------------------------------------------------------------------

interface PanelHeaderProps {
  title: string
  icon: React.ReactNode
  editMode: boolean
  isFirst: boolean
  isLast: boolean
  onMoveUp: () => void
  onMoveDown: () => void
  onRemove: () => void
}

function PanelHeader({ title, icon, editMode, isFirst, isLast, onMoveUp, onMoveDown, onRemove }: PanelHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 14px 4px',
        flexShrink: 0,
      }}
    >
      <span style={{ color: 'var(--aurora-accent)' }}>{icon}</span>
      <span
        style={{
          flex: 1,
          fontSize: 10,
          fontWeight: 700,
          color: 'var(--aurora-muted)',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {title}
      </span>
      {editMode && (
        <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
          <SmallBtn title="Move up" disabled={isFirst} onClick={onMoveUp}>
            <ChevronUp size={10} />
          </SmallBtn>
          <SmallBtn title="Move down" disabled={isLast} onClick={onMoveDown}>
            <ChevronDown size={10} />
          </SmallBtn>
          <SmallBtn title="Remove" danger onClick={onRemove}>
            <X size={10} />
          </SmallBtn>
        </div>
      )}
    </div>
  )
}

interface SmallBtnProps {
  title: string
  disabled?: boolean
  danger?: boolean
  onClick?: () => void
  children: React.ReactNode
}

function SmallBtn({ title, disabled, danger, onClick, children }: SmallBtnProps) {
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 18,
        height: 18,
        borderRadius: 4,
        border: '1px solid var(--aurora-glass-border)',
        background: 'var(--aurora-glass)',
        cursor: disabled ? 'default' : 'pointer',
        color: danger ? 'var(--aurora-danger)' : 'var(--aurora-muted)',
        opacity: disabled ? 0.3 : 1,
        padding: 0,
      }}
    >
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function WidgetRail() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { layout, setRailCollapsed, updateRail } = useDashboardLayout()

  const [editMode, setEditMode] = useState(false)
  const [showPicker, setShowPicker] = useState(false)

  const collapsed = layout.rail.collapsed
  const widgetIds = layout.rail.widgets

  const activeWidgets = resolveWidgets(widgetIds, 'panel', isAdmin) as PanelWidgetDef[]
  const availableWidgets = getWidgets('panel', isAdmin) as PanelWidgetDef[]

  const moveUp = (idx: number) => {
    if (idx === 0) return
    const newWidgets = [...widgetIds]
    ;[newWidgets[idx - 1], newWidgets[idx]] = [newWidgets[idx], newWidgets[idx - 1]]
    updateRail({ ...layout.rail, widgets: newWidgets })
  }

  const moveDown = (idx: number) => {
    if (idx >= widgetIds.length - 1) return
    const newWidgets = [...widgetIds]
    ;[newWidgets[idx], newWidgets[idx + 1]] = [newWidgets[idx + 1], newWidgets[idx]]
    updateRail({ ...layout.rail, widgets: newWidgets })
  }

  const removeWidget = (id: string) => {
    updateRail({ ...layout.rail, widgets: widgetIds.filter((w) => w !== id) })
  }

  const addWidget = (id: string) => {
    if (!widgetIds.includes(id)) {
      updateRail({ ...layout.rail, widgets: [...widgetIds, id] })
    }
  }

  return (
    <aside
      className="aurora-rail"
      style={{
        width: collapsed ? 36 : 260,
        minWidth: collapsed ? 36 : 260,
        background: 'var(--aurora-glass)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        borderLeft: '1px solid var(--aurora-divider)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1)',
        overflow: 'hidden',
        flexShrink: 0,
      } as React.CSSProperties}
    >
      {/* Header row: title + collapse toggle + edit button */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          padding: collapsed ? '12px 0' : '10px 10px 10px 14px',
          borderBottom: '1px solid var(--aurora-divider)',
          flexShrink: 0,
          gap: 4,
        }}
      >
        {!collapsed && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: 'var(--aurora-muted)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            Panel
          </span>
        )}

        {/* Edit/done button (only when expanded) */}
        {!collapsed && (
          <button
            onClick={() => {
              if (editMode) {
                setEditMode(false)
                setShowPicker(false)
              } else {
                setEditMode(true)
              }
            }}
            title={editMode ? 'Done editing' : 'Customize panel'}
            style={headerBtnStyle}
            onMouseEnter={btnHoverOn}
            onMouseLeave={btnHoverOff}
          >
            {editMode ? <Check size={11} /> : <Settings2 size={11} />}
          </button>
        )}

        {/* Collapse/expand toggle */}
        <button
          onClick={() => setRailCollapsed(!collapsed)}
          title={collapsed ? 'Expand panel' : 'Collapse panel'}
          style={headerBtnStyle}
          onMouseEnter={btnHoverOn}
          onMouseLeave={btnHoverOff}
        >
          {collapsed ? <ChevronsLeft size={13} /> : <ChevronsRight size={13} />}
        </button>
      </div>

      {/* Content: only when expanded */}
      {!collapsed && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '10px 0 14px' }}>
          {activeWidgets.map((widget, idx) => {
            const Icon = widget.icon
            const WidgetComponent = widget.component
            return (
              <div
                key={widget.id}
                style={{
                  marginBottom: idx < activeWidgets.length - 1 ? 12 : 0,
                  outline: editMode ? '1px dashed var(--aurora-pill-border)' : 'none',
                  outlineOffset: -2,
                  borderRadius: editMode ? 8 : 0,
                  margin: editMode ? '0 6px 8px' : undefined,
                }}
              >
                <PanelHeader
                  title={widget.title}
                  icon={<Icon size={12} />}
                  editMode={editMode}
                  isFirst={idx === 0}
                  isLast={idx === activeWidgets.length - 1}
                  onMoveUp={() => moveUp(idx)}
                  onMoveDown={() => moveDown(idx)}
                  onRemove={() => removeWidget(widget.id)}
                />
                {!editMode && (
                  <div style={{ padding: '4px 14px 0' }}>
                    <WidgetComponent />
                  </div>
                )}
                {editMode && (
                  <div style={{ padding: '4px 14px 6px' }}>
                    <span style={{ fontSize: 11, color: 'var(--aurora-muted)', fontStyle: 'italic' }}>
                      {widget.title} widget content
                    </span>
                  </div>
                )}
              </div>
            )
          })}

          {/* Empty state */}
          {activeWidgets.length === 0 && (
            <div style={{ padding: '16px 14px' }}>
              <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
                No panel widgets. Click the settings icon to add some.
              </p>
            </div>
          )}

          {/* Add widget button (edit mode) */}
          {editMode && (
            <div style={{ padding: '0 10px', position: 'relative' }}>
              <button
                onClick={() => setShowPicker(!showPicker)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  width: '100%',
                  padding: '7px 10px',
                  background: 'var(--aurora-glass)',
                  border: '1px dashed var(--aurora-pill-border)',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 12,
                  color: 'var(--aurora-accent)',
                  marginTop: 6,
                }}
              >
                <Plus size={12} />
                Add widget
              </button>
              {showPicker && (
                <AddWidgetPicker
                  available={availableWidgets}
                  activeIds={widgetIds}
                  onAdd={addWidget}
                  onClose={() => setShowPicker(false)}
                />
              )}
            </div>
          )}
        </div>
      )}
    </aside>
  )
}

// ---------------------------------------------------------------------------
// Shared button styles for the rail header
// ---------------------------------------------------------------------------

const headerBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '4px 5px',
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 8,
  cursor: 'pointer',
  color: 'var(--aurora-muted)',
  transition: 'all 0.15s',
  flexShrink: 0,
}

function btnHoverOn(e: React.MouseEvent<HTMLButtonElement>) {
  const el = e.currentTarget as HTMLButtonElement
  el.style.borderColor = 'var(--aurora-pill-border)'
  el.style.color = 'var(--aurora-accent)'
}

function btnHoverOff(e: React.MouseEvent<HTMLButtonElement>) {
  const el = e.currentTarget as HTMLButtonElement
  el.style.borderColor = 'var(--aurora-glass-border)'
  el.style.color = 'var(--aurora-muted)'
}
