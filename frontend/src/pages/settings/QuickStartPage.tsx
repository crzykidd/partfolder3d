/**
 * QuickStartPage — onboarding guide for new PartFolder 3D users.
 *
 * Role-aware checklist: admins see additional setup steps (libraries, AI
 * tagging, invites, backups, sharing). Regular users see universal steps.
 *
 * Live status badges are shown for three cheaply-checkable steps:
 *   • Libraries   — listLibraries length > 0        (admin only, admin API)
 *   • Path prefix — /api/me/path-prefix != null      (all users)
 *   • AI provider — listAiProviders length > 0       (admin only, admin API)
 *
 * Badges are best-effort: if a query fails the badge is simply omitted.
 * No backend changes required — all queries reuse existing api.ts functions.
 *
 * Routes deep-linked here are verified against App.tsx.
 */

import React from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  HardDrive,
  SlidersHorizontal,
  Package,
  Zap,
  Mail,
  Archive,
  Share2,
  ArrowRight,
} from 'lucide-react'

import { useAuth } from '@/context/AuthContext'
import * as api from '@/lib/api'
import { AdminPage, PageHeader, Badge, Card } from '@/components/ui'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StatusKey = 'libraries' | 'pathPrefix' | 'aiProviders'

interface StepDef {
  icon: React.ReactNode
  title: string
  description: string
  /** Verified App.tsx route */
  to: string
  cta: string
  /** If true, only shown to admin users */
  adminOnly?: boolean
  /** Maps to a live status query (omit for no badge) */
  statusKey?: StatusKey
}

// ---------------------------------------------------------------------------
// Step definitions — routes verified against App.tsx on 2026-06-28
// ---------------------------------------------------------------------------

const STEPS: StepDef[] = [
  {
    icon: <HardDrive size={20} />,
    title: 'Add a library',
    description:
      'Libraries are where your model files live — set up at least one mount path before importing assets.',
    to: '/admin/libraries',
    cta: 'Manage libraries',
    adminOnly: true,
    statusKey: 'libraries',
  },
  {
    icon: <SlidersHorizontal size={20} />,
    title: 'Personalize your workspace',
    description:
      'Set your theme (light / dark / system), choose top-bar or sidebar navigation, and configure the local path display so on-disk paths match where you open files.',
    to: '/settings',
    cta: 'Open settings',
    statusKey: 'pathPrefix',
  },
  {
    icon: <Package size={20} />,
    title: 'Import your first asset',
    description:
      'Start an import session to drag-and-drop upload files or paste a source URL. You can also drop a folder into the inbox for bulk import.',
    to: '/imports',
    cta: 'Go to imports',
  },
  {
    icon: <Zap size={20} />,
    title: 'Enable AI tagging (optional)',
    description:
      'Add a Claude, OpenAI, or Ollama API key to auto-suggest tags during import. Usage and estimated cost are tracked in AI Usage.',
    to: '/admin/ai-providers',
    cta: 'Configure AI providers',
    adminOnly: true,
    statusKey: 'aiProviders',
  },
  {
    icon: <Mail size={20} />,
    title: 'Invite your team',
    description:
      'PartFolder 3D has no open registration. Send invite links to teammates from the Invites page.',
    to: '/admin/invites',
    cta: 'Manage invites',
    adminOnly: true,
  },
  {
    icon: <Archive size={20} />,
    title: 'Set up backups',
    description:
      'Schedule automatic database and config backups. Library files are intentionally not backed up — they live on your own storage.',
    to: '/admin/backups',
    cta: 'Configure backups',
    adminOnly: true,
  },
  {
    icon: <Share2 size={20} />,
    title: 'Share your catalog',
    description:
      'Create per-item share links from any item page, or mint a full-site read-only share link for guests. The Share Audit page logs every view.',
    to: '/admin/shares',
    cta: 'Share audit',
    adminOnly: true,
  },
]

// ---------------------------------------------------------------------------
// StepCard
// ---------------------------------------------------------------------------

interface StepCardProps {
  step: StepDef
  /** undefined = no badge; true = Done; false = To do */
  done: boolean | undefined
}

function StepCard({ step, done }: StepCardProps) {
  return (
    <Card
      accent={done === true}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      {/* Icon row + status badge */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 10,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 40,
            height: 40,
            borderRadius: 10,
            flexShrink: 0,
            background:
              done === true
                ? 'rgba(15,164,171,0.15)'
                : 'var(--aurora-glass)',
            border:
              done === true
                ? '1px solid rgba(15,164,171,0.3)'
                : '1px solid var(--aurora-glass-border)',
            color:
              done === true ? 'var(--aurora-accent)' : 'var(--aurora-muted)',
          }}
        >
          {step.icon}
        </div>
        {done !== undefined && (
          done
            ? <Badge variant="success">Done</Badge>
            : <Badge variant="warning">To do</Badge>
        )}
      </div>

      {/* Title + description */}
      <div style={{ flex: 1 }}>
        <h3
          style={{
            margin: '0 0 6px',
            fontSize: 14,
            fontWeight: 700,
            color: 'var(--aurora-text)',
          }}
        >
          {step.title}
        </h3>
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: 'var(--aurora-muted)',
            lineHeight: 1.6,
          }}
        >
          {step.description}
        </p>
      </div>

      {/* CTA link */}
      <Link
        to={step.to}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--aurora-accent)',
          textDecoration: 'none',
        }}
      >
        {step.cta}
        <ArrowRight size={14} />
      </Link>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// QuickStartPage
// ---------------------------------------------------------------------------

export function QuickStartPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  // --- Live status queries — best-effort; badge hidden on error/loading ---

  const librariesQ = useQuery({
    queryKey: ['quick-start', 'libraries'],
    queryFn: api.listLibraries,
    retry: false,
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  })

  const pathPrefixQ = useQuery({
    queryKey: ['quick-start', 'path-prefix'],
    queryFn: api.getPathPrefix,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const aiProvidersQ = useQuery({
    queryKey: ['quick-start', 'ai-providers'],
    queryFn: api.listAiProviders,
    retry: false,
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  })

  // Resolve live status per key (undefined = no data yet or error → omit badge)
  const statusMap: Record<StatusKey, boolean | undefined> = {
    libraries:
      librariesQ.isSuccess ? librariesQ.data.length > 0 : undefined,
    pathPrefix:
      pathPrefixQ.isSuccess ? pathPrefixQ.data.path_prefix != null : undefined,
    aiProviders:
      aiProvidersQ.isSuccess ? aiProvidersQ.data.length > 0 : undefined,
  }

  const visibleSteps = STEPS.filter((s) => !s.adminOnly || isAdmin)

  return (
    <AdminPage>
      <PageHeader
        title="Quick Start"
        description="Complete these steps to get your PartFolder 3D instance up and running."
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: 16,
        }}
      >
        {visibleSteps.map((step) => (
          <StepCard
            key={step.title}
            step={step}
            done={step.statusKey ? statusMap[step.statusKey] : undefined}
          />
        ))}
      </div>
    </AdminPage>
  )
}
