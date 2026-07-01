/**
 * UsersPage — admin user management.
 *
 * GET /api/users → paginated table with email, name, role, active badge.
 * Row actions: disable/enable (PATCH is_active), promote to admin (PATCH role).
 *
 * Styling: Aurora aesthetic (B3b restyle — visual pass, all behavior preserved).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  AdminPage, PageHeader,
  Badge,
  Button,
  DataTable, TableRow, Td,
} from '@/components/ui'

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

function UserRow({ user }: { user: api.UserSummary }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (update: api.UpdateUserRequest) => api.updateUser(user.id, update),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  const roleVariant = user.role === 'admin' ? 'accent' : 'muted'
  const activeVariant = user.is_active ? 'success' : 'danger'

  return (
    <TableRow>
      <Td style={{ fontFamily: 'monospace', fontSize: 12 }}>{user.email}</Td>
      <Td>{user.name ?? <span style={{ color: 'var(--aurora-muted)' }}>—</span>}</Td>
      <Td><Badge variant={roleVariant}>{user.role}</Badge></Td>
      <Td><Badge variant={activeVariant}>{user.is_active ? 'Active' : 'Disabled'}</Badge></Td>
      <Td>
        <div style={{ display: 'flex', gap: 6 }}>
          <Button
            variant="ghost"
            size="sm"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ is_active: !user.is_active })}
            extraStyle={user.is_active
              ? { color: 'var(--aurora-danger)', borderColor: 'rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.08)' }
              : { color: 'var(--aurora-accent)', borderColor: 'rgba(15,164,171,0.3)', background: 'rgba(15,164,171,0.08)' }
            }
          >
            {user.is_active ? 'Disable' : 'Enable'}
          </Button>
          {user.role !== 'admin' && (
            <Button
              variant="ghost"
              size="sm"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate({ role: 'admin' })}
            >
              Make admin
            </Button>
          )}
        </div>
        {mutation.isError && (
          <span style={{ fontSize: 11, color: 'var(--aurora-danger)', display: 'block', marginTop: 4 }}>
            {mutation.error instanceof Error ? mutation.error.message : 'Action failed'}
          </span>
        )}
      </Td>
    </TableRow>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const COLUMNS = ['Email', 'Name', 'Role', 'Status', 'Actions']

export function UsersPage() {
  const { data: users = [], isLoading, isError, error } = useQuery({
    queryKey: ['users'],
    queryFn: api.listUsers,
  })

  return (
    <AdminPage>
      <PageHeader
        title="Users"
        description="Manage user accounts and roles."
        meta={isLoading ? undefined : `${users.length} user${users.length === 1 ? '' : 's'}`}
      />

      {isError && (
        <div style={{ fontSize: 12, color: 'var(--aurora-danger)' }}>
          {error instanceof Error ? error.message : 'Failed to load users.'}
        </div>
      )}

      <DataTable
        columns={COLUMNS}
        isLoading={isLoading}
        isEmpty={!isLoading && users.length === 0}
        emptyMessage="No users found."
      >
        {users.map((user) => (
          <UserRow key={user.id} user={user} />
        ))}
      </DataTable>
    </AdminPage>
  )
}
