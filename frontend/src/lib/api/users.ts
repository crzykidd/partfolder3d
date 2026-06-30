import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Users (admin)
// ---------------------------------------------------------------------------

export interface UserSummary {
  id: number
  email: string
  name: string
  role: string
  is_active: boolean
}

export interface UpdateUserRequest {
  name?: string
  role?: string
  is_active?: boolean
}

export const listUsers = (): Promise<UserSummary[]> =>
  apiFetch<UserSummary[]>('/api/users')

export const updateUser = (
  userId: number,
  body: UpdateUserRequest,
): Promise<UserSummary> =>
  apiFetch<UserSummary>(`/api/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
