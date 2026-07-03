/**
 * Tests for SetupPage — regression guards for issue #13 and confirm-password.
 *
 * Tests:
 *  - onSuccess awaits the me refetch before calling navigate (race fix)
 *  - Mismatched confirm-password blocks step advance with the correct error
 *  - Matching confirm-password allows advancing to step 2
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '@/components/ThemeProvider'
import { SetupPage } from '@/pages/SetupPage'
import { useNavigate } from 'react-router-dom'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Module-level mocks
// ---------------------------------------------------------------------------

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: vi.fn() }
})

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    runSetup: vi.fn(),
    getMe: vi.fn(),
    getSetupStatus: vi.fn(),
    logout: vi.fn().mockResolvedValue({ ok: true }),
    updateTheme: vi.fn().mockResolvedValue({ theme_pref: 'system' }),
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSetupPage(qc: QueryClient) {
  return render(
    <ThemeProvider defaultTheme="system" storageKey="test-setup-theme">
      <QueryClientProvider client={qc}>
        <SetupPage />
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

/** Fill all step-1 fields and optionally click the Next button. */
function fillStep1(opts: {
  password?: string
  confirmPassword?: string
  clickNext?: boolean
}) {
  const { password = 'hunter2correct', confirmPassword = 'hunter2correct', clickNext = true } = opts

  fireEvent.change(screen.getByLabelText(/email/i), {
    target: { value: 'admin@test.com' },
  })
  fireEvent.change(screen.getByLabelText(/your name/i), {
    target: { value: 'Admin' },
  })
  // "Password *" — regex anchored so it doesn't match "Confirm password"
  fireEvent.change(screen.getByLabelText(/^password/i), {
    target: { value: password },
  })
  fireEvent.change(screen.getByLabelText(/confirm password/i), {
    target: { value: confirmPassword },
  })

  if (clickNext) {
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
  }
}

// ---------------------------------------------------------------------------
// Suite: auto-login navigation race (issue #13)
// ---------------------------------------------------------------------------

describe('SetupPage auto-login navigation (issue #13)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('awaits the me refetch before calling navigate', async () => {
    // Control exactly when refetchQueries resolves so we can check the state
    // midway — before and after the refetch completes.
    let resolveRefetch!: () => void
    const refetchDone = new Promise<void>((resolve) => {
      resolveRefetch = resolve
    })

    const mockNavigate = vi.fn()
    vi.mocked(useNavigate).mockReturnValue(mockNavigate)

    vi.mocked(api.runSetup).mockResolvedValue({ ok: true, user_id: 1 })

    const qc = makeQC()
    // Intercept refetchQueries on this client instance.
    const refetchSpy = vi.spyOn(qc, 'refetchQueries').mockReturnValue(
      refetchDone as ReturnType<QueryClient['refetchQueries']>,
    )

    renderSetupPage(qc)

    // Navigate wizard to step 2
    fillStep1({})
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /finish setup/i })).toBeInTheDocument(),
    )

    // Submit the form
    fireEvent.click(screen.getByRole('button', { name: /finish setup/i }))

    // onSuccess fires (runSetup resolved) → should call refetchQueries and WAIT
    await waitFor(() => expect(refetchSpy).toHaveBeenCalledWith({ queryKey: ['me'] }))

    // navigate must NOT have been called yet — the refetch is still pending.
    // With the old fire-and-forget code, navigate fired synchronously in
    // onSuccess (before any await) and this assertion would fail.
    expect(mockNavigate).not.toHaveBeenCalled()

    // Resolve the pending refetch
    act(() => {
      resolveRefetch()
    })

    // Now navigate should fire with ('/', {replace:true})
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })

  it('falls back to /login if the me refetch throws', async () => {
    const mockNavigate = vi.fn()
    vi.mocked(useNavigate).mockReturnValue(mockNavigate)

    vi.mocked(api.runSetup).mockResolvedValue({ ok: true, user_id: 1 })

    const qc = makeQC()
    vi.spyOn(qc, 'refetchQueries').mockRejectedValue(new Error('network error'))

    renderSetupPage(qc)
    fillStep1({})
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /finish setup/i })).toBeInTheDocument(),
    )

    fireEvent.click(screen.getByRole('button', { name: /finish setup/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login', { replace: true })
    })
    expect(mockNavigate).not.toHaveBeenCalledWith('/', expect.anything())
  })
})

// ---------------------------------------------------------------------------
// Suite: confirm-password validation
// ---------------------------------------------------------------------------

describe('SetupPage confirm-password validation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useNavigate).mockReturnValue(vi.fn())
  })

  it('shows "Passwords do not match" error when passwords differ', async () => {
    renderSetupPage(makeQC())

    fillStep1({ password: 'hunter2correct', confirmPassword: 'differentpass', clickNext: false })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    })

    // Should still be on step 1 — "Optional configuration" heading not shown
    expect(screen.queryByText('Optional configuration')).not.toBeInTheDocument()
  })

  it('blocks submission when confirm-password is empty', async () => {
    renderSetupPage(makeQC())

    fillStep1({ password: 'hunter2correct', confirmPassword: '', clickNext: false })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    })
    expect(screen.queryByText('Optional configuration')).not.toBeInTheDocument()
  })

  it('allows advancing to step 2 when passwords match', async () => {
    renderSetupPage(makeQC())

    fillStep1({ password: 'hunter2correct', confirmPassword: 'hunter2correct' })

    await waitFor(() => {
      expect(screen.getByText('Optional configuration')).toBeInTheDocument()
    })
    expect(screen.queryByText('Passwords do not match')).not.toBeInTheDocument()
  })

  it('clears confirm-password error when user corrects the field', async () => {
    renderSetupPage(makeQC())

    // First: wrong confirm password
    fillStep1({ password: 'hunter2correct', confirmPassword: 'wrong', clickNext: false })
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => {
      expect(screen.getByText('Passwords do not match')).toBeInTheDocument()
    })

    // Correct the confirm-password field
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: 'hunter2correct' },
    })

    // Error should be cleared immediately on change
    expect(screen.queryByText('Passwords do not match')).not.toBeInTheDocument()
  })
})
