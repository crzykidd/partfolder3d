/**
 * navConfig.ts — single source of truth for the authenticated app navigation.
 *
 * Groups → items with real routes from App.tsx and role-gating via 'admin' | 'user'.
 * Items with `action: 'add-asset'` open AddAssetModal instead of navigating.
 *
 * Used by both SideNavShell and TopNavShell so every route exists in exactly one place.
 */

import {
  LayoutGrid,
  Heart,
  Package,
  PlusCircle,
  SlidersHorizontal,
  Key,
  Cpu,
  Calendar,
  AlertTriangle,
  GitBranch,
  Eye,
  Users,
  Mail,
  Zap,
  Archive,
  Download,
  Hash,
  Settings,
  BarChart2,
  Share2,
  Printer,
  ShieldCheck,
  HardDrive,
  Activity,
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
}

export interface NavGroupDef {
  id: string
  label: string
  /** If true, only visible to admin users. */
  requiresAdmin?: boolean
  items: NavItemDef[]
}

// ---------------------------------------------------------------------------
// Nav model — verified against App.tsx routes on 2026-06-28 (AI Usage added)
// ---------------------------------------------------------------------------

export const NAV_GROUPS: NavGroupDef[] = [
  {
    id: 'library',
    label: 'Library',
    items: [
      { label: 'Catalog',      icon: LayoutGrid,  path: '/catalog' },
      { label: 'My Favorites', icon: Heart,        path: '/catalog?favorited=true' },
      { label: 'My Creations', icon: Printer,      path: '/me/creations' },
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
      { label: 'Settings',  icon: SlidersHorizontal, path: '/settings' },
      { label: 'API Keys',  icon: Key,               path: '/settings/api-keys' },
    ],
  },
  {
    id: 'operations',
    label: 'Operations',
    requiresAdmin: true,
    items: [
      { label: 'Jobs',           icon: Cpu,           path: '/admin/jobs' },
      { label: 'Scheduled Jobs', icon: Calendar,      path: '/admin/scheduled-jobs' },
      { label: 'Issues',         icon: AlertTriangle, path: '/admin/issues' },
      { label: 'Change Log',     icon: GitBranch,     path: '/admin/changes' },
      { label: 'Reviews',        icon: Eye,           path: '/admin/reviews' },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    requiresAdmin: true,
    items: [
      { label: 'Libraries',         icon: HardDrive,   path: '/admin/libraries' },
      { label: 'Users',             icon: Users,       path: '/admin/users' },
      { label: 'Invites',           icon: Mail,        path: '/admin/invites' },
      { label: 'AI Providers',      icon: Zap,         path: '/admin/ai-providers' },
      { label: 'Site Capabilities', icon: ShieldCheck, path: '/admin/site-capabilities' },
      { label: 'Backups',           icon: Archive,     path: '/admin/backups' },
      { label: 'Export',            icon: Download,    path: '/admin/export' },
      { label: 'Pending Tags',      icon: Hash,        path: '/admin/pending-tags' },
      { label: 'Tag Admin',         icon: Settings,    path: '/admin/tags' },
      { label: 'Print Stats',       icon: BarChart2,   path: '/admin/print-stats' },
      { label: 'Share Audit',       icon: Share2,      path: '/admin/shares' },
      { label: 'AI Usage',          icon: Activity,    path: '/admin/ai-usage' },
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
