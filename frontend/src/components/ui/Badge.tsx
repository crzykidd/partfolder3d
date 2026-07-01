/**
 * Badge — Aurora status badge primitive.
 *
 * Variants cover all status/severity/type combos used across admin pages.
 * Semantic colors use Tailwind dark: variants; aurora-specific tints use inline style.
 *
 * Reusable by B3b for Users, Settings, etc. pages.
 */

import React from 'react'

// ---------------------------------------------------------------------------
// Variants
// ---------------------------------------------------------------------------

export type BadgeVariant =
  | 'success'   // green  — succeeded, resolved, approved, active
  | 'danger'    // red    — failed, critical, revoked, rejected
  | 'warning'   // amber  — open issues, pending
  | 'info'      // blue   — running (job status), info severity
  | 'violet'    // violet — sidecar_sync behavior
  | 'orange'    // orange — file_changes behavior
  | 'muted'     // gray   — ignored, idle, integrity, "all"
  | 'accent'    // teal   — aurora-branded highlight (enabled, etc.)

const BADGE_CLASS: Record<BadgeVariant, string> = {
  success: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  danger:  'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
  info:    'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  violet:  'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200',
  orange:  'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  // muted + accent use inline styles (aurora CSS vars not in Tailwind)
  muted:   '',
  accent:  '',
}

// Inline styles for aurora-var-based variants (muted + accent)
const BADGE_INLINE: Partial<Record<BadgeVariant, React.CSSProperties>> = {
  muted: {
    background: 'var(--aurora-glass)',
    color: 'var(--aurora-muted)',
    border: '1px solid var(--aurora-glass-border)',
  },
  accent: {
    background: 'rgba(15,164,171,0.12)',
    color: 'var(--aurora-accent)',
    border: '1px solid rgba(15,164,171,0.3)',
  },
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

interface BadgeProps {
  variant: BadgeVariant
  children: React.ReactNode
  className?: string
}

export function Badge({ variant, children, className }: BadgeProps) {
  const baseClass = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium'
  const variantClass = BADGE_CLASS[variant]
  const inlineStyle = BADGE_INLINE[variant] ?? {}

  return (
    <span
      className={`${baseClass} ${variantClass} ${className ?? ''}`}
      style={inlineStyle}
    >
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Convenience helpers — map domain values to variants
// ---------------------------------------------------------------------------

/** Map a job status string → Badge variant */
export function jobStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'running':   return 'info'
    case 'succeeded': return 'success'
    case 'failed':    return 'danger'
    case 'queued':    return 'muted'
    default:          return 'muted'
  }
}

/** Map a scheduled-job last-run status → Badge variant */
export function schedJobStatusVariant(status: string | null): BadgeVariant {
  if (!status) return 'muted'
  return status === 'succeeded' ? 'success' : 'danger'
}

/** Map an issue severity → Badge variant */
export function severityVariant(severity: string): BadgeVariant {
  switch (severity) {
    case 'critical': return 'danger'
    case 'warning':  return 'warning'
    default:         return 'info'
  }
}

/** Map an issue/review status → Badge variant */
export function issueStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case 'open':     return 'warning'
    case 'resolved': return 'success'
    case 'approved': return 'success'
    case 'pending':  return 'warning'
    case 'rejected': return 'danger'
    case 'ignored':  return 'muted'
    default:         return 'muted'
  }
}

/** Map a reconcile behavior → Badge variant */
export function behaviorVariant(behavior: string): BadgeVariant {
  switch (behavior) {
    case 'sidecar_sync':  return 'violet'
    case 'file_changes':  return 'orange'
    case 're_render':     return 'info'
    case 'orphan':        return 'danger'
    default:              return 'muted'
  }
}
