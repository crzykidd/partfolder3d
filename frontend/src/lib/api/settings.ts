import { apiFetch } from './core'

// ---------------------------------------------------------------------------
// Settings (admin)
// ---------------------------------------------------------------------------

export interface SettingOut {
  key: string
  value: unknown
}

export const listSettings = (): Promise<SettingOut[]> =>
  apiFetch<SettingOut[]>('/api/settings')

export const upsertSetting = (key: string, value: unknown): Promise<SettingOut> =>
  apiFetch<SettingOut>(`/api/settings/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  })

// ---------------------------------------------------------------------------
// Render mode (admin) — key: "render.mode"
// ---------------------------------------------------------------------------

export type RenderMode = 'all' | 'no_images' | 'off'

export const RENDER_MODE_LABELS: Record<RenderMode, string> = {
  all: 'Render all models',
  no_images: 'Render only when a model has no images',
  off: 'Disable rendering',
}

export const setRenderMode = (value: RenderMode): Promise<SettingOut> =>
  upsertSetting('render.mode', value)
