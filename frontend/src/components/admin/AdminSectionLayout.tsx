/**
 * AdminSectionLayout — tab-bar layout for the 5 themed admin sections.
 *
 * Each of the 5 admin section routes (`/admin/content`, `/admin/access`,
 * `/admin/ai`, `/admin/activity`, `/admin/data`) uses this as its route
 * element.  It renders an Aurora underline tab bar and an <Outlet/> below,
 * so each section's child routes (e.g. `libraries`, `tags`) appear inside
 * the same shell without re-rendering the tab bar.
 *
 * Active tab is detected by NavLink's built-in isActive prop (end-matching
 * so `/admin/content/libraries` is active only when on that exact segment).
 */

import { NavLink, Outlet } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdminTab {
  label: string
  /** Absolute path, e.g. "/admin/content/libraries". */
  path: string
}

interface AdminSectionLayoutProps {
  tabs: AdminTab[]
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AdminSectionLayout({ tabs }: AdminSectionLayoutProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {/* ── Tab bar ── */}
      <div
        style={{
          display: 'flex',
          gap: 0,
          borderBottom: '1px solid var(--aurora-glass-border)',
          marginBottom: 24,
          overflowX: 'auto',
          scrollbarWidth: 'none' as const,
        }}
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.path}
            to={tab.path}
            end
            style={({ isActive }) => ({
              padding: '8px 18px',
              fontSize: 13.5,
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
              textDecoration: 'none',
              borderBottom: isActive
                ? '2px solid var(--aurora-accent)'
                : '2px solid transparent',
              marginBottom: -1,
              display: 'inline-block',
              transition: 'color 0.15s, border-color 0.15s',
              whiteSpace: 'nowrap' as const,
              boxShadow: isActive ? '0 1px 0 var(--aurora-accent-glow)' : 'none',
              flexShrink: 0,
            })}
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      {/* ── Active tab content ── */}
      <Outlet />
    </div>
  )
}
