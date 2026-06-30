import { apiFetch, apiFetchForm } from './core'

// ---------------------------------------------------------------------------
// Phase 7 — Print Records
// ---------------------------------------------------------------------------

export interface PrintRecord {
  id: number
  item_key: string
  note: string | null
  visibility: string  // 'private' | 'public'
  date: string | null
  printer: string | null
  material: string | null
  filament_color: string | null
  nozzle_diameter: number | null
  layer_height: number | null
  supports: boolean | null
  success: boolean | null
  rating: number | null
  filament_length_mm: number | null
  filament_weight_g: number | null
  estimated_print_time_s: number | null
  gcode_file_path: string | null
  print_photo_path: string | null
  logged_by_id: number | null
  created_at: string
  updated_at: string
}

export interface PrintRecordIn {
  note?: string | null
  visibility?: string
  date?: string | null
  printer?: string | null
  material?: string | null
  filament_color?: string | null
  nozzle_diameter?: number | null
  layer_height?: number | null
  supports?: boolean | null
  success?: boolean | null
  rating?: number | null
}

export type PrintRecordPatch = PrintRecordIn

export interface MostPrintedItem {
  item_id: number
  item_key: string | null
  title: string | null
  count: number
}

export interface PrintStats {
  total_prints: number
  success_count: number
  fail_count: number
  success_rate: number | null
  total_filament_length_mm: number
  total_filament_weight_g: number
  total_print_time_s: number
  avg_print_time_s: number | null
  most_printed_items: MostPrintedItem[]
}

export const listPrintRecords = (key: string): Promise<PrintRecord[]> =>
  apiFetch<PrintRecord[]>(`/api/items/${key}/print-records`)

export const createPrintRecord = (
  key: string,
  body: PrintRecordIn,
): Promise<PrintRecord> =>
  apiFetch<PrintRecord>(`/api/items/${key}/print-records`, {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const updatePrintRecord = (
  key: string,
  recordId: number,
  body: PrintRecordPatch,
): Promise<PrintRecord> =>
  apiFetch<PrintRecord>(`/api/items/${key}/print-records/${recordId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deletePrintRecord = (key: string, recordId: number): Promise<void> =>
  apiFetch<void>(`/api/items/${key}/print-records/${recordId}`, {
    method: 'DELETE',
  })

export const uploadGcode = (
  key: string,
  recordId: number,
  file: File,
): Promise<PrintRecord> => {
  const form = new FormData()
  form.append('file', file)
  return apiFetchForm<PrintRecord>(
    `/api/items/${key}/print-records/${recordId}/gcode`,
    form,
  )
}

export const uploadPrintPhoto = (
  key: string,
  recordId: number,
  file: File,
): Promise<PrintRecord> => {
  const form = new FormData()
  form.append('file', file)
  return apiFetchForm<PrintRecord>(
    `/api/items/${key}/print-records/${recordId}/photo`,
    form,
  )
}

export const getPrintStats = (): Promise<PrintStats> =>
  apiFetch<PrintStats>('/api/print-stats')
