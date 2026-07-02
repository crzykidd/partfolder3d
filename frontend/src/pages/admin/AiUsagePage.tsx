/**
 * AiUsagePage — AI usage tracking (Phase 13).
 *
 * Route: /admin/ai-usage  (admin only)
 *
 * Shows three windowed stat cards (24h / 7d / 30d) with call counts,
 * token totals, and estimated cost; plus a provider/model breakdown table
 * for the 30-day window.  Cost estimates are sourced from the local pricing
 * table and labelled as estimates (rates may drift).
 *
 * Styling: Aurora aesthetic — matches existing admin pages.
 * Stack: TanStack Query + apiFetch.  No Mantine, no toast, no new deps.
 */

import { useQuery } from '@tanstack/react-query'
import { Activity } from 'lucide-react'
import * as api from '@/lib/api'
import type { AiUsageWindow } from '@/lib/api'
import {
  AdminPage,
  PageHeader,
  DataTable,
  TableRow,
  Td,
  Badge,
  EmptyState,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function fmtCost(cost: number | null): string {
  if (cost === null) return '—'
  if (cost === 0) return '$0.00'
  if (cost < 0.01) return `<$0.01`
  return `$${cost.toFixed(4)}`
}

function providerLabel(provider: string): string {
  if (provider === 'openai') return 'OpenAI'
  return provider.charAt(0).toUpperCase() + provider.slice(1)
}

// ---------------------------------------------------------------------------
// Window stat card
// ---------------------------------------------------------------------------

interface WindowCardProps {
  label: string
  data: AiUsageWindow
}

function WindowCard({ label, data }: WindowCardProps) {
  return (
    <div
      style={{
        background: 'var(--aurora-card)',
        border: '1px solid var(--aurora-card-border)',
        borderRadius: 12,
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {/* Window label */}
      <p
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: 'var(--aurora-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          margin: 0,
        }}
      >
        {label}
      </p>

      {/* Call count */}
      <div>
        <p
          style={{
            fontSize: 28,
            fontWeight: 800,
            color: 'var(--aurora-text)',
            letterSpacing: '-0.02em',
            margin: 0,
          }}
        >
          {data.calls.toLocaleString()}
        </p>
        <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: '2px 0 0' }}>
          {data.calls === 1 ? 'call' : 'calls'}
        </p>
      </div>

      {/* Token breakdown */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
          borderTop: '1px solid var(--aurora-divider)',
          paddingTop: 8,
        }}
      >
        <TokenLine label="Input" value={data.input_tokens} />
        <TokenLine label="Output" value={data.output_tokens} />
        <TokenLine label="Total" value={data.total_tokens} bold />
      </div>

      {/* Estimated cost */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderTop: '1px solid var(--aurora-divider)',
          paddingTop: 8,
        }}
      >
        <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
          Est. cost
        </span>
        <span
          style={{
            fontSize: 13,
            fontWeight: 700,
            color:
              data.estimated_cost_usd === null
                ? 'var(--aurora-muted)'
                : 'var(--aurora-text)',
            fontStyle: data.estimated_cost_usd === null ? 'italic' : undefined,
          }}
        >
          {fmtCost(data.estimated_cost_usd)}
        </span>
      </div>
    </div>
  )
}

function TokenLine({
  label,
  value,
  bold,
}: {
  label: string
  value: number
  bold?: boolean
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{label}</span>
      <span
        style={{
          fontSize: 12,
          fontWeight: bold ? 700 : 400,
          color: 'var(--aurora-text)',
          fontFamily: 'monospace',
        }}
      >
        {fmtTokens(value)}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Breakdown table
// ---------------------------------------------------------------------------

const BREAKDOWN_COLS = ['Provider', 'Model', 'Calls', 'Input', 'Output', 'Total', 'Est. Cost']

function BreakdownTable({
  rows,
}: {
  rows: api.AiUsageBreakdownRow[]
}) {
  return (
    <DataTable
      columns={BREAKDOWN_COLS}
      isEmpty={rows.length === 0}
      emptyMessage="No usage recorded in the last 30 days."
    >
      {rows.map((row, idx) => (
        <TableRow key={idx}>
          <Td>
            <Badge variant="accent">{providerLabel(row.provider)}</Badge>
          </Td>
          <Td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--aurora-muted)' }}>
            {row.model ?? <span style={{ fontStyle: 'italic', opacity: 0.6 }}>default</span>}
          </Td>
          <Td style={{ fontWeight: 600 }}>{row.calls.toLocaleString()}</Td>
          <Td style={{ fontFamily: 'monospace', fontSize: 12 }}>{fmtTokens(row.input_tokens)}</Td>
          <Td style={{ fontFamily: 'monospace', fontSize: 12 }}>{fmtTokens(row.output_tokens)}</Td>
          <Td style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 600 }}>
            {fmtTokens(row.total_tokens)}
          </Td>
          <Td
            style={{
              fontFamily: 'monospace',
              fontSize: 12,
              color: row.estimated_cost_usd === null ? 'var(--aurora-muted)' : 'var(--aurora-text)',
              fontStyle: row.estimated_cost_usd === null ? 'italic' : undefined,
            }}
          >
            {fmtCost(row.estimated_cost_usd)}
          </Td>
        </TableRow>
      ))}
    </DataTable>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function AiUsagePage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['ai-usage-summary'],
    queryFn: api.getAiUsageSummary,
    staleTime: 60_000,
  })

  const hasAnyUsage =
    data &&
    (data.last_30d.calls > 0 ||
      data.last_7d.calls > 0 ||
      data.last_24h.calls > 0)

  return (
    <AdminPage>
      <PageHeader
        title="AI Usage"
        description="Token usage and estimated cost for AI calls (tag suggestions, description cleanup, summarization). Cost estimates are derived from locally configured per-model rates and may differ from actual billing."
      />

      {isLoading && (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)' }}>Loading…</p>
      )}

      {isError && (
        <p style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load AI usage data.'}
        </p>
      )}

      {data && !hasAnyUsage && (
        <EmptyState
          icon={<Activity size={32} />}
          title="No AI usage yet"
          description="AI usage will appear here once tag suggestions, description cleanup, or summarization have been used."
        />
      )}

      {data && hasAnyUsage && (
        <>
          {/* Windowed stat cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <WindowCard label="Last 24 hours" data={data.last_24h} />
            <WindowCard label="Last 7 days" data={data.last_7d} />
            <WindowCard label="Last 30 days" data={data.last_30d} />
          </div>

          {/* Provider / model breakdown */}
          {data.breakdown.length > 0 && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: 'var(--aurora-text)',
                }}
              >
                Provider / Model Breakdown (30 days)
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: 'var(--aurora-muted)',
                  margin: '-6px 0 0',
                }}
              >
                Costs are estimates from configured per-model rates. "—" means the
                rate for that model is not configured.
              </p>
              <BreakdownTable rows={data.breakdown} />
            </section>
          )}
        </>
      )}
    </AdminPage>
  )
}
