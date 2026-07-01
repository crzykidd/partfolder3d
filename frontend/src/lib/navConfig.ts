/**
 * navConfig.ts — single source of truth for the authenticated app navigation.
 *
 * Groups → items with real routes from App.tsx and role-gating via 'admin' | 'user'.
 * Items with `action: 'add-asset'` open AddAssetModal instead of navigating.
 *
 * Used by both SideNavShell and TopNavShell so every route exists in exactly one place.
 *
 * Admin nav (2026-06-29 reorg): the old Operations + 12-item Admin groups are
 * replaced by ONE 'admin' group of 5 section items, each pointing to the
 * first tab of its section.  Individual tab routes live in App.tsx.
 */

import {
  LayoutGrid,
  Heart,
  Package,
  PlusCircle,
  SlidersHorizontal,
  Key,
  Rocket,
  Layers,
  Users,
  Cpu,
  Activity,
  HardDrive,
  Printer,
  type LucideIcon,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type UserRole = 'admin' | 'user'

export type NavLayout = 'top' | 'side'

export interface NavItemDef {
  label: string
  icon: LucideIcon
  /** Undefined for action-only items (e.g. modal triggers). */
  path?: string
  /** A named action that the shell handles (e.g. open AddAssetModal). */
  action?: 'add-asset'
  /**
   * Optional active-highlight prefix. When set, the nav item is highlighted
   * whenever the current pathname starts with this prefix — used for section
   * items whose `path` points at a default sub-route (e.g. the Admin sections
   * land on `/admin/activity/jobs` but should stay highlighted on any
   * `/admin/activity/*` tab).
   */
  match?: string
}

export interface NavGroupDef {
  id: string
  label: string
  /** If true, only visible to admin users. */
  requiresAdmin?: boolean
  items: NavItemDef[]
}

// ---------------------------------------------------------------------------
// Nav model
// ---------------------------------------------------------------------------

export const NAV_GROUPS: NavGroupDef[] = [
  {
    id: 'library',
    label: 'Library',
    items: [
      { label: 'Catalog',      icon: LayoutGrid, path: '/catalog' },
      { label: 'My Favorites', icon: Heart,       path: '/catalog?favorited=true' },
      { label: 'My Creations', icon: Printer,     path: '/me/creations' },
    ],
  },
  {
    id: 'import',
    label: 'Import',
    items: [
      { label: 'Add Asset', icon: PlusCircle, action: 'add-asset' },
      { label: 'Imports',   icon: Package,    path: '/imports' },
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    items: [
      { label: 'Quick Start', icon: Rocket,            path: '/quick-start' },
      { label: 'Settings',    icon: SlidersHorizontal, path: '/settings' },
      { label: 'API Keys',    icon: Key,               path: '/settings/api-keys' },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    requiresAdmin: true,
    items: [
      { label: 'Content',        icon: Layers,    path: '/admin/content/libraries', match: '/admin/content' },
      { label: 'Users & Access', icon: Users,     path: '/admin/access/users',     match: '/admin/access' },
      { label: 'AI & Scraping',  icon: Cpu,       path: '/admin/ai/providers',     match: '/admin/ai' },
      { label: 'Jobs & Activity', icon: Activity, path: '/admin/activity/jobs',    match: '/admin/activity' },
      { label: 'Data & Backups', icon: HardDrive, path: '/admin/data/backups',     match: '/admin/data' },
    ],
  },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Return the groups visible for the given role. */
export function getVisibleGroups(role: UserRole): NavGroupDef[] {
  return NAV_GROUPS.filter((g) => !g.requiresAdmin || role === 'admin')
}

/** Return the role-based default nav layout when no explicit preference is set. */
export function getDefaultLayout(role: UserRole): NavLayout {
  return role === 'admin' ? 'side' : 'top'
}
