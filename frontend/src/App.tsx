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
import { PendingTagsPage } from '@/pages/admin/PendingTagsPage'
import { IssuesPage } from '@/pages/admin/IssuesPage'
import { ChangesPage } from '@/pages/admin/ChangesPage'
import { ReviewsPage } from '@/pages/admin/ReviewsPage'
import { PrintStatsPage } from '@/pages/admin/PrintStatsPage'
import { ShareAuditPage } from '@/pages/admin/ShareAuditPage'
import { AiProvidersPage } from '@/pages/admin/AiProvidersPage'

import { PublicSharePage } from '@/pages/PublicSharePage'

// UI prototype examples — no auth required, standalone mock pages
import { ExamplesIndex } from '@/pages/examples/ExamplesIndex'
import { Example1 } from '@/pages/examples/Example1'
import { Example2 } from '@/pages/examples/Example2'
import { Example3 } from '@/pages/examples/Example3'

import { ImportsPage } from '@/pages/ImportsPage'
import { ImportWizardPage } from '@/pages/ImportWizardPage'

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
              {/* Public share page — unauthenticated, outside all guards */}
              <Route path="/share/:token" element={<PublicSharePage />} />

              {/* UI prototype examples — no auth, standalone mock pages */}
              <Route path="/examples" element={<ExamplesIndex />} />
              <Route path="/example1" element={<Example1 />} />
              <Route path="/example2" element={<Example2 />} />
              <Route path="/example3" element={<Example3 />} />

              {/* Protected routes — must be authenticated */}
              <Route element={<AuthGuard />}>
                <Route element={<AppShell />}>
                  <Route index element={<VersionPage />} />

                  {/* Catalog */}
                  <Route path="/catalog" element={<CatalogPage />} />
                  <Route path="/items/:key" element={<ItemPage />} />
                  <Route path="/creators/:creatorId" element={<CreatorPage />} />
                  <Route path="/me/creations" element={<MyCreationsPage />} />

                  {/* Phase 5 — Import wizard */}
                  <Route path="/imports" element={<ImportsPage />} />
                  <Route path="/import/:sessionId" element={<ImportWizardPage />} />

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
                  <Route
                    path="/admin/pending-tags"
                    element={
                      <AdminGuard>
                        <PendingTagsPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/issues"
                    element={
                      <AdminGuard>
                        <IssuesPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/changes"
                    element={
                      <AdminGuard>
                        <ChangesPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/reviews"
                    element={
                      <AdminGuard>
                        <ReviewsPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/print-stats"
                    element={
                      <AdminGuard>
                        <PrintStatsPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/shares"
                    element={
                      <AdminGuard>
                        <ShareAuditPage />
                      </AdminGuard>
                    }
                  />
                  <Route
                    path="/admin/ai-providers"
                    element={
                      <AdminGuard>
                        <AiProvidersPage />
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
