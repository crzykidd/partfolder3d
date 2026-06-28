/**
 * TopNavShell — Aurora top-navigation shell using Radix dropdown menus.
 *
 * Features:
 *   - Sticky top bar: brand + nav group dropdowns (Radix) + Add Asset CTA + theme + user menu
 *   - Aurora glass styling (--aurora-* CSS variables)
 *   - Real routes from navConfig.ts (role-filtered via useAuth)
 *   - Top stat strip below the nav bar
 *   - Collapsible Quick Import right rail
 *   - User menu: theme toggle, nav-layout toggle (→ SideNav), version + release notes, logout
 *
 * Layout toggle via useNavLayout() — "Switch to Side Nav" calls setLayout('side').
 */

import React, { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import {
  ChevronDown,
  Sun,
  Moon,
  LogOut,
  ExternalLink,
  PanelLeft,
  PlusCircle,
} from 'lucide-react'

import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/components/ThemeProvider'
import { useNavLayout } from '@/hooks/useNavLayout'
import { useLocalStorage } from '@/hooks/useLocalStorage'
import { getVisibleGroups, type NavGroupDef, type NavItemDef } from '@/lib/navConfig'
import { StatStrip } from './StatStrip'
import { QuickImportRail } from './QuickImportRail'
import { AddAssetModal } from '@/components/AddAssetModal'
import * as api from '@/lib/api'

const RELEASES_URL = 'https://github.com/crzykidd/partfolder3d/releases'

// ---------------------------------------------------------------------------
// Shared menu button
// ---------------------------------------------------------------------------

interface MenuButtonProps {
  icon: React.ReactNode
  label: string
  onClick: () => void
  danger?: boolean
}

function MenuButton({ icon, label, onClick, danger }: MenuButtonProps) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 9,
        width: '100%',
        padding: '8px 14px',
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        fontSize: 13,
        color: danger ? 'var(--aurora-danger)' : 'var(--aurora-text-dim)',
        borderRadius: 9,
        textAlign: 'left',
        boxSizing: 'border-box',
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.background = 'transparent'
      }}
    >
      {icon}
      {label}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Nav group dropdown (Radix)
// ---------------------------------------------------------------------------

interface NavDropdownProps {
  group: NavGroupDef
  onAction: (action: NavItemDef['action']) => void
  reviewBadge?: number
}

function NavGroupDropdown({ group, onAction, reviewBadge }: NavDropdownProps) {
  const navigate = useNavigate()

  const handleSelect = (item: NavItemDef) => {
    if (item.action) {
      onAction(item.action)
    } else if (item.path) {
      navigate(item.path)
    }
  }

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '6px 10px',
            border: '1px solid transparent',
            borderRadius: 8,
            background: 'transparent',
            color: 'var(--aurora-text-dim)',
            fontSize: 13.5,
            fontWeight: 500,
            cursor: 'pointer',
            transition: 'all 0.12s',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.background = 'var(--aurora-glass-hover)'
            el.style.color = 'var(--aurora-text)'
            el.style.borderColor = 'var(--aurora-glass-border)'
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.background = 'transparent'
            el.style.color = 'var(--aurora-text-dim)'
            el.style.borderColor = 'transparent'
          }}
        >
          {group.label}
          <ChevronDown size={12} style={{ opacity: 0.6 }} />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          sideOffset={6}
          style={{
            background: 'var(--aurora-palette-bg)',
            border: '1px solid var(--aurora-palette-border)',
            borderRadius: 12,
            padding: '6px',
            minWidth: 200,
            boxShadow: '0 8px 30px rgba(0,0,0,0.25), 0 0 0 1px var(--aurora-glass-border)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            zIndex: 9999,
          } as React.CSSProperties}
        >
          {group.items.map((item) => {
            const Icon = item.icon
            const badge =
              item.path === '/admin/reviews' && reviewBadge != null && reviewBadge > 0
                ? reviewBadge
                : undefined

            return (
              <DropdownMenu.Item
                key={item.label}
                onSelect={() => handleSelect(item)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 13.5,
                  color: 'var(--aurora-text-dim)',
                  outline: 'none',
                  transition: 'all 0.1s',
                }}
                onMouseEnter={(e) => {
                  const el = e.currentTarget as HTMLElement
                  el.style.background = 'var(--aurora-palette-hover)'
                  el.style.color = 'var(--aurora-text)'
                }}
                onMouseLeave={(e) => {
                  const el = e.currentTarget as HTMLElement
                  el.style.background = 'transparent'
                  el.style.color = 'var(--aurora-text-dim)'
                }}
              >
                <span style={{ color: 'var(--aurora-accent)', display: 'flex', flexShrink: 0 }}>
                  <Icon size={14} />
                </span>
                <span style={{ flex: 1 }}>{item.label}</span>
                {badge != null && (
                  <span
                    style={{
                      background: 'var(--aurora-accent)',
                      color: 'var(--aurora-accent-fg)',
                      borderRadius: 10,
                      padding: '1px 7px',
                      fontSize: 11,
                      fontWeight: 700,
                      boxShadow: '0 0 6px var(--aurora-accent-glow)',
                    }}
                  >
                    {badge > 99 ? '99+' : badge}
                  </span>
                )}
              </DropdownMenu.Item>
            )
          })}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function TopNavShell() {
  const { user, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const { setLayout } = useNavLayout()
  const navigate = useNavigate()

  const isAdmin = user?.role === 'admin'
  const role = isAdmin ? 'admin' : ('user' as const)

  const [showUserMenu, setShowUserMenu] = useState(false)
  const [addAssetOpen, setAddAssetOpen] = useState(false)
  const [railCollapsed, setRailCollapsed] = useLocalStorage('aurora-rail-collapsed', false)

  const visibleGroups = getVisibleGroups(role)

  // Version from server
  const { data: versionData } = useQuery({
    queryKey: ['version'],
    queryFn: (): Promise<{ version: string }> =>
      fetch('/api/version').then((r) => r.json()),
    staleTime: Infinity,
  })
  const version = versionData?.version ?? null

  // Pending reviews badge (admin only)
  const { data: pendingReviews } = useQuery({
    queryKey: ['reviews-pending-count'],
    queryFn: () => api.listReviews({ status: 'pending', per_page: 1 }),
    enabled: isAdmin,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  const reviewBadge = pendingReviews?.total

  const isDark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  const handleLogout = async () => {
    setShowUserMenu(false)
    await logout()
    navigate('/login', { replace: true })
  }

  const handleAction = (action: NavItemDef['action']) => {
    if (action === 'add-asset') setAddAssetOpen(true)
  }

  const initials = (user?.name ?? 'U').slice(0, 1).toUpperCase()

  return (
    <div
      style={{
        minHeight: '100vh',
        background: `linear-gradient(145deg, var(--aurora-bg-from) 0%, var(--aurora-bg-to) 100%)`,
        color: 'var(--aurora-text)',
        fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
        fontSize: 13,
        display: 'flex',
        flexDirection: 'column',
      }}
      onClick={() => showUserMenu && setShowUserMenu(false)}
    >
      {/* ── Top nav bar ── */}
      <nav
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 50,
          background: 'var(--aurora-glass)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderBottom: '1px solid var(--aurora-glass-border)',
          height: 54,
          display: 'flex',
          alignItems: 'center',
          padding: '0 20px',
          gap: 8,
          flexShrink: 0,
        } as React.CSSProperties}
      >
        {/* Brand */}
        <a
          href="/"
          style={{
            textDecoration: 'none',
            fontWeight: 800,
            fontSize: 15,
            letterSpacing: '-0.02em',
            marginRight: 12,
            flexShrink: 0,
          }}
        >
          <span
            style={{
              color: 'var(--aurora-accent)',
              textShadow: '0 0 20px var(--aurora-accent-glow)',
            }}
          >
            Part
          </span>
          <span style={{ color: 'var(--aurora-text)' }}>Folder</span>
          <span style={{ color: 'var(--aurora-muted)', fontSize: 12, fontWeight: 400 }}> 3D</span>
        </a>

        {/* Nav group dropdowns */}
        <div style={{ display: 'flex', gap: 2, flex: 1, overflow: 'hidden' }}>
          {visibleGroups.map((group) => (
            <NavGroupDropdown
              key={group.id}
              group={group}
              onAction={handleAction}
              reviewBadge={reviewBadge}
            />
          ))}
        </div>

        {/* Quick import CTA */}
        <button
          onClick={() => setAddAssetOpen(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 12px',
            background: 'var(--aurora-accent)',
            color: 'var(--aurora-accent-fg)',
            border: 'none',
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 2px 12px var(--aurora-accent-glow)',
            flexShrink: 0,
            transition: 'opacity 0.15s',
          }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLButtonElement).style.opacity = '0.9'
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLButtonElement).style.opacity = '1'
          }}
        >
          <PlusCircle size={14} />
          Add Asset
        </button>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(isDark ? 'light' : 'dark')}
          title="Toggle theme"
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 9,
            cursor: 'pointer',
            color: 'var(--aurora-muted)',
            display: 'flex',
            padding: 7,
            transition: 'all 0.15s',
            flexShrink: 0,
          }}
          onMouseEnter={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.borderColor = 'var(--aurora-pill-border)'
            el.style.color = 'var(--aurora-accent)'
          }}
          onMouseLeave={(e) => {
            const el = e.currentTarget as HTMLButtonElement
            el.style.borderColor = 'var(--aurora-glass-border)'
            el.style.color = 'var(--aurora-muted)'
          }}
        >
          {isDark ? <Sun size={14} /> : <Moon size={14} />}
        </button>

        {/* Avatar + user menu */}
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <button
            onClick={(e) => {
              e.stopPropagation()
              setShowUserMenu(!showUserMenu)
            }}
            title={user?.name ?? 'User menu'}
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #0FA4AB, #0c6d72)',
              color: '#FFF',
              border: '2px solid var(--aurora-pill-border)',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 800,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 16px var(--aurora-accent-glow)',
            }}
          >
            {initials}
          </button>

          {showUserMenu && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                position: 'absolute',
                top: 40,
                right: 0,
                zIndex: 200,
                background: 'var(--aurora-palette-bg)',
                border: '1px solid var(--aurora-palette-border)',
                borderRadius: 14,
                padding: '5px',
                minWidth: 210,
                boxShadow: '0 16px 48px rgba(0,0,0,0.4)',
                backdropFilter: 'blur(30px)',
                WebkitBackdropFilter: 'blur(30px)',
              } as React.CSSProperties}
            >
              {/* User info */}
              <div
                style={{
                  padding: '9px 14px',
                  borderBottom: '1px solid var(--aurora-divider)',
                  marginBottom: 3,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-text)' }}>
                  {user?.name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>{user?.email}</div>
                <div
                  style={{
                    marginTop: 4,
                    fontSize: 10,
                    fontWeight: 700,
                    color: 'var(--aurora-accent)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                  }}
                >
                  {user?.role}
                </div>
              </div>

              <MenuButton
                icon={isDark ? <Sun size={13} /> : <Moon size={13} />}
                label="Toggle theme"
                onClick={() => {
                  setTheme(isDark ? 'light' : 'dark')
                  setShowUserMenu(false)
                }}
              />

              <MenuButton
                icon={<PanelLeft size={13} />}
                label="Switch to Side Nav"
                onClick={() => {
                  setLayout('side')
                  setShowUserMenu(false)
                }}
              />

              <a
                href={RELEASES_URL}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 9,
                  width: '100%',
                  padding: '8px 14px',
                  fontSize: 13,
                  color: 'var(--aurora-text-dim)',
                  textDecoration: 'none',
                  borderRadius: 9,
                  boxSizing: 'border-box',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLElement).style.background = 'var(--aurora-glass-hover)'
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLElement).style.background = 'transparent'
                }}
              >
                <ExternalLink size={13} />
                {version ? `v${version} — Notes` : 'Release notes'}
              </a>

              <div
                style={{
                  borderTop: '1px solid var(--aurora-divider)',
                  marginTop: 3,
                  paddingTop: 3,
                }}
              >
                <MenuButton
                  icon={<LogOut size={13} />}
                  label="Sign out"
                  onClick={handleLogout}
                  danger
                />
              </div>
            </div>
          )}
        </div>
      </nav>

      {/* Stat strip */}
      <StatStrip />

      {/* Content row */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <main
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '18px 20px',
          }}
        >
          <Outlet />
        </main>

        <QuickImportRail
          collapsed={railCollapsed}
          onToggle={() => setRailCollapsed(!railCollapsed)}
        />
      </div>

      <AddAssetModal open={addAssetOpen} onClose={() => setAddAssetOpen(false)} />
    </div>
  )
}
