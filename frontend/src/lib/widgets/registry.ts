/**
 * Widget registry — the single place to add dashboard widgets.
 *
 * Two regions:
 *   'stat'  — top stat strip tiles; value derived from StatDataCache
 *   'panel' — right rail widgets; self-contained React components
 *
 * Role defaults:
 *   admin → compact density, 8 stat tiles (incl. admin), quick-import rail
 *   user  → comfortable density, 5 basic stat tiles, quick-import rail
 *
 * To add a widget: add one entry to WIDGET_REGISTRY. The shells pick it up
 * automatically via getWidgets() / getWidgetById().
 */

import {
  LayoutGrid,
  Activity,
  Package,
  Star,
  Cpu,
  AlertTriangle,
  Eye,
  Hash,
  Heart,
  Users,
  HardDrive,
  PlusCircle,
  Clock,
  CheckSquare,
} from 'lucide-react'

import type { WidgetDef } from './types'
import { QuickImportWidget } from './panel/QuickImportWidget'
import { RecentItemsWidget } from './panel/RecentItemsWidget'
import { JobsMiniWidget } from './panel/JobsMiniWidget'
import { PendingReviewsWidget } from './panel/PendingReviewsWidget'
import { FavoritesMiniWidget } from './panel/FavoritesMiniWidget'

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

export const WIDGET_REGISTRY: WidgetDef[] = [
  // ------ Stat tiles ------

  {
    id: 'total-assets',
    title: 'Total Assets',
    region: 'stat',
    icon: LayoutGrid,
    color: 'var(--aurora-stat1)',
    defaultForRoles: ['admin', 'user'],
    getValue: (c) => (c.totalAssets != null ? c.totalAssets.toLocaleString() : '—'),
    linkTo: '/catalog',
  },

  {
    id: 'prints-done',
    title: 'Prints Done',
    region: 'stat',
    icon: Activity,
    color: 'var(--aurora-stat2)',
    defaultForRoles: ['admin', 'user'],
    getValue: (c) =>
      c.printStats?.total_prints != null ? c.printStats.total_prints.toLocaleString() : '—',
    linkTo: '/admin/content/print-stats',
  },

  {
    id: 'filament-used',
    title: 'Filament',
    region: 'stat',
    icon: Package,
    color: 'var(--aurora-stat3)',
    defaultForRoles: ['admin', 'user'],
    getValue: (c) =>
      c.printStats?.total_filament_weight_g != null
        ? `${(c.printStats.total_filament_weight_g / 1000).toFixed(1)} kg`
        : '—',
    linkTo: '/admin/content/print-stats',
  },

  {
    id: 'success-rate',
    title: 'Success Rate',
    region: 'stat',
    icon: Star,
    color: 'var(--aurora-stat4)',
    defaultForRoles: ['admin', 'user'],
    getValue: (c) =>
      c.printStats?.success_rate != null
        ? `${Math.round(c.printStats.success_rate * 100)}%`
        : '—',
    linkTo: '/admin/content/print-stats',
  },

  {
    id: 'jobs-running',
    title: 'Jobs Running',
    region: 'stat',
    icon: Cpu,
    color: 'var(--aurora-stat5)',
    defaultForRoles: ['admin', 'user'],
    getValue: (c) => (c.jobsRunning != null ? String(c.jobsRunning) : '—'),
    linkTo: '/admin/activity/jobs',
  },

  {
    id: 'open-issues',
    title: 'Open Issues',
    region: 'stat',
    icon: AlertTriangle,
    color: '#f59e0b',
    defaultForRoles: ['admin'],
    requiresAdmin: true,
    getValue: (c) => (c.openIssues != null ? String(c.openIssues) : '—'),
    linkTo: '/admin/activity/issues',
  },

  {
    id: 'pending-reviews',
    title: 'Pending Reviews',
    region: 'stat',
    icon: Eye,
    color: '#8b5cf6',
    defaultForRoles: ['admin'],
    requiresAdmin: true,
    getValue: (c) => (c.pendingReviews != null ? String(c.pendingReviews) : '—'),
    linkTo: '/admin/activity/reviews',
  },

  {
    id: 'pending-tags',
    title: 'Pending Tags',
    region: 'stat',
    icon: Hash,
    color: '#ec4899',
    defaultForRoles: ['admin'],
    requiresAdmin: true,
    getValue: (c) => {
      if (c.allTagsCount != null && c.activeTagsCount != null) {
        return String(Math.max(0, c.allTagsCount - c.activeTagsCount))
      }
      return '—'
    },
    linkTo: '/admin/content/tags',
  },

  {
    id: 'favorites',
    title: 'My Favorites',
    region: 'stat',
    icon: Heart,
    color: '#ef4444',
    defaultForRoles: [],
    getValue: (c) => (c.favoritesCount != null ? String(c.favoritesCount) : '—'),
    linkTo: '/catalog?favorited=true',
  },

  {
    id: 'creators',
    title: 'Creators',
    region: 'stat',
    icon: Users,
    color: '#06b6d4',
    defaultForRoles: [],
    getValue: (c) => (c.creatorsCount != null ? String(c.creatorsCount) : '—'),
  },

  {
    id: 'storage-used',
    title: 'Storage Used',
    region: 'stat',
    icon: HardDrive,
    color: '#6366f1',
    defaultForRoles: [],
    // No backend endpoint yet — always shows graceful dash
    getValue: (_c) => '—',
  },

  // ------ Panel widgets ------

  {
    id: 'quick-import',
    title: 'Quick Import',
    region: 'panel',
    icon: PlusCircle,
    defaultForRoles: ['admin', 'user'],
    component: QuickImportWidget,
  },

  {
    id: 'recent-items',
    title: 'Recent Items',
    region: 'panel',
    icon: Clock,
    defaultForRoles: [],
    component: RecentItemsWidget,
  },

  {
    id: 'jobs-mini',
    title: 'Jobs Running',
    region: 'panel',
    icon: Cpu,
    defaultForRoles: [],
    requiresAdmin: true,
    component: JobsMiniWidget,
  },

  {
    id: 'pending-reviews-panel',
    title: 'Pending Reviews',
    region: 'panel',
    icon: CheckSquare,
    defaultForRoles: [],
    requiresAdmin: true,
    component: PendingReviewsWidget,
  },

  {
    id: 'favorites-mini',
    title: 'My Favorites',
    region: 'panel',
    icon: Heart,
    defaultForRoles: [],
    component: FavoritesMiniWidget,
  },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** All widgets in a given region. */
export function getWidgets(region: 'stat' | 'panel', isAdmin = false): WidgetDef[] {
  return WIDGET_REGISTRY.filter(
    (w) => w.region === region && (!w.requiresAdmin || isAdmin),
  )
}

/** Lookup a widget by id (returns undefined if not found). */
export function getWidgetById(id: string): WidgetDef | undefined {
  return WIDGET_REGISTRY.find((w) => w.id === id)
}

/**
 * Resolve an ordered list of widget IDs to WidgetDef objects, filtering out
 * unknown IDs and (optionally) admin-only widgets for non-admin users.
 */
export function resolveWidgets(
  ids: string[],
  region: 'stat' | 'panel',
  isAdmin = false,
): WidgetDef[] {
  return ids
    .map((id) => getWidgetById(id))
    .filter(
      (w): w is WidgetDef =>
        w !== undefined &&
        w.region === region &&
        (!w.requiresAdmin || isAdmin),
    )
}
