/**
 * ThreeMfPanel — collapsible per-file detail panel for 3MF files.
 *
 * Collapsed summary: filename · Sliced/Unsliced badge · print time · total
 * filament weight · object count · plate count · embedded thumbnail · chevron.
 *
 * Expanded: per-filament rows (color swatch · type · g · m), per-plate
 * breakdown (index · time · weight), per-object list (name · dims · color).
 *
 * Labels sliced data (est_method='sliced') vs. volume-estimate data so the
 * user can tell real slicer numbers from rough estimates.
 */

import React, { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import type { FileObjectAnalysis, FilamentEntry, PlateEntry } from '@/lib/api/items'
import { fileDownloadUrl } from '@/lib/api'

// ---------------------------------------------------------------------------
// Small shared helpers
// ---------------------------------------------------------------------------

/** Render a square color swatch for a hex string (e.g. "#FF0000"). */
function ColorSwatch({ hex, size = 12 }: { hex: string; size?: number }) {
  const valid = /^#[0-9A-Fa-f]{3,8}$/.test(hex)
  if (!valid) return null
  return (
    <span
      title={hex}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: 3,
        border: '1px solid var(--aurora-glass-border)',
        background: hex,
        flexShrink: 0,
      }}
    />
  )
}

/** Format a seconds count into "Xh Ym" or "Ym" string. */
export function formatDuration(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

// ---------------------------------------------------------------------------
// ThreeMfPanel
// ---------------------------------------------------------------------------

export interface ThreeMfPanelProps {
  /** Basename of the 3MF file (displayed in the collapsed header). */
  fileName: string
  /** The file's object_analysis — must be non-null for this component to render. */
  analysis: FileObjectAnalysis
  /** The item key, used to build the thumbnail image URL. */
  itemKey: string
  /** Whether the panel starts expanded. Defaults to false (collapsed). */
  defaultExpanded?: boolean
}

export function ThreeMfPanel({
  fileName,
  analysis,
  itemKey,
  defaultExpanded = false,
}: ThreeMfPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  const isSliced = analysis.sliced === true || analysis.est_method === 'sliced'
  const filamentList: FilamentEntry[] = analysis.filament ?? []
  const plateList: PlateEntry[] = analysis.plates ?? []

  // Collapsed summary values
  const totalG = analysis.total_est_grams ?? 0
  const printTimeS = analysis.print_time_s ?? null
  const objectCount = isSliced
    ? (analysis.plate_count != null && analysis.plate_count > 0 ? analysis.plate_count : analysis.total_objects)
    : analysis.total_objects
  const plateCount = analysis.plate_count ?? 0

  // Badge colours
  const slicedBadge: React.CSSProperties = isSliced
    ? {
        background: 'rgba(16,185,129,0.15)',
        color: '#10B981',
        border: '1px solid rgba(16,185,129,0.35)',
      }
    : {
        background: 'rgba(245,158,11,0.15)',
        color: '#D97706',
        border: '1px solid rgba(245,158,11,0.35)',
      }

  const badgeBase: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 700,
    padding: '1px 6px',
    borderRadius: 20,
    flexShrink: 0,
  }

  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 10,
        overflow: 'hidden',
      }}
    >
      {/* Collapsed / summary row — always visible */}
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          width: '100%',
          padding: '10px 14px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          color: 'var(--aurora-text)',
        }}
      >
        {/* Expand chevron */}
        <span style={{ color: 'var(--aurora-muted)', flexShrink: 0 }}>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>

        {/* Per-file embedded thumbnail from analysis.thumbnail_path */}
        {analysis.thumbnail_path && (
          <img
            src={fileDownloadUrl(itemKey, analysis.thumbnail_path)}
            alt="3MF thumbnail"
            style={{
              width: 36,
              height: 36,
              objectFit: 'cover',
              borderRadius: 6,
              border: '1px solid var(--aurora-glass-border)',
              flexShrink: 0,
            }}
            loading="lazy"
          />
        )}

        {/* Filename */}
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            fontFamily: 'monospace',
            color: 'var(--aurora-text)',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {fileName}
        </span>

        {/* Sliced / Unsliced badge */}
        <span style={{ ...badgeBase, ...slicedBadge }}>
          {isSliced ? 'Sliced' : 'Unsliced'}
        </span>

        {/* Summary stats */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginLeft: 'auto',
            flexShrink: 0,
            fontSize: 11,
            color: 'var(--aurora-text-dim)',
            flexWrap: 'wrap',
            justifyContent: 'flex-end',
          }}
        >
          {printTimeS != null && (
            <span title="Estimated print time">{formatDuration(printTimeS)}</span>
          )}
          {totalG > 0 && (
            <span title={isSliced ? 'Filament weight (from slicer)' : 'Estimated filament weight'}>
              {isSliced ? '' : '~'}{totalG.toFixed(1)}g
            </span>
          )}
          {isSliced ? (
            <>
              {plateCount > 0 && (
                <span>{plateCount} plate{plateCount !== 1 ? 's' : ''}</span>
              )}
              {filamentList.length > 0 && (
                <span>{filamentList.length} filament{filamentList.length !== 1 ? 's' : ''}</span>
              )}
            </>
          ) : (
            analysis.total_objects > 0 && (
              <span>{analysis.total_objects} object{analysis.total_objects !== 1 ? 's' : ''}</span>
            )
          )}
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            borderTop: '1px solid var(--aurora-divider)',
            padding: '12px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          {isSliced ? (
            <SlicedDetail
              analysis={analysis}
              filamentList={filamentList}
              plateList={plateList}
              itemKey={itemKey}
            />
          ) : (
            <UnslicedDetail analysis={analysis} />
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sliced detail (est_method = 'sliced')
// ---------------------------------------------------------------------------

interface SlicedDetailProps {
  analysis: FileObjectAnalysis
  filamentList: FilamentEntry[]
  plateList: PlateEntry[]
  itemKey: string
}

function SlicedDetail({ analysis, filamentList, plateList }: SlicedDetailProps) {
  const sectionLabel: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--aurora-muted)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginBottom: 6,
  }

  const cellStyle: React.CSSProperties = {
    fontSize: 12,
    color: 'var(--aurora-text-dim)',
  }

  return (
    <>
      {/* Metadata row (slicer / printer) */}
      {(analysis.slicer || analysis.printer_model) && (
        <div style={{ display: 'flex', gap: 18, fontSize: 11, color: 'var(--aurora-muted)', flexWrap: 'wrap' }}>
          {analysis.slicer && <span>Slicer: <span style={{ color: 'var(--aurora-text-dim)' }}>{analysis.slicer}</span></span>}
          {analysis.printer_model && <span>Printer: <span style={{ color: 'var(--aurora-text-dim)' }}>{analysis.printer_model}</span></span>}
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              padding: '1px 6px',
              borderRadius: 20,
              background: 'rgba(16,185,129,0.1)',
              color: '#10B981',
              border: '1px solid rgba(16,185,129,0.3)',
            }}
          >
            Real slicer data
          </span>
        </div>
      )}

      {/* Filament rows */}
      {filamentList.length > 0 && (
        <div>
          <div style={sectionLabel}>Filaments</div>
          <div
            style={{
              background: 'var(--aurora-card)',
              border: '1px solid var(--aurora-card-border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {filamentList.map((fil, idx) => (
              <div
                key={fil.slot}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                  flexWrap: 'wrap',
                }}
              >
                {/* Slot + swatch */}
                <span style={{ fontSize: 10, color: 'var(--aurora-muted)', minWidth: 16 }}>
                  {fil.slot}
                </span>
                {fil.color_hex && <ColorSwatch hex={fil.color_hex} size={14} />}

                {/* Type */}
                <span style={cellStyle}>{fil.type ?? 'Unknown'}</span>

                {/* Weight / length */}
                <span style={{ ...cellStyle, marginLeft: 'auto' }}>
                  {fil.used_g != null && <span>{fil.used_g.toFixed(1)}g</span>}
                  {fil.used_g != null && fil.used_m != null && (
                    <span style={{ color: 'var(--aurora-muted)', margin: '0 4px' }}>·</span>
                  )}
                  {fil.used_m != null && (
                    <span style={{ color: 'var(--aurora-muted)' }}>{fil.used_m.toFixed(2)}m</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-plate breakdown */}
      {plateList.length > 0 && (
        <div>
          <div style={sectionLabel}>Plates</div>
          <div
            style={{
              background: 'var(--aurora-card)',
              border: '1px solid var(--aurora-card-border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {plateList.map((plate, idx) => (
              <div
                key={plate.index}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '8px 12px',
                  borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                }}
              >
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)', minWidth: 50 }}>
                  Plate {plate.index}
                </span>
                {plate.print_time_s != null && (
                  <span style={cellStyle}>{formatDuration(plate.print_time_s)}</span>
                )}
                {plate.weight_g != null && (
                  <span style={{ ...cellStyle, marginLeft: 'auto' }}>
                    {plate.weight_g.toFixed(1)}g
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-object list (from the objects[] built by _build_sliced_analysis) */}
      {analysis.objects.length > 0 && (
        <div>
          <div style={sectionLabel}>Objects / Filament slots</div>
          <div
            style={{
              background: 'var(--aurora-card)',
              border: '1px solid var(--aurora-card-border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {analysis.objects.map((obj, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '7px 12px',
                  borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                  flexWrap: 'wrap',
                }}
              >
                {obj.colors.filter(Boolean).map((hex, ci) => (
                  <ColorSwatch key={ci} hex={hex} size={11} />
                ))}
                <span style={{ fontSize: 12, color: 'var(--aurora-text)', fontFamily: 'monospace' }}>
                  {obj.name}
                </span>
                {obj.est_grams != null && (
                  <span style={{ ...cellStyle, marginLeft: 'auto' }}>
                    {obj.est_grams.toFixed(1)}g
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Unsliced detail (est_method = 'volume' — trimesh estimate)
// ---------------------------------------------------------------------------

function UnslicedDetail({ analysis }: { analysis: FileObjectAnalysis }) {
  const sectionLabel: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    color: 'var(--aurora-muted)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginBottom: 6,
  }

  const densityNote =
    'Grams = volume × density × infill % — configurable in admin settings. Real values require slicing.'

  return (
    <>
      <div
        style={{
          fontSize: 11,
          color: 'var(--aurora-muted)',
          padding: '6px 10px',
          background: 'rgba(245,158,11,0.08)',
          border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 7,
        }}
      >
        Volume estimate — numbers are rough (2–5× off without slicing).
        Slice in Bambu Studio / OrcaSlicer for real values.
      </div>

      {/* Objects */}
      {analysis.objects.length > 0 && (
        <div>
          <div style={sectionLabel}>Objects</div>
          <div
            style={{
              background: 'var(--aurora-card)',
              border: '1px solid var(--aurora-card-border)',
              borderRadius: 8,
              overflow: 'hidden',
            }}
          >
            {analysis.objects.map((obj, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '8px 12px',
                  borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12, fontWeight: 500, fontFamily: 'monospace', color: 'var(--aurora-text)' }}>
                      {obj.name}
                    </span>
                    {obj.low_confidence && (
                      <span
                        title="Non-watertight mesh — convex hull used for volume. Estimate may be significantly off."
                        style={{
                          fontSize: 9,
                          fontWeight: 700,
                          padding: '1px 5px',
                          borderRadius: 20,
                          background: 'rgba(245,158,11,0.15)',
                          color: '#D97706',
                          border: '1px solid rgba(245,158,11,0.3)',
                          cursor: 'help',
                        }}
                      >
                        LOW CONF
                      </span>
                    )}
                  </div>
                  {obj.dims_mm && (
                    <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>
                      {obj.dims_mm[0]}×{obj.dims_mm[1]}×{obj.dims_mm[2]} mm
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
                  {obj.colors.filter(Boolean).slice(0, 6).map((hex, ci) => (
                    <ColorSwatch key={ci} hex={hex} />
                  ))}
                  {obj.est_grams != null && (
                    <span
                      style={{ fontSize: 11, color: 'var(--aurora-text-dim)' }}
                      title={densityNote}
                    >
                      ~{obj.est_grams.toFixed(2)}g
                      <span style={{ fontSize: 10, color: 'var(--aurora-muted)', marginLeft: 2 }}>est.</span>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )
}
