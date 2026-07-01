/**
 * AuroraShell — picks SideNavShell or TopNavShell based on the per-user nav-layout preference.
 *
 * Uses useNavLayout() which resolves: server pref → localStorage → role default.
 * Renders immediately with the localStorage/role-default shell (no flash) while
 * the server pref loads in the background.
 *
 * This is what App.tsx mounts inside <AuthGuard>. Public routes (login, setup,
 * examples, share) remain outside and are unchanged.
 */

import { SideNavShell } from './SideNavShell'
import { TopNavShell } from './TopNavShell'
import { useNavLayout } from '@/hooks/useNavLayout'

export function AuroraShell() {
  const { layout } = useNavLayout()
  return layout === 'side' ? <SideNavShell /> : <TopNavShell />
}
