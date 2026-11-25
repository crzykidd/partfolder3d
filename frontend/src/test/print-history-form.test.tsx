/** PrintHistorySection still works after the PrintRecordFields extraction. */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...actual, listPrintRecords: vi.fn(), createPrintRecord: vi.fn() }
})

import * as api from '@/lib/api'
import { PrintHistorySection } from '@/pages/item/PrintHistory'

describe('PrintHistorySection form (shared PrintRecordFields)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listPrintRecords).mockResolvedValue([])
  })

  it('opens the Log a Print form and submits a normalised body', async () => {
    vi.mocked(api.createPrintRecord).mockResolvedValue({
      id: 9, item_key: 'abc', note: null, visibility: 'private', date: null, printer: null,
      material: 'PLA', filament_color: null, nozzle_diameter: null, layer_height: null,
      supports: null, success: true, rating: null, filament_length_mm: null,
      filament_weight_g: null, estimated_print_time_s: null, gcode_file_path: null,
      print_photo_path: null, logged_by_id: 1, created_at: '', updated_at: '',
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <PrintHistorySection itemKey="abc" />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(api.listPrintRecords).toHaveBeenCalled())
    fireEvent.click(await screen.findByRole('button', { name: /Log a print|Log print|Add/i }))
    expect(await screen.findByText('Log a Print')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('e.g. PLA'), { target: { value: 'PLA' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log print' }))
    await waitFor(() =>
      expect(api.createPrintRecord).toHaveBeenCalledWith(
        'abc',
        expect.objectContaining({ material: 'PLA', printer: null, note: null, visibility: 'private' }),
      ),
    )
  })
})
