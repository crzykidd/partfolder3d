/**
 * TagsStep — Step 3 of the import wizard.
 *
 * Confirmed tags (removable chips) + pending/reconcile chips (accept/reject) +
 * AI tag suggestions (click-to-add box) + typeahead autocomplete +
 * pending-tag-on-Next confirmation prompt.
 */

import { type KeyboardEvent, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'
import {
  acceptPendingTag,
  rejectPendingTag,
  removeConfirmedTag,
  addConfirmedTag,
  pendingTagNextAction,
} from '@/lib/import-utils'
import {
  SECTION_LABEL,
  AURORA_BTN_GHOST_SM,
  AURORA_BTN_PRIMARY,
  AURORA_BTN_GHOST,
  AURORA_INPUT,
  onAuroraFocus,
  onAuroraBlur,
} from './styles'

export interface TagsStepProps {
  session: api.ImportSession
  onNext: () => void
  onPrev: () => void
}

export function TagsStep({ session, onNext, onPrev }: TagsStepProps) {
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

  // Existing catalog tags — an INDEPENDENT query from the AI suggest-tags call.
  // Renders as soon as GET /api/tags resolves so a slow/unconfigured AI provider
  // can never stall this step. AI suggestions (below) layer in asynchronously.
  const existingTagsQuery = useQuery({
    queryKey: ['import-tags-catalog'],
    queryFn: () => api.listTags({ in_use_only: true, per_page: 24 }),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })
  const existingTags = existingTagsQuery.data?.tags ?? []

  // Autocomplete state
  const [acResults, setAcResults] = useState<api.TagSummary[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const acContainerRef = useRef<HTMLDivElement>(null)

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
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setShowPendingPrompt(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [showPendingPrompt])

  // Debounced tag search for autocomplete
  useEffect(() => {
    const trimmed = input.trim()
    if (!trimmed) {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      setAcResults([])
      setDropdownOpen(false)
      setActiveIdx(-1)
      return
    }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      api.listTags({ search: trimmed, per_page: 10 })
        .then((res) => {
          setAcResults(res.tags)
          setDropdownOpen(true)
          setActiveIdx(-1)
        })
        .catch(() => {
          // Best-effort — don't surface network errors in the autocomplete
        })
    }, 200)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input])

  // Close dropdown on click-outside
  useEffect(() => {
    if (!dropdownOpen) return
    const handler = (e: MouseEvent) => {
      if (acContainerRef.current && !acContainerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
        setActiveIdx(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [dropdownOpen])

  // Autocomplete: filter out already-confirmed tags and compute dropdown items
  const filteredAc = acResults.filter((t) => !confirmed.includes(t.name))
  const inputNorm = input.trim().toLowerCase()
  const hasExactMatch = filteredAc.some((t) => t.name.toLowerCase() === inputNorm)
  const showCreateNew = inputNorm.length > 0 && !hasExactMatch
  const totalAcItems = filteredAc.length + (showCreateNew ? 1 : 0)

  // Select an existing tag from the autocomplete dropdown
  const selectExistingTag = (tagName: string) => {
    setConfirmed((c) => addConfirmedTag(c, tagName))
    setInput('')
    setDropdownOpen(false)
    setAcResults([])
    setActiveIdx(-1)
  }

  // Select "Create new tag" from the autocomplete dropdown — same flow as manual Add
  const selectCreateNew = () => {
    const newConfirmed = addConfirmedTag(confirmed, input)
    if (newConfirmed !== confirmed) {
      setConfirmed(newConfirmed)
      setInput('')
    }
    setDropdownOpen(false)
    setAcResults([])
    setActiveIdx(-1)
  }

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

  const handleInputKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    // Autocomplete keyboard navigation (when dropdown is open)
    if (dropdownOpen && totalAcItems > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIdx((i) => Math.min(i + 1, totalAcItems - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIdx((i) => Math.max(i - 1, -1))
        return
      }
      if (e.key === 'Enter' && activeIdx >= 0) {
        e.preventDefault()
        if (activeIdx < filteredAc.length) {
          selectExistingTag(filteredAc[activeIdx].name)
        } else {
          selectCreateNew()
        }
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setDropdownOpen(false)
        setActiveIdx(-1)
        return
      }
    }
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

      {/* Existing catalog tags — independent of AI; renders as soon as
          listTags resolves, so the step is fully usable without an AI provider. */}
      {(() => {
        if (existingTagsQuery.isLoading) {
          return (
            <p style={{ fontSize: 11, color: 'var(--aurora-muted)', margin: 0 }}>
              Loading existing tags…
            </p>
          )
        }
        const available = existingTags.filter(
          (t) => !confirmed.includes(t.name) && !pending.includes(t.name),
        )
        if (available.length === 0) return null
        return (
          <div>
            <span style={SECTION_LABEL}>Popular tags — click to add</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {available.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setConfirmed((c) => addConfirmedTag(c, t.name))}
                  title={`Add tag "${t.name}"`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    borderRadius: 20,
                    padding: '4px 12px',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                    userSelect: 'none',
                    background: 'rgba(15,164,171,0.08)',
                    border: '1px solid var(--aurora-pill-border)',
                    color: 'var(--aurora-accent)',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(15,164,171,0.18)'
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.background = 'rgba(15,164,171,0.08)'
                  }}
                >
                  + #{t.name}
                </button>
              ))}
            </div>
          </div>
        )
      })()}

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

        const chipBase: import('react').CSSProperties = {
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

      {/* Manual tag input with typeahead autocomplete */}
      <div ref={acContainerRef} style={{ position: 'relative' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Type to search existing tags or add new"
            style={{ ...AURORA_INPUT, flex: 1 }}
            onFocus={onAuroraFocus}
            onBlur={onAuroraBlur}
            aria-autocomplete="list"
            aria-expanded={dropdownOpen && totalAcItems > 0}
            aria-haspopup="listbox"
            role="combobox"
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

        {/* Autocomplete dropdown */}
        {dropdownOpen && totalAcItems > 0 && (
          <div
            role="listbox"
            aria-label="Tag suggestions"
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 40, // stop before the Add button
              zIndex: 100,
              marginTop: 4,
              background: 'var(--aurora-card)',
              border: '1px solid var(--aurora-card-border)',
              borderRadius: 8,
              boxShadow: '0 8px 24px rgba(0,0,0,0.28)',
              overflow: 'hidden',
            }}
          >
            {filteredAc.map((tag, idx) => (
              <div
                key={tag.id}
                role="option"
                aria-selected={idx === activeIdx}
                onMouseDown={(e) => { e.preventDefault(); selectExistingTag(tag.name) }}
                onMouseEnter={() => setActiveIdx(idx)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: 13,
                  color: idx === activeIdx ? 'var(--aurora-accent)' : 'var(--aurora-text)',
                  background: idx === activeIdx ? 'var(--aurora-glass)' : 'transparent',
                  transition: 'background 0.1s',
                  borderBottom: idx < filteredAc.length - 1 || showCreateNew ? '1px solid var(--aurora-glass-border)' : 'none',
                }}
              >
                <span>#{tag.name}</span>
                {tag.item_count > 0 && (
                  <span style={{ fontSize: 11, color: 'var(--aurora-muted)', flexShrink: 0 }}>
                    {tag.item_count} item{tag.item_count !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            ))}
            {showCreateNew && (
              <div
                role="option"
                aria-selected={activeIdx === filteredAc.length}
                onMouseDown={(e) => { e.preventDefault(); selectCreateNew() }}
                onMouseEnter={() => setActiveIdx(filteredAc.length)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 13,
                  color: activeIdx === filteredAc.length ? 'var(--aurora-accent)' : 'var(--aurora-text-dim)',
                  background: activeIdx === filteredAc.length ? 'var(--aurora-glass)' : 'transparent',
                  transition: 'background 0.1s',
                  fontStyle: 'italic',
                }}
              >
                <span>+</span>
                <span>Create new tag: &ldquo;{input.trim()}&rdquo;</span>
              </div>
            )}
          </div>
        )}
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
