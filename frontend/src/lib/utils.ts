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

/**
 * Returns `url` only when it is a safe http/https absolute URL, otherwise
 * `undefined`.
 *
 * Bind this to every `href` that renders a user-supplied or scraped URL
 * (source_url, profile_url, …).  When it returns `undefined`, React omits the
 * attribute entirely, so the `<a>` renders as non-navigating text instead of a
 * live `javascript:`/`data:` link.  Handles null/undefined/relative gracefully.
 */
export function safeHref(url?: string | null): string | undefined {
  if (!url) return undefined
  return isSafeHttpUrl(url) ? url : undefined
}
