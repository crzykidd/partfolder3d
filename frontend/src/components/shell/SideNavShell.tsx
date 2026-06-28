/**
 * SideNavShell — Aurora collapsible sidebar navigation shell.
 *
 * Features:
 *   - Glass sidebar (full ↔ icon-rail, persisted to localStorage)
 *   - Grouped nav with collapse/expand (persisted)
 *   - Pill active state with teal glow
 *   - Real routes from navConfig.ts (role-filtered via useAuth)
 *   - Top stat strip + collapsible Quick Import right rail
 *   - User menu with: theme toggle, nav-layout toggle (→ TopNav), version + release notes, logout
 *   - Version from GET /api/version
 *
 * Layout toggle stored via useNavLayout() — clicking "Switch to Top Nav" in
 * the user menu calls setLayout('top') and the shell swaps.
 */

import React, { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronDown,
  Sun,
  Moon,
  LogOut,
  ExternalLink,
  PanelLeft,
  PanelTop,
} from 'lucide-react'

import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/components/ThemeProvider'
import { useNavLayout } from '@/hooks/useNavLayout'
import { useLocalStorage } from '@/hooks/useLocalStorage'
import { getVisibleGroups, type NavItemDef } from '@/lib/navConfig'
import { StatStrip } from './StatStrip'
import { QuickImportRail } from './QuickImportRail'
import { AddAssetModal } from '@/components/AddAssetModal'
import * as api from '@/lib/api'

const RELEASES_URL = 'https://github.com/crzykidd/partfolder3d/releases'

// ---------------------------------------------------------------------------
// Nav item — uses NavLink for route links; button for actions
// ---------------------------------------------------------------------------

interface NavItemProps {
  item: NavItemDef
  collapsed: boolean
  onAction: (action: NavItemDef['action']) => void
  pendingBadge?: number
}

function SideNavItem({ item, collapsed, onAction, pendingBadge }: NavItemProps) {
  const Icon = item.icon
  const isAction = Boolean(item.action)

  const commonStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: collapsed ? 0 : 9,
    width: collapsed ? '100%' : 'calc(100% - 16px)',
    padding: collapsed ? '9px 0' : '6px 12px',
    margin: collapsed ? '0' : '0 8px',
    justifyContent: collapsed ? 'center' : 'flex-start',
    border: '1px solid transparent',
    borderRadius: 10,
    cursor: 'pointer',
    fontSize: 13,
    background: 'transparent',
    textDecoration: 'none',
    fontWeight: 400,
    color: 'var(--aurora-text-dim)',
    transition: 'all 0.15s cubic-bezier(0.4,0,0.2,1)',
  }

  const hoverOn = (e: React.MouseEvent<HTMLElement>) => {
    const el = e.currentTarget as HTMLElement
    el.style.background = 'var(--aurora-glass-hover)'
    el.style.color = 'var(--aurora-text)'
  }
  const hoverOff = (e: React.MouseEvent<HTMLElement>) => {
    const el = e.currentTarget as HTMLElement
    // Only reset if not the active link — NavLink active overrides keep it
    if (!el.classList.contains('nav-active')) {
      el.style.background = 'transparent'
      el.style.color = 'var(--aurora-text-dim)'
    }
  }

  const innerContent = (
    <>
      <Icon size={14} style={{ flexShrink: 0 }} />
      {!collapsed && (
        <>
          <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {item.label}
          </span>
          {pendingBadge != null && pendingBadge > 0 && (
            <span
              style={{
                background: 'var(--aurora-accent)',
                color: 'var(--aurora-accent-fg)',
                borderRadius: 20,
                padding: '0 6px',
                fontSize: 10,
                fontWeight: 700,
                lineHeight: '16px',
                boxShadow: '0 0 8px var(--aurora-accent-glow)',
                flexShrink: 0,
              }}
            >
              {pendingBadge > 99 ? '99+' : pendingBadge}
            </span>
          )}
        </>
      )}
    </>
  )

  if (isAction || !item.path) {
    return (
      <button
        title={collapsed ? item.label : undefined}
        onClick={() => onAction(item.action)}
        style={commonStyle}
        onMouseEnter={hoverOn}
        onMouseLeave={hoverOff}
      >
        {innerContent}
      </button>
    )
  }

  return (
    <NavLink
      to={item.path}
      end={item.path === '/catalog'}
      title={collapsed ? item.label : undefined}
      style={({ isActive }) => ({
        ...commonStyle,
        background: isActive ? 'var(--aurora-pill)' : 'transparent',
        border: `1px solid ${isActive ? 'var(--aurora-pill-border)' : 'transparent'}`,
        color: isActive ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
        fontWeight: isActive ? 600 : 400,
        boxShadow: isActive ? 'var(--aurora-glow)' : 'none',
      })}
      onMouseEnter={(e) => {
        const el = e.currentTarget as HTMLElement
        const style = window.getComputedStyle(el)
        if (style.color !== 'rgb(15, 164, 171)') {
          el.style.background = 'var(--aurora-glass-hover)'
          el.style.color = 'var(--aurora-text)'
        }
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget as HTMLElement
        const style = window.getComputedStyle(el)
        if (style.color !== 'rgb(15, 164, 171)') {
          el.style.background = 'transparent'
          el.style.color = 'var(--aurora-text-dim)'
        }
      }}
    >
      {innerContent}
    </NavLink>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SideNavShell() {
  const { user, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const { setLayout } = useNavLayout()
  const navigate = useNavigate()

  const isAdmin = user?.role === 'admin'
  const role = isAdmin ? 'admin' : ('user' as const)

  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage('aurora-sidebar-collapsed', false)
  const [collapsedGroups, setCollapsedGroups] = useLocalStorage<string[]>('aurora-sidebar-groups', [])
  const [railCollapsed, setRailCollapsed] = useLocalStorage('aurora-rail-collapsed', false)
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [addAssetOpen, setAddAssetOpen] = useState(false)

  const visibleGroups = getVisibleGroups(role)

  // Version from server
  const { data: versionData } = useQuery({
    queryKey: ['version'],
    queryFn: (): Promise<{ version: string }> => fetch('/api/version').then((r) => r.json()),
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

  const toggleGroup = (id: string) => {
    setCollapsedGroups((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const handleAction = (action: NavItemDef['action']) => {
    if (action === 'add-asset') setAddAssetOpen(true)
  }

  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  const handleLogout = async () => {
    setShowUserMenu(false)
    await logout()
    navigate('/login', { replace: true })
  }

  // User avatar initials
  const initials = (user?.name ?? 'U').slice(0, 1).toUpperCase()

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        overflow: 'hidden',
        background: `linear-gradient(145deg, var(--aurora-bg-from) 0%, var(--aurora-bg-to) 100%)`,
        color: 'var(--aurora-text)',
        fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
        fontSize: 13,
      }}
      onClick={() => showUserMenu && setShowUserMenu(false)}
    >
      {/* ── Glass sidebar ── */}
      <aside
        style={{
          width: sidebarCollapsed ? 56 : 234,
          minWidth: sidebarCollapsed ? 56 : 234,
          background: 'var(--aurora-glass)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderRight: '1px solid var(--aurora-glass-border)',
          display: 'flex',
          flexDirection: 'column',
          transition: 'width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1)',
          overflow: 'hidden',
          zIndex: 10,
          flexShrink: 0,
        } as React.CSSProperties}
      >
        {/* Logo + collapse toggle */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: sidebarCollapsed ? 'center' : 'space-between',
            padding: sidebarCollapsed ? '0 16px' : '0 10px 0 18px',
            height: 54,
            borderBottom: '1px solid var(--aurora-glass-border)',
            flexShrink: 0,
          }}
        >
          {!sidebarCollapsed && (
            <a href="/" style={{ textDecoration: 'none', fontWeight: 800, fontSize: 15, letterSpacing: '-0.02em' }}>
              <span style={{ color: 'var(--aurora-accent)', textShadow: '0 0 20px var(--aurora-accent-glow)' }}>
                Part
              </span>
              <span style={{ color: 'var(--aurora-text)' }}>Folder</span>
              <span style={{ color: 'var(--aurora-muted)', fontSize: 12, fontWeight: 400 }}> 3D</span>
            </a>
          )}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: 8,
              cursor: 'pointer',
              color: 'var(--aurora-muted)',
              display: 'flex',
              padding: '5px 6px',
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-pill-border)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-accent)'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)'
            }}
          >
            <ChevronDown
              size={14}
              style={{ transform: sidebarCollapsed ? 'rotate(-90deg)' : 'rotate(90deg)', transition: 'transform 0.2s' }}
            />
          </button>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 0', scrollbarWidth: 'none' as const }}>
          {visibleGroups.map((group) => {
            const isGroupOpen = !collapsedGroups.includes(group.id)
            return (
              <div key={group.id} style={{ marginBottom: 4 }}>
                {/* Group label (hidden in icon-rail mode) */}
                {!sidebarCollapsed && (
                  <button
                    onClick={() => toggleGroup(group.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                      padding: '4px 18px',
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--aurora-muted)',
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                    }}
                  >
                    <span>{group.label}</span>
                    <ChevronDown
                      size={11}
                      style={{
                        transition: 'transform 0.2s cubic-bezier(0.4,0,0.2,1)',
                        transform: isGroupOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                      }}
                    />
                  </button>
                )}

                {/* Items — animated collapse */}
                <div
                  style={{
                    overflow: 'hidden',
                    maxHeight: isGroupOpen || sidebarCollapsed ? '600px' : '0',
                    transition: 'max-height 0.25s cubic-bezier(0.4,0,0.2,1)',
                  }}
                >
                  {group.items.map((item) => (
                    <SideNavItem
                      key={item.label}
                      item={item}
                      collapsed={sidebarCollapsed}
                      onAction={handleAction}
                      pendingBadge={item.path === '/admin/reviews' ? reviewBadge : undefined}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </nav>

        {/* Footer — version + release notes */}
        <div
          style={{
            borderTop: '1px solid var(--aurora-glass-border)',
            padding: sidebarCollapsed ? '10px 0' : '10px 18px',
            flexShrink: 0,
            display: 'flex',
            justifyContent: sidebarCollapsed ? 'center' : 'space-between',
            alignItems: 'center',
          }}
        >
          {sidebarCollapsed ? (
            <ExternalLink size={13} style={{ color: 'var(--aurora-muted)' }} />
          ) : (
            <>
              <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                {version ? `v${version}` : '…'}
              </span>
              <a
                href={RELEASES_URL}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 3,
                  fontSize: 11,
                  color: 'var(--aurora-accent)',
                  textDecoration: 'none',
                }}
              >
                Release notes <ExternalLink size={10} />
              </a>
            </>
          )}
        </div>
      </aside>

      {/* ── Main area ── */}
      <div
        style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
        onClick={() => showUserMenu && setShowUserMenu(false)}
      >
        {/* Top bar */}
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 16px',
            height: 54,
            background: 'var(--aurora-glass)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            borderBottom: '1px solid var(--aurora-glass-border)',
            flexShrink: 0,
          } as React.CSSProperties}
        >
          <div style={{ flex: 1 }} />

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
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-pill-border)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-accent)'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)'
            }}
          >
            {isDark ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          {/* Avatar + user menu */}
          <div style={{ position: 'relative' }}>
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

            {/* Dropdown */}
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
                  minWidth: 200,
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

                {/* Toggle theme */}
                <MenuButton
                  icon={isDark ? <Sun size={13} /> : <Moon size={13} />}
                  label="Toggle theme"
                  onClick={() => { setTheme(isDark ? 'light' : 'dark'); setShowUserMenu(false) }}
                />

                {/* Switch nav layout */}
                <MenuButton
                  icon={<PanelTop size={13} />}
                  label="Switch to Top Nav"
                  onClick={() => { setLayout('top'); setShowUserMenu(false) }}
                />

                {/* Release notes */}
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

                {/* Sign out */}
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
        </header>

        {/* Stat strip */}
        <StatStrip />

        {/* Content row (main + right rail) */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          <main
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '18px 20px',
              scrollbarWidth: 'thin' as const,
              scrollbarColor: 'var(--aurora-glass) transparent',
            } as React.CSSProperties}
          >
            <Outlet />
          </main>

          <QuickImportRail
            collapsed={railCollapsed}
            onToggle={() => setRailCollapsed(!railCollapsed)}
          />
        </div>
      </div>

      {/* Global add-asset modal (triggered from sidebar nav item) */}
      <AddAssetModal open={addAssetOpen} onClose={() => setAddAssetOpen(false)} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared menu button helper
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
