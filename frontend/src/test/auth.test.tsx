/**
 * Tests for AuthContext and AuthGuard routing logic.
 *
 * Tests:
 *  - AuthContext exposes correct user/isAuthenticated/isLoading state
 *  - AuthGuard redirects to /setup when uninitialized
 *  - AuthGuard redirects to /login when unauthenticated
 *  - AuthGuard renders children when authenticated
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '@/components/ThemeProvider'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import { AuthGuard, AdminGuard } from '@/components/AuthGuard'
import type { MeResponse } from '@/lib/api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock the api module globally; individual tests override what they need.
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    getMe: vi.fn(),
    getSetupStatus: vi.fn(),
    logout: vi.fn().mockResolvedValue({ ok: true }),
    updateTheme: vi.fn().mockResolvedValue({ theme_pref: 'system' }),
  }
})

import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
}

function Wrapper({ children, initialPath = '/' }: { children: React.ReactNode; initialPath?: string }) {
  const qc = makeQueryClient()
  return (
    <ThemeProvider defaultTheme="system" storageKey="test-theme">
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[initialPath]}>
          <AuthProvider>{children}</AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

function AuthDisplay() {
  const { user, isLoading, isAuthenticated } = useAuth()
  if (isLoading) return <div data-testid="loading">loading</div>
  return (
    <div>
      <div data-testid="authenticated">{String(isAuthenticated)}</div>
      <div data-testid="user-name">{user?.name ?? 'null'}</div>
      <div data-testid="user-role">{user?.role ?? 'null'}</div>
    </div>
  )
}

const MOCK_USER: MeResponse = {
  user_id: 1,
  email: 'admin@test.com',
  name: 'Admin',
  role: 'admin',
  theme_pref: 'system',
  is_active: true,
}

// ---------------------------------------------------------------------------
// AuthContext state machine
// ---------------------------------------------------------------------------

describe('AuthContext state machine', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading initially then authenticated=true when /me returns user', async () => {
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)

    render(
      <Wrapper>
        <AuthDisplay />
      </Wrapper>,
    )

    expect(screen.getByTestId('loading')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.queryByTestId('loading')).not.toBeInTheDocument()
    })

    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user-name').textContent).toBe('Admin')
    expect(screen.getByTestId('user-role').textContent).toBe('admin')
  })

  it('shows authenticated=false when /me returns 401', async () => {
    vi.mocked(api.getMe).mockRejectedValue(
      new api.ApiError(401, 'Unauthorized'),
    )

    render(
      <Wrapper>
        <AuthDisplay />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.queryByTestId('loading')).not.toBeInTheDocument()
    })

    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('user-name').textContent).toBe('null')
  })
})

// ---------------------------------------------------------------------------
// First-run routing
// ---------------------------------------------------------------------------

describe('AuthGuard first-run routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('redirects to /setup when instance is not initialized', async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({ initialized: false })
    vi.mocked(api.getMe).mockRejectedValue(new api.ApiError(401, 'Unauthorized'))

    render(
      <Wrapper>
        <Routes>
          <Route path="/setup" element={<div data-testid="setup-page">Setup</div>} />
          <Route element={<AuthGuard />}>
            <Route path="/" element={<div data-testid="home">Home</div>} />
          </Route>
        </Routes>
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('setup-page')).toBeInTheDocument()
    })
  })

  it('redirects to /login when initialized but unauthenticated', async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({ initialized: true })
    vi.mocked(api.getMe).mockRejectedValue(new api.ApiError(401, 'Unauthorized'))

    render(
      <Wrapper>
        <Routes>
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
          <Route element={<AuthGuard />}>
            <Route path="/" element={<div data-testid="home">Home</div>} />
          </Route>
        </Routes>
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('login-page')).toBeInTheDocument()
    })
  })

  it('renders protected content when authenticated', async () => {
    vi.mocked(api.getSetupStatus).mockResolvedValue({ initialized: true })
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)

    render(
      <Wrapper>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route
              element={<Outlet />}
            >
              <Route path="/" element={<div data-testid="home">Home</div>} />
            </Route>
          </Route>
        </Routes>
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('home')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// AdminGuard
// ---------------------------------------------------------------------------

describe('AdminGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children for admin users', async () => {
    vi.mocked(api.getMe).mockResolvedValue(MOCK_USER)

    render(
      <Wrapper>
        <AuthDisplay />
        <AdminGuard>
          <div data-testid="admin-content">Admin only</div>
        </AdminGuard>
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('admin-content')).toBeInTheDocument()
    })
  })

  it('shows 403 for non-admin users', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...MOCK_USER,
      role: 'user',
    })

    render(
      <Wrapper>
        <AuthDisplay />
        <AdminGuard>
          <div data-testid="admin-content">Admin only</div>
        </AdminGuard>
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument()
      expect(screen.getByText('Access Denied')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// Theme sync
// ---------------------------------------------------------------------------

describe('Theme sync (server → client)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Clear localStorage theme before each test
    localStorage.removeItem('test-theme')
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('calls updateTheme when setTheme is called while authenticated', async () => {
    vi.mocked(api.getMe).mockResolvedValue({
      ...MOCK_USER,
      theme_pref: 'dark',
    })
    vi.mocked(api.updateTheme).mockResolvedValue({ theme_pref: 'dark' })

    function ThemeChanger() {
      const { setTheme } = useContext_ThemeProvider()
      const { isAuthenticated } = useAuth()
      return (
        <div>
          <div data-testid="auth">{String(isAuthenticated)}</div>
          <button
            data-testid="toggle-theme"
            onClick={() => setTheme('light')}
          >
            Toggle
          </button>
        </div>
      )
    }

    const { fireEvent } = await import('@testing-library/react')
    const { useContext } = await import('react')
    const { ThemeProviderContext } = await import('@/components/ThemeProvider')
    function useContext_ThemeProvider() {
      return useContext(ThemeProviderContext)
    }

    const qc = makeQueryClient()
    render(
      <ThemeProvider defaultTheme="system" storageKey="test-theme">
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <AuthProvider>
              <ThemeChanger />
            </AuthProvider>
          </MemoryRouter>
        </QueryClientProvider>
      </ThemeProvider>,
    )

    // Wait for auth to resolve
    await waitFor(() => {
      expect(screen.getByTestId('auth').textContent).toBe('true')
    })

    // Trigger theme change
    fireEvent.click(screen.getByTestId('toggle-theme'))

    await waitFor(() => {
      expect(api.updateTheme).toHaveBeenCalledWith('light')
    })
  })
})
