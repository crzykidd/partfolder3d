/**
 * api/index.ts — Barrel re-exporting every symbol from all domain modules.
 *
 * Consumers import from '@/lib/api' (or relative './api') unchanged.
 * No behavior change — pure structural split of the former api.ts monolith.
 */
export * from './core'
export * from './setup'
export * from './auth'
export * from './users'
export * from './invites'
export * from './password-reset'
export * from './settings'
export * from './me'
export * from './api-keys'
export * from './items'
export * from './libraries'
export * from './import'
export * from './print-records'
export * from './shares'
export * from './jobs'
export * from './scheduled-jobs'
export * from './issues'
export * from './changes'
export * from './reviews'
export * from './ai'
export * from './backups'
export * from './export'
export * from './tag-admin'
export * from './agentql'
