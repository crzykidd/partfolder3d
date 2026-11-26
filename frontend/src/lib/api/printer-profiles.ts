import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Per-user printer profiles (presets for the Log-print form)
// ---------------------------------------------------------------------------

export interface PrinterProfile {
  id: number
  name: string
  printer: string | null
  material: string | null
  filament_color: string | null
  nozzle_diameter: number | null
  layer_height: number | null
  supports: boolean | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface PrinterProfileIn {
  name: string
  printer?: string | null
  material?: string | null
  filament_color?: string | null
  nozzle_diameter?: number | null
  layer_height?: number | null
  supports?: boolean | null
  is_default?: boolean
}

export type PrinterProfilePatch = Partial<PrinterProfileIn>

export const listPrinterProfiles = (): Promise<PrinterProfile[]> =>
  apiFetch<PrinterProfile[]>('/api/me/printer-profiles')

export const createPrinterProfile = (body: PrinterProfileIn): Promise<PrinterProfile> =>
  apiFetch<PrinterProfile>('/api/me/printer-profiles', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const updatePrinterProfile = (
  id: number,
  body: PrinterProfilePatch,
): Promise<PrinterProfile> =>
  apiFetch<PrinterProfile>(`/api/me/printer-profiles/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deletePrinterProfile = (id: number): Promise<void> =>
  apiFetch<void>(`/api/me/printer-profiles/${id}`, { method: 'DELETE' })
