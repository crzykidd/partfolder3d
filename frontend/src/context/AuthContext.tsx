/**
 * AuthContext — provides auth state to the whole app.
 *
 * Also wraps the ThemeProviderContext so theme changes are server-persisted
 * when the user is logged in (while falling back to localStorage-only when not).
 *
 * Provider chain:
 *   ThemeProvider → QueryClientProvider → BrowserRouter → AuthProvider → …
 *
 * AuthProvider lives inside QueryClientProvider (needs useQuery) and inside
 * ThemeProvider (needs to intercept setTheme).
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useEffect,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { ThemeProviderContext } from '@/components/ThemeProvider'
import type { Theme } from '@/components/ThemeProvider'
import * as api from '@/lib/api'

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

export type AuthUser = api.MeResponse

interface AuthContextValue {
  /** Undefined while loading; null when unauthenticated. */
  user: AuthUser | null
  isLoading: boolean
  isAuthenticated: boolean
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  logout: async () => undefined,
})

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const themeCtx = useContext(ThemeProviderContext)

  const { data: user, isLoading } = useQuery<AuthUser | null>({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api.getMe()
      } catch (err) {
        if (err instanceof api.ApiError && (err.status === 401 || err.status === 403)) {
          return null
        }
        throw err
      }
    },
    staleTime: 0,   // always re-check on mount
    retry: false,   // don't retry 401s
  })

  const isAuthenticated = Boolean(user)

  // Server → client: sync server theme_pref when the user loads.
  // Only set on first login (when user_id changes) to avoid clobbering
  // an in-session theme change.
  const userId = user?.user_id
  useEffect(() => {
    if (user?.theme_pref) {
      themeCtx.setTheme(user.theme_pref as Theme)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]) // intentionally only re-run when the user identity changes

  const logout = useCallback(async () => {
    await api.logout()
    queryClient.setQueryData(['me'], null)
    queryClient.clear()
  }, [queryClient])

  // Client → server: wrap setTheme so it also persists to the server when
  // the user is authenticated.
  const serverAwareSetTheme = useCallback(
    (newTheme: Theme) => {
      themeCtx.setTheme(newTheme)
      if (isAuthenticated) {
        api.updateTheme(newTheme).catch(() => {
          // fire-and-forget; localStorage is already updated
        })
      }
    },
    [themeCtx, isAuthenticated],
  )

  // Re-provide ThemeProviderContext with the server-syncing setTheme so that
  // ThemeToggle (and any other component using useTheme()) gets it for free.
  const wrappedThemeCtx = useMemo(
    () => ({ theme: themeCtx.theme, setTheme: serverAwareSetTheme }),
    [themeCtx.theme, serverAwareSetTheme],
  )

  const authValue = useMemo<AuthContextValue>(
    () => ({
      user: user ?? null,
      isLoading,
      isAuthenticated,
      logout,
    }),
    [user, isLoading, isAuthenticated, logout],
  )

  return (
    <AuthContext.Provider value={authValue}>
      <ThemeProviderContext.Provider value={wrappedThemeCtx}>
        {children}
      </ThemeProviderContext.Provider>
    </AuthContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAuth(): AuthContextValue {
  return useContext(AuthContext)
}
