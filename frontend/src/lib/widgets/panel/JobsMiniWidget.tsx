/**
 * JobsMiniWidget — panel widget showing active/running jobs.
 *
 * Data: GET /api/jobs?status=running&per_page=5 (polls every 30s)
 * Graceful empty state if no running jobs.
 */

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Cpu, CheckCircle, XCircle, Loader } from 'lucide-react'

import * as api from '@/lib/api'

function statusIcon(status: string) {
  if (status === 'running') return <Loader size={11} style={{ color: 'var(--aurora-accent)', flexShrink: 0 }} />
  if (status === 'succeeded') return <CheckCircle size={11} style={{ color: '#22c55e', flexShrink: 0 }} />
  if (status === 'failed') return <XCircle size={11} style={{ color: 'var(--aurora-danger)', flexShrink: 0 }} />
  return <Cpu size={11} style={{ color: 'var(--aurora-muted)', flexShrink: 0 }} />
}

export function JobsMiniWidget() {
  const navigate = useNavigate()

  const { data } = useQuery({
    queryKey: ['widget-jobs-mini'],
    queryFn: () => api.listJobs({ status: 'running', per_page: 5 }),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  })

  const jobs = data?.jobs ?? []
  const total = data?.total ?? 0

  if (jobs.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 10px',
          borderRadius: 8,
          background: 'var(--aurora-card)',
          border: '1px solid var(--aurora-card-border)',
        }}
      >
        <Cpu size={12} style={{ color: 'var(--aurora-muted)' }} />
        <span style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>No running jobs</span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {jobs.map((job) => (
        <button
          key={job.id}
          onClick={() => navigate('/admin/jobs')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: '100%',
            padding: '6px 8px',
            background: 'var(--aurora-card)',
            border: '1px solid var(--aurora-card-border)',
            borderRadius: 8,
            cursor: 'pointer',
            textAlign: 'left',
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.background = 'var(--aurora-glass-hover)'
            el.style.borderColor = 'var(--aurora-pill-border)'
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.background = 'var(--aurora-card)'
            el.style.borderColor = 'var(--aurora-card-border)'
          }}
        >
          {statusIcon(job.status)}
          <span
            style={{
              fontSize: 11,
              color: 'var(--aurora-text)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1,
            }}
          >
            {job.type}
          </span>
          <span style={{ fontSize: 10, color: 'var(--aurora-muted)', flexShrink: 0 }}>
            {Math.round(job.progress * 100)}%
          </span>
        </button>
      ))}
      {total > jobs.length && (
        <button
          onClick={() => navigate('/admin/jobs')}
          style={{
            fontSize: 11,
            color: 'var(--aurora-accent)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            textAlign: 'left',
            padding: '2px 8px',
          }}
        >
          +{total - jobs.length} more →
        </button>
      )}
    </div>
  )
}
