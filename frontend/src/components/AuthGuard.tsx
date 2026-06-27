/**
 * AuthGuard — protects authenticated routes.
 *
 * On app load we first check setup status:
 *   - Not initialized → redirect to /setup
 *   - Initialized but unauthenticated → redirect to /login
 *   - Authenticated → render children
 *
 * AdminGuard further restricts to role === "admin".
 */

import React from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { useAuth } from '@/context/AuthContext'
import { getSetupStatus } from '@/lib/api'

// ---------------------------------------------------------------------------
// AuthGuard — renders children only when authenticated
// ---------------------------------------------------------------------------

export function AuthGuard() {
  const { user, isLoading } = useAuth()

  const { data: setup, isLoading: setupLoading } = useQuery({
    queryKey: ['setupStatus'],
    queryFn: getSetupStatus,
    staleTime: 60_000,
    retry: false,
  })

  const location = useLocation()

  if (isLoading || setupLoading) {
    return <LoadingScreen />
  }

  if (setup && !setup.initialized) {
    return <Navigate to="/setup" replace />
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}

// ---------------------------------------------------------------------------
// AdminGuard — render children only for admin users
// ---------------------------------------------------------------------------

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()

  if (!user) return null

  if (user.role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <h1 className="text-2xl font-bold text-destructive">Access Denied</h1>
        <p className="text-muted-foreground">
          This area requires administrator privileges.
        </p>
      </div>
    )
  }

  return <>{children}</>
}

// ---------------------------------------------------------------------------
// Shared loading screen
// ---------------------------------------------------------------------------

function LoadingScreen() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p className="text-muted-foreground text-sm animate-pulse">Loading…</p>
    </div>
  )
}
