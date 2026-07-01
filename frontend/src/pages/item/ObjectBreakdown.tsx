import React from 'react'

import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Object breakdown section (Phase 16)
// ---------------------------------------------------------------------------

export interface ObjectBreakdownProps {
  item: api.ItemDetail
}

/** Small color swatch when a hex code is available. */
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

export function ObjectBreakdownSection({ item }: ObjectBreakdownProps) {
  // Collect analyzed model files
  const analyzedFiles = item.files.filter(
    (f) => f.role === 'model' && f.object_analysis != null,
  )
  const pendingFiles = item.files.filter(
    (f) => f.role === 'model' && f.object_analysis == null,
  )

  if (analyzedFiles.length === 0 && pendingFiles.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
        No model files.
      </p>
    )
  }

  if (analyzedFiles.length === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
        Analysis pending — will appear after the background worker runs.
      </p>
    )
  }

  const densityNote = 'Grams = volume × 1.24 g/cm³ (PLA default) × infill % — configurable in admin settings. Real values require slicing.'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Item-level summary bar */}
      {(item.analysis_total_objects != null) && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px 20px',
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            padding: '10px 14px',
            fontSize: 12,
          }}
        >
          <span style={{ color: 'var(--aurora-text-dim)' }}>
            <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
              {item.analysis_total_objects}
            </span>
            {' '}object{item.analysis_total_objects !== 1 ? 's' : ''}
          </span>
          <span style={{ color: 'var(--aurora-text-dim)' }}>
            <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
              {item.analysis_total_colors}
            </span>
            {' '}color{item.analysis_total_colors !== 1 ? 's' : ''}
          </span>
          {item.analysis_total_est_grams != null && (
            <span style={{ color: 'var(--aurora-text-dim)' }}>
              <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
                ~{item.analysis_total_est_grams.toFixed(1)}g
              </span>
              {' '}est.
              <span
                style={{ cursor: 'help', marginLeft: 4, fontSize: 10, color: 'var(--aurora-muted)' }}
                title={densityNote}
              >
                (?)
              </span>
            </span>
          )}
          {pendingFiles.length > 0 && (
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
              ({pendingFiles.length} file{pendingFiles.length > 1 ? 's' : ''} pending)
            </span>
          )}
        </div>
      )}

      {/* Per-file breakdown */}
      {analyzedFiles.map((file) => {
        const a = file.object_analysis!
        return (
          <div key={file.id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* File header */}
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--aurora-muted)', fontFamily: 'monospace' }}>
              {file.path}
            </div>

            {/* Object rows */}
            <div
              style={{
                background: 'var(--aurora-glass)',
                border: '1px solid var(--aurora-glass-border)',
                borderRadius: 10,
                overflow: 'hidden',
              }}
            >
              {a.objects.map((obj, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 12,
                    padding: '10px 14px',
                    borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                    flexWrap: 'wrap',
                  }}
                >
                  {/* Left: name + dims + low-confidence badge */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
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
                            padding: '1px 6px',
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

                  {/* Right: colors + grams */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0, flexWrap: 'wrap' }}>
                    {/* Color swatches */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      {obj.colors.filter(Boolean).slice(0, 8).map((hex, ci) => (
                        <ColorSwatch key={ci} hex={hex} />
                      ))}
                      {obj.colors.filter(Boolean).length > 8 && (
                        <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>
                          +{obj.colors.filter(Boolean).length - 8}
                        </span>
                      )}
                      <span style={{ fontSize: 11, color: 'var(--aurora-text-dim)' }}>
                        {obj.color_count} color{obj.color_count !== 1 ? 's' : ''}
                      </span>
                    </div>

                    {/* Estimated grams */}
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

            {/* File totals row */}
            {a.objects.length > 1 && (
              <div
                style={{
                  display: 'flex',
                  gap: 12,
                  fontSize: 11,
                  color: 'var(--aurora-muted)',
                  paddingLeft: 14,
                  flexWrap: 'wrap',
                }}
              >
                <span>File total: {a.total_objects} objects</span>
                <span>{a.total_colors} distinct color{a.total_colors !== 1 ? 's' : ''}</span>
                {a.total_est_grams != null && (
                  <span>~{a.total_est_grams.toFixed(1)}g est.</span>
                )}
              </div>
            )}
          </div>
        )
      })}

      {/* Footnote */}
      <p style={{ fontSize: 10, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
        Grams are a rough volume-based estimate (can be 2–5× off without real slicing).{' '}
        Assumptions: density and infill % from admin settings.
        LOW CONF = non-watertight mesh; convex hull used for volume.
      </p>
    </div>
  )
}
