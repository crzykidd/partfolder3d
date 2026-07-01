/**
 * StatStrip — Aurora stat tiles row with real backend data.
 *
 * Data sources:
 *   Total Assets  → GET /api/items?per_page=1 → .total
 *   Prints Done   → GET /api/print-stats → .total_prints
 *   Filament      → GET /api/print-stats → .total_filament_weight_g (kg)
 *   Success Rate  → GET /api/print-stats → .success_rate (%)
 *   Jobs Running  → GET /api/jobs?status=running&per_page=1 → .total
 *
 * On any error a graceful dash is shown — never an error state.
 * Polls every 60 s for jobs running; other stats are stale for 5 min.
 */

import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { LayoutGrid, Activity, Package, Star, Cpu } from 'lucide-react'

import * as api from '@/lib/api'

interface StatTileProps {
  label: string
  value: string
  icon: React.ReactNode
  color: string
}

function StatTile({ label, value, icon, color }: StatTileProps) {
  return (
    <div
      style={{
        background: 'var(--aurora-card)',
        border: '1px solid var(--aurora-card-border)',
        borderRadius: 12,
        padding: '10px 14px',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        flex: 1,
        minWidth: 0,
        transition: 'border-color 0.15s, box-shadow 0.15s',
        cursor: 'default',
      } as React.CSSProperties}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = `${color}40`
        ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 0 20px ${color}20`
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.borderColor = 'var(--aurora-card-border)'
        ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          fontSize: 10,
          fontWeight: 700,
          color: 'var(--aurora-muted)',
          letterSpacing: '0.07em',
          textTransform: 'uppercase',
          marginBottom: 5,
        }}
      >
        <span style={{ color }}>{icon}</span>
        {label}
      </div>
      <div
        style={{
          fontSize: 20,
          fontWeight: 800,
          color: 'var(--aurora-text)',
          fontVariantNumeric: 'tabular-nums',
          letterSpacing: '-0.02em',
          textShadow: `0 0 30px ${color}30`,
        }}
      >
        {value}
      </div>
    </div>
  )
}

export function StatStrip() {
  const { data: itemsData } = useQuery({
    queryKey: ['stat-items-count'],
    queryFn: () => api.listItems({ per_page: 1 }),
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data: printStats } = useQuery({
    queryKey: ['stat-print-stats'],
    queryFn: () => api.getPrintStats(),
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data: jobsRunning } = useQuery({
    queryKey: ['stat-jobs-running'],
    queryFn: () => api.listJobs({ status: 'running', per_page: 1 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  })

  const totalAssets = itemsData?.total != null ? itemsData.total.toLocaleString() : '—'
  const printsDone = printStats?.total_prints != null ? printStats.total_prints.toLocaleString() : '—'
  const filamentKg =
    printStats?.total_filament_weight_g != null
      ? `${(printStats.total_filament_weight_g / 1000).toFixed(1)} kg`
      : '—'
  const successRate =
    printStats?.success_rate != null ? `${Math.round(printStats.success_rate * 100)}%` : '—'
  const runningJobs = jobsRunning?.total != null ? String(jobsRunning.total) : '—'

  return (
    <div
      style={{
        display: 'flex',
        gap: 8,
        padding: '8px 16px',
        background: 'var(--aurora-glass)',
        borderBottom: '1px solid var(--aurora-divider)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        flexShrink: 0,
      } as React.CSSProperties}
    >
      <StatTile
        label="Total Assets"
        value={totalAssets}
        icon={<LayoutGrid size={12} />}
        color="var(--aurora-stat1)"
      />
      <StatTile
        label="Prints Done"
        value={printsDone}
        icon={<Activity size={12} />}
        color="var(--aurora-stat2)"
      />
      <StatTile
        label="Filament"
        value={filamentKg}
        icon={<Package size={12} />}
        color="var(--aurora-stat3)"
      />
      <StatTile
        label="Success Rate"
        value={successRate}
        icon={<Star size={12} />}
        color="var(--aurora-stat4)"
      />
      <StatTile
        label="Jobs Running"
        value={runningJobs}
        icon={<Cpu size={12} />}
        color="var(--aurora-stat5)"
      />
    </div>
  )
}
