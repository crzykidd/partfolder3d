import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Download } from 'lucide-react'

import * as api from '@/lib/api'
import { mapBundleStatus, shouldContinuePolling, type ZipPollStatus } from '@/lib/catalog-utils'

import { AURORA_BTN_GHOST, AURORA_BTN_PRIMARY, formatBytes } from './styles'

// ---------------------------------------------------------------------------
// Downloads section
// ---------------------------------------------------------------------------

export interface DownloadsSectionProps {
  itemKey: string
  files: api.FileOut[]
}

export function DownloadsSection({ itemKey, files }: DownloadsSectionProps) {
  const [bundleId, setBundleId] = useState<string | null>(null)
  const [zipStatus, setZipStatus] = useState<ZipPollStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [includeHistory, setIncludeHistory] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const zipMutation = useMutation({
    mutationFn: () => api.queueZip(itemKey, { includeHistory }),
    onMutate: () => {
      setZipStatus('queued')
      setErrorMsg(null)
    },
    onSuccess: (bundle) => {
      setBundleId(bundle.id)
      setZipStatus(mapBundleStatus(bundle.status))
    },
    onError: () => {
      setZipStatus('failed')
      setErrorMsg('Failed to request ZIP.')
    },
  })

  // Reset zip state when includeHistory changes
  const prevIncludeHistory = useRef(includeHistory)
  useEffect(() => {
    if (prevIncludeHistory.current !== includeHistory) {
      prevIncludeHistory.current = includeHistory
      setZipStatus('idle')
      setBundleId(null)
      setErrorMsg(null)
      stopPoll()
    }
  }, [includeHistory, stopPoll])

  // Poll when we have a bundleId and status is queued/building
  useEffect(() => {
    if (!bundleId || !shouldContinuePolling(zipStatus)) {
      stopPoll()
      return
    }

    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const bundle = await api.pollZip(itemKey, bundleId)
        const status = mapBundleStatus(bundle.status)
        setZipStatus(status)
        if (bundle.error_message) setErrorMsg(bundle.error_message)
        if (!shouldContinuePolling(status)) stopPoll()
      } catch {
        setZipStatus('failed')
        setErrorMsg('Polling failed.')
        stopPoll()
      }
    }, 2000)

    return stopPoll
  }, [bundleId, zipStatus, itemKey, stopPoll])

  const handleDownloadZip = useCallback(() => {
    if (bundleId && zipStatus === 'ready') {
      window.open(api.zipDownloadUrl(itemKey, bundleId))
    }
  }, [bundleId, zipStatus, itemKey])

  const zipLabel: Record<ZipPollStatus, string> = {
    idle: 'Download all as ZIP',
    queued: 'Queued…',
    building: 'Building ZIP…',
    ready: 'Download ZIP',
    failed: 'ZIP failed — retry?',
    expired: 'ZIP expired — retry?',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Individual files */}
      {files.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: 0 }}>
          No files catalogued yet.
        </p>
      ) : (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            overflow: 'hidden',
          }}
        >
          {files.map((file, idx) => (
            <div
              key={file.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderTop: idx > 0 ? '1px solid var(--aurora-divider)' : 'none',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 12, fontWeight: 500, fontFamily: 'monospace', color: 'var(--aurora-text)' }}>
                  {file.path}
                </span>
                <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
                  {file.role} · {formatBytes(file.size)}
                </span>
              </div>
              <a
                href={api.fileDownloadUrl(itemKey, file.path)}
                download
                style={{
                  ...AURORA_BTN_GHOST,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  textDecoration: 'none',
                  flexShrink: 0,
                }}
              >
                <Download size={12} />
                Download
              </a>
            </div>
          ))}
        </div>
      )}

      {/* ZIP download */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Include history checkbox */}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 12,
            cursor: 'pointer',
            userSelect: 'none',
            color: 'var(--aurora-text-dim)',
          }}
        >
          <input
            type="checkbox"
            checked={includeHistory}
            onChange={(e) => setIncludeHistory(e.target.checked)}
            style={{ accentColor: 'var(--aurora-accent)', width: 14, height: 14 }}
          />
          <span>Include print history</span>
          <span
            style={{ fontSize: 11, color: 'var(--aurora-muted)', cursor: 'help' }}
            title="Adds a print-history.json to the ZIP. Public records always included; private records included only for your own download."
          >
            (?)
          </span>
        </label>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={
              zipStatus === 'ready'
                ? handleDownloadZip
                : zipStatus === 'idle' || zipStatus === 'failed' || zipStatus === 'expired'
                  ? () => zipMutation.mutate()
                  : undefined
            }
            disabled={zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending}
            style={{
              ...AURORA_BTN_PRIMARY,
              opacity: zipStatus === 'queued' || zipStatus === 'building' || zipMutation.isPending ? 0.5 : 1,
            }}
          >
            {zipLabel[zipStatus]}
          </button>
          {errorMsg && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{errorMsg}</span>
          )}
          {(zipStatus === 'queued' || zipStatus === 'building') && (
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
              Polling every 2 s…
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
