import React, { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Check, Copy } from 'lucide-react'

import * as api from '@/lib/api'
import { detectOS, rewriteLocalPath } from '@/lib/catalog-utils'

import { AURORA_BTN_GHOST } from './styles'

// ---------------------------------------------------------------------------
// OS override (localStorage) — read/write helper used by PathDisplay
// ---------------------------------------------------------------------------

const _OS_OVERRIDE_KEY = 'pf3d_os_override'

function _readOSOverride(): 'windows' | 'posix' | 'auto' {
  try {
    const v = localStorage.getItem(_OS_OVERRIDE_KEY)
    if (v === 'windows' || v === 'posix' || v === 'auto') return v
  } catch { /* ignore */ }
  return 'auto'
}

function _effectiveOS(): 'windows' | 'posix' {
  const override = _readOSOverride()
  return override === 'auto' ? detectOS() : override
}

// ---------------------------------------------------------------------------
// PathDisplay — per-library × per-OS path rewrite
// ---------------------------------------------------------------------------

export interface PathDisplayProps {
  dirPath: string
  itemKey: string
  libraryId: number
}

export function PathDisplay({ dirPath, itemKey, libraryId }: PathDisplayProps) {
  const [copied, setCopied] = useState(false)

  const librariesQ = useQuery({
    queryKey: ['libraries'],
    queryFn: api.listLibraries,
    staleTime: 5 * 60_000,
  })

  const prefixesQ = useQuery({
    queryKey: ['path-prefixes'],
    queryFn: api.getPathPrefixes,
    staleTime: 60_000,
  })

  // Resolve: find library mount_path + user's prefix entry for this library + OS.
  const library = librariesQ.data?.find((l) => l.id === libraryId)
  const prefixMap = prefixesQ.data?.path_prefixes ?? {}
  const libEntry = prefixMap[String(libraryId)]
  const os = _effectiveOS()
  const localPrefix = libEntry?.[os] ?? null

  const displayPath = library
    ? rewriteLocalPath(dirPath, library.mount_path, localPrefix, os)
    : dirPath  // fallback: library not loaded yet, show raw

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(displayPath)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API unavailable (non-HTTPS in dev)
    }
  }, [displayPath])

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--aurora-input-bg)',
        border: '1px solid var(--aurora-input-border)',
        borderRadius: 10,
        padding: '8px 12px',
      }}
    >
      <code style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, fontFamily: 'monospace', color: 'var(--aurora-text-dim)' }}>
        {displayPath}
      </code>
      <button
        onClick={handleCopy}
        style={{
          ...AURORA_BTN_GHOST,
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '4px 10px',
          flexShrink: 0,
        }}
        title="Copy path"
      >
        {copied ? <Check size={12} style={{ color: '#22C55E' }} /> : <Copy size={12} />}
        {copied ? 'Copied' : 'Copy'}
      </button>
      <Link
        to={`/settings?from=/items/${itemKey}`}
        style={{ flexShrink: 0, fontSize: 11, color: 'var(--aurora-muted)', textDecoration: 'none', transition: 'color 0.15s' }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-accent)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--aurora-muted)' }}
        title="Configure path prefixes"
      >
        Edit prefixes
      </Link>
    </div>
  )
}
