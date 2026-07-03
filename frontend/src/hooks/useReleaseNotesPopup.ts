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
    queryKey: ['version'],
    queryFn: fetchCurrentVersion,
    staleTime: 60_000,
  })

  // First-ever use: no lastSeen stored.  Silently record current version as the
  // baseline so the NEXT upgrade triggers the modal.  No modal shown here.
  useEffect(() => {
    if (currentVersion !== undefined && lastSeen === null) {
      setLastSeen(currentVersion)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentVersion]) // intentionally excludes lastSeen/setLastSeen to run only once per version load

  // Show the modal only when lastSeen is set AND the running version is newer.
  const shouldShow =
    currentVersion !== undefined &&
    lastSeen !== null &&
    compareSemver(currentVersion, lastSeen) > 0

  const dismiss = () => {
    if (currentVersion !== undefined) {
      setLastSeen(currentVersion)
    }
  }

  return {
    shouldShow,
    currentVersion: currentVersion ?? null,
    dismiss,
  }
}
