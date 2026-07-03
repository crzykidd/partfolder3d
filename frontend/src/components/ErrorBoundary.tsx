/**
 * ErrorBoundary — top-level crash guard.
 *
 * React error boundaries must be class components.  This catches any render /
 * lifecycle error thrown below it and shows a readable fallback instead of an
 * unmounted (blank/black) app.  Wrapped around the whole app in App.tsx, inside
 * ThemeProvider so the fallback can use the aurora CSS variables.
 *
 * The "Reset app data" action clears localStorage (theme, seen-version, etc.) —
 * useful because a corrupted local value is one way to wedge the app — and
 * reloads.  The server session is an httpOnly cookie, so the user stays logged in.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

const btnBase: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  padding: '9px 16px',
  borderRadius: 9,
  cursor: 'pointer',
  border: '1px solid transparent',
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // React logs this in dev; keep an explicit log for production diagnostics.
    // eslint-disable-next-line no-console
    console.error('App crashed (caught by ErrorBoundary):', error, info.componentStack)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  private handleReset = (): void => {
    try {
      window.localStorage.clear()
    } catch {
      /* ignore storage errors */
    }
    window.location.reload()
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div
        style={{
          position: 'fixed',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          background: 'var(--aurora-bg, #0b1220)',
          color: 'var(--aurora-text, #e6edf5)',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        <div
          style={{
            maxWidth: 520,
            width: '100%',
            background: 'var(--aurora-card, rgba(255,255,255,0.04))',
            border: '1px solid var(--aurora-card-border, rgba(255,255,255,0.10))',
            borderRadius: 14,
            padding: 28,
          }}
        >
          <h1 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700 }}>
            Something went wrong
          </h1>
          <p
            style={{
              margin: '0 0 16px',
              fontSize: 13,
              lineHeight: 1.5,
              color: 'var(--aurora-muted, #9fb0c3)',
            }}
          >
            The app hit an unexpected error and couldn&apos;t render. Try reloading. If it keeps
            happening, &quot;Reset app data&quot; clears local settings (you stay logged in on the
            server) and reloads.
          </p>
          <pre
            style={{
              margin: '0 0 18px',
              padding: 12,
              fontSize: 12,
              background: 'rgba(0,0,0,0.35)',
              borderRadius: 8,
              color: 'var(--aurora-danger, #ff6b6b)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              maxHeight: 160,
              overflow: 'auto',
            }}
          >
            {error.message || String(error)}
          </pre>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              onClick={this.handleReload}
              style={{
                ...btnBase,
                background: 'var(--aurora-accent, #0FA4AB)',
                color: '#fff',
              }}
            >
              Reload
            </button>
            <button
              onClick={this.handleReset}
              style={{
                ...btnBase,
                background: 'transparent',
                color: 'var(--aurora-text, #e6edf5)',
                borderColor: 'var(--aurora-card-border, rgba(255,255,255,0.20))',
              }}
            >
              Reset app data &amp; reload
            </button>
          </div>
        </div>
      </div>
    )
  }
}
