/**
 * ObjectBreakdown — per-file mesh analysis for STL/OBJ model files.
 *
 * Each analyzed file is shown as a collapsible section (collapsed by default)
 * for consistency with the 3MF collapsible detail panels in DownloadsPanel.
 * Files with est_method='sliced' (3MF) are handled separately by ThreeMfPanel;
 * this component covers STL/OBJ (est_method='volume') breakdown.
 *
 * Pending model files are split by type:
 *  - .3mf: not mesh-analyzed (says so plainly; no false "pending")
 *  - .stl/.obj/.ply: correlate with the analyze_item job to show running/queued/failed/no-job
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

import * as api from '@/lib/api'
import type { ItemJobSummary } from '@/lib/api/items'
import { is3mf } from '@/lib/file-tree'

// ---------------------------------------------------------------------------
// Object breakdown section (Phase 16)
// ---------------------------------------------------------------------------

export interface ObjectBreakdownProps {
  item: api.ItemDetail
  /** Active + recent-failed jobs from GET /api/items/{key}/jobs, polled by ItemPage. */
  jobs: ItemJobSummary[]
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

/** Collapsible per-file analysis card (STL/OBJ — volume estimate). */
function AnalysisFileCard({ file }: { file: api.FileOut }) {
  const [open, setOpen] = useState(false)
  const a = file.object_analysis!

  const densityNote =
    'Grams = volume × 1.24 g/cm³ (PLA default) × infill % — configurable in admin settings. Real values require slicing.'

  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 10,
        overflow: 'hidden',
      }}
    >
      {/* Collapsed header */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
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
        <span style={{ color: 'var(--aurora-muted)', flexShrink: 0 }}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
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
            flex: 1,
          }}
          title={file.path}
        >
          {file.path}
        </span>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexShrink: 0,
            fontSize: 11,
            color: 'var(--aurora-text-dim)',
          }}
        >
          <span>{a.total_objects} object{a.total_objects !== 1 ? 's' : ''}</span>
          <span>{a.total_colors} color{a.total_colors !== 1 ? 's' : ''}</span>
          {a.total_est_grams != null && (
            <span title={densityNote}>~{a.total_est_grams.toFixed(1)}g est.</span>
          )}
        </div>
      </button>

      {/* Expanded — object rows */}
      {open && (
        <div style={{ borderTop: '1px solid var(--aurora-divider)' }}>
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
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      fontFamily: 'monospace',
                      color: 'var(--aurora-text)',
                    }}
                  >
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
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  flexShrink: 0,
                  flexWrap: 'wrap',
                }}
              >
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
                {obj.est_grams != null && (
                  <span
                    style={{ fontSize: 11, color: 'var(--aurora-text-dim)' }}
                    title={densityNote}
                  >
                    ~{obj.est_grams.toFixed(2)}g
                    <span style={{ fontSize: 10, color: 'var(--aurora-muted)', marginLeft: 2 }}>
                      est.
                    </span>
                  </span>
                )}
              </div>
            </div>
          ))}

          {/* File totals footer */}
          {a.objects.length > 1 && (
            <div
              style={{
                display: 'flex',
                gap: 12,
                fontSize: 11,
                color: 'var(--aurora-muted)',
                padding: '8px 14px',
                borderTop: '1px solid var(--aurora-divider)',
                flexWrap: 'wrap',
              }}
            >
              <span>File total: {a.total_objects} objects</span>
              <span>{a.total_colors} distinct color{a.total_colors !== 1 ? 's' : ''}</span>
              {a.total_est_grams != null && <span>~{a.total_est_grams.toFixed(1)}g est.</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pending-state sub-components
// ---------------------------------------------------------------------------

const JOBS_LINK = '/admin/activity/jobs'

function JobsLink() {
  return (
    <Link
      to={JOBS_LINK}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        color: 'var(--aurora-accent)',
        textDecoration: 'none',
        fontSize: 11,
      }}
    >
      View in Jobs
      <ExternalLink size={10} />
    </Link>
  )
}

/** Progress bar (0–100 %). */
function ProgressBar({ value }: { value: number }) {
  return (
    <div
      style={{
        height: 4,
        borderRadius: 2,
        background: 'var(--aurora-glass-border)',
        overflow: 'hidden',
        width: '100%',
        maxWidth: 200,
      }}
    >
      <div
        style={{
          height: '100%',
          width: `${Math.min(100, Math.max(0, value))}%`,
          background: 'var(--aurora-accent)',
          borderRadius: 2,
          transition: 'width 0.3s ease',
        }}
      />
    </div>
  )
}

/** Pending status banner for mesh files (stl/obj/ply) — correlates with analyze_item job. */
function MeshPendingStatus({ jobs }: { jobs: ItemJobSummary[] }) {
  // Find the most recent analyze_item job (jobs are returned newest-first by the endpoint)
  const analyzeJob = jobs.find((j) => j.type === 'analyze_item')

  if (analyzeJob) {
    if (analyzeJob.status === 'running') {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--aurora-text-dim)' }}>
              Analyzing… {analyzeJob.progress}%
            </span>
            <JobsLink />
          </div>
          <ProgressBar value={analyzeJob.progress} />
        </div>
      )
    }

    if (analyzeJob.status === 'queued') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: 'var(--aurora-text-dim)' }}>
            Analysis queued
          </span>
          <JobsLink />
        </div>
      )
    }

    if (analyzeJob.status === 'failed') {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
              Analysis failed
            </span>
            <JobsLink />
          </div>
          {analyzeJob.error && (
            <span
              style={{
                fontSize: 11,
                color: 'var(--aurora-muted)',
                fontFamily: 'monospace',
                wordBreak: 'break-all',
              }}
            >
              {analyzeJob.error}
            </span>
          )}
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
            Use <strong style={{ color: 'var(--aurora-text)' }}>Rescan disk</strong> in
            Files &amp; Downloads above to re-queue it.
          </span>
        </div>
      )
    }
  }

  // No job found
  return (
    <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
      Analysis hasn't run yet — use{' '}
      <strong style={{ fontStyle: 'normal', color: 'var(--aurora-text)' }}>Rescan disk</strong>{' '}
      in Files &amp; Downloads above to queue it.
    </p>
  )
}

export function ObjectBreakdownSection({ item, jobs }: ObjectBreakdownProps) {
  // Only show STL/OBJ model files here; sliced 3MF is handled by ThreeMfPanel inline in the tree
  const analyzedFiles = item.files.filter(
    (f) =>
      f.role === 'model' &&
      f.object_analysis != null &&
      f.object_analysis.est_method !== 'sliced',
  )
  const pendingFiles = item.files.filter(
    (f) => f.role === 'model' && f.object_analysis == null,
  )

  // Split pending files: 3MF (read, not mesh-analyzed) vs mesh (stl/obj/ply — analyzable)
  const pending3mfFiles = pendingFiles.filter((f) => is3mf(f.path))
  const pendingMeshFiles = pendingFiles.filter((f) => !is3mf(f.path))

  // For sliced 3MFs handled in the file tree, also count unsliced 3MFs
  const slicedCount = item.files.filter(
    (f) => f.role === 'model' && f.object_analysis?.est_method === 'sliced',
  ).length

  if (analyzedFiles.length === 0 && pendingFiles.length === 0 && slicedCount === 0) {
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
        No model files.
      </p>
    )
  }

  // No analyzed or sliced files yet — render per-type pending messages
  if (analyzedFiles.length === 0 && slicedCount === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* 3MF pending: not mesh-analyzed by design */}
        {pending3mfFiles.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
              {pending3mfFiles.length === 1
                ? `${pending3mfFiles[0].path} is`
                : `${pending3mfFiles.length} .3mf files are`}{' '}
              read, not mesh-analyzed — slice details (if any) appear inline in{' '}
              <strong style={{ fontStyle: 'normal' }}>Files &amp; Downloads</strong> above.
            </p>
          </div>
        )}
        {/* Mesh pending: show job status */}
        {pendingMeshFiles.length > 0 && (
          <MeshPendingStatus jobs={jobs} />
        )}
      </div>
    )
  }

  if (analyzedFiles.length === 0) {
    // All model files are sliced 3MF — shown inline in the file tree
    return (
      <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
        3MF slice details are shown inline in the Files &amp; Downloads section above.
      </p>
    )
  }

  const densityNote =
    'Grams = volume × 1.24 g/cm³ (PLA default) × infill % — configurable in admin settings. Real values require slicing.'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Item-level summary bar */}
      {item.analysis_total_objects != null && (
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
            </span>{' '}
            object{item.analysis_total_objects !== 1 ? 's' : ''}
          </span>
          <span style={{ color: 'var(--aurora-text-dim)' }}>
            <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
              {item.analysis_total_colors}
            </span>{' '}
            color{item.analysis_total_colors !== 1 ? 's' : ''}
          </span>
          {item.analysis_total_est_grams != null && (
            <span style={{ color: 'var(--aurora-text-dim)' }}>
              <span style={{ fontWeight: 700, color: 'var(--aurora-text)' }}>
                ~{item.analysis_total_est_grams.toFixed(1)}g
              </span>{' '}
              est.
              <span
                style={{
                  cursor: 'help',
                  marginLeft: 4,
                  fontSize: 10,
                  color: 'var(--aurora-muted)',
                }}
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

      {/* Per-file collapsible cards */}
      {analyzedFiles.map((file) => (
        <AnalysisFileCard key={file.id} file={file} />
      ))}

      {/* Footnote */}
      <p style={{ fontSize: 10, color: 'var(--aurora-muted)', margin: 0, lineHeight: 1.5 }}>
        Grams are a rough volume-based estimate (can be 2–5× off without real slicing).{' '}
        Assumptions: density and infill % from admin settings. LOW CONF = non-watertight mesh;
        convex hull used for volume.
      </p>
    </div>
  )
}
