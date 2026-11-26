/** Printer profiles: Settings section + PrintRecordFields profile loading. */

import React, { useState } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    listPrinterProfiles: vi.fn(),
    createPrinterProfile: vi.fn(),
    updatePrinterProfile: vi.fn(),
    deletePrinterProfile: vi.fn(),
  }
})

import * as api from '@/lib/api'
import { PrinterProfilesSection } from '@/pages/settings/PrinterProfilesSection'
import {
  PrintRecordFields,
  blankPrintRecord,
  applyPrinterProfile,
} from '@/pages/item/PrintRecordFields'

function prof(over: Partial<api.PrinterProfile>): api.PrinterProfile {
  return {
    id: 1, name: 'X1C PLA', printer: 'Bambu X1C', material: 'PLA', filament_color: null,
    nozzle_diameter: 0.4, layer_height: 0.2, supports: null, is_default: false,
    created_at: '', updated_at: '', ...over,
  }
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('PrinterProfilesSection', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the empty state', async () => {
    vi.mocked(api.listPrinterProfiles).mockResolvedValue([])
    wrap(<PrinterProfilesSection />)
    expect(await screen.findByText(/Save your printer, material/)).toBeInTheDocument()
  })

  it('lists, creates, sets default and deletes', async () => {
    vi.mocked(api.listPrinterProfiles).mockResolvedValue([
      prof({ id: 1, name: 'A', is_default: true }),
      prof({ id: 2, name: 'B' }),
    ])
    vi.mocked(api.createPrinterProfile).mockResolvedValue(prof({ id: 3, name: 'New' }))
    vi.mocked(api.updatePrinterProfile).mockResolvedValue(prof({ id: 2, is_default: true }))
    vi.mocked(api.deletePrinterProfile).mockResolvedValue(undefined)
    wrap(<PrinterProfilesSection />)

    expect(await screen.findByText('A')).toBeInTheDocument()
    expect(screen.getByText('Default')).toBeInTheDocument()
    expect(screen.getAllByText(/Bambu X1C · PLA · 0.4 mm nozzle · 0.2 mm layer/)).toHaveLength(2)

    // create
    fireEvent.click(screen.getByRole('button', { name: 'Add profile' }))
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'New' } })
    fireEvent.change(screen.getByLabelText('Nozzle (mm)'), { target: { value: '0.6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add profile' }))
    await waitFor(() =>
      expect(api.createPrinterProfile).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'New', nozzle_diameter: 0.6, printer: null, supports: null }),
      ),
    )

    // set default on B (only non-default row has the button)
    fireEvent.click(screen.getByRole('button', { name: 'Set default' }))
    await waitFor(() => expect(api.updatePrinterProfile).toHaveBeenCalledWith(2, { is_default: true }))

    // delete with confirm
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[1])
    expect(api.deletePrinterProfile).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm delete' }))
    await waitFor(() => expect(api.deletePrinterProfile).toHaveBeenCalledWith(2))
  })
})

function Harness({ applyDefault }: { applyDefault: boolean }) {
  const [form, setForm] = useState<api.PrintRecordIn>(() => ({
    ...blankPrintRecord(),
    ...(applyDefault ? {} : { printer: 'My Printer', material: 'ABS' }),
  }))
  return <PrintRecordFields form={form} setForm={setForm} applyDefaultProfile={applyDefault} />
}

describe('applyPrinterProfile', () => {
  it('copies non-null values only', () => {
    const form = { ...blankPrintRecord(), filament_color: 'Red', supports: true }
    const out = applyPrinterProfile(form, prof({ filament_color: null, supports: null }))
    expect(out.printer).toBe('Bambu X1C')
    expect(out.nozzle_diameter).toBe(0.4)
    expect(out.filament_color).toBe('Red')
    expect(out.supports).toBe(true)
  })
})

describe('PrintRecordFields profile select', () => {
  beforeEach(() => vi.clearAllMocks())

  it('is hidden when the user has no profiles', async () => {
    vi.mocked(api.listPrinterProfiles).mockResolvedValue([])
    wrap(<Harness applyDefault />)
    await waitFor(() => expect(api.listPrinterProfiles).toHaveBeenCalled())
    expect(screen.queryByLabelText('Load from profile')).toBeNull()
  })

  it('selecting a profile fills fields and leaves null-profile fields alone', async () => {
    vi.mocked(api.listPrinterProfiles).mockResolvedValue([prof({ id: 5, filament_color: null })])
    wrap(<Harness applyDefault={false} />)
    const select = await screen.findByLabelText('Load from profile')
    fireEvent.change(select, { target: { value: '5' } })
    expect(screen.getByPlaceholderText('e.g. Bambu X1C')).toHaveValue('Bambu X1C')
    expect(screen.getByPlaceholderText('e.g. PLA')).toHaveValue('PLA')
    expect(screen.getByPlaceholderText('0.4')).toHaveValue(0.4)
    expect(screen.getByPlaceholderText('e.g. Black')).toHaveValue('')
  })

  it('default profile pre-fills a new form', async () => {
    vi.mocked(api.listPrinterProfiles).mockResolvedValue([
      prof({ id: 7, name: 'Default one', material: 'PETG', is_default: true }),
    ])
    wrap(<Harness applyDefault />)
    await waitFor(() => expect(screen.getByPlaceholderText('e.g. PLA')).toHaveValue('PETG'))
    expect(screen.getByLabelText('Load from profile')).toHaveValue('7')
  })

  it('does not auto-fill when applyDefaultProfile is off (edit form)', async () => {
    vi.mocked(api.listPrinterProfiles).mockResolvedValue([
      prof({ id: 7, material: 'PETG', is_default: true }),
    ])
    wrap(<Harness applyDefault={false} />)
    await screen.findByLabelText('Load from profile')
    expect(screen.getByPlaceholderText('e.g. PLA')).toHaveValue('ABS')
    expect(screen.getByLabelText('Load from profile')).toHaveValue('')
  })
})
