/**
 * UsersPage — admin user management.
 *
 * GET /api/users → TanStack Table with email, name, role, active badge.
 * Row actions: disable/enable (PATCH is_active), promote to admin (PATCH role).
 */

import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import * as api from '@/lib/api'

const col = createColumnHelper<api.UserSummary>()

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        role === 'admin'
          ? 'bg-primary/10 text-primary'
          : 'bg-muted text-muted-foreground'
      }`}
    >
      {role}
    </span>
  )
}

function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        active ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
      }`}
    >
      {active ? 'Active' : 'Disabled'}
    </span>
  )
}

function RowActions({ user }: { user: api.UserSummary }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (update: api.UpdateUserRequest) =>
      api.updateUser(user.id, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => mutation.mutate({ is_active: !user.is_active })}
        disabled={mutation.isPending}
        className="text-xs text-muted-foreground hover:text-foreground underline disabled:opacity-50"
      >
        {user.is_active ? 'Disable' : 'Enable'}
      </button>
      {user.role !== 'admin' && (
        <button
          onClick={() => mutation.mutate({ role: 'admin' })}
          disabled={mutation.isPending}
          className="text-xs text-muted-foreground hover:text-foreground underline disabled:opacity-50"
        >
          Make admin
        </button>
      )}
    </div>
  )
}

const columns = [
  col.accessor('email', {
    header: 'Email',
    cell: (info) => (
      <span className="font-mono text-sm">{info.getValue()}</span>
    ),
  }),
  col.accessor('name', { header: 'Name' }),
  col.accessor('role', {
    header: 'Role',
    cell: (info) => <RoleBadge role={info.getValue()} />,
  }),
  col.accessor('is_active', {
    header: 'Status',
    cell: (info) => <ActiveBadge active={info.getValue()} />,
  }),
  col.display({
    id: 'actions',
    header: 'Actions',
    cell: (info) => <RowActions user={info.row.original} />,
  }),
]

export function UsersPage() {
  const { data: users = [], isLoading, isError } = useQuery({
    queryKey: ['users'],
    queryFn: api.listUsers,
  })

  const table = useReactTable({
    data: users,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Users</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage user accounts and roles.
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && (
        <p className="text-sm text-destructive">Failed to load users.</p>
      )}

      {!isLoading && !isError && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-t border-border hover:bg-muted/30 transition-colors"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-4 py-8 text-center text-sm text-muted-foreground"
                  >
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
