/**
 * AppShell — main layout: header (logo + nav + theme toggle) + page outlet.
 */

import { Outlet, NavLink } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'

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

export function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur">
        <div className="container mx-auto flex h-14 items-center px-4">
          <Logo />

          {/* Nav placeholder — routes are added in Phase 3+ */}
          <nav className="ml-6 flex items-center gap-4">
            <NavItem to="/">Dashboard</NavItem>
            {/* More nav items added as pages land */}
          </nav>

          {/* Right side: theme toggle */}
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* ── Page content ── */}
      <main className="container mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
