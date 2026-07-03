import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 5 — Libraries
// ---------------------------------------------------------------------------

export interface LibraryOut {
  id: number
  name: string
  mount_path: string
  enabled: boolean
  item_count: number
}

export interface LibraryCreate {
  name: string
  mount_path: string
}

export const listLibraries = (): Promise<LibraryOut[]> =>
  apiFetch<LibraryOut[]>('/api/libraries')

export const createLibrary = (body: LibraryCreate): Promise<LibraryOut> =>
  apiFetch<LibraryOut>('/api/libraries', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const disableLibrary = (id: number): Promise<void> =>
  apiFetch<void>(`/api/libraries/${id}`, { method: 'DELETE' })

export const enableLibrary = (id: number): Promise<LibraryOut> =>
  apiFetch<LibraryOut>(`/api/libraries/${id}/enable`, { method: 'POST' })

export const purgeLibrary = (id: number): Promise<void> =>
  apiFetch<void>(`/api/libraries/${id}/purge`, { method: 'DELETE' })

// ---------------------------------------------------------------------------
// Issue #8 — Admin filesystem browser
// ---------------------------------------------------------------------------

export interface FsBrowseEntry {
  name: string
  abs_path: string
}

export interface FsBrowseResult {
  path: string | null
  parent: string | null
  entries: FsBrowseEntry[]
}

export const fsBrowse = (path?: string): Promise<FsBrowseResult> => {
  const params = path ? `?path=${encodeURIComponent(path)}` : ''
  return apiFetch<FsBrowseResult>(`/api/admin/fs/browse${params}`)
}
