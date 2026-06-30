/**
 * Widget registry types.
 *
 * Two regions: 'stat' (top stat strip tiles) and 'panel' (right rail panels).
 * Stat widgets use a central StatDataCache so shared queries (e.g. print-stats)
 * are fetched once regardless of how many tiles reference them.
 * Panel widgets are self-contained React components.
 */

import type { LucideIcon } from 'lucide-react'
import type React from 'react'

import type { PrintStats } from '@/lib/api'

export type UserRole = 'admin' | 'user'

/** All pre-fetched stat data; each field is undefined until the query resolves. */
export interface StatDataCache {
  totalAssets?: number
  printStats?: PrintStats
  jobsRunning?: number
  openIssues?: number
  pendingReviews?: number
  allTagsCount?: number
  activeTagsCount?: number
  favoritesCount?: number
  creatorsCount?: number
}

/** Stat-tile widget definition. */
export interface StatWidgetDef {
  id: string
  title: string
  region: 'stat'
  icon: LucideIcon
  /** CSS variable or literal color for the tile accent. */
  color: string
  /** Roles for which this widget appears by default. Omit = no default. */
  defaultForRoles: UserRole[]
  /** Admin-only: widget hidden from non-admin users in the picker. */
  requiresAdmin?: boolean
  /** Derive the display value from the pre-fetched data cache. */
  getValue: (cache: StatDataCache) => string
  /**
   * Optional react-router path to navigate to when the tile is clicked.
   * Omit for tiles with no sensible detail page (e.g. storage-used, creators).
   * Tiles without linkTo remain non-clickable.
   */
  linkTo?: string
}

/** Panel (right rail) widget definition. */
export interface PanelWidgetDef {
  id: string
  title: string
  region: 'panel'
  icon: LucideIcon
  defaultForRoles: UserRole[]
  requiresAdmin?: boolean
  component: React.ComponentType
}

export type WidgetDef = StatWidgetDef | PanelWidgetDef
