/**
 * SetupPage — first-run wizard.
 *
 * Shown when GET /api/setup/status returns { initialized: false }.
 * Step 1 (required): admin email, name, password, instance name, timezone.
 * Step 2 (skippable): library, AI, tag seed — surfaced as a "configure later" panel.
 *
 * On submit: POST /api/setup → auto-logged in → redirect to /.
 */

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'

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

  const mutation = useMutation({
    mutationFn: () => api.runSetup(form),
    onSuccess: () => {
      // The instance is now initialized and the backend auto-logged us in.
      // Write setupStatus directly (not invalidate) so AuthGuard doesn't read a
      // stale `initialized:false` from cache during the refetch and bounce us
      // back to /setup. Refetch /me so AuthContext picks up the new session.
      queryClient.setQueryData(['setupStatus'], { initialized: true })
      queryClient.invalidateQueries({ queryKey: ['me'] })
      navigate('/', { replace: true })
    },
  })

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    setFieldErrors((prev) => ({ ...prev, [name]: '' }))
  }

  const validate = (): boolean => {
    const errors: Record<string, string> = {}
    if (!form.admin_email) errors['admin_email'] = 'Email is required'
    if (!form.admin_name.trim()) errors['admin_name'] = 'Name is required'
    if (form.admin_password.length < 8)
      errors['admin_password'] = 'Password must be at least 8 characters'
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
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-foreground">Welcome to PartFolder 3D</h1>
          <p className="mt-2 text-muted-foreground">
            Let's get your instance set up. This only takes a minute.
          </p>
          <div className="flex justify-center gap-2 mt-4">
            <StepDot n={1} current={step} />
            <StepDot n={2} current={step} />
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            {step === 1 && (
              <Step1
                form={form}
                errors={fieldErrors}
                onChange={handleChange}
              />
            )}

            {step === 2 && <Step2 />}

            {mutation.isError && (
              <p className="mt-4 text-sm text-destructive">
                {mutation.error instanceof api.ApiError
                  ? mutation.error.message
                  : 'Setup failed. Please try again.'}
              </p>
            )}

            <div className="mt-6 flex gap-3">
              {step === 2 && (
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="flex-1 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                  Back
                </button>
              )}
              {step === 1 && (
                <button
                  type="button"
                  onClick={handleNext}
                  className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  Next
                </button>
              )}
              {step === 2 && (
                <button
                  type="submit"
                  disabled={mutation.isPending}
                  className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  {mutation.isPending ? 'Setting up…' : 'Finish Setup'}
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
      className={`h-2 w-8 rounded-full transition-colors ${
        n <= current ? 'bg-primary' : 'bg-muted'
      }`}
    />
  )
}

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null
  return <p className="mt-1 text-xs text-destructive">{msg}</p>
}

interface Step1Props {
  form: {
    admin_email: string
    admin_name: string
    admin_password: string
    instance_name: string
    timezone: string
  }
  errors: Record<string, string>
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void
}

function Step1({ form, errors, onChange }: Step1Props) {
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Admin account &amp; instance basics</h2>

      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="admin_email">
          Email <span className="text-destructive">*</span>
        </label>
        <input
          id="admin_email"
          name="admin_email"
          type="email"
          autoComplete="email"
          value={form.admin_email}
          onChange={onChange}
          className="input-base w-full"
          placeholder="admin@example.com"
        />
        <FieldError msg={errors['admin_email']} />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="admin_name">
          Your name <span className="text-destructive">*</span>
        </label>
        <input
          id="admin_name"
          name="admin_name"
          type="text"
          autoComplete="name"
          value={form.admin_name}
          onChange={onChange}
          className="input-base w-full"
          placeholder="Alice"
        />
        <FieldError msg={errors['admin_name']} />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="admin_password">
          Password <span className="text-destructive">*</span>
        </label>
        <input
          id="admin_password"
          name="admin_password"
          type="password"
          autoComplete="new-password"
          value={form.admin_password}
          onChange={onChange}
          className="input-base w-full"
          placeholder="At least 8 characters"
        />
        <FieldError msg={errors['admin_password']} />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="instance_name">
          Instance name <span className="text-destructive">*</span>
        </label>
        <input
          id="instance_name"
          name="instance_name"
          type="text"
          value={form.instance_name}
          onChange={onChange}
          className="input-base w-full"
          placeholder="PartFolder 3D"
        />
        <FieldError msg={errors['instance_name']} />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="timezone">
          Timezone
        </label>
        <select
          id="timezone"
          name="timezone"
          value={form.timezone}
          onChange={onChange}
          className="input-base w-full"
        >
          {TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}

function Step2() {
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Optional configuration</h2>
      <p className="text-sm text-muted-foreground">
        The following can be configured later in <strong>Settings</strong>. Skip
        ahead or come back any time.
      </p>

      <div className="rounded-md border border-border bg-muted/30 p-4 flex flex-col gap-2">
        <SkipItem label="Library paths" desc="Add and configure your 3D-print library storage mounts." />
        <SkipItem label="AI provider" desc="Connect Claude, OpenAI, or a local LLM for tag suggestions." />
        <SkipItem label="Tag seed" desc="Pre-populate a starter set of canonical tags." />
        <SkipItem label="Backup schedule" desc="Configure automated DB + config backups." />
      </div>

      <p className="text-xs text-muted-foreground">
        Click <strong>Finish Setup</strong> to complete and log in as admin.
      </p>
    </div>
  )
}

function SkipItem({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 text-muted-foreground">·</span>
      <div>
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm text-muted-foreground"> — {desc}</span>
      </div>
    </div>
  )
}
