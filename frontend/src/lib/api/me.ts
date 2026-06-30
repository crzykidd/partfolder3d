import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Per-user theme
// ---------------------------------------------------------------------------

export const updateTheme = (theme_pref: string): Promise<{ theme_pref: string }> =>
  apiFetch<{ theme_pref: string }>('/api/me/theme', {
    method: 'PUT',
    body: JSON.stringify({ theme_pref }),
  })

// ---------------------------------------------------------------------------
// Per-user nav layout (Phase 11)
// ---------------------------------------------------------------------------

export const getNavLayout = (): Promise<{ nav_layout: string }> =>
  apiFetch<{ nav_layout: string }>('/api/me/nav-layout')

export const updateNavLayout = (nav_layout: string | null): Promise<{ nav_layout: string }> =>
  apiFetch<{ nav_layout: string }>('/api/me/nav-layout', {
    method: 'PUT',
    body: JSON.stringify({ nav_layout }),
  })

// ---------------------------------------------------------------------------
// Per-user dashboard layout (Phase 12)
// ---------------------------------------------------------------------------

export interface DashboardStatsLayout {
  density: 'comfortable' | 'compact'
  tiles: string[]
}

export interface DashboardRailLayout {
  collapsed: boolean
  widgets: string[]
}

export interface DashboardLayout {
  stats: DashboardStatsLayout
  rail: DashboardRailLayout
}

export const getDashboardLayout = (): Promise<{ dashboard_layout: DashboardLayout }> =>
  apiFetch<{ dashboard_layout: DashboardLayout }>('/api/me/dashboard')

export const updateDashboardLayout = (
  dashboard_layout: DashboardLayout,
): Promise<{ dashboard_layout: DashboardLayout }> =>
  apiFetch<{ dashboard_layout: DashboardLayout }>('/api/me/dashboard', {
    method: 'PUT',
    body: JSON.stringify({ dashboard_layout }),
  })
