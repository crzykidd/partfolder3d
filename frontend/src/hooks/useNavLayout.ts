/**
 * useNavLayout — per-user nav layout preference ('top' | 'side').
 *
 * Resolution order:
 *   1. Server preference via GET /api/me/nav-layout (TanStack Query, cached)
 *   2. localStorage key 'partfolder3d-nav-layout' (fallback if server errors/404)
 *   3. Role default: admin → 'side', user → 'top'
 *
 * Graceful fallback: if GET /api/me/nav-layout errors (e.g. migration not yet
 * applied on a running container), the app NEVER hard-breaks — it falls back to
 * localStorage + role default silently.
 *
 * setLayout(layout) persists optimistically to localStorage first, then PUTs
 * to the server (fire-and-forget). The query cache is updated immediately so
 * the shell re-renders without a round-trip delay.
 */

import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/context/AuthContext'
import * as api from '@/lib/api'
import { getDefaultLayout, type NavLayout } from '@/lib/navConfig'

const LS_KEY = 'partfolder3d-nav-layout'

function readLocalStorage(): NavLayout | null {
  try {
    const raw = window.localStorage.getItem(LS_KEY)
    if (raw === 'top' || raw === 'side') return raw
  } catch {
    // ignore
  }
  return null
}

function writeLocalStorage(layout: NavLayout): void {
  try {
    window.localStorage.setItem(LS_KEY, layout)
  } catch {
    // ignore
  }
}

export interface NavLayoutHook {
  /** The currently resolved layout. Never undefined after loading. */
  layout: NavLayout
  isLoading: boolean
  setLayout: (layout: NavLayout) => void
}

export function useNavLayout(): NavLayoutHook {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const role = (user?.role ?? 'user') as 'admin' | 'user'
  const roleDefault = getDefaultLayout(role)

  const { data: serverData, isLoading } = useQuery({
    queryKey: ['nav-layout'],
    queryFn: async () => {
      try {
        return await api.getNavLayout()
      } catch {
        // Graceful fallback — return null so callers use localStorage / role default
        return null
      }
    },
    enabled: Boolean(user),
    staleTime: 5 * 60_000,
    retry: false,
  })

  // Resolve: server → localStorage → role default
  const resolvedLayout: NavLayout = (() => {
    if (isLoading) {
      // While loading, prefer localStorage so there's no flash
      return readLocalStorage() ?? roleDefault
    }
    if (serverData?.nav_layout === 'top' || serverData?.nav_layout === 'side') {
      return serverData.nav_layout as NavLayout
    }
    return readLocalStorage() ?? roleDefault
  })()

  const setLayout = useCallback(
    (layout: NavLayout) => {
      // 1. Optimistic update — cache + localStorage immediately
      writeLocalStorage(layout)
      queryClient.setQueryData(['nav-layout'], { nav_layout: layout })

      // 2. Fire-and-forget PUT to server
      api.updateNavLayout(layout).catch(() => {
        // Non-fatal; localStorage already holds the preference
      })
    },
    [queryClient],
  )

  return { layout: resolvedLayout, isLoading, setLayout }
}
