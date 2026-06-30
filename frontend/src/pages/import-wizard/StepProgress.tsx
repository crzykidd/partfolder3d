/**
 * StepProgress — Aurora stepper progress indicator for the import wizard.
 */

import { Fragment } from 'react'
import { Check } from 'lucide-react'
import {
  WIZARD_STEPS,
  STEP_LABELS,
  type WizardStep,
  stepIndex,
} from '@/lib/import-utils'

interface StepProgressProps {
  current: WizardStep
}

export function StepProgress({ current }: StepProgressProps) {
  const idx = stepIndex(current)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
      {WIZARD_STEPS.map((step, i) => (
        <Fragment key={step}>
          {/* Step column */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
            {/* Circle */}
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 13,
                fontWeight: 700,
                transition: 'all 0.25s',
                background: i <= idx ? 'var(--aurora-accent)' : 'var(--aurora-glass)',
                border: i <= idx ? 'none' : '1px solid var(--aurora-glass-border)',
                color: i <= idx ? 'var(--aurora-accent-fg)' : 'var(--aurora-muted)',
                boxShadow: i === idx
                  ? '0 0 0 4px var(--aurora-pill), 0 0 16px var(--aurora-accent-glow)'
                  : 'none',
              }}
            >
              {i < idx ? <Check size={14} /> : i + 1}
            </div>
            {/* Label */}
            <span
              style={{
                marginTop: 6,
                fontSize: 10,
                fontWeight: i === idx ? 700 : 400,
                color: i === idx
                  ? 'var(--aurora-accent)'
                  : i < idx
                  ? 'var(--aurora-text-dim)'
                  : 'var(--aurora-muted)',
                whiteSpace: 'nowrap',
                textAlign: 'center',
              }}
            >
              {STEP_LABELS[step]}
            </span>
          </div>

          {/* Connector */}
          {i < WIZARD_STEPS.length - 1 && (
            <div
              style={{
                flex: 1,
                height: 2,
                marginTop: 15,
                background: i < idx ? 'var(--aurora-accent)' : 'var(--aurora-glass-border)',
                transition: 'background 0.3s',
              }}
            />
          )}
        </Fragment>
      ))}
    </div>
  )
}
