import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Returns true only when `url` is a safe http: or https: URL.
 *
 * Blocks javascript:, data:, vbscript:, and any other scheme that could
 * execute code when placed in an <a href>.  Used as an XSS guard before
 * rendering user-supplied URLs as live links.
 */
export function isSafeHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}
