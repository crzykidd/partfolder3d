/**
 * ImportWizardPage — multi-step wizard for reviewing and committing an import session.
 *
 * Route: /import/:sessionId
 *
 * Steps:
 *   1. Title      — edit confirmed_title; show source URL; site-setup prompt if needed.
 *   2. Images     — scrollable strip; Set as default; upload additional images.
 *   3. Tags       — confirmed chips (removable) + pending chips (accept/reject) + manual input.
 *   4. Creator    — toggle attributed / own design.
 *   5. Summary    — read-only review; Commit or Cancel.
 *
 * Polls GET /api/import-sessions/{id} every 3 s while status=processing.
 *
 * Styling: Aurora aesthetic — glass cards, teal accent (#0FA4AB), --aurora-* CSS vars.
 */

import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import * as api from '@/lib/api'
import {
  WIZARD_STEPS,
  STEP_LABELS,
  type WizardStep,
  nextStep,
  prevStep,
  stepIndex,
  acceptPendingTag,
  rejectPendingTag,
  removeConfirmedTag,
  addConfirmedTag,
  pendingTagNextAction,
  isProcessing,
  isEditable,
  extractDomain,
} from '@/lib/import-utils'

// ---------------------------------------------------------------------------
// Aurora style constants
// ---------------------------------------------------------------------------

const AURORA_CARD: React.CSSProperties = {
  background: 'var(--aurora-card)',
  border: '1px solid var(--aurora-card-border)',
  borderRadius: 14,
  backdropFilter: 'blur(16px)',
  WebkitBackdropFilter: 'blur(16px)',
}

const AURORA_INPUT: React.CSSProperties = {
  background: 'var(--aurora-input-bg)',
  border: '1px solid var(--aurora-input-border)',
  borderRadius: 8,
  color: 'var(--aurora-text)',
  padding: '7px 11px',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  transition: 'border-color 0.15s, box-shadow 0.15s',
  boxSizing: 'border-box',
  display: 'block',
}

const AURORA_BTN_PRIMARY: React.CSSProperties = {
  background: 'var(--aurora-accent)',
  border: 'none',
  borderRadius: 20,
  color: 'var(--aurora-accent-fg)',
  fontSize: 13,
  fontWeight: 700,
  padding: '8px 22px',
  cursor: 'pointer',
  boxShadow: '0 4px 14px var(--aurora-accent-glow)',
  transition: 'opacity 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

const AURORA_BTN_GHOST: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 13,
  padding: '7px 18px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
}

const AURORA_BTN_GHOST_SM: React.CSSProperties = {
  background: 'var(--aurora-glass)',
  border: '1px solid var(--aurora-glass-border)',
  borderRadius: 20,
  color: 'var(--aurora-text-dim)',
  fontSize: 11,
  padding: '4px 12px',
  cursor: 'pointer',
  transition: 'all 0.15s',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
}

const SECTION_LABEL: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--aurora-muted)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: 6,
}

// Focus/blur handlers for aurora inputs
function onAuroraFocus(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-pill-border)'
  e.currentTarget.style.boxShadow = '0 0 0 3px var(--aurora-pill)'
}
function onAuroraBlur(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
  e.currentTarget.style.borderColor = 'var(--aurora-input-border)'
  e.currentTarget.style.boxShadow = 'none'
}

// ---------------------------------------------------------------------------
// Progress indicator (Aurora stepper)
// ---------------------------------------------------------------------------

function StepProgress({ current }: { current: WizardStep }) {
  const idx = stepIndex(current)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
      {WIZARD_STEPS.map((step, i) => (
        <React.Fragment key={step}>
          {/* Step column */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
            {/* Circle */}
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 13,
                fontWeight: 700,
                transition: 'all 0.25s',
                background: i <= idx ? 'var(--aurora-accent)' : 'var(--aurora-glass)',
                border: i <= idx ? 'none' : '1px solid var(--aurora-glass-border)',
                color: i <= idx ? 'var(--aurora-accent-fg)' : 'var(--aurora-muted)',
                boxShadow: i === idx
                  ? '0 0 0 4px var(--aurora-pill), 0 0 16px var(--aurora-accent-glow)'
                  : 'none',
              }}
            >
              {i < idx ? <Check size={14} /> : i + 1}
            </div>
            {/* Label */}
            <span
              style={{
                marginTop: 6,
                fontSize: 10,
                fontWeight: i === idx ? 700 : 400,
                color: i === idx
                  ? 'var(--aurora-accent)'
                  : i < idx
                  ? 'var(--aurora-text-dim)'
                  : 'var(--aurora-muted)',
                whiteSpace: 'nowrap',
                textAlign: 'center',
              }}
            >
              {STEP_LABELS[step]}
            </span>
          </div>

          {/* Connector */}
          {i < WIZARD_STEPS.length - 1 && (
            <div
              style={{
                flex: 1,
                height: 2,
                marginTop: 15,
                background: i < idx ? 'var(--aurora-accent)' : 'var(--aurora-glass-border)',
                transition: 'background 0.3s',
              }}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Site-setup banner
// ---------------------------------------------------------------------------

interface SiteSetupBannerProps {
  domain: string
  cap: api.SiteCapability
  sessionId: string
}

function SiteSetupBanner({ domain, cap, sessionId }: SiteSetupBannerProps) {
  const [token, setToken] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const patchMutation = useMutation({
    mutationFn: () => api.patchSiteCapability(domain, { token: token.trim() }),
    onSuccess: () => {
      setSaved(true)
      setToken('')
      void queryClient.invalidateQueries({ queryKey: ['site-cap', domain] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save token.'),
  })

  if (!cap.requires_token && !cap.is_manual_only) return null

  return (
    <div
      style={{
        background: 'rgba(245,158,11,0.08)',
        border: '1px solid rgba(245,158,11,0.3)',
        borderRadius: 10,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {cap.is_manual_only && (
        <p style={{ fontSize: 13, fontWeight: 600, color: '#D97706', margin: 0 }}>
          This site requires manual file upload — automatic downloading is not supported.
          Please upload the files yourself in the previous step.
        </p>
      )}
      {cap.requires_token && !cap.has_token && (
        <>
          <p style={{ fontSize: 13, fontWeight: 600, color: '#D97706', margin: 0 }}>
            This site requires an API token to import files automatically.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your API token here"
              style={{ ...AURORA_INPUT, flex: 1 }}
              onFocus={onAuroraFocus}
              onBlur={onAuroraBlur}
            />
            <button
              type="button"
              disabled={patchMutation.isPending || !token.trim()}
              onClick={() => { setError(null); setSaved(false); patchMutation.mutate() }}
              style={{
                background: '#D97706',
                border: 'none',
                borderRadius: 20,
                color: '#FFFFFF',
                fontSize: 12,
                fontWeight: 700,
                padding: '6px 16px',
                cursor: 'pointer',
                opacity: patchMutation.isPending || !token.trim() ? 0.5 : 1,
                transition: 'opacity 0.15s',
                flexShrink: 0,
              }}
            >
              {patchMutation.isPending ? 'Saving…' : 'Save Token'}
            </button>
          </div>
          {saved && (
            <p style={{ fontSize: 12, color: '#16A34A', margin: 0 }}>✓ Token saved.</p>
          )}
          {error && (
            <p style={{ fontSize: 12, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
          )}
        </>
      )}
      {cap.requires_token && cap.has_token && (
        <p style={{ fontSize: 13, color: '#D97706', margin: 0 }}>
          Token is configured for this site.{' '}
          <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>
            (Session: {sessionId.slice(0, 8)}…)
          </span>
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared: AI text preview panel
// ---------------------------------------------------------------------------

function AiTextPreview({
  text,
  onUse,
  onDiscard,
}: {
  text: string
  onUse: () => void
  onDiscard: () => void
}) {
  return (
    <div
      style={{
        background: 'var(--aurora-glass)',
        border: '1px solid var(--aurora-glass-border)',
        borderRadius: 10,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <span style={SECTION_LABEL}>AI suggestion — preview</span>
      <p
        style={{
          fontSize: 13,
          color: 'var(--aurora-text)',
          lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
          margin: 0,
        }}
      >
        {text}
      </p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          onClick={onUse}
          style={AURORA_BTN_PRIMARY}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
        >
          Use this
        </button>
        <button
          type="button"
          onClick={onDiscard}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Discard
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 1: Title
// ---------------------------------------------------------------------------

interface TitleStepProps {
  session: api.ImportSession
  onNext: () => void
}

function TitleStep({ session, onNext }: TitleStepProps) {
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

// ---------------------------------------------------------------------------
// Step 2: Images
// ---------------------------------------------------------------------------

interface ImagesStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

function ImagesStep({ session, onNext, onPrev }: ImagesStepProps) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const setDefaultMutation = useMutation({
    mutationFn: (path: string) =>
      api.patchImportSession(session.id, { default_image_path: path }),
    onSuccess: (updated) =>
      queryClient.setQueryData(['import-session', session.id], updated),
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to set default image.'),
  })

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => api.uploadSessionFiles(session.id, files),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to upload images.'),
  })

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const files = Array.from(e.target.files)
    uploadMutation.mutate(files)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <p style={{ fontSize: 13, color: 'var(--aurora-muted)', margin: 0 }}>
        {session.images.length === 0
          ? 'No images yet. You can upload some below.'
          : `${session.images.length} image(s). Click "Set as default" to choose the cover image.`}
      </p>

      {/* Horizontal scrollable strip */}
      {session.images.length > 0 && (
        <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8 }}>
          {[...session.images]
            .sort((a, b) => a.order - b.order)
            .map((img) => (
              <div key={img.id} style={{ position: 'relative', flexShrink: 0 }}>
                <div
                  style={{
                    width: 160,
                    height: 160,
                    overflow: 'hidden',
                    borderRadius: 10,
                    border: img.is_default
                      ? '2px solid var(--aurora-accent)'
                      : '2px solid var(--aurora-glass-border)',
                    boxShadow: img.is_default ? 'var(--aurora-glow)' : 'none',
                    transition: 'border-color 0.15s, box-shadow 0.15s',
                  }}
                >
                  {img.is_url ? (
                    <img
                      src={img.path}
                      alt=""
                      style={{ height: '100%', width: '100%', objectFit: 'cover', display: 'block' }}
                      onError={(e) => {
                        ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        height: '100%',
                        width: '100%',
                        background: 'var(--aurora-glass)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: 12,
                        boxSizing: 'border-box',
                      }}
                    >
                      <span
                        style={{
                          fontSize: 10,
                          color: 'var(--aurora-muted)',
                          textAlign: 'center',
                          lineHeight: 1.4,
                          wordBreak: 'break-all',
                          fontFamily: 'monospace',
                        }}
                      >
                        {img.path.split('/').pop()}
                        <br />
                        <span style={{ fontSize: 9, color: 'var(--aurora-muted)', fontFamily: 'sans-serif' }}>
                          (preview after commit)
                        </span>
                      </span>
                    </div>
                  )}
                </div>
                {img.is_default && (
                  <span
                    style={{
                      position: 'absolute',
                      top: 6,
                      left: 6,
                      background: 'var(--aurora-accent)',
                      color: 'var(--aurora-accent-fg)',
                      borderRadius: 20,
                      fontSize: 9,
                      fontWeight: 700,
                      padding: '2px 8px',
                      boxShadow: '0 0 8px var(--aurora-accent-glow)',
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                    }}
                  >
                    Default
                  </span>
                )}
                {!img.is_default && (
                  <button
                    type="button"
                    disabled={setDefaultMutation.isPending}
                    onClick={() => { setError(null); setDefaultMutation.mutate(img.path) }}
                    style={{
                      marginTop: 6,
                      width: '100%',
                      background: 'none',
                      border: 'none',
                      fontSize: 11,
                      color: 'var(--aurora-muted)',
                      cursor: 'pointer',
                      textDecoration: 'underline',
                      opacity: setDefaultMutation.isPending ? 0.5 : 1,
                      transition: 'color 0.15s',
                      padding: 0,
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-accent)' }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
                  >
                    Set as default
                  </button>
                )}
              </div>
            ))}
        </div>
      )}

      {/* Upload images */}
      <div>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
          style={{
            ...AURORA_BTN_GHOST,
            opacity: uploadMutation.isPending ? 0.5 : 1,
            cursor: uploadMutation.isPending ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => { if (!uploadMutation.isPending) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" style={{ width: 14, height: 14 }}>
            <path d="M9.25 13.25a.75.75 0 0 0 1.5 0V4.636l2.955 3.129a.75.75 0 0 0 1.09-1.03l-4.25-4.5a.75.75 0 0 0-1.09 0l-4.25 4.5a.75.75 0 1 0 1.09 1.03L9.25 4.636v8.614Z" />
            <path d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z" />
          </svg>
          {uploadMutation.isPending ? 'Uploading…' : 'Upload Images'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          onChange={handleUpload}
        />
      </div>

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4 }}>
        <button
          type="button"
          onClick={onPrev}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={onNext}
          style={AURORA_BTN_PRIMARY}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
        >
          Next →
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 3: Tags
// ---------------------------------------------------------------------------

interface TagsStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

function TagsStep({ session, onNext, onPrev }: TagsStepProps) {
  const queryClient = useQueryClient()
  const [confirmed, setConfirmed] = useState<string[]>(
    session.tag_state?.confirmed ?? [],
  )
  const [pending, setPending] = useState<string[]>(
    session.tag_state?.pending ?? [],
  )
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  // Inline prompt shown when user clicks Next with unadded tag text
  const [showPendingPrompt, setShowPendingPrompt] = useState(false)
  const addAndContinueBtnRef = useRef<HTMLButtonElement>(null)
  // Guard: auto-suggest fires at most once per step entry
  const autoSuggestFiredRef = useRef(false)

  const [tagProviderAvailable, setTagProviderAvailable] = useState<boolean | null>(null)
  const [aiTagSuggestions, setAiTagSuggestions] = useState<api.AiTagSuggestionOut | null>(null)
  const [tagAiStatus, setTagAiStatus] = useState<string | null>(null)

  const patchMutation = useMutation({
    mutationFn: (tags: string[]) =>
      api.patchImportSession(session.id, { confirmed_tags: tags }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      onNext()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save tags.'),
  })

  const suggestTagsMutation = useMutation({
    mutationFn: () => api.aiSuggestTags(session.id),
    onSuccess: (result) => {
      setTagProviderAvailable(result.provider_available)
      if (!result.provider_available) return
      if (result.error) {
        setTagAiStatus(`Error: ${result.error}`)
        setTimeout(() => setTagAiStatus(null), 3000)
        return
      }
      if (result.canonical.length > 0 || result.new_suggestions.length > 0) {
        setAiTagSuggestions(result)
      } else {
        setTagAiStatus('No tag suggestions found.')
        setTimeout(() => setTagAiStatus(null), 3000)
      }
    },
    onError: (err) => {
      setTagAiStatus(`Error: ${err instanceof Error ? err.message : 'Request failed'}`)
      setTimeout(() => setTagAiStatus(null), 3000)
    },
  })

  // Auto-suggest once on step entry: cheap status probe first, then suggest if available.
  useEffect(() => {
    if (autoSuggestFiredRef.current) return
    autoSuggestFiredRef.current = true
    api
      .getAiStatus()
      .then((r) => {
        setTagProviderAvailable(r.provider_available)
        if (r.provider_available) {
          suggestTagsMutation.mutate()
        }
      })
      .catch(() => {
        // Best-effort: failure silently leaves the manual button available.
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Focus the "Add & continue" button when the pending-tag prompt appears
  useEffect(() => {
    if (showPendingPrompt) {
      addAndContinueBtnRef.current?.focus()
    }
  }, [showPendingPrompt])

  // ESC dismisses the pending-tag prompt
  useEffect(() => {
    if (!showPendingPrompt) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowPendingPrompt(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [showPendingPrompt])

  const handleAccept = (tag: string) => {
    const [c, p] = acceptPendingTag(confirmed, pending, tag)
    setConfirmed(c)
    setPending(p)
  }

  const handleReject = (tag: string) => {
    const [c, p] = rejectPendingTag(confirmed, pending, tag)
    setConfirmed(c)
    setPending(p)
  }

  const handleRemoveConfirmed = (tag: string) => {
    setConfirmed(removeConfirmedTag(confirmed, tag))
  }

  const handleAddTag = () => {
    const newConfirmed = addConfirmedTag(confirmed, input)
    if (newConfirmed !== confirmed) {
      setConfirmed(newConfirmed)
      setInput('')
    }
  }

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddTag()
    }
  }

  const handleNext = () => {
    setError(null)
    if (pendingTagNextAction(input, confirmed) === 'prompt') {
      // Non-empty, non-duplicate text in the input → ask the user
      setShowPendingPrompt(true)
      return
    }
    // Empty or duplicate input → clear silently and advance
    if (input.trim()) setInput('')
    patchMutation.mutate(confirmed)
  }

  // "Add & continue" — add the pending text then advance
  const handleAddAndContinue = () => {
    const newConfirmed = addConfirmedTag(confirmed, input)
    setConfirmed(newConfirmed)
    setInput('')
    setShowPendingPrompt(false)
    setError(null)
    patchMutation.mutate(newConfirmed)
  }

  // "Discard & continue" — clear the input text and advance without adding
  const handleDiscardAndContinue = () => {
    setInput('')
    setShowPendingPrompt(false)
    setError(null)
    patchMutation.mutate(confirmed)
  }

  const noTagProvider = tagProviderAvailable === false

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Confirmed tags */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <span style={{ ...SECTION_LABEL, marginBottom: 0 }}>Confirmed Tags</span>
          <button
            type="button"
            disabled={suggestTagsMutation.isPending || noTagProvider}
            title={noTagProvider ? 'No AI provider configured' : 'Get tag suggestions from AI'}
            onClick={() => {
              setTagAiStatus(null)
              suggestTagsMutation.mutate()
            }}
            style={{
              ...AURORA_BTN_GHOST_SM,
              opacity: suggestTagsMutation.isPending || noTagProvider ? 0.4 : 1,
              cursor: suggestTagsMutation.isPending || noTagProvider ? 'not-allowed' : 'pointer',
            }}
            onMouseEnter={(e) => { if (!suggestTagsMutation.isPending && !noTagProvider) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            ✦ {suggestTagsMutation.isPending ? 'Suggesting…' : 'Suggest tags (AI)'}
          </button>
          {noTagProvider && (
            <span style={{ fontSize: 11, color: 'var(--aurora-muted)' }}>No AI configured</span>
          )}
          {tagAiStatus && (
            <span style={{ fontSize: 11, color: 'var(--aurora-danger)' }}>{tagAiStatus}</span>
          )}
        </div>

        {confirmed.length === 0 ? (
          <div>
            <p style={{ fontSize: 13, color: 'var(--aurora-muted)', fontStyle: 'italic', margin: '0 0 4px' }}>
              No tags yet.
            </p>
            <p style={{ fontSize: 11, color: '#D97706', margin: 0 }}>
              Tip: add at least one tag to make this item discoverable.
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {confirmed.map((tag) => (
              <span
                key={tag}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  background: 'var(--aurora-pill)',
                  border: '1px solid var(--aurora-pill-border)',
                  borderRadius: 20,
                  padding: '4px 12px 4px 10px',
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--aurora-accent)',
                }}
              >
                #{tag}
                <button
                  type="button"
                  onClick={() => handleRemoveConfirmed(tag)}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    cursor: 'pointer',
                    color: 'var(--aurora-accent)',
                    lineHeight: 1,
                    fontSize: 13,
                    display: 'flex',
                    alignItems: 'center',
                    opacity: 0.7,
                    transition: 'opacity 0.15s',
                  }}
                  aria-label={`Remove tag ${tag}`}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.7' }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* AI tag suggestions card — click-to-add; chips disappear once added */}
      {(() => {
        if (!aiTagSuggestions || !aiTagSuggestions.provider_available || aiTagSuggestions.error) return null
        const unconfirmedCanonical = aiTagSuggestions.canonical.filter((t) => !confirmed.includes(t))
        const unconfirmedNew = aiTagSuggestions.new_suggestions.filter((t) => !confirmed.includes(t))
        if (unconfirmedCanonical.length === 0 && unconfirmedNew.length === 0) return null

        const addSuggestion = (tag: string) => setConfirmed((c) => addConfirmedTag(c, tag))
        const addAllCanonical = () => {
          setConfirmed((c) => unconfirmedCanonical.reduce((acc, t) => addConfirmedTag(acc, t), c))
        }
        const addAllNew = () => {
          setConfirmed((c) => unconfirmedNew.reduce((acc, t) => addConfirmedTag(acc, t), c))
        }

        const chipBase: React.CSSProperties = {
          display: 'inline-flex',
          alignItems: 'center',
          borderRadius: 20,
          padding: '4px 12px',
          fontSize: 11,
          fontWeight: 600,
          cursor: 'pointer',
          transition: 'all 0.15s',
          userSelect: 'none',
        }

        return (
          <div
            style={{
              background: 'var(--aurora-glass)',
              border: '1px solid var(--aurora-glass-border)',
              borderRadius: 10,
              padding: '14px 16px',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={SECTION_LABEL}>AI Tag Suggestions — click a chip to add</span>
              <button
                type="button"
                onClick={() => setAiTagSuggestions(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 11,
                  color: 'var(--aurora-muted)',
                  padding: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  transition: 'color 0.15s',
                }}
                aria-label="Dismiss AI suggestions"
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
              >
                ✕ Dismiss
              </button>
            </div>

            {unconfirmedCanonical.length > 0 && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
                    Matches your tags:
                  </p>
                  {unconfirmedCanonical.length > 1 && (
                    <button
                      type="button"
                      onClick={addAllCanonical}
                      style={{
                        ...AURORA_BTN_GHOST_SM,
                        fontSize: 10,
                        padding: '2px 10px',
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
                    >
                      Add all
                    </button>
                  )}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {unconfirmedCanonical.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => addSuggestion(tag)}
                      title={`Add tag "${tag}"`}
                      style={{
                        ...chipBase,
                        background: 'rgba(15,164,171,0.08)',
                        border: '1px solid var(--aurora-pill-border)',
                        color: 'var(--aurora-accent)',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'rgba(15,164,171,0.18)'
                        ;(e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 0 2px var(--aurora-pill-border)'
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'rgba(15,164,171,0.08)'
                        ;(e.currentTarget as HTMLButtonElement).style.boxShadow = 'none'
                      }}
                    >
                      + #{tag}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {unconfirmedNew.length > 0 && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
                    New suggestions:
                  </p>
                  {unconfirmedNew.length > 1 && (
                    <button
                      type="button"
                      onClick={addAllNew}
                      style={{
                        ...AURORA_BTN_GHOST_SM,
                        fontSize: 10,
                        padding: '2px 10px',
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
                    >
                      Add all
                    </button>
                  )}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {unconfirmedNew.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => addSuggestion(tag)}
                      title={`Add tag "${tag}"`}
                      style={{
                        ...chipBase,
                        background: 'var(--aurora-glass)',
                        border: '1px dashed var(--aurora-glass-border)',
                        color: 'var(--aurora-text-dim)',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)'
                        ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-muted)'
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)'
                        ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--aurora-glass-border)'
                      }}
                    >
                      + #{tag}
                    </button>
                  ))}
                </div>
                <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: '8px 0 0', lineHeight: 1.5 }}>
                  Added now — your item gets tagged immediately. New tags are
                  reviewed by an admin before joining the global tag cloud.
                </p>
              </div>
            )}
          </div>
        )
      })()}

      {/* Pending / suggested tags from session reconciliation */}
      {pending.length > 0 && (
        <div>
          <span style={SECTION_LABEL}>Suggested tags (not yet in the catalog — accept or skip)</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {pending.map((tag) => (
              <span
                key={tag}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  background: 'var(--aurora-glass)',
                  border: '1px dashed var(--aurora-glass-border)',
                  borderRadius: 20,
                  padding: '4px 10px',
                  fontSize: 12,
                  color: 'var(--aurora-text-dim)',
                }}
              >
                #{tag}
                <button
                  type="button"
                  onClick={() => handleAccept(tag)}
                  title="Accept"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#16A34A', fontSize: 14, padding: 0, lineHeight: 1, display: 'flex' }}
                >
                  ✓
                </button>
                <button
                  type="button"
                  onClick={() => handleReject(tag)}
                  title="Reject"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--aurora-danger)', fontSize: 13, padding: 0, lineHeight: 1, display: 'flex' }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Manual tag input */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="Add a tag and press Enter"
          style={{ ...AURORA_INPUT, flex: 1 }}
          onFocus={onAuroraFocus}
          onBlur={onAuroraBlur}
        />
        <button
          type="button"
          onClick={handleAddTag}
          disabled={!input.trim()}
          style={{
            ...AURORA_BTN_GHOST,
            opacity: !input.trim() ? 0.4 : 1,
            cursor: !input.trim() ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => { if (input.trim()) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          Add
        </button>
      </div>

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      {/* Pending-tag confirmation prompt — shown when user clicks Next with unadded text */}
      {showPendingPrompt && (
        <div
          role="alertdialog"
          aria-label="Unadded tag confirmation"
          style={{
            background: 'rgba(15, 164, 171, 0.06)',
            border: '1px solid var(--aurora-pill-border)',
            borderRadius: 10,
            padding: '14px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          <p style={{ fontSize: 13, color: 'var(--aurora-text)', margin: 0 }}>
            You typed{' '}
            <strong style={{ color: 'var(--aurora-accent)' }}>"{input.trim()}"</strong>
            {' '}but haven't added it yet. What would you like to do?
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <button
              ref={addAndContinueBtnRef}
              type="button"
              disabled={patchMutation.isPending}
              onClick={handleAddAndContinue}
              style={{
                ...AURORA_BTN_PRIMARY,
                opacity: patchMutation.isPending ? 0.6 : 1,
              }}
              onMouseEnter={(e) => { if (!patchMutation.isPending) (e.currentTarget as HTMLButtonElement).style.opacity = '0.85' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = patchMutation.isPending ? '0.6' : '1' }}
            >
              {patchMutation.isPending ? 'Saving…' : 'Add & continue'}
            </button>
            <button
              type="button"
              disabled={patchMutation.isPending}
              onClick={handleDiscardAndContinue}
              style={{
                ...AURORA_BTN_GHOST,
                opacity: patchMutation.isPending ? 0.5 : 1,
                cursor: patchMutation.isPending ? 'not-allowed' : 'pointer',
              }}
              onMouseEnter={(e) => { if (!patchMutation.isPending) (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
            >
              Discard & continue
            </button>
            <button
              type="button"
              onClick={() => setShowPendingPrompt(false)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--aurora-muted)',
                fontSize: 13,
                cursor: 'pointer',
                padding: '4px 0',
                textDecoration: 'underline',
                transition: 'color 0.15s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-text)' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--aurora-muted)' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Normal nav buttons — hidden while the pending-tag prompt is showing */}
      {!showPendingPrompt && (
        <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4 }}>
          <button
            type="button"
            onClick={onPrev}
            style={AURORA_BTN_GHOST}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            ← Back
          </button>
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
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 4: Creator
// ---------------------------------------------------------------------------

interface CreatorStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

function CreatorStep({ session, onNext, onPrev }: CreatorStepProps) {
  const queryClient = useQueryClient()
  const [ownDesign, setOwnDesign] = useState(session.creator_is_own_design)
  const [creatorName, setCreatorName] = useState(session.creator_name ?? '')
  const [profileUrl, setProfileUrl] = useState(session.creator_profile_url ?? '')
  const [error, setError] = useState<string | null>(null)

  const patchMutation = useMutation({
    mutationFn: () =>
      api.patchImportSession(session.id, {
        creator_is_own_design: ownDesign,
        creator_name: ownDesign ? null : creatorName.trim() || null,
        creator_profile_url: ownDesign ? null : profileUrl.trim() || null,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['import-session', session.id], updated)
      onNext()
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : 'Failed to save creator.'),
  })

  const handleNext = () => {
    setError(null)
    patchMutation.mutate()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Own design toggle — aurora interactive card */}
      <label
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          background: ownDesign ? 'var(--aurora-pill)' : 'var(--aurora-glass)',
          border: `1px solid ${ownDesign ? 'var(--aurora-pill-border)' : 'var(--aurora-glass-border)'}`,
          borderRadius: 10,
          padding: '14px 16px',
          cursor: 'pointer',
          transition: 'all 0.2s',
          boxShadow: ownDesign ? 'var(--aurora-glow)' : 'none',
        }}
      >
        <input
          type="checkbox"
          checked={ownDesign}
          onChange={(e) => setOwnDesign(e.target.checked)}
          style={{ accentColor: 'var(--aurora-accent)', width: 16, height: 16, cursor: 'pointer', flexShrink: 0 }}
        />
        <div>
          <p style={{ fontSize: 14, fontWeight: 600, color: ownDesign ? 'var(--aurora-accent)' : 'var(--aurora-text)', margin: '0 0 2px', transition: 'color 0.2s' }}>
            This is my own design
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            Links this item to your account in "My Creations"
          </p>
        </div>
      </label>

      {/* Attribution fields */}
      {!ownDesign && (
        <div
          style={{
            background: 'var(--aurora-glass)',
            border: '1px solid var(--aurora-glass-border)',
            borderRadius: 10,
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          <span style={SECTION_LABEL}>Attributed to a creator</span>

          <div>
            <label style={SECTION_LABEL}>Designer name</label>
            <input
              type="text"
              value={creatorName}
              onChange={(e) => setCreatorName(e.target.value)}
              placeholder="Creator name"
              style={AURORA_INPUT}
              onFocus={onAuroraFocus}
              onBlur={onAuroraBlur}
            />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <label style={{ ...SECTION_LABEL, marginBottom: 0 }}>Profile URL</label>
              <span style={{ fontSize: 10, color: 'var(--aurora-muted)' }}>optional</span>
            </div>
            <input
              type="url"
              value={profileUrl}
              onChange={(e) => setProfileUrl(e.target.value)}
              placeholder="https://…"
              style={AURORA_INPUT}
              onFocus={onAuroraFocus}
              onBlur={onAuroraBlur}
            />
            {profileUrl && (
              <a
                href={profileUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: 'block', marginTop: 4, fontSize: 11, color: 'var(--aurora-accent)', textDecoration: 'none' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
              >
                Open profile ↗
              </a>
            )}
          </div>
        </div>
      )}

      {error && (
        <p style={{ fontSize: 13, color: 'var(--aurora-danger)', margin: 0 }}>{error}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4 }}>
        <button
          type="button"
          onClick={onPrev}
          style={AURORA_BTN_GHOST}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
        >
          ← Back
        </button>
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

// ---------------------------------------------------------------------------
// Step 5: Summary + Commit
// ---------------------------------------------------------------------------

interface SummaryStepProps {
  session: api.ImportSession
  onPrev: () => void
  onCancelled: () => void
}

function SummaryStep({ session, onPrev, onCancelled }: SummaryStepProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [commitError, setCommitError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)

  const commitMutation = useMutation({
    mutationFn: () => api.commitImportSession(session.id),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['import-session', session.id] })
      navigate(`/items/${result.item_key}`)
    },
    onError: (err) =>
      setCommitError(err instanceof Error ? err.message : 'Commit failed.'),
  })

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelImportSession(session.id),
    onSuccess: () => {
      onCancelled()
      navigate('/catalog')
    },
  })

  const handleCancel = () => {
    if (!window.confirm('Discard this import session?')) return
    setCancelling(true)
    cancelMutation.mutate()
  }

  const confirmed = session.tag_state?.confirmed ?? []
  const title = session.confirmed_title ?? session.suggested_title ?? '—'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* Summary table */}
      <div style={{ ...AURORA_CARD, overflow: 'hidden' }}>
        <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
          <tbody>
            <SummaryRow label="Title" value={title} />
            <SummaryRow
              label="Creator"
              value={
                session.creator_is_own_design
                  ? 'My own design'
                  : session.creator_name ?? '—'
              }
            />
            <SummaryRow
              label="Tags"
              value={confirmed.length ? confirmed.join(', ') : '—'}
            />
            <SummaryRow
              label="Library"
              value={session.library_id != null ? `ID ${session.library_id}` : '—'}
            />
            <SummaryRow
              label="Source"
              value={session.source_url ?? '—'}
              isLink={!!session.source_url}
              href={session.source_url ?? undefined}
            />
            <SummaryRow
              label="Images"
              value={`${session.images.length} image(s)`}
            />
          </tbody>
        </table>
      </div>

      {/* No library warning */}
      {!session.library_id && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: 'rgba(245,158,11,0.08)',
            border: '1px solid rgba(245,158,11,0.25)',
            borderRadius: 8,
            padding: '10px 14px',
          }}
        >
          <span style={{ fontSize: 13, color: '#D97706' }}>
            ⚠ No library selected. Go back to the Title step to set one.
          </span>
        </div>
      )}

      {/* Commit error */}
      {commitError && (
        <div
          style={{
            background: 'rgba(220,38,38,0.08)',
            border: '1px solid rgba(220,38,38,0.25)',
            borderRadius: 10,
            padding: '12px 16px',
          }}
        >
          <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-danger)', margin: '0 0 4px' }}>
            Commit failed: {commitError}
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            Your session data is preserved — fix the issue and try again.
          </p>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <button
          type="button"
          disabled={cancelling}
          onClick={handleCancel}
          style={{
            background: 'transparent',
            border: '1px solid rgba(220,38,38,0.35)',
            borderRadius: 20,
            color: 'var(--aurora-danger)',
            fontSize: 13,
            padding: '7px 18px',
            cursor: 'pointer',
            opacity: cancelling ? 0.5 : 1,
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => { if (!cancelling) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(220,38,38,0.06)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
        >
          {cancelling ? 'Cancelling…' : 'Cancel Import'}
        </button>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            type="button"
            onClick={onPrev}
            style={AURORA_BTN_GHOST}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass-hover)' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = 'var(--aurora-glass)' }}
          >
            ← Back
          </button>
          <button
            type="button"
            disabled={commitMutation.isPending || !session.library_id}
            onClick={() => { setCommitError(null); commitMutation.mutate() }}
            style={{
              background: '#16A34A',
              border: 'none',
              borderRadius: 20,
              color: '#FFFFFF',
              fontSize: 13,
              fontWeight: 700,
              padding: '8px 24px',
              cursor: commitMutation.isPending || !session.library_id ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 14px rgba(22,163,74,0.28)',
              transition: 'opacity 0.15s',
              opacity: commitMutation.isPending || !session.library_id ? 0.5 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
            onMouseEnter={(e) => {
              if (!commitMutation.isPending && session.library_id)
                (e.currentTarget as HTMLButtonElement).style.opacity = '0.85'
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.opacity =
                commitMutation.isPending || !session.library_id ? '0.5' : '1'
            }}
          >
            {commitMutation.isPending ? 'Committing…' : 'Commit to Library →'}
          </button>
        </div>
      </div>
    </div>
  )
}

function SummaryRow({
  label,
  value,
  isLink,
  href,
}: {
  label: string
  value: string
  isLink?: boolean
  href?: string
}) {
  return (
    <tr style={{ borderBottom: '1px solid var(--aurora-divider)' }}>
      <td
        style={{
          width: 100,
          padding: '10px 16px',
          fontSize: 10,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: 'var(--aurora-muted)',
          verticalAlign: 'top',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </td>
      <td style={{ padding: '10px 16px', color: 'var(--aurora-text)', wordBreak: 'break-word', fontSize: 13 }}>
        {isLink && href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--aurora-accent)', textDecoration: 'none' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
          >
            {value}
          </a>
        ) : (
          <span>{value}</span>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Processing overlay
// ---------------------------------------------------------------------------

function ProcessingOverlay({ sessionId }: { sessionId: string }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 18,
        padding: '60px 24px',
      }}
    >
      {/* Aurora spinner */}
      <div
        className="animate-spin"
        style={{
          width: 44,
          height: 44,
          borderRadius: '50%',
          border: '3px solid var(--aurora-glass)',
          borderTopColor: 'var(--aurora-accent)',
          boxShadow: '0 0 20px var(--aurora-accent-glow)',
        }}
      />
      <div style={{ textAlign: 'center' }}>
        <p style={{ fontSize: 15, fontWeight: 700, color: 'var(--aurora-text)', margin: '0 0 6px' }}>
          Processing your import…
        </p>
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: '0 0 8px' }}>
          Scraping metadata and reconciling tags. This usually takes a few seconds.
        </p>
        <p style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--aurora-muted)', margin: 0 }}>
          Session {sessionId.slice(0, 8)}…
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ImportWizardPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [step, setStep] = useState<WizardStep>('title')

  const { data: session, isLoading, isError, error } = useQuery({
    queryKey: ['import-session', sessionId],
    queryFn: () => api.getImportSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && isProcessing(data.status)) return 3_000
      return false
    },
  })

  // Advance automatically from processing → pending_wizard
  useEffect(() => {
    if (session && !isProcessing(session.status) && step === 'title') {
      // Ensure we stay on title when first arriving from processing state
    }
  }, [session, step])

  if (!sessionId) {
    return <p style={{ color: 'var(--aurora-danger)', fontSize: 13 }}>No session ID in URL.</p>
  }

  if (isLoading) {
    return (
      <div style={{ padding: '48px 0', textAlign: 'center', fontSize: 13, color: 'var(--aurora-muted)' }}>
        Loading…
      </div>
    )
  }

  if (isError || !session) {
    return (
      <p style={{ color: 'var(--aurora-danger)', fontSize: 13 }}>
        {error instanceof Error ? error.message : 'Failed to load session.'}
      </p>
    )
  }

  // Terminal states
  if (session.status === 'committed') {
    return (
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <div
          style={{
            ...AURORA_CARD,
            padding: '48px 24px',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 14,
          }}
        >
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              background: 'rgba(22,163,74,0.15)',
              border: '1px solid rgba(22,163,74,0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Check size={22} style={{ color: '#16A34A' }} />
          </div>
          <div>
            <p style={{ fontSize: 16, fontWeight: 700, color: 'var(--aurora-text)', margin: '0 0 8px' }}>
              This session has already been committed.
            </p>
            <a
              href="/catalog"
              style={{ color: 'var(--aurora-accent)', fontSize: 13, textDecoration: 'none' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
            >
              Browse catalog →
            </a>
          </div>
        </div>
      </div>
    )
  }

  if (session.status === 'cancelled') {
    return (
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <div
          style={{
            ...AURORA_CARD,
            padding: '48px 24px',
            textAlign: 'center',
          }}
        >
          <p style={{ fontSize: 14, color: 'var(--aurora-muted)', margin: '0 0 10px' }}>
            This import session was cancelled.
          </p>
          <a
            href="/catalog"
            style={{ color: 'var(--aurora-accent)', fontSize: 13, textDecoration: 'none' }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'underline' }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.textDecoration = 'none' }}
          >
            Back to catalog →
          </a>
        </div>
      </div>
    )
  }

  const editable = isEditable(session.status)
  const processing = isProcessing(session.status)

  return (
    <div
      style={{
        maxWidth: 640,
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        color: 'var(--aurora-text)',
      }}
    >
      {/* Page header */}
      <div>
        <h1
          style={{
            fontSize: 22,
            fontWeight: 800,
            color: 'var(--aurora-text)',
            letterSpacing: '-0.02em',
            margin: '0 0 4px',
          }}
        >
          Import Wizard
        </h1>
        <p style={{ fontSize: 12, color: 'var(--aurora-muted)', margin: 0 }}>
          Review and finalize your import before adding it to the library.
        </p>
      </div>

      {/* Error banner for failed sessions */}
      {session.status === 'failed' && session.error && (
        <div
          style={{
            background: 'rgba(220,38,38,0.08)',
            border: '1px solid rgba(220,38,38,0.25)',
            borderRadius: 10,
            padding: '12px 16px',
          }}
        >
          <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--aurora-danger)', margin: '0 0 4px' }}>
            Import processing failed
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-danger)', fontFamily: 'monospace', margin: '0 0 4px' }}>
            {session.error}
          </p>
          <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
            You can still edit the fields below and commit manually.
          </p>
        </div>
      )}

      {/* Processing spinner */}
      {processing ? (
        <div style={AURORA_CARD}>
          <ProcessingOverlay sessionId={session.id} />
        </div>
      ) : !editable ? null : (
        /* Wizard card */
        <div style={{ ...AURORA_CARD, padding: '28px 24px' }}>
          {/* Stepper */}
          <div style={{ marginBottom: 28 }}>
            <StepProgress current={step} />
          </div>

          {/* Step content */}
          {step === 'title' && (
            <TitleStep
              session={session}
              onNext={() => setStep(nextStep(step))}
            />
          )}
          {step === 'images' && (
            <ImagesStep
              session={session}
              onNext={() => setStep(nextStep(step))}
              onPrev={() => setStep(prevStep(step))}
            />
          )}
          {step === 'tags' && (
            <TagsStep
              session={session}
              onNext={() => setStep(nextStep(step))}
              onPrev={() => setStep(prevStep(step))}
            />
          )}
          {step === 'creator' && (
            <CreatorStep
              session={session}
              onNext={() => setStep(nextStep(step))}
              onPrev={() => setStep(prevStep(step))}
            />
          )}
          {step === 'summary' && (
            <SummaryStep
              session={session}
              onPrev={() => setStep(prevStep(step))}
              onCancelled={() => {}}
            />
          )}
        </div>
      )}
    </div>
  )
}
