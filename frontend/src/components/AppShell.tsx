/**
 * AppShell — main layout: header (logo + nav + theme toggle + user menu) + page outlet.
 */

import React, { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ThemeToggle } from './ThemeToggle'
import { useAuth } from '@/context/AuthContext'
import { AddAssetModal } from './AddAssetModal'
import * as api from '@/lib/api'

/**
 * Logo using <picture> for theme-aware swap.
 * Images are served from /img/ (mapped to docs/images/ in nginx config).
 */
function Logo() {
  return (
    <a href="/" className="flex items-center gap-2">
      {/* light logo shown in light mode; dark logo shown in dark mode */}
      <img
        src="/img/logo-horizontal-light.png"
        alt="PartFolder 3D"
        className="h-8 dark:hidden"
        onError={(e) => {
          // Graceful fallback: text logo if images are not yet available (dev)
          const el = e.currentTarget
          el.style.display = 'none'
          const next = el.nextElementSibling as HTMLElement | null
          if (next) next.style.display = ''
        }}
      />
      <img
        src="/img/logo-horizontal-dark.png"
        alt="PartFolder 3D"
        className="hidden h-8 dark:block"
        onError={(e) => {
          const el = e.currentTarget
          el.style.display = 'none'
        }}
      />
      {/* Text fallback shown when images fail (dev without docker) */}
      <span
        className="text-xl font-bold text-primary"
        style={{ display: 'none' }}
        aria-hidden="true"
      >
        PartFolder 3D
      </span>
    </a>
  )
}

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `text-sm font-medium transition-colors hover:text-primary
        ${isActive ? 'text-primary' : 'text-muted-foreground'}`
      }
    >
      {children}
    </NavLink>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  if (!user) return null

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground hidden sm:block">
        {user.name}
      </span>
      <button
        onClick={handleLogout}
        className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        title="Sign out"
      >
        Sign out
      </button>
    </div>
  )
}

export function AppShell() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [addAssetOpen, setAddAssetOpen] = useState(false)

  // Pending review count badge — polled every 60 s; only for admins.
  const { data: pendingReviews } = useQuery({
    queryKey: ['reviews-pending-count'],
    queryFn: () => api.listReviews({ status: 'pending', per_page: 1 }),
    enabled: isAdmin,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur">
        <div className="container mx-auto flex h-14 items-center px-4">
          <Logo />

          {/* Nav */}
          <nav className="ml-6 flex items-center gap-4">
            <NavItem to="/catalog">Catalog</NavItem>
            <NavItem to="/catalog?favorited=true">My Favorites</NavItem>
            <NavItem to="/me/creations">My Creations</NavItem>
            <NavItem to="/imports">Imports</NavItem>
            <NavItem to="/settings">Settings</NavItem>
            <NavItem to="/settings/api-keys">API keys</NavItem>
            {isAdmin && (
              <>
                <NavItem to="/admin/users">Users</NavItem>
                <NavItem to="/admin/invites">Invites</NavItem>
                <NavItem to="/admin/password-reset">Reset</NavItem>
                <NavItem to="/admin/jobs">Jobs</NavItem>
                <NavItem to="/admin/scheduled-jobs">Schedules</NavItem>
                <NavItem to="/admin/pending-tags">Pending Tags</NavItem>
                <NavItem to="/admin/issues">Issues</NavItem>
                <NavItem to="/admin/changes">Change Log</NavItem>
                <NavItem to="/admin/print-stats">Print Stats</NavItem>
                <NavItem to="/admin/shares">Site Shares</NavItem>
                <span className="relative inline-flex items-center">
                  <NavItem to="/admin/reviews">Review Queue</NavItem>
                  {pendingReviews && pendingReviews.total > 0 && (
                    <span className="ml-1 inline-flex items-center justify-center rounded-full bg-red-500 px-1.5 py-0.5 text-xs font-bold text-white leading-none min-w-[1.25rem]">
                      {pendingReviews.total > 99 ? '99+' : pendingReviews.total}
                    </span>
                  )}
                </span>
              </>
            )}
          </nav>

          {/* Right side: Add Asset + theme toggle + user menu */}
          <div className="ml-auto flex items-center gap-4">
            <button
              onClick={() => setAddAssetOpen(true)}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 transition-colors"
              aria-label="Add Asset"
            >
              + Add Asset
            </button>
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>
      </header>

      {/* ── Page content ── */}
      <main className="container mx-auto px-4 py-6">
        <Outlet />
      </main>

      {/* ── Add Asset Modal ── */}
      <AddAssetModal
        open={addAssetOpen}
        onClose={() => setAddAssetOpen(false)}
      />
    </div>
  )
}
