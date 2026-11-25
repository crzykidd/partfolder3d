/**
 * Build info baked into this bundle at build time (frontend/Dockerfile ENV ->
 * Vite). `npm run dev` and vitest fall back to local/unknown.
 */

export type BuildInfo = {
  version: string
  commit: string
  channel: string
  build_date: string
}

const env = import.meta.env as Record<string, string | undefined>

export const BUILD_INFO: BuildInfo = {
  version: env.VITE_APP_VERSION || 'unknown',
  commit: env.VITE_GIT_SHA || 'unknown',
  channel: env.VITE_BUILD_CHANNEL || 'local',
  build_date: env.VITE_BUILD_DATE || 'unknown',
}
