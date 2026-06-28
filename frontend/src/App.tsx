/**
 * App root — providers + router.
 *
 * Provider order (outer → inner):
 *   ThemeProvider → QueryClientProvider → BrowserRouter → AuthProvider → Routes
 *
 * AuthProvider lives inside QueryClientProvider (it needs useQuery) and inside
 * BrowserRouter (AuthGuard uses navigation hooks).
 */

import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '@/components/ThemeProvider'
import { AuthProvider } from '@/context/AuthContext'
import { AuthGuard, AdminGuard } from '@/components/AuthGuard'
import { AppShell } from '@/components/AppShell'

import { VersionPage } from '@/pages/VersionPage'
import { SetupPage } from '@/pages/SetupPage'
import { LoginPage } from '@/pages/LoginPage'
import { InviteAcceptPage } from '@/pages/InviteAcceptPage'
import { ResetPasswordPage } from '@/pages/ResetPasswordPage'

import { CatalogPage } from '@/pages/CatalogPage'
import { ItemPage } from '@/pages/ItemPage'
import { CreatorPage } from '@/pages/CreatorPage'
import { MyCreationsPage } from '@/pages/MyCreationsPage'

import { UsersPage } from '@/pages/admin/UsersPage'
import { InvitesPage } from '@/pages/admin/InvitesPage'
import { PasswordResetPage } from '@/pages/admin/PasswordResetPage'
import { JobsPage } from '@/pages/admin/JobsPage'
import { ScheduledJobsPage } from '@/pages/admin/ScheduledJobsPage'

import { SettingsPage } from '@/pages/settings/SettingsPage'
import { ApiKeysPage } from '@/pages/settings/ApiKeysPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="partfolder3d-theme">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              {/* Public routes — no auth required */}
              <Route path="/setup" element={<SetupPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/invites/:token/accept" element={<InviteAcceptPage />} />
              <Route path="/password-reset/:token" element={<ResetPasswordPage />} />

              {/* Protected routes — must be authenticated */}
              <Route element={<AuthGuard />}>
                <Route element={<AppShell />}>
                  <Route index element={<VersionPage />} />

                  {/* Catalog */}
                  <Route path="/catalog" element={<CatalogPage />} />
                  <Route path="/items/:key" element={<ItemPage />} />
                  <Route path="/creators/:creatorId" element={<CreatorPage />} />
                  <Route path="/me/creations" element={<MyCreationsPage />} />

                  {/* Settings */}
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/settings/api-keys" element={<ApiKeysPage />} />

                  {/* Admin area */}
                  <Route
                    path="/admin/users"
                    element={
                      <AdminGuard>
                        <UsersPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/invites"
                    element={
                      <AdminGuard>
                        <InvitesPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/password-reset"
                    element={
                      <AdminGuard>
                        <PasswordResetPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/jobs"
                    element={
                      <AdminGuard>
                        <JobsPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/scheduled-jobs"
                    element={
                      <AdminGuard>
                        <ScheduledJobsPage />
                      </AdminGuard>
                    }
                  />
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export default App
