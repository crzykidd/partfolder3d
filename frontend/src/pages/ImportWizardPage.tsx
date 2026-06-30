/**
 * ImportWizardPage — multi-step wizard for reviewing and committing an import session.
 *
 * Route: /import/:sessionId
 *
 * Steps:
 *   1. Title      — edit confirmed_title; show source URL; site-setup prompt if needed.
 *   2. Images     — scrollable strip; Set as default; upload additional images.
 *   3. Tags       — confirmed chips (removable) + pending chips (accept/reject) + manual input.
 *   4. Creator    — toggle attributed / own design.
 *   5. Summary    — read-only review; Commit or Cancel.
 *
 * Polls GET /api/import-sessions/{id} every 3 s while status=processing.
 *
 * Styling: Aurora aesthetic — glass cards, teal accent (#0FA4AB), --aurora-* CSS vars.
 */

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import * as api from '@/lib/api'
import {
  type WizardStep,
  nextStep,
  prevStep,
  isProcessing,
  isEditable,
} from '@/lib/import-utils'
import { AURORA_CARD } from './import-wizard/styles'
import { StepProgress } from './import-wizard/StepProgress'
import { ProcessingOverlay } from './import-wizard/ProcessingOverlay'
import { TitleStep } from './import-wizard/TitleStep'
import { ImagesStep } from './import-wizard/ImagesStep'
import { TagsStep } from './import-wizard/TagsStep'
import { CreatorStep } from './import-wizard/CreatorStep'
import { SummaryStep } from './import-wizard/SummaryStep'

export function ImportWizardPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [step, setStep] = useState<WizardStep>('title')

  const { data: session, isLoading, isError, error } = useQuery({
    queryKey: ['import-session', sessionId],
    queryFn: () => api.getImportSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && isProcessing(data.status)) return 3_000
      return false
    },
  })

  // Advance automatically from processing → pending_wizard
  useEffect(() => {
    if (session && !isProcessing(session.status) && step === 'title') {
      // Ensure we stay on title when first arriving from processing state
    }
  }, [session, step])

  if (!sessionId) {
    return <p style={{ color: 'var(--aurora-danger)', fontSize: 13 }}>No session ID in URL.</p>
  }

  if (isLoading) {
    return (
      <div style={{ padding: '48px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
        Loading…
      </div>
    )
  }

  if (isError || !session) {
    return (
      <p style={{ color: 'var(--aurora-danger)', fontSize: 13 }}>
        {error instanceof Error ? error.message : 'Failed to load session.'}
      </p>
    )
  }

  // Terminal states
  if (session.status === 'committed') {
    return (
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <div
          style={{
            ...AURORA_CARD,
            padding: '48px 24px',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 14,
          }}
        >
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              background: 'rgba(22,163,74,0.15)',
              border: '1px solid rgba(22,163,74,0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Check size={22} style={{ color: '#16A34A' }} />
          </div>
          <div>
            <p style={{ fontSize: 16, fontWeight: 700, color: 'var(--aurora-text)', margin: '0 0 8px' }}>
              This session has already been committed.
            </p>
            <a
              href="/catalog"
              style={{ color: 'var(--aurora-accent)', fontSize: 13, textDecoration: 'none' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
            >
              Browse catalog →
            </a>
          </div>
        </div>
      </div>
    )
  }

  if (session.status === 'cancelled') {
    return (
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <div
          style={{
            ...AURORA_CARD,
            padding: '48px 24px',
            textAlign: 'center',
          }}
        >
          <p style={{ fontSize: 14, color: 'var(--aurora-muted)', margin: '0 0 10px' }}>
            This import session was cancelled.
          </p>
          <a
            href="/catalog"
            style={{ color: 'var(--aurora-accent)', fontSize: 13, textDecoration: 'none' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
          >
            Back to catalog →
          </a>
        </div>
      </div>
    )
  }

  const editable = isEditable(session.status)
  const processing = isProcessing(session.status)

  return (
    <div
      style={{
        maxWidth: 640,
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        color: 'var(--aurora-text)',
      }}
    >
      {/* Page header */}
      <div>
        <h1
          style={{
            fontSize: 22,
            fontWeight: 800,
            color: 'var(--aurora-text)',
            letterSpacing: '-0.02em',
            margin: '0 0 4px',
          }}
        >
          Import Wizard
        </h1>
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
          Review and finalize your import before adding it to the library.
        </p>
      </div>

      {/* Error banner for failed sessions */}
      {session.status === 'failed' && session.error && (
        <div
          style={{
            background: 'rgba(220,38,38,0.08)',
            border: '1px solid rgba(220,38,38,0.25)',
            borderRadius: 10,
            padding: '12px 16px',
          }}
        >
          <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-danger)', margin: '0 0 4px' }}>
            Import processing failed
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-danger)', fontFamily: 'monospace', margin: '0 0 4px' }}>
            {session.error}
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            You can still edit the fields below and commit manually.
          </p>
        </div>
      )}

      {/* Scrape note — AgentQL fetch notice or blocked/budget message */}
      {session.scrape_note && (
        <div
          style={{
            background: session.scrape_note.startsWith('Fetched via AgentQL')
              ? 'rgba(15,164,171,0.06)'
              : 'rgba(245,158,11,0.07)',
            border: `1px solid ${session.scrape_note.startsWith('Fetched via AgentQL')
              ? 'rgba(15,164,171,0.25)'
              : 'rgba(245,158,11,0.25)'}`,
            borderRadius: 10,
            padding: '10px 14px',
          }}
        >
          <p
            style={{
              fontSize: 12,
              color: session.scrape_note.startsWith('Fetched via AgentQL')
                ? 'var(--aurora-accent)'
                : '#D97706',
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            {session.scrape_note}
          </p>
        </div>
      )}

      {/* Processing spinner */}
      {processing ? (
        <div style={AURORA_CARD}>
          <ProcessingOverlay sessionId={session.id} />
        </div>
      ) : !editable ? null : (
        /* Wizard card */
        <div style={{ ...AURORA_CARD, padding: '28px 24px' }}>
          {/* Stepper */}
          <div style={{ marginBottom: 28 }}>
            <StepProgress current={step} />
          </div>

          {/* Step content */}
          {step === 'title' && (
            <TitleStep
              session={session}
              onNext={() => setStep(nextStep(step))}
            />
          )}
          {step === 'images' && (
            <ImagesStep
              session={session}
              onNext={() => setStep(nextStep(step))}
              onPrev={() => setStep(prevStep(step))}
            />
          )}
          {step === 'tags' && (
            <TagsStep
              session={session}
              onNext={() => setStep(nextStep(step))}
              onPrev={() => setStep(prevStep(step))}
            />
          )}
          {step === 'creator' && (
            <CreatorStep
              session={session}
              onNext={() => setStep(nextStep(step))}
              onPrev={() => setStep(prevStep(step))}
            />
          )}
          {step === 'summary' && (
            <SummaryStep
              session={session}
              onPrev={() => setStep(prevStep(step))}
              onCancelled={() => {}}
            />
          )}
        </div>
      )}
    </div>
  )
}
