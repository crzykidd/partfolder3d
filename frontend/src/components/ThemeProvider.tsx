/**
 * ThemeProvider — system / light / dark theme with localStorage persistence.
 *
 * Strategy:
 *  1. On first load, reads from localStorage (key: "partfolder3d-theme").
 *  2. Falls back to "system" (inherits the OS preference via
 *     `prefers-color-scheme`).
 *  3. Applies a "dark" or "light" class to <html> so Tailwind's dark-mode
 *     class strategy kicks in.  CSS vars in index.css do the rest.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
} from 'react'

export type Theme = 'dark' | 'light' | 'system'

type ThemeProviderProps = {
  children: React.ReactNode
  defaultTheme?: Theme
  storageKey?: string
}

type ThemeProviderState = {
  theme: Theme
  setTheme: (theme: Theme) => void
}

const ThemeProviderContext = createContext<ThemeProviderState>({
  theme: 'system',
  setTheme: () => undefined,
})

export function ThemeProvider({
  children,
  defaultTheme = 'system',
  storageKey = 'partfolder3d-theme',
}: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem(storageKey) as Theme | null) ?? defaultTheme,
  )

  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')

    if (theme === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      root.classList.add(systemTheme)
    } else {
      root.classList.add(theme)
    }
  }, [theme])

  const setTheme = (newTheme: Theme) => {
    localStorage.setItem(storageKey, newTheme)
    setThemeState(newTheme)
  }

  return (
    <ThemeProviderContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeProviderContext.Provider>
  )
}

export function useTheme(): ThemeProviderState {
  const ctx = useContext(ThemeProviderContext)
  if (ctx === undefined) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
