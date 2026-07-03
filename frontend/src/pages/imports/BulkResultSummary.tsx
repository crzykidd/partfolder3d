/**
 * BulkResultSummary — result panel shown after a bulk-commit run
 * (committed / needs-review counts + skipped / errors lists).
 */

import type * as api from '@/lib/api'

interface BulkResultSummaryProps {
  result: api.BulkCommitResponse
  onClose: () => void
}

export function BulkResultSummary({ result, onClose }: BulkResultSummaryProps) {
  const { total, committed, skipped, errors } = result
  const needsReview = total - committed

  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 12,
        padding: '16px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        minWidth: 280,
        maxWidth: 480,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)', margin: 0 }}>
          Bulk commit result
        </p>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--aurora-muted)', fontSize: 15, lineHeight: 1, padding: 2 }}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <p style={{ fontSize: 13, color: 'var(--aurora-text-dim)', margin: 0 }}>
        <span style={{ color: '#16A34A', fontWeight: 700 }}>{committed}</span>
        {' '}committed
        {needsReview > 0 && (
          <>
            {' '}·{' '}
            <span style={{ color: '#D97706', fontWeight: 700 }}>{needsReview}</span>
            {' '}need review
          </>
        )}
        {' '}(of {total} total)
      </p>

      {skipped.length > 0 && (
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 6px' }}>
            Skipped
          </p>
          <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--aurora-muted)', display: 'flex', flexDirection: 'column', gap: 3 }}>
            {skipped.map((s) => (
              <li key={s.session_id} style={{ fontFamily: 'monospace' }}>
                {s.session_id.slice(0, 8)}… — {s.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {errors.length > 0 && (
        <div>
          <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--aurora-danger)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 6px' }}>
            Errors
          </p>
          <ul style={{ margin: 0, padding: '0 0 0 16px', fontSize: 12, color: 'var(--aurora-danger)', display: 'flex', flexDirection: 'column', gap: 3 }}>
            {errors.map((e) => (
              <li key={e.session_id} style={{ fontFamily: 'monospace' }}>
                {e.session_id.slice(0, 8)}… — {e.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
