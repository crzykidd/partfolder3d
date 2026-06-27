/**
 * ThemeToggle — cycles through system → light → dark.
 * Uses lucide-react icons; requires ThemeProvider in the tree.
 */

import { Moon, Sun, SunMoon } from 'lucide-react'
import { useTheme, type Theme } from './ThemeProvider'

const CYCLE: Theme[] = ['system', 'light', 'dark']

function ThemeIcon({ theme }: { theme: Theme }) {
  if (theme === 'dark') return <Moon className="h-4 w-4" />
  if (theme === 'light') return <Sun className="h-4 w-4" />
  return <SunMoon className="h-4 w-4" />
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  const handleClick = () => {
    const idx = CYCLE.indexOf(theme)
    const next = CYCLE[(idx + 1) % CYCLE.length]
    setTheme(next)
  }

  const label =
    theme === 'dark' ? 'Dark mode' : theme === 'light' ? 'Light mode' : 'System theme'

  return (
    <button
      onClick={handleClick}
      aria-label={`Toggle theme (current: ${label})`}
      title={label}
      className="inline-flex items-center justify-center rounded-md p-2 text-sm font-medium
        transition-colors hover:bg-accent hover:text-accent-foreground
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ThemeIcon theme={theme} />
      <span className="sr-only">{label}</span>
    </button>
  )
}
