/**
 * useDashboardLayout — per-user dashboard layout preference.
 *
 * Resolution order:
 *   1. Server preference via GET /api/me/dashboard (TanStack Query, cached)
 *   2. localStorage key 'partfolder3d-dashboard-layout' (fallback if server errors/404)
 *   3. Role default: admin → compact+admin tiles; user → comfortable+basic tiles
 *
 * Graceful fallback: if GET /api/me/dashboard errors (e.g. migration 0012 not yet
 * applied on a running container), the app NEVER hard-breaks — falls back to
 * localStorage + role default silently.
 *
 * updateStats / updateRail / setRailCollapsed: optimistic update to localStorage
 * + query cache immediately, then PUT to server fire-and-forget.
 */

import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/context/AuthContext'
import * as api from '@/lib/api'
import type { DashboardLayout } from '@/lib/api'

const LS_KEY = 'partfolder3d-dashboard-layout'

// ---------------------------------------------------------------------------
// Role defaults
// ---------------------------------------------------------------------------

const ADMIN_DEFAULT_LAYOUT: DashboardLayout = {
  stats: {
    density: 'compact',
    tiles: [
      'total-assets',
      'prints-done',
      'filament-used',
      'success-rate',
      'jobs-running',
      'pending-reviews',
      'open-issues',
      'pending-tags',
    ],
  },
  rail: { collapsed: false, widgets: ['quick-import'] },
}

const USER_DEFAULT_LAYOUT: DashboardLayout = {
  stats: {
    density: 'comfortable',
    tiles: ['total-assets', 'prints-done', 'filament-used', 'success-rate', 'jobs-running'],
  },
  rail: { collapsed: false, widgets: ['quick-import'] },
}

export function getRoleDefault(role: 'admin' | 'user'): DashboardLayout {
  return role === 'admin' ? ADMIN_DEFAULT_LAYOUT : USER_DEFAULT_LAYOUT
}

// ---------------------------------------------------------------------------
// localStorage helpers
// ---------------------------------------------------------------------------

function readLocalStorage(): DashboardLayout | null {
  try {
    const raw = window.localStorage.getItem(LS_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as DashboardLayout
    // Basic shape validation
    if (
      parsed &&
      typeof parsed === 'object' &&
      parsed.stats &&
      Array.isArray(parsed.stats.tiles) &&
      parsed.rail &&
      Array.isArray(parsed.rail.widgets)
    ) {
      return parsed
    }
  } catch {
    // ignore
  }
  return null
}

function writeLocalStorage(layout: DashboardLayout): void {
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(layout))
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface DashboardLayoutHook {
  layout: DashboardLayout
  isLoading: boolean
  updateStats: (stats: DashboardLayout['stats']) => void
  updateRail: (rail: DashboardLayout['rail']) => void
  setRailCollapsed: (collapsed: boolean) => void
}

export function useDashboardLayout(): DashboardLayoutHook {
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const role = (user?.role ?? 'user') as 'admin' | 'user'
  const roleDefault = getRoleDefault(role)

  const { data: serverData, isLoading } = useQuery({
    queryKey: ['dashboard-layout'],
    queryFn: async () => {
      try {
        return await api.getDashboardLayout()
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
  const resolvedLayout: DashboardLayout = (() => {
    if (isLoading) {
      return readLocalStorage() ?? roleDefault
    }
    if (serverData?.dashboard_layout) {
      return serverData.dashboard_layout
    }
    return readLocalStorage() ?? roleDefault
  })()

  const persist = useCallback(
    (layout: DashboardLayout) => {
      // 1. Optimistic update — localStorage + cache immediately
      writeLocalStorage(layout)
      queryClient.setQueryData(['dashboard-layout'], { dashboard_layout: layout })

      // 2. Fire-and-forget PUT
      api.updateDashboardLayout(layout).catch(() => {
        // Non-fatal; localStorage holds the preference
      })
    },
    [queryClient],
  )

  const updateStats = useCallback(
    (stats: DashboardLayout['stats']) => {
      persist({ ...resolvedLayout, stats })
    },
    [persist, resolvedLayout],
  )

  const updateRail = useCallback(
    (rail: DashboardLayout['rail']) => {
      persist({ ...resolvedLayout, rail })
    },
    [persist, resolvedLayout],
  )

  const setRailCollapsed = useCallback(
    (collapsed: boolean) => {
      persist({
        ...resolvedLayout,
        rail: { ...resolvedLayout.rail, collapsed },
      })
    },
    [persist, resolvedLayout],
  )

  return { layout: resolvedLayout, isLoading, updateStats, updateRail, setRailCollapsed }
}
