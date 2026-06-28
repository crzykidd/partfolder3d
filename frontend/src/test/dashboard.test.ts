/**
 * Tests for the widget framework (Phase 12 / UI A2):
 *   - Widget registry: filtering by region + role
 *   - Default layout by role (admin vs user)
 *   - useDashboardLayout fallback resolution logic (pure function simulation)
 *   - resolveWidgets: unknown IDs filtered, admin-only filtered for non-admin
 */

import { describe, it, expect } from 'vitest'
import {
  WIDGET_REGISTRY,
  getWidgets,
  getWidgetById,
  resolveWidgets,
} from '@/lib/widgets/registry'
import { getRoleDefault } from '@/hooks/useDashboardLayout'
import type { DashboardLayout } from '@/lib/api'

// ---------------------------------------------------------------------------
// Widget registry: region filtering
// ---------------------------------------------------------------------------

describe('WIDGET_REGISTRY structure', () => {
  it('every widget has an id, title, region, icon, and defaultForRoles', () => {
    for (const w of WIDGET_REGISTRY) {
      expect(w.id).toBeTruthy()
      expect(w.title).toBeTruthy()
      expect(w.region === 'stat' || w.region === 'panel').toBe(true)
      expect(w.icon).toBeTruthy()
      expect(Array.isArray(w.defaultForRoles)).toBe(true)
    }
  })

  it('stat widgets have a getValue function', () => {
    const statWidgets = WIDGET_REGISTRY.filter((w) => w.region === 'stat')
    for (const w of statWidgets) {
      expect(typeof (w as { getValue?: unknown }).getValue).toBe('function')
    }
  })

  it('panel widgets have a component', () => {
    const panelWidgets = WIDGET_REGISTRY.filter((w) => w.region === 'panel')
    for (const w of panelWidgets) {
      expect(typeof (w as { component?: unknown }).component).toBe('function')
    }
  })

  it('all widget IDs are unique', () => {
    const ids = WIDGET_REGISTRY.map((w) => w.id)
    const uniqueIds = new Set(ids)
    expect(ids.length).toBe(uniqueIds.size)
  })

  it('contains the 5 core stat tiles from A1', () => {
    const coreIds = ['total-assets', 'prints-done', 'filament-used', 'success-rate', 'jobs-running']
    for (const id of coreIds) {
      expect(getWidgetById(id)).toBeDefined()
      expect(getWidgetById(id)?.region).toBe('stat')
    }
  })

  it('quick-import is a panel widget', () => {
    const w = getWidgetById('quick-import')
    expect(w?.region).toBe('panel')
  })

  it('admin-only stat widgets are present', () => {
    const adminOnlyIds = ['open-issues', 'pending-reviews', 'pending-tags']
    for (const id of adminOnlyIds) {
      const w = getWidgetById(id)
      expect(w).toBeDefined()
      expect(w?.requiresAdmin).toBe(true)
    }
  })
})

// ---------------------------------------------------------------------------
// getWidgets: region + admin filtering
// ---------------------------------------------------------------------------

describe('getWidgets', () => {
  it('returns only stat widgets when region=stat', () => {
    const widgets = getWidgets('stat', true)
    for (const w of widgets) {
      expect(w.region).toBe('stat')
    }
  })

  it('returns only panel widgets when region=panel', () => {
    const widgets = getWidgets('panel', true)
    for (const w of widgets) {
      expect(w.region).toBe('panel')
    }
  })

  it('admin=true includes admin-only widgets', () => {
    const adminWidgets = getWidgets('stat', true)
    const ids = adminWidgets.map((w) => w.id)
    expect(ids).toContain('pending-reviews')
    expect(ids).toContain('open-issues')
    expect(ids).toContain('pending-tags')
  })

  it('admin=false excludes admin-only widgets', () => {
    const userWidgets = getWidgets('stat', false)
    const ids = userWidgets.map((w) => w.id)
    expect(ids).not.toContain('pending-reviews')
    expect(ids).not.toContain('open-issues')
    expect(ids).not.toContain('pending-tags')
  })

  it('core tiles visible to non-admin', () => {
    const userWidgets = getWidgets('stat', false)
    const ids = userWidgets.map((w) => w.id)
    expect(ids).toContain('total-assets')
    expect(ids).toContain('prints-done')
  })
})

// ---------------------------------------------------------------------------
// getWidgetById
// ---------------------------------------------------------------------------

describe('getWidgetById', () => {
  it('returns undefined for unknown id', () => {
    expect(getWidgetById('does-not-exist')).toBeUndefined()
  })

  it('returns the correct widget for known id', () => {
    const w = getWidgetById('total-assets')
    expect(w?.title).toBe('Total Assets')
    expect(w?.region).toBe('stat')
  })
})

// ---------------------------------------------------------------------------
// resolveWidgets
// ---------------------------------------------------------------------------

describe('resolveWidgets', () => {
  it('filters out unknown IDs gracefully', () => {
    const resolved = resolveWidgets(['total-assets', 'fake-widget', 'jobs-running'], 'stat', false)
    expect(resolved.map((w) => w.id)).toEqual(['total-assets', 'jobs-running'])
  })

  it('preserves order of the input IDs', () => {
    const ids = ['jobs-running', 'total-assets', 'prints-done']
    const resolved = resolveWidgets(ids, 'stat', false)
    expect(resolved.map((w) => w.id)).toEqual(ids)
  })

  it('filters admin-only widgets for non-admin when isAdmin=false', () => {
    const resolved = resolveWidgets(
      ['total-assets', 'pending-reviews', 'jobs-running'],
      'stat',
      false,
    )
    const ids = resolved.map((w) => w.id)
    expect(ids).toContain('total-assets')
    expect(ids).not.toContain('pending-reviews')
    expect(ids).toContain('jobs-running')
  })

  it('includes admin-only widgets when isAdmin=true', () => {
    const resolved = resolveWidgets(
      ['total-assets', 'pending-reviews', 'jobs-running'],
      'stat',
      true,
    )
    const ids = resolved.map((w) => w.id)
    expect(ids).toContain('pending-reviews')
  })

  it('filters to correct region', () => {
    // quick-import is panel; should not appear in stat region
    const resolved = resolveWidgets(['total-assets', 'quick-import'], 'stat', false)
    const ids = resolved.map((w) => w.id)
    expect(ids).toContain('total-assets')
    expect(ids).not.toContain('quick-import')
  })
})

// ---------------------------------------------------------------------------
// getRoleDefault: admin vs user layouts
// ---------------------------------------------------------------------------

describe('getRoleDefault', () => {
  it('admin gets compact density', () => {
    const layout = getRoleDefault('admin')
    expect(layout.stats.density).toBe('compact')
  })

  it('user gets comfortable density', () => {
    const layout = getRoleDefault('user')
    expect(layout.stats.density).toBe('comfortable')
  })

  it('admin layout includes admin-only tiles', () => {
    const layout = getRoleDefault('admin')
    expect(layout.stats.tiles).toContain('pending-reviews')
    expect(layout.stats.tiles).toContain('open-issues')
    expect(layout.stats.tiles).toContain('pending-tags')
  })

  it('user layout does NOT include admin-only tiles', () => {
    const layout = getRoleDefault('user')
    expect(layout.stats.tiles).not.toContain('pending-reviews')
    expect(layout.stats.tiles).not.toContain('open-issues')
    expect(layout.stats.tiles).not.toContain('pending-tags')
  })

  it('both layouts include the 5 core stat tiles', () => {
    const coreIds = ['total-assets', 'prints-done', 'filament-used', 'success-rate', 'jobs-running']
    for (const role of ['admin', 'user'] as const) {
      const layout = getRoleDefault(role)
      for (const id of coreIds) {
        expect(layout.stats.tiles).toContain(id)
      }
    }
  })

  it('default rail includes quick-import', () => {
    for (const role of ['admin', 'user'] as const) {
      const layout = getRoleDefault(role)
      expect(layout.rail.widgets).toContain('quick-import')
    }
  })

  it('default rail is not collapsed', () => {
    for (const role of ['admin', 'user'] as const) {
      const layout = getRoleDefault(role)
      expect(layout.rail.collapsed).toBe(false)
    }
  })
})

// ---------------------------------------------------------------------------
// useDashboardLayout fallback resolution logic (pure simulation)
// ---------------------------------------------------------------------------

describe('dashboard layout fallback resolution logic', () => {
  /**
   * Simulate the resolution logic from useDashboardLayout without a browser.
   * Mirrors the hook's resolution order: server → localStorage → role default.
   */
  function resolveLayout(
    serverLayout: DashboardLayout | null | undefined,
    localStorageLayout: DashboardLayout | null,
    role: 'admin' | 'user',
  ): DashboardLayout {
    const roleDefault = getRoleDefault(role)
    if (serverLayout) return serverLayout
    if (localStorageLayout) return localStorageLayout
    return roleDefault
  }

  const mockLayout: DashboardLayout = {
    stats: { density: 'compact', tiles: ['total-assets'] },
    rail: { collapsed: true, widgets: [] },
  }

  const localLayout: DashboardLayout = {
    stats: { density: 'comfortable', tiles: ['prints-done'] },
    rail: { collapsed: false, widgets: ['quick-import'] },
  }

  it('prefers server layout when available', () => {
    const result = resolveLayout(mockLayout, localLayout, 'user')
    expect(result.stats.tiles).toEqual(['total-assets'])
    expect(result.rail.collapsed).toBe(true)
  })

  it('falls back to localStorage when server returns null', () => {
    const result = resolveLayout(null, localLayout, 'admin')
    expect(result.stats.tiles).toEqual(['prints-done'])
  })

  it('falls back to localStorage when server returns undefined (error)', () => {
    const result = resolveLayout(undefined, localLayout, 'user')
    expect(result.stats.tiles).toEqual(['prints-done'])
  })

  it('falls back to role default when both server and localStorage are null', () => {
    const adminResult = resolveLayout(null, null, 'admin')
    expect(adminResult.stats.density).toBe('compact')

    const userResult = resolveLayout(null, null, 'user')
    expect(userResult.stats.density).toBe('comfortable')
  })

  it('role defaults match the spec (admin→compact+admin tiles, user→comfortable+basic)', () => {
    const adminResult = resolveLayout(null, null, 'admin')
    expect(adminResult.stats.density).toBe('compact')
    expect(adminResult.stats.tiles).toContain('pending-reviews')

    const userResult = resolveLayout(null, null, 'user')
    expect(userResult.stats.density).toBe('comfortable')
    expect(userResult.stats.tiles).not.toContain('pending-reviews')
  })
})

// ---------------------------------------------------------------------------
// Stat widget getValue functions
// ---------------------------------------------------------------------------

describe('stat widget getValue functions', () => {
  const statWidgets = WIDGET_REGISTRY.filter((w) => w.region === 'stat') as Array<{
    id: string
    getValue: (cache: Record<string, unknown>) => string
  }>

  it('returns graceful dash when cache is empty', () => {
    for (const w of statWidgets) {
      if (w.id === 'storage-used') continue // always dashes
      const result = w.getValue({})
      // Should be '—' when data is missing
      expect(result).toBe('—')
    }
  })

  it('storage-used always returns dash (no endpoint)', () => {
    const storageWidget = statWidgets.find((w) => w.id === 'storage-used')
    expect(storageWidget).toBeDefined()
    const result = storageWidget!.getValue({ storageUsed: '5GB' })
    expect(result).toBe('—')
  })

  it('total-assets formats number with locale', () => {
    const w = statWidgets.find((w) => w.id === 'total-assets')!
    expect(w.getValue({ totalAssets: 1234 })).toBe('1,234')
    expect(w.getValue({ totalAssets: 0 })).toBe('0')
    expect(w.getValue({})).toBe('—')
  })

  it('success-rate formats as percentage', () => {
    const w = statWidgets.find((w) => w.id === 'success-rate')!
    // printStats.success_rate is a fraction (0-1)
    expect(w.getValue({ printStats: { success_rate: 0.95 } as never })).toBe('95%')
    expect(w.getValue({ printStats: { success_rate: 0 } as never })).toBe('0%')
  })

  it('filament-used converts grams to kg', () => {
    const w = statWidgets.find((w) => w.id === 'filament-used')!
    expect(w.getValue({ printStats: { total_filament_weight_g: 1500 } as never })).toBe('1.5 kg')
  })

  it('pending-tags computes difference of all minus active', () => {
    const w = statWidgets.find((w) => w.id === 'pending-tags')!
    expect(w.getValue({ allTagsCount: 10, activeTagsCount: 7 })).toBe('3')
    expect(w.getValue({ allTagsCount: 5, activeTagsCount: 5 })).toBe('0')
    // If only one count available, show dash
    expect(w.getValue({ allTagsCount: 10 })).toBe('—')
  })
})
