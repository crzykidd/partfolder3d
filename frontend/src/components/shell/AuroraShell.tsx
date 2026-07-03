/**
 * AuroraShell — picks SideNavShell or TopNavShell based on the per-user nav-layout preference.
 *
 * Uses useNavLayout() which resolves: server pref → localStorage → role default.
 * Renders immediately with the localStorage/role-default shell (no flash) while
 * the server pref loads in the background.
 *
 * Also renders the post-upgrade "What's New" modal once per version upgrade.
 *
 * This is what App.tsx mounts inside <AuthGuard>. Public routes (login, setup,
 * examples, share) remain outside and are unchanged.
 */

import { SideNavShell } from './SideNavShell'
import { TopNavShell } from './TopNavShell'
import { useNavLayout } from '@/hooks/useNavLayout'
import { useReleaseNotesPopup } from '@/hooks/useReleaseNotesPopup'
import { ReleaseNotesModal } from '@/components/ReleaseNotesModal'

export function AuroraShell() {
  const { layout } = useNavLayout()
  const { shouldShow, currentVersion, dismiss } = useReleaseNotesPopup()

  return (
    <>
      {layout === 'side' ? <SideNavShell /> : <TopNavShell />}
      {shouldShow && currentVersion && (
        <ReleaseNotesModal version={currentVersion} onClose={dismiss} />
      )}
    </>
  )
}
