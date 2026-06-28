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
 */

import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  isProcessing,
  isEditable,
  extractDomain,
} from '@/lib/import-utils'

// ---------------------------------------------------------------------------
// Progress indicator
// ---------------------------------------------------------------------------

function StepProgress({
  current,
}: {
  current: WizardStep
}) {
  const idx = stepIndex(current)
  return (
    <div className="flex items-center gap-1">
      {WIZARD_STEPS.map((step, i) => (
        <React.Fragment key={step}>
          <div
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors ${
              i < idx
                ? 'bg-primary text-primary-foreground'
                : i === idx
                  ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
                  : 'bg-muted text-muted-foreground'
            }`}
          >
            {i < idx ? (
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4">
                <path fillRule="evenodd" d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207Z" clipRule="evenodd" />
              </svg>
            ) : (
              i + 1
            )}
          </div>
          {i < WIZARD_STEPS.length - 1 && (
            <div
              className={`h-0.5 flex-1 transition-colors ${i < idx ? 'bg-primary' : 'bg-muted'}`}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Site-setup banner (shown on Title step when site needs a token)
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
    mutationFn: () =>
      api.patchSiteCapability(domain, { token: token.trim() }),
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
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-600/40 dark:bg-amber-900/20">
      {cap.is_manual_only && (
        <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
          This site requires manual file upload — automatic downloading is not supported.
          Please upload the files yourself in the previous step.
        </p>
      )}
      {cap.requires_token && !cap.has_token && (
        <div className="mt-2 space-y-2">
          <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
            This site requires an API token to import files automatically.
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your API token here"
              className="input-base flex-1 text-sm"
            />
            <button
              type="button"
              disabled={patchMutation.isPending || !token.trim()}
              onClick={() => { setError(null); setSaved(false); patchMutation.mutate() }}
              className="rounded-md bg-amber-600 px-3 py-1 text-sm text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {patchMutation.isPending ? 'Saving…' : 'Save Token'}
            </button>
          </div>
          {saved && (
            <p className="text-xs text-green-700 dark:text-green-400">Token saved.</p>
          )}
          {error && (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          )}
        </div>
      )}
      {cap.requires_token && cap.has_token && (
        <p className="text-sm text-amber-800 dark:text-amber-200">
          Token is configured for this site.{' '}
          <span className="text-xs text-muted-foreground">
            (Session: {sessionId.slice(0, 8)}…)
          </span>
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared: AI text preview panel (cleanup / summarize result)
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
    <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        AI suggestion — preview
      </p>
      <p className="text-sm whitespace-pre-wrap">{text}</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onUse}
          className="rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground hover:opacity-90 transition-colors"
        >
          Use this
        </button>
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-md border border-border px-3 py-1 text-xs hover:bg-accent transition-colors"
        >
          Discard
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 1: Title (+ description editing + AI description assistance)
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

  // AI-assist state: null = unknown (optimistic), false = no provider, true = available
  const [providerAvailable, setProviderAvailable] = useState<boolean | null>(null)
  // Pending AI suggestion — null until user triggers a button, then set to text
  const [aiDescText, setAiDescText] = useState<string | null>(null)
  const [aiStatus, setAiStatus] = useState<string | null>(null)

  const domain = session.source_url ? extractDomain(session.source_url) : null

  const { data: siteCap } = useQuery({
    queryKey: ['site-cap', domain],
    queryFn: () => api.getSiteCapability(domain!),
    enabled: domain != null,
    retry: false,
  })

  // Probe AI availability once on mount (only when there is something to process)
  useEffect(() => {
    if (!session.description?.trim()) return
    api
      .aiCleanupDescription(session.id)
      .then((r) => setProviderAvailable(r.provider_available))
      .catch(() => {}) // network error → leave as null (buttons stay enabled)
    // Intentionally fire once on mount only; session.id stable for a given route.
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
    <div className="space-y-4">
      {/* Title */}
      <div>
        <label className="mb-1 block text-sm font-medium">Title</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="input-base w-full text-base"
          placeholder="Item title"
          autoFocus
        />
        {session.suggested_title && title !== session.suggested_title && (
          <button
            type="button"
            className="mt-1 text-xs text-muted-foreground hover:text-primary underline"
            onClick={() => setTitle(session.suggested_title!)}
          >
            Reset to suggested: "{session.suggested_title}"
          </button>
        )}
      </div>

      {/* Description */}
      <div>
        <label className="mb-1 block text-sm font-medium">
          Description{' '}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          className="input-base w-full resize-y text-sm"
          placeholder="Describe this item…"
        />

        {/* AI description buttons — only shown when there is text to process */}
        {description.trim() && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={aiPending || noProvider}
              title={noProvider ? 'No AI provider configured' : undefined}
              onClick={() => {
                setAiStatus(null)
                setAiDescText(null)
                cleanupMutation.mutate()
              }}
              className="rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
            >
              {cleanupMutation.isPending ? 'Cleaning…' : 'Clean up (AI)'}
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
              className="rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
            >
              {summarizeMutation.isPending ? 'Summarizing…' : 'Summarize scrape (AI)'}
            </button>
            {noProvider && (
              <span className="text-xs text-muted-foreground/70">
                No AI provider configured
              </span>
            )}
            {aiStatus && (
              <span className="text-xs text-red-600 dark:text-red-400">
                {aiStatus}
              </span>
            )}
          </div>
        )}

        {/* AI text preview */}
        {aiDescText && (
          <div className="mt-2">
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

      {session.source_url && (
        <p className="text-sm text-muted-foreground">
          Source:{' '}
          <a
            href={session.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline break-all"
          >
            {session.source_url}
          </a>
        </p>
      )}

      {domain && siteCap && (
        <SiteSetupBanner
          domain={domain}
          cap={siteCap}
          sessionId={session.id}
        />
      )}

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          disabled={patchMutation.isPending}
          onClick={handleNext}
          className="rounded-md bg-primary px-5 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
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
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {session.images.length === 0
          ? 'No images yet. You can upload some below.'
          : `${session.images.length} image(s). Click "Set as default" to choose the cover image.`}
      </p>

      {/* Horizontal scrollable strip */}
      {session.images.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {[...session.images]
            .sort((a, b) => a.order - b.order)
            .map((img) => (
              <div key={img.id} className="relative shrink-0">
                <div
                  className={`h-40 w-40 overflow-hidden rounded-lg border-2 transition-colors ${
                    img.is_default ? 'border-primary' : 'border-border'
                  }`}
                >
                  {img.is_url ? (
                    <img
                      src={img.path}
                      alt=""
                      className="h-full w-full object-cover"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  ) : (
                    /* Local staged files have no public API endpoint until committed */
                    <div className="flex h-full w-full items-center justify-center bg-muted/50 text-center">
                      <span className="px-2 text-[10px] text-muted-foreground leading-tight">
                        {img.path.split('/').pop()}
                        <br />
                        (preview after commit)
                      </span>
                    </div>
                  )}
                </div>
                {img.is_default && (
                  <span className="absolute left-1 top-1 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
                    Default
                  </span>
                )}
                {!img.is_default && (
                  <button
                    type="button"
                    disabled={setDefaultMutation.isPending}
                    onClick={() => { setError(null); setDefaultMutation.mutate(img.path) }}
                    className="mt-1 w-full rounded text-center text-xs text-muted-foreground hover:text-primary underline disabled:opacity-50"
                  >
                    Set as default
                  </button>
                )}
              </div>
            ))}
        </div>
      )}

      {/* Upload additional images */}
      <div>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors disabled:opacity-50"
        >
          {uploadMutation.isPending ? 'Uploading…' : '+ Upload Images'}
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
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex justify-between">
        <button
          type="button"
          onClick={onPrev}
          className="rounded-md border border-border px-5 py-2 text-sm hover:bg-accent"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={onNext}
          className="rounded-md bg-primary px-5 py-2 text-sm text-primary-foreground hover:opacity-90"
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

  // AI tag suggestion state
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
      if (!result.provider_available) return // button will now show disabled
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
    patchMutation.mutate(confirmed)
  }

  const noTagProvider = tagProviderAvailable === false

  return (
    <div className="space-y-4">
      {/* Confirmed tags */}
      <div>
        <div className="mb-2 flex items-center gap-3">
          <h3 className="text-sm font-medium">Tags</h3>
          {/* AI suggest button */}
          <button
            type="button"
            disabled={suggestTagsMutation.isPending || noTagProvider}
            title={noTagProvider ? 'No AI provider configured' : 'Get tag suggestions from AI'}
            onClick={() => {
              setTagAiStatus(null)
              suggestTagsMutation.mutate()
            }}
            className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
          >
            {suggestTagsMutation.isPending ? 'Suggesting…' : 'Suggest tags (AI)'}
          </button>
          {noTagProvider && (
            <span className="text-xs text-muted-foreground/70">No AI configured</span>
          )}
          {tagAiStatus && (
            <span className="text-xs text-red-600 dark:text-red-400">{tagAiStatus}</span>
          )}
        </div>

        {confirmed.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No tags yet.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {confirmed.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-sm font-medium text-primary"
              >
                {tag}
                <button
                  type="button"
                  onClick={() => handleRemoveConfirmed(tag)}
                  className="hover:opacity-70"
                  aria-label={`Remove tag ${tag}`}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
        {confirmed.length === 0 && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Tip: add at least one tag to make this item discoverable.
          </p>
        )}
      </div>

      {/* AI tag suggestions card */}
      {aiTagSuggestions && aiTagSuggestions.provider_available && !aiTagSuggestions.error && (
        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              AI Tag Suggestions
            </p>
            <button
              type="button"
              onClick={() => setAiTagSuggestions(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
              aria-label="Dismiss AI suggestions"
            >
              ✕ Dismiss
            </button>
          </div>

          {aiTagSuggestions.canonical.length > 0 && (
            <div>
              <p className="mb-1 text-xs text-muted-foreground">
                Matching existing catalog tags:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {aiTagSuggestions.canonical.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2.5 py-0.5 text-xs"
                  >
                    {tag}
                    {!confirmed.includes(tag) && (
                      <button
                        type="button"
                        onClick={() => setConfirmed((c) => addConfirmedTag(c, tag))}
                        title={`Add tag "${tag}"`}
                        className="text-green-600 hover:opacity-80"
                      >
                        +
                      </button>
                    )}
                    {confirmed.includes(tag) && (
                      <span className="text-muted-foreground/60 text-[10px]">✓</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {aiTagSuggestions.new_suggestions.length > 0 && (
            <div>
              <p className="mb-1 text-xs text-muted-foreground">
                New tags (will need admin approval after commit):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {aiTagSuggestions.new_suggestions.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-full border border-dashed border-border bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                  >
                    {tag}
                    {!confirmed.includes(tag) && (
                      <button
                        type="button"
                        onClick={() => setConfirmed((c) => addConfirmedTag(c, tag))}
                        title={`Add tag "${tag}"`}
                        className="text-green-600 hover:opacity-80"
                      >
                        +
                      </button>
                    )}
                    {confirmed.includes(tag) && (
                      <span className="text-muted-foreground/60 text-[10px]">✓</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Pending / suggested tags */}
      {pending.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-muted-foreground">
            Suggested tags (new — need approval after commit)
          </h3>
          <div className="flex flex-wrap gap-2">
            {pending.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-border bg-muted px-2.5 py-1 text-sm text-muted-foreground"
              >
                {tag}
                <button
                  type="button"
                  onClick={() => handleAccept(tag)}
                  title="Accept"
                  className="text-green-600 hover:opacity-80"
                >
                  ✓
                </button>
                <button
                  type="button"
                  onClick={() => handleReject(tag)}
                  title="Reject"
                  className="text-red-500 hover:opacity-80"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Manual tag input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="Add a tag and press Enter"
          className="input-base flex-1 text-sm"
        />
        <button
          type="button"
          onClick={handleAddTag}
          disabled={!input.trim()}
          className="rounded-md border border-border px-3 py-1 text-sm hover:bg-accent disabled:opacity-40"
        >
          Add
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex justify-between">
        <button
          type="button"
          onClick={onPrev}
          className="rounded-md border border-border px-5 py-2 text-sm hover:bg-accent"
        >
          ← Back
        </button>
        <button
          type="button"
          disabled={patchMutation.isPending}
          onClick={handleNext}
          className="rounded-md bg-primary px-5 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {patchMutation.isPending ? 'Saving…' : 'Next →'}
        </button>
      </div>
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
  const [profileUrl, setProfileUrl] = useState(
    session.creator_profile_url ?? '',
  )
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
    <div className="space-y-4">
      {/* Own design toggle */}
      <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-border p-3 hover:bg-muted/30 transition-colors">
        <input
          type="checkbox"
          checked={ownDesign}
          onChange={(e) => setOwnDesign(e.target.checked)}
          className="h-4 w-4 rounded border-border accent-primary"
        />
        <div>
          <p className="text-sm font-medium">This is my own design</p>
          <p className="text-xs text-muted-foreground">
            Links this item to your account in "My Creations"
          </p>
        </div>
      </label>

      {/* Attribution fields */}
      {!ownDesign && (
        <div className="space-y-3 rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium text-muted-foreground">
            Attributed to a creator
          </h3>
          <div>
            <label className="mb-1 block text-sm font-medium">Designer name</label>
            <input
              type="text"
              value={creatorName}
              onChange={(e) => setCreatorName(e.target.value)}
              placeholder="Creator name"
              className="input-base w-full"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Profile URL{' '}
              <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
              type="url"
              value={profileUrl}
              onChange={(e) => setProfileUrl(e.target.value)}
              placeholder="https://…"
              className="input-base w-full"
            />
            {profileUrl && (
              <a
                href={profileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 block text-xs text-primary hover:underline"
              >
                Open profile ↗
              </a>
            )}
          </div>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex justify-between">
        <button
          type="button"
          onClick={onPrev}
          className="rounded-md border border-border px-5 py-2 text-sm hover:bg-accent"
        >
          ← Back
        </button>
        <button
          type="button"
          disabled={patchMutation.isPending}
          onClick={handleNext}
          className="rounded-md bg-primary px-5 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
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
    <div className="space-y-5">
      <div className="rounded-lg border border-border">
        <table className="w-full text-sm">
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

      {!session.library_id && (
        <p className="text-sm text-amber-600 dark:text-amber-400">
          ⚠ No library selected. Go back to the Title step to set one.
        </p>
      )}

      {commitError && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 dark:border-red-700 dark:bg-red-900/20">
          <p className="text-sm font-medium text-red-700 dark:text-red-300">
            Commit failed: {commitError}
          </p>
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            Your session data is preserved — fix the issue and try again.
          </p>
        </div>
      )}

      <div className="flex justify-between">
        <button
          type="button"
          disabled={cancelling}
          onClick={handleCancel}
          className="rounded-md border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
        >
          {cancelling ? 'Cancelling…' : 'Cancel Import'}
        </button>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onPrev}
            className="rounded-md border border-border px-5 py-2 text-sm hover:bg-accent"
          >
            ← Back
          </button>
          <button
            type="button"
            disabled={commitMutation.isPending || !session.library_id}
            onClick={() => { setCommitError(null); commitMutation.mutate() }}
            className="rounded-md bg-green-600 px-6 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {commitMutation.isPending ? 'Committing…' : 'Commit to Library'}
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
    <tr className="border-b border-border last:border-0">
      <td className="w-32 shrink-0 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </td>
      <td className="px-4 py-3">
        {isLink && href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline break-all"
          >
            {value}
          </a>
        ) : (
          <span className="break-words">{value}</span>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Processing spinner (while status=processing)
// ---------------------------------------------------------------------------

function ProcessingOverlay({ sessionId }: { sessionId: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      <div className="text-center">
        <p className="font-medium">Processing your import…</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Scraping metadata and reconciling tags. This usually takes a few seconds.
        </p>
        <p className="mt-2 font-mono text-xs text-muted-foreground">
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
    // Poll every 3 s while processing
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
    return <p className="text-red-600">No session ID in URL.</p>
  }

  if (isLoading) {
    return <p className="text-muted-foreground text-sm">Loading session…</p>
  }

  if (isError || !session) {
    return (
      <p className="text-red-600">
        {error instanceof Error ? error.message : 'Failed to load session.'}
      </p>
    )
  }

  // Handle terminal / unexpected statuses
  if (session.status === 'committed') {
    return (
      <div className="py-12 text-center">
        <p className="text-lg font-medium text-green-700 dark:text-green-400">
          This session has already been committed.
        </p>
        <a href="/catalog" className="mt-2 block text-primary hover:underline">
          Browse catalog →
        </a>
      </div>
    )
  }

  if (session.status === 'cancelled') {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">This import session was cancelled.</p>
        <a href="/catalog" className="mt-2 block text-primary hover:underline">
          Back to catalog
        </a>
      </div>
    )
  }

  const editable = isEditable(session.status)
  const processing = isProcessing(session.status)

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold">Import Wizard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Review and finalize your import before adding it to the library.
        </p>
      </div>

      {/* Error banner for failed sessions */}
      {session.status === 'failed' && session.error && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 dark:border-red-700 dark:bg-red-900/20">
          <p className="text-sm font-medium text-red-700 dark:text-red-300">
            Import processing failed
          </p>
          <p className="mt-1 text-xs text-red-600 dark:text-red-400 font-mono">
            {session.error}
          </p>
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            You can still edit the fields below and commit manually.
          </p>
        </div>
      )}

      {/* Processing state */}
      {processing ? (
        <ProcessingOverlay sessionId={session.id} />
      ) : !editable ? null : (
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          {/* Step progress */}
          <div className="mb-6 space-y-2">
            <StepProgress current={step} />
            <p className="text-center text-sm font-medium">
              Step {stepIndex(step) + 1} of {WIZARD_STEPS.length}:{' '}
              {STEP_LABELS[step]}
            </p>
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
