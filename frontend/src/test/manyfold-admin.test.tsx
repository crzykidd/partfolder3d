/**
 * Tests for ManyfoldPage — admin CRUD for Manyfold instance configuration
 * (Manyfold connector Part 3 — frontend).
 *
 * Covers:
 *  - Renders the instance list (display name, base_url, client_id, secret/enabled badges).
 *  - Add instance form calls createManyfoldInstance and closes on success.
 *  - Test connection surfaces success (ok=true, scope) and failure (ok=false, message).
 *  - The client secret is never rendered back anywhere in the row or edit panel.
 *  - Enable toggle calls patchManyfoldInstance({ enabled }).
 *  - Delete requires a confirm click before calling deleteManyfoldInstance.
 *
 * Hermetic: the @/lib/api module is mocked — no real network is touched.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ManyfoldPage } from '@/pages/admin/ManyfoldPage'
import type { ManyfoldInstance } from '@/lib/api'

// ---------------------------------------------------------------------------
// Module-level api mock
// ---------------------------------------------------------------------------

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    listManyfoldInstances: vi.fn(),
    createManyfoldInstance: vi.fn(),
    patchManyfoldInstance: vi.fn(),
    deleteManyfoldInstance: vi.fn(),
    testManyfoldConnection: vi.fn(),
  }
})

import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeInstance(overrides: Partial<ManyfoldInstance> = {}): ManyfoldInstance {
  return {
    id: 1,
    base_url: 'https://manyfold.example.com',
    domain: 'manyfold.example.com',
    display_name: 'My Manyfold',
    client_id: 'client-abc-123',
    has_secret: true,
    scopes: 'public read',
    enabled: true,
    last_connected_at: null,
    notes: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  }
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeQC()}>
      <MemoryRouter>
        <ManyfoldPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ManyfoldPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the instance list with name, base_url, client_id, and badges', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([makeInstance()])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Manyfold')).toBeInTheDocument()
    })
    expect(screen.getByText('https://manyfold.example.com')).toBeInTheDocument()
    expect(screen.getByText('client-abc-123')).toBeInTheDocument()
    expect(screen.getByText('Secret set')).toBeInTheDocument()
  })

  it('shows an empty state when no instances are configured', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(
        screen.getByText(/No Manyfold instances configured/i),
      ).toBeInTheDocument()
    })
  })

  it('never renders the client secret anywhere on the page', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([makeInstance()])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Manyfold')).toBeInTheDocument()
    })

    // Open the edit panel — its secret field must be blank (write-only), never
    // pre-filled with a real secret value.
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))

    const secretInput = screen.getByPlaceholderText(
      '•••••••• (leave blank to keep current secret)',
    ) as HTMLInputElement
    expect(secretInput.value).toBe('')
    expect(secretInput.type).toBe('password')
  })

  it('add instance form calls createManyfoldInstance and closes on success', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([])
    vi.mocked(api.createManyfoldInstance).mockResolvedValue(makeInstance({ id: 2 }))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/No Manyfold instances configured/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /add instance/i }))

    fireEvent.change(screen.getByPlaceholderText('https://manyfold.example.com'), {
      target: { value: 'https://mf.example.org' },
    })
    fireEvent.change(screen.getByPlaceholderText('OAuth client_id'), {
      target: { value: 'my-client-id' },
    })
    fireEvent.change(screen.getByPlaceholderText('Write-only; stored encrypted'), {
      target: { value: 'super-secret' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Add Instance' }))

    await waitFor(() => {
      expect(vi.mocked(api.createManyfoldInstance)).toHaveBeenCalledWith(
        expect.objectContaining({
          base_url: 'https://mf.example.org',
          client_id: 'my-client-id',
          client_secret: 'super-secret',
          scopes: 'public read',
          enabled: true,
        }),
      )
    })

    // Form closes after success — the placeholder for base_url is gone.
    await waitFor(() => {
      expect(
        screen.queryByPlaceholderText('https://manyfold.example.com'),
      ).not.toBeInTheDocument()
    })
  })

  it('shows the OAuth application hint with the entered base_url', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/No Manyfold instances configured/i)).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /add instance/i }))

    fireEvent.change(screen.getByPlaceholderText('https://manyfold.example.com'), {
      target: { value: 'https://mf.example.org' },
    })

    expect(
      screen.getByText('https://mf.example.org/oauth/applications'),
    ).toBeInTheDocument()
    expect(screen.getByText(/client-credentials/)).toBeInTheDocument()
    expect(screen.getByText(/public read/)).toBeInTheDocument()
  })

  it('test connection shows success with the granted scope', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([makeInstance()])
    vi.mocked(api.testManyfoldConnection).mockResolvedValue({ ok: true, scope: 'public read' })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Manyfold')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }))

    await waitFor(() => {
      expect(screen.getByText(/Connection OK/)).toBeInTheDocument()
    })
    expect(screen.getByText(/scope: public read/)).toBeInTheDocument()
    expect(vi.mocked(api.testManyfoldConnection)).toHaveBeenCalledWith(1)
  })

  it('test connection surfaces a structured failure message', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([makeInstance()])
    vi.mocked(api.testManyfoldConnection).mockResolvedValue({
      ok: false,
      message: 'Invalid or missing client credentials (HTTP 401).',
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Manyfold')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/Invalid or missing client credentials/),
      ).toBeInTheDocument()
    })
  })

  it('enable toggle calls patchManyfoldInstance with the new enabled state', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([makeInstance({ enabled: true })])
    vi.mocked(api.patchManyfoldInstance).mockResolvedValue(makeInstance({ enabled: false }))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Manyfold')).toBeInTheDocument()
    })

    const toggle = screen.getByRole('switch', { name: /disable instance/i })
    fireEvent.click(toggle)

    await waitFor(() => {
      expect(vi.mocked(api.patchManyfoldInstance)).toHaveBeenCalledWith(1, { enabled: false })
    })
  })

  it('delete requires a confirm click before calling deleteManyfoldInstance', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([makeInstance()])
    vi.mocked(api.deleteManyfoldInstance).mockResolvedValue(undefined)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('My Manyfold')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    // First click shows a confirm — delete is not called yet.
    expect(vi.mocked(api.deleteManyfoldInstance)).not.toHaveBeenCalled()
    const confirmBtn = screen.getByRole('button', { name: 'Confirm' })

    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(vi.mocked(api.deleteManyfoldInstance)).toHaveBeenCalledWith(1)
    })
  })

  it('shows "No secret" badge when has_secret is false', async () => {
    vi.mocked(api.listManyfoldInstances).mockResolvedValue([
      makeInstance({ has_secret: false }),
    ])

    renderPage()

    await waitFor(() => {
      const row = screen.getByText('My Manyfold').closest('tr')!
      expect(within(row).getByText('No secret')).toBeInTheDocument()
    })
  })
})
