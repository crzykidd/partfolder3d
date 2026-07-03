/**
 * App root — providers + router.
 *
 * Provider order (outer → inner):
 *   ThemeProvider → QueryClientProvider → BrowserRouter → AuthProvider → Routes
 *
 * AuthProvider lives inside QueryClientProvider (it needs useQuery) and inside
 * BrowserRouter (AuthGuard uses navigation hooks).
 *
 * Admin area: 5 tabbed sections using AdminSectionLayout.
 * Back-compat <Navigate replace> redirects preserve every old /admin/* bookmark.
 */

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ThemeProvider } from '@/components/ThemeProvider'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { AuthProvider } from '@/context/AuthContext'
import { AuthGuard, AdminGuard } from '@/components/AuthGuard'
import { AuroraShell } from '@/components/shell/AuroraShell'
import { AdminSectionLayout } from '@/components/admin/AdminSectionLayout'

import { VersionPage } from '@/pages/VersionPage'
import { SetupPage } from '@/pages/SetupPage'
import { LoginPage } from '@/pages/LoginPage'
import { InviteAcceptPage } from '@/pages/InviteAcceptPage'
import { ResetPasswordPage } from '@/pages/ResetPasswordPage'

import { CatalogPage } from '@/pages/CatalogPage'
import { ItemPage } from '@/pages/ItemPage'
import { CreatorPage } from '@/pages/CreatorPage'
import { MyCreationsPage } from '@/pages/MyCreationsPage'

// Admin page components — reused unchanged inside tab outlets
import { LibrariesPage } from '@/pages/admin/LibrariesPage'
import { TagAdminPage } from '@/pages/admin/TagAdminPage'
import { PrintStatsPage } from '@/pages/admin/PrintStatsPage'
import { UsersPage } from '@/pages/admin/UsersPage'
import { InvitesPage } from '@/pages/admin/InvitesPage'
import { PasswordResetPage } from '@/pages/admin/PasswordResetPage'
import { AiProvidersPage } from '@/pages/admin/AiProvidersPage'
import { AiUsagePage } from '@/pages/admin/AiUsagePage'
import { SiteCapabilitiesPage } from '@/pages/admin/SiteCapabilitiesPage'
import { JobsPage } from '@/pages/admin/JobsPage'
import { ScheduledJobsPage } from '@/pages/admin/ScheduledJobsPage'
import { ReviewsPage } from '@/pages/admin/ReviewsPage'
import { IssuesPage } from '@/pages/admin/IssuesPage'
import { ChangesPage } from '@/pages/admin/ChangesPage'
import { BackupsPage } from '@/pages/admin/BackupsPage'
import { ExportPage } from '@/pages/admin/ExportPage'
import { ShareAuditPage } from '@/pages/admin/ShareAuditPage'

import { PublicSharePage } from '@/pages/PublicSharePage'

import { ImportsPage } from '@/pages/ImportsPage'
import { ImportWizardPage } from '@/pages/ImportWizardPage'

import { SettingsPage } from '@/pages/settings/SettingsPage'
import { ApiKeysPage } from '@/pages/settings/ApiKeysPage'
import { QuickStartPage } from '@/pages/settings/QuickStartPage'

// ---------------------------------------------------------------------------
// Section tab configs — co-located with routes for easy maintenance
// ---------------------------------------------------------------------------

const CONTENT_TABS = [
  { label: 'Libraries',   path: '/admin/content/libraries' },
  { label: 'Tags',        path: '/admin/content/tags' },
  { label: 'Print Stats', path: '/admin/content/print-stats' },
]

const ACCESS_TABS = [
  { label: 'Users',           path: '/admin/access/users' },
  { label: 'Invites',         path: '/admin/access/invites' },
  { label: 'Password Resets', path: '/admin/access/password-resets' },
]

const AI_TABS = [
  { label: 'AI Providers',     path: '/admin/ai/providers' },
  { label: 'AI Usage',         path: '/admin/ai/usage' },
  { label: 'Site Capabilities', path: '/admin/ai/sites' },
]

const ACTIVITY_TABS = [
  { label: 'Jobs',       path: '/admin/activity/jobs' },
  { label: 'Scheduled',  path: '/admin/activity/scheduled' },
  { label: 'Reviews',    path: '/admin/activity/reviews' },
  { label: 'Issues',     path: '/admin/activity/issues' },
  { label: 'Change Log', path: '/admin/activity/changes' },
]

const DATA_TABS = [
  { label: 'Backups',     path: '/admin/data/backups' },
  { label: 'Export',      path: '/admin/data/export' },
  { label: 'Share Audit', path: '/admin/data/shares' },
]

// ---------------------------------------------------------------------------
// QueryClient
// ---------------------------------------------------------------------------

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
      <ErrorBoundary>
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

              {/* Protected routes — must be authenticated */}
              <Route element={<AuthGuard />}>
                <Route element={<AuroraShell />}>
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
                  <Route path="/quick-start" element={<QuickStartPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/settings/api-keys" element={<ApiKeysPage />} />

                  {/* ── Admin area — 5 tabbed sections, each guarded individually ── */}

                  {/* Content: Libraries · Tags · Print Stats */}
                  <Route
                    path="/admin/content"
                    element={
                      <AdminGuard>
                        <AdminSectionLayout tabs={CONTENT_TABS} />
                      </AdminGuard>
                    }
                  >
                    <Route index element={<Navigate to="/admin/content/libraries" replace />} />
                    <Route path="libraries" element={<LibrariesPage />} />
                    <Route path="tags" element={<TagAdminPage />} />
                    <Route path="print-stats" element={<PrintStatsPage />} />
                  </Route>

                  {/* Users & Access: Users · Invites · Password Resets */}
                  <Route
                    path="/admin/access"
                    element={
                      <AdminGuard>
                        <AdminSectionLayout tabs={ACCESS_TABS} />
                      </AdminGuard>
                    }
                  >
                    <Route index element={<Navigate to="/admin/access/users" replace />} />
                    <Route path="users" element={<UsersPage />} />
                    <Route path="invites" element={<InvitesPage />} />
                    <Route path="password-resets" element={<PasswordResetPage />} />
                  </Route>

                  {/* AI & Scraping: AI Providers · AI Usage · Site Capabilities */}
                  <Route
                    path="/admin/ai"
                    element={
                      <AdminGuard>
                        <AdminSectionLayout tabs={AI_TABS} />
                      </AdminGuard>
                    }
                  >
                    <Route index element={<Navigate to="/admin/ai/providers" replace />} />
                    <Route path="providers" element={<AiProvidersPage />} />
                    <Route path="usage" element={<AiUsagePage />} />
                    <Route path="sites" element={<SiteCapabilitiesPage />} />
                  </Route>

                  {/* Jobs & Activity: Jobs · Scheduled · Reviews · Issues · Change Log */}
                  <Route
                    path="/admin/activity"
                    element={
                      <AdminGuard>
                        <AdminSectionLayout tabs={ACTIVITY_TABS} />
                      </AdminGuard>
                    }
                  >
                    <Route index element={<Navigate to="/admin/activity/jobs" replace />} />
                    <Route path="jobs" element={<JobsPage />} />
                    <Route path="scheduled" element={<ScheduledJobsPage />} />
                    <Route path="reviews" element={<ReviewsPage />} />
                    <Route path="issues" element={<IssuesPage />} />
                    <Route path="changes" element={<ChangesPage />} />
                  </Route>

                  {/* Data & Backups: Backups · Export · Share Audit */}
                  <Route
                    path="/admin/data"
                    element={
                      <AdminGuard>
                        <AdminSectionLayout tabs={DATA_TABS} />
                      </AdminGuard>
                    }
                  >
                    <Route index element={<Navigate to="/admin/data/backups" replace />} />
                    <Route path="backups" element={<BackupsPage />} />
                    <Route path="export" element={<ExportPage />} />
                    <Route path="shares" element={<ShareAuditPage />} />
                  </Route>

                  {/* ── Back-compat redirects — Content ── */}
                  <Route path="/admin/libraries"   element={<Navigate to="/admin/content/libraries"   replace />} />
                  <Route path="/admin/tags"         element={<Navigate to="/admin/content/tags"         replace />} />
                  <Route path="/admin/pending-tags" element={<Navigate to="/admin/content/tags"         replace />} />
                  <Route path="/admin/print-stats"  element={<Navigate to="/admin/content/print-stats"  replace />} />

                  {/* ── Back-compat redirects — Users & Access ── */}
                  <Route path="/admin/users"           element={<Navigate to="/admin/access/users"           replace />} />
                  <Route path="/admin/invites"         element={<Navigate to="/admin/access/invites"         replace />} />
                  <Route path="/admin/password-reset"  element={<Navigate to="/admin/access/password-resets" replace />} />
                  <Route path="/admin/password-resets" element={<Navigate to="/admin/access/password-resets" replace />} />

                  {/* ── Back-compat redirects — AI & Scraping ── */}
                  <Route path="/admin/ai-providers"      element={<Navigate to="/admin/ai/providers" replace />} />
                  <Route path="/admin/ai-usage"          element={<Navigate to="/admin/ai/usage"     replace />} />
                  <Route path="/admin/site-capabilities" element={<Navigate to="/admin/ai/sites"     replace />} />

                  {/* ── Back-compat redirects — Jobs & Activity ── */}
                  <Route path="/admin/jobs"           element={<Navigate to="/admin/activity/jobs"      replace />} />
                  <Route path="/admin/scheduled-jobs" element={<Navigate to="/admin/activity/scheduled" replace />} />
                  <Route path="/admin/reviews"        element={<Navigate to="/admin/activity/reviews"   replace />} />
                  <Route path="/admin/issues"         element={<Navigate to="/admin/activity/issues"    replace />} />
                  <Route path="/admin/changes"        element={<Navigate to="/admin/activity/changes"   replace />} />

                  {/* ── Back-compat redirects — Data & Backups ── */}
                  <Route path="/admin/backups" element={<Navigate to="/admin/data/backups" replace />} />
                  <Route path="/admin/export"  element={<Navigate to="/admin/data/export"  replace />} />
                  <Route path="/admin/shares"  element={<Navigate to="/admin/data/shares"  replace />} />
                </Route>
              </Route>
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
      </ErrorBoundary>
    </ThemeProvider>
  )
}

export default App
