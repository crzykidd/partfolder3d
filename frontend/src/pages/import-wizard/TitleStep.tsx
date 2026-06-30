/**
 * TitleStep — Step 1 of the import wizard.
 *
 * Lets the user edit the confirmed title, add/edit a description,
 * run AI cleanup or summarize on the description, see the source URL,
 * and configure the site API token if needed.
 */

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { extractDomain } from '@/lib/import-utils'
import {
  SECTION_LABEL,
  AURORA_INPUT,
  AURORA_BTN_GHOST_SM,
  AURORA_BTN_PRIMARY,
  onAuroraFocus,
  onAuroraBlur,
} from './styles'
import { SiteSetupBanner } from './SiteSetupBanner'
import { AiTextPreview } from './AiTextPreview'

export interface TitleStepProps {
  session: api.ImportSession
  onNext: () => void
}

export function TitleStep({ session, onNext }: TitleStepProps) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(
    session.confirmed_title ?? session.suggested_title ?? '',
  )
  const [description, setDescription] = useState(session.description ?? '')
  const [error, setError] = useState<string | null>(null)

  const [providerAvailable, setProviderAvailable] = useState<boolean | null>(null)
  const [aiDescText, setAiDescText] = useState<string | null>(null)
  const [aiStatus, setAiStatus] = useState<string | null>(null)

  const domain = session.source_url ? extractDomain(session.source_url) : null

  const { data: siteCap } = useQuery({
    queryKey: ['site-cap', domain],
    queryFn: () => api.getSiteCapability(domain!),
    enabled: domain != null,
    retry: false,
  })

  // Cheap probe — no AI call, no token spend, no usage row written.
  useEffect(() => {
    api
      .getAiStatus()
      .then((r) => setProviderAvailable(r.provider_available))
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const patchMutation = useMutation({
    mutationFn: () =>
      api.patchImportSession(session.id, {
        confirmed_title: title.trim() || null,
        description: description.trim() || null,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      onNext()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save title.'),
  })

  const cleanupMutation = useMutation({
    mutationFn: () => api.aiCleanupDescription(session.id),
    onSuccess: (result) => {
      setProviderAvailable(result.provider_available)
      if (!result.provider_available) return
      if (result.error) {
        setAiStatus(`Error: ${result.error}`)
        setTimeout(() => setAiStatus(null), 3000)
        return
      }
      if (result.text) setAiDescText(result.text)
    },
    onError: (err) => {
      setAiStatus(`Error: ${err instanceof Error ? err.message : 'Request failed'}`)
      setTimeout(() => setAiStatus(null), 3000)
    },
  })

  const summarizeMutation = useMutation({
    mutationFn: () => api.aiSummarize(session.id),
    onSuccess: (result) => {
      setProviderAvailable(result.provider_available)
      if (!result.provider_available) return
      if (result.error) {
        setAiStatus(`Error: ${result.error}`)
        setTimeout(() => setAiStatus(null), 3000)
        return
      }
      if (result.text) setAiDescText(result.text)
    },
    onError: (err) => {
      setAiStatus(`Error: ${err instanceof Error ? err.message : 'Request failed'}`)
      setTimeout(() => setAiStatus(null), 3000)
    },
  })

  const handleNext = () => {
    setError(null)
    if (!title.trim()) {
      setError('Please enter a title.')
      return
    }
    patchMutation.mutate()
  }

  const noProvider = providerAvailable === false
  const aiPending = cleanupMutation.isPending || summarizeMutation.isPending

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Title */}
      <div>
        <label style={SECTION_LABEL}>Title</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ ...AURORA_INPUT, fontSize: 15, fontWeight: 500 }}
          placeholder="Item title"
          autoFocus
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
        {session.suggested_title && title !== session.suggested_title && (
          <button
            type="button"
            style={{
              background: 'none',
              border: 'none',
              padding: '4px 0',
              fontSize: 11,
              color: 'var(--aurora-muted)',
              cursor: 'pointer',
              textDecoration: 'underline',
              transition: 'color 0.15s',
            }}
            onClick={() => setTitle(session.suggested_title!)}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-accent)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
          >
            Reset to suggested: "{session.suggested_title}"
          </button>
        )}
      </div>

      {/* Description */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <label style={{ ...SECTION_LABEL, marginBottom: 0 }}>Description</label>
          <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>optional</span>
        </div>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          style={{ ...AURORA_INPUT, resize: 'vertical', lineHeight: 1.6 }}
          placeholder="Describe this item…"
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />

        {/* AI description buttons */}
        {description.trim() && (
          <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
            <button
              type="button"
              disabled={aiPending || noProvider}
              title={noProvider ? 'No AI provider configured' : undefined}
              onClick={() => {
                setAiStatus(null)
                setAiDescText(null)
                cleanupMutation.mutate()
              }}
              style={{
                ...AURORA_BTN_GHOST_SM,
                opacity: aiPending || noProvider ? 0.4 : 1,
                cursor: aiPending || noProvider ? 'not-allowed' : 'pointer',
              }}
              onMouseEnter={(e) => { if (!aiPending && !noProvider) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
            >
              ✦ {cleanupMutation.isPending ? 'Cleaning…' : 'Clean up (AI)'}
            </button>
            <button
              type="button"
              disabled={aiPending || noProvider}
              title={noProvider ? 'No AI provider configured' : undefined}
              onClick={() => {
                setAiStatus(null)
                setAiDescText(null)
                summarizeMutation.mutate()
              }}
              style={{
                ...AURORA_BTN_GHOST_SM,
                opacity: aiPending || noProvider ? 0.4 : 1,
                cursor: aiPending || noProvider ? 'not-allowed' : 'pointer',
              }}
              onMouseEnter={(e) => { if (!aiPending && !noProvider) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
            >
              ✦ {summarizeMutation.isPending ? 'Summarizing…' : 'Summarize scrape (AI)'}
            </button>
            {noProvider && (
              <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>No AI provider configured</span>
            )}
            {aiStatus && (
              <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{aiStatus}</span>
            )}
          </div>
        )}

        {/* AI text preview */}
        {aiDescText && (
          <div style={{ marginTop: 12 }}>
            <AiTextPreview
              text={aiDescText}
              onUse={() => {
                setDescription(aiDescText)
                setAiDescText(null)
              }}
              onDiscard={() => setAiDescText(null)}
            />
          </div>
        )}
      </div>

      {/* Source URL */}
      {session.source_url && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 8,
            padding: '8px 12px',
          }}
        >
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--aurora-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', flexShrink: 0 }}>
            Source
          </span>
          <a
            href={session.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 12,
              color: 'var(--aurora-accent)',
              textDecoration: 'none',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1,
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
          >
            {session.source_url}
          </a>
        </div>
      )}

      {/* Site setup banner */}
      {domain && siteCap && (
        <SiteSetupBanner domain={domain} cap={siteCap} sessionId={session.id} />
      )}

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          type="button"
          disabled={patchMutation.isPending}
          onClick={handleNext}
          style={{
            ...AURORA_BTN_PRIMARY,
            opacity: patchMutation.isPending ? 0.6 : 1,
          }}
          onMouseEnter={(e) => { if (!patchMutation.isPending) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = patchMutation.isPending ? '0.6' : '1' }}
        >
          {patchMutation.isPending ? 'Saving…' : 'Next →'}
        </button>
      </div>
    </div>
  )
}
