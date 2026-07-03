/**
 * SetupPage — first-run wizard.
 *
 * Shown when GET /api/setup/status returns { initialized: false }.
 * Step 1 (required): admin email, name, password, instance name, timezone.
 * Step 2 (skippable): library, AI, tag seed — surfaced as a "configure later" panel.
 *
 * On submit: POST /api/setup → auto-logged in → redirect to /.
 *
 * Styling: standalone Aurora screen (gradient bg + glass card, dark+light).
 */

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'
import { AuroraInput, AuroraSelect } from '@/components/ui'

const TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Vancouver',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Amsterdam',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Kolkata',
  'Australia/Sydney',
]

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const PAGE_STYLE: React.CSSProperties = {
  minHeight: '100vh',
  background: 'linear-gradient(135deg, var(--aurora-bg-from) 0%, var(--aurora-bg-to) 100%)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '32px 16px',
}

const CARD_STYLE: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 16,
  backdropFilter: 'blur(20px)',
  WebkitBackdropFilter: 'blur(20px)',
  padding: '28px 32px',
}

const LABEL_STYLE: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.07em',
  display: 'block',
  marginBottom: 5,
}

const BTN_PRIMARY: React.CSSProperties = {
  flex: 1,
  background: 'var(--aurora-accent)',
  color: '#fff',
  border: 'none',
  borderRadius: 10,
  padding: '10px 16px',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

const BTN_GHOST: React.CSSProperties = {
  flex: 1,
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 10,
  color: 'var(--aurora-text-dim)',
  padding: '10px 16px',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'opacity 0.15s',
}

// ---------------------------------------------------------------------------
// SetupPage
// ---------------------------------------------------------------------------

export function SetupPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [step, setStep] = useState<1 | 2>(1)
  const [form, setForm] = useState({
    admin_email: '',
    admin_name: '',
    admin_password: '',
    instance_name: 'PartFolder 3D',
    timezone: 'UTC',
  })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  // Confirm-password is local UI state only — never sent to the API.
  const [confirmPassword, setConfirmPassword] = useState('')
  // True while awaiting the /me refetch post-mutation so the button stays
  // disabled/loading across the entire submit flow (issue #13 fix).
  const [isNavigating, setIsNavigating] = useState(false)

  const mutation = useMutation({
    mutationFn: () => api.runSetup(form),
    onSuccess: async () => {
      // The instance is now initialized and the backend auto-logged us in.
      // Write setupStatus directly (not invalidate) so AuthGuard doesn't read a
      // stale `initialized:false` from cache during the refetch and bounce us
      // back to /setup.
      queryClient.setQueryData(['setupStatus'], { initialized: true })
      setIsNavigating(true)
      try {
        // Await the /me refetch so AuthContext.user is populated before we
        // navigate.  Without this await, AuthGuard renders with user===null and
        // isLoading===false (background refetch doesn't flip isLoading) and
        // immediately redirects to /login — the race described in issue #13.
        await queryClient.refetchQueries({ queryKey: ['me'] })
        navigate('/', { replace: true })
      } catch {
        // Refetch failed (e.g. transient network error).  The session cookie is
        // set; fall back to /login where the user can proceed normally.
        navigate('/login', { replace: true })
      }
    },
  })

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target
    if (name === 'admin_confirm_password') {
      setConfirmPassword(value)
      setFieldErrors((prev) => ({ ...prev, admin_confirm_password: '' }))
    } else {
      setForm((prev) => ({ ...prev, [name]: value }))
      setFieldErrors((prev) => ({ ...prev, [name]: '' }))
    }
  }

  const validate = (): boolean => {
    const errors: Record<string, string> = {}
    if (!form.admin_email) errors['admin_email'] = 'Email is required'
    if (!form.admin_name.trim()) errors['admin_name'] = 'Name is required'
    if (form.admin_password.length < 8)
      errors['admin_password'] = 'Password must be at least 8 characters'
    if (form.admin_password !== confirmPassword)
      errors['admin_confirm_password'] = 'Passwords do not match'
    if (!form.instance_name.trim())
      errors['instance_name'] = 'Instance name is required'
    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleNext = () => {
    if (validate()) setStep(2)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (step === 1) {
      handleNext()
      return
    }
    if (!validate()) return
    mutation.mutate()
  }

  return (
    <div style={PAGE_STYLE}>
      <div style={{ width: '100%', maxWidth: 460 }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          {/* Brand mark */}
          <div
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 48,
              height: 48,
              borderRadius: 14,
              background: 'var(--aurora-accent)',
              boxShadow: 'var(--aurora-glow)',
              marginBottom: 14,
            }}
          >
            <span style={{ color: '#fff', fontWeight: 900, fontSize: 18, letterSpacing: '-0.03em' }}>PF</span>
          </div>
          <h1
            style={{
              margin: 0,
              fontSize: 22,
              fontWeight: 800,
              color: 'var(--aurora-text)',
              letterSpacing: '-0.02em',
            }}
          >
            Welcome to PartFolder 3D
          </h1>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--aurora-muted)' }}>
            Let's get your instance set up. This only takes a minute.
          </p>
          {/* Step dots */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginTop: 14 }}>
            <StepDot n={1} current={step} />
            <StepDot n={2} current={step} />
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={CARD_STYLE}>
            {step === 1 && (
              <Step1
                form={form}
                confirmPassword={confirmPassword}
                errors={fieldErrors}
                onChange={handleChange}
              />
            )}

            {step === 2 && <Step2 />}

            {mutation.isError && (
              <p style={{ margin: '12px 0 0', fontSize: 13, color: 'var(--aurora-danger)' }}>
                {mutation.error instanceof api.ApiError
                  ? mutation.error.message
                  : 'Setup failed. Please try again.'}
              </p>
            )}

            <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
              {step === 2 && (
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  style={BTN_GHOST}
                >
                  Back
                </button>
              )}
              {step === 1 && (
                <button
                  type="button"
                  onClick={handleNext}
                  style={BTN_PRIMARY}
                >
                  Next
                </button>
              )}
              {step === 2 && (
                <button
                  type="submit"
                  disabled={mutation.isPending || isNavigating}
                  style={{
                    ...BTN_PRIMARY,
                    opacity: (mutation.isPending || isNavigating) ? 0.6 : 1,
                    cursor: (mutation.isPending || isNavigating) ? 'not-allowed' : 'pointer',
                  }}
                >
                  {mutation.isPending
                    ? 'Setting up…'
                    : isNavigating
                    ? 'Logging in…'
                    : 'Finish Setup'}
                </button>
              )}
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StepDot({ n, current }: { n: number; current: number }) {
  return (
    <div
      style={{
        height: 6,
        width: 28,
        borderRadius: 3,
        background: n <= current ? 'var(--aurora-accent)' : 'var(--aurora-glass-border)',
        transition: 'background 0.2s',
      }}
    />
  )
}

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null
  return (
    <p style={{ margin: '4px 0 0', fontSize: 11, color: 'var(--aurora-danger)' }}>{msg}</p>
  )
}

interface Step1Props {
  form: {
    admin_email: string
    admin_name: string
    admin_password: string
    instance_name: string
    timezone: string
  }
  confirmPassword: string
  errors: Record<string, string>
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void
}

function Step1({ form, confirmPassword, errors, onChange }: Step1Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
        Admin account &amp; instance basics
      </h2>

      <div>
        <label htmlFor="admin_email" style={LABEL_STYLE}>
          Email <span style={{ color: 'var(--aurora-danger)' }}>*</span>
        </label>
        <AuroraInput
          id="admin_email"
          name="admin_email"
          type="email"
          autoComplete="email"
          value={form.admin_email}
          onChange={onChange}
          placeholder="admin@example.com"
        />
        <FieldError msg={errors['admin_email']} />
      </div>

      <div>
        <label htmlFor="admin_name" style={LABEL_STYLE}>
          Your name <span style={{ color: 'var(--aurora-danger)' }}>*</span>
        </label>
        <AuroraInput
          id="admin_name"
          name="admin_name"
          type="text"
          autoComplete="name"
          value={form.admin_name}
          onChange={onChange}
          placeholder="Alice"
        />
        <FieldError msg={errors['admin_name']} />
      </div>

      <div>
        <label htmlFor="admin_password" style={LABEL_STYLE}>
          Password <span style={{ color: 'var(--aurora-danger)' }}>*</span>
        </label>
        <AuroraInput
          id="admin_password"
          name="admin_password"
          type="password"
          autoComplete="new-password"
          value={form.admin_password}
          onChange={onChange}
          placeholder="At least 8 characters"
        />
        <FieldError msg={errors['admin_password']} />
      </div>

      <div>
        <label htmlFor="admin_confirm_password" style={LABEL_STYLE}>
          Confirm password <span style={{ color: 'var(--aurora-danger)' }}>*</span>
        </label>
        <AuroraInput
          id="admin_confirm_password"
          name="admin_confirm_password"
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={onChange}
          placeholder="Re-enter your password"
        />
        <FieldError msg={errors['admin_confirm_password']} />
      </div>

      <div>
        <label htmlFor="instance_name" style={LABEL_STYLE}>
          Instance name <span style={{ color: 'var(--aurora-danger)' }}>*</span>
        </label>
        <AuroraInput
          id="instance_name"
          name="instance_name"
          type="text"
          value={form.instance_name}
          onChange={onChange}
          placeholder="PartFolder 3D"
        />
        <FieldError msg={errors['instance_name']} />
      </div>

      <div>
        <label htmlFor="timezone" style={LABEL_STYLE}>Timezone</label>
        <AuroraSelect
          id="timezone"
          name="timezone"
          value={form.timezone}
          onChange={onChange}
        >
          {TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </AuroraSelect>
      </div>
    </div>
  )
}

function Step2() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)' }}>
        Optional configuration
      </h2>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--aurora-muted)' }}>
        The following can be configured later in <strong>Settings</strong>. Skip
        ahead or come back any time.
      </p>

      <div
        style={{
          borderRadius: 10,
          border: '1px solid var(--aurora-glass-border)',
          background: 'var(--aurora-glass)',
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        <SkipItem label="Library paths" desc="Add and configure your 3D-print library storage mounts." />
        <SkipItem label="AI provider" desc="Connect Claude, OpenAI, or a local LLM for tag suggestions." />
        <SkipItem label="Tag seed" desc="Pre-populate a starter set of canonical tags." />
        <SkipItem label="Backup schedule" desc="Configure automated DB + config backups." />
      </div>

      <p style={{ margin: 0, fontSize: 12, color: 'var(--aurora-muted)' }}>
        Click <strong>Finish Setup</strong> to complete and log in as admin.
      </p>
    </div>
  )
}

function SkipItem({ label, desc }: { label: string; desc: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
      <span
        style={{
          marginTop: 5,
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: 'var(--aurora-accent)',
          flexShrink: 0,
        }}
      />
      <div>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--aurora-text)' }}>{label}</span>
        <span style={{ fontSize: 13, color: 'var(--aurora-muted)' }}> — {desc}</span>
      </div>
    </div>
  )
}
