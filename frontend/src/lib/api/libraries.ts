import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Phase 5 — Libraries
// ---------------------------------------------------------------------------

export interface LibraryOut {
  id: number
  name: string
  mount_path: string
  enabled: boolean
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
