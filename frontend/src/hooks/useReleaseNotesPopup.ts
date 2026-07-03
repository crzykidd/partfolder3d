/**
 * useReleaseNotesPopup — decides when to show the "What's New" modal.
 *
 * Rules:
 *  - "Last seen version" is stored in localStorage under 'partfolder3d-seen-version'.
 *  - On first-ever use (no stored value), silently record the current version so
 *    future upgrades can trigger the modal.  Do NOT show on first use.
 *  - When a stored version exists and the running version is strictly newer,
 *    shouldShow = true.
 *  - Calling dismiss() records the current version as seen so the modal won't
 *    re-appear until the next upgrade.
 *
 * Version comparison uses numeric semver triples (not lexicographic).
 */

import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { useLocalStorage } from './useLocalStorage'
import { compareSemver } from '@/lib/releaseNotes'

const LS_KEY = 'partfolder3d-seen-version'

async function fetchCurrentVersion(): Promise<string> {
  const res = await fetch('/api/version')
  if (!res.ok) throw new Error(`version fetch failed: ${res.statusText}`)
  const data = (await res.json()) as { version: string }
  return data.version
}

export interface UseReleaseNotesPopupResult {
  /** True when the modal should be displayed */
  shouldShow: boolean
  /** The running version string, or null while loading */
  currentVersion: string | null
  /** Call on modal close — records current version as seen */
  dismiss: () => void
}

export function useReleaseNotesPopup(): UseReleaseNotesPopupResult {
  const [lastSeen, setLastSeen] = useLocalStorage<string | null>(LS_KEY, null)

  const { data: currentVersion } = useQuery({
    // Distinct key from the ['version'] query used by VersionPage + the nav
    // shells — that query resolves to a { version } OBJECT.  Sharing the key put
    // an object into this hook's string slot and crashed compareSemver, blanking
    // the whole app via AuroraShell.  Keep this query isolated to a string.
    queryKey: ['release-notes-version'],
    queryFn: fetchCurrentVersion,
    staleTime: 60_000,
  })

  // Only real strings are valid versions.  A legacy/poisoned non-string value
  // (from the earlier key collision, possibly already saved in localStorage) is
  // treated as unset so it is overwritten below instead of crashing the compare.
  const currentVersionStr = typeof currentVersion === 'string' ? currentVersion : null
  const lastSeenStr = typeof lastSeen === 'string' ? lastSeen : null

  // First load (or a poisoned seen-value): record the current version as the
  // baseline so the NEXT upgrade triggers the modal.  No modal shown here.
  useEffect(() => {
    if (currentVersionStr !== null && lastSeenStr === null) {
      setLastSeen(currentVersionStr)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentVersionStr]) // run once per version load

  // Show the modal only when lastSeen is set AND the running version is newer.
  const shouldShow =
    currentVersionStr !== null &&
    lastSeenStr !== null &&
    compareSemver(currentVersionStr, lastSeenStr) > 0

  const dismiss = () => {
    if (currentVersionStr !== null) {
      setLastSeen(currentVersionStr)
    }
  }

  return {
    shouldShow,
    currentVersion: currentVersionStr,
    dismiss,
  }
}
