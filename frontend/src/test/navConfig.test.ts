/**
 * Tests for:
 *   - navConfig: role-filtering (getVisibleGroups)
 *   - navConfig: layout default by role (getDefaultLayout)
 *   - navConfig: all paths in NAV_GROUPS exist in the real route tree
 *   - useNavLayout: fallback resolution logic (pure logic, no network)
 */

import { describe, it, expect } from 'vitest'
import {
  NAV_GROUPS,
  getVisibleGroups,
  getDefaultLayout,
} from '@/lib/navConfig'

// Real routes from App.tsx — used to verify navConfig paths
const REAL_ROUTES = new Set([
  '/catalog',
  '/catalog?favorited=true',
  '/me/creations',
  '/imports',
  '/settings',
  '/settings/api-keys',
  '/admin/jobs',
  '/admin/scheduled-jobs',
  '/admin/issues',
  '/admin/changes',
  '/admin/reviews',
  '/admin/libraries',
  '/admin/users',
  '/admin/invites',
  '/admin/ai-providers',
  '/admin/site-capabilities',
  '/admin/backups',
  '/admin/export',
  '/admin/pending-tags',
  '/admin/tags',
  '/admin/print-stats',
  '/admin/shares',
])

// ---------------------------------------------------------------------------
// getVisibleGroups
// ---------------------------------------------------------------------------

describe('getVisibleGroups', () => {
  it('returns all groups for admin', () => {
    const groups = getVisibleGroups('admin')
    const ids = groups.map((g) => g.id)
    expect(ids).toContain('library')
    expect(ids).toContain('import')
    expect(ids).toContain('settings')
    expect(ids).toContain('operations')
    expect(ids).toContain('admin')
  })

  it('excludes admin-only groups for regular users', () => {
    const groups = getVisibleGroups('user')
    const ids = groups.map((g) => g.id)
    expect(ids).toContain('library')
    expect(ids).toContain('import')
    expect(ids).toContain('settings')
    expect(ids).not.toContain('operations')
    expect(ids).not.toContain('admin')
  })

  it('non-admin user gets fewer total nav items than admin', () => {
    const adminItems = getVisibleGroups('admin').flatMap((g) => g.items)
    const userItems = getVisibleGroups('user').flatMap((g) => g.items)
    expect(adminItems.length).toBeGreaterThan(userItems.length)
  })

  it('user groups contain no admin-only items with paths', () => {
    const userGroups = getVisibleGroups('user')
    for (const group of userGroups) {
      expect(group.requiresAdmin).toBeFalsy()
    }
  })
})

// ---------------------------------------------------------------------------
// getDefaultLayout
// ---------------------------------------------------------------------------

describe('getDefaultLayout', () => {
  it('returns side for admin', () => {
    expect(getDefaultLayout('admin')).toBe('side')
  })

  it('returns top for regular user', () => {
    expect(getDefaultLayout('user')).toBe('top')
  })
})

// ---------------------------------------------------------------------------
// Route verification — all paths in NAV_GROUPS must be real routes
// ---------------------------------------------------------------------------

describe('NAV_GROUPS path verification', () => {
  it('every item path in NAV_GROUPS is a real App.tsx route', () => {
    const badPaths: string[] = []
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        if (item.path && !REAL_ROUTES.has(item.path)) {
          badPaths.push(`${group.id}/${item.label}: "${item.path}"`)
        }
      }
    }
    expect(badPaths).toEqual([])
  })

  it('all admin route paths are in the admin or operations groups', () => {
    const adminPaths = ['/admin/users', '/admin/jobs', '/admin/reviews']
    for (const path of adminPaths) {
      const found = NAV_GROUPS.flatMap((g) => g.items).some((i) => i.path === path)
      expect(found).toBe(true)
    }
  })
})

// ---------------------------------------------------------------------------
// NAV_GROUPS structure invariants
// ---------------------------------------------------------------------------

describe('NAV_GROUPS structure', () => {
  it('every item has a label and icon', () => {
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        expect(item.label).toBeTruthy()
        expect(item.icon).toBeTruthy()
      }
    }
  })

  it('every item has either a path or an action (not both, not neither)', () => {
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        const hasPath = Boolean(item.path)
        const hasAction = Boolean(item.action)
        // Must have at least one
        expect(hasPath || hasAction).toBe(true)
        // action items should not have paths (they open modals)
        if (hasAction) {
          expect(item.path).toBeUndefined()
        }
      }
    }
  })

  it('add-asset is the only action item and has no path', () => {
    const actionItems = NAV_GROUPS.flatMap((g) => g.items).filter((i) => i.action)
    expect(actionItems).toHaveLength(1)
    expect(actionItems[0].action).toBe('add-asset')
    expect(actionItems[0].path).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// useNavLayout fallback logic (pure function simulation)
// ---------------------------------------------------------------------------

describe('useNavLayout fallback resolution logic', () => {
  /**
   * Simulate the layout resolution logic from useNavLayout.ts without
   * needing a browser or network. Tests the pure logic only.
   */
  function resolveLayout(
    serverLayout: string | null | undefined,
    localStorageLayout: string | null,
    role: 'admin' | 'user',
  ): 'top' | 'side' {
    const roleDefault = getDefaultLayout(role)
    if (serverLayout === 'top' || serverLayout === 'side') return serverLayout
    if (localStorageLayout === 'top' || localStorageLayout === 'side') return localStorageLayout
    return roleDefault
  }

  it('prefers server layout when available', () => {
    expect(resolveLayout('side', 'top', 'user')).toBe('side')
    expect(resolveLayout('top', 'side', 'admin')).toBe('top')
  })

  it('falls back to localStorage when server returns null', () => {
    expect(resolveLayout(null, 'side', 'user')).toBe('side')
    expect(resolveLayout(null, 'top', 'admin')).toBe('top')
  })

  it('falls back to localStorage when server returns undefined (error)', () => {
    expect(resolveLayout(undefined, 'side', 'user')).toBe('side')
    expect(resolveLayout(undefined, 'top', 'admin')).toBe('top')
  })

  it('falls back to role default when both server and localStorage are null', () => {
    expect(resolveLayout(null, null, 'admin')).toBe('side')
    expect(resolveLayout(null, null, 'user')).toBe('top')
  })

  it('ignores invalid localStorage values and uses role default', () => {
    expect(resolveLayout(null, 'left', 'admin')).toBe('side')
    expect(resolveLayout(null, 'horizontal', 'user')).toBe('top')
  })

  it('role defaults match the spec (admin→side, user→top)', () => {
    expect(resolveLayout(null, null, 'admin')).toBe('side')
    expect(resolveLayout(null, null, 'user')).toBe('top')
  })
})
