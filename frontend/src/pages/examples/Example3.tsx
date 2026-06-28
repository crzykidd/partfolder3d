/**
 * Example 3 — "Aurora" (your highest-polish, most distinctive take)
 *
 * Deep dark gradient canvas, glassmorphic sidebar with backdrop blur, pill-
 * shaped nav items with teal glow, animated group collapse, and a ⌘K command
 * palette overlay.  Light mode: cool frosted glass on a soft gradient.
 *
 * All data is mock — no API calls, no auth context required.
 */

import React, { useState, useEffect, useRef } from 'react'
import {
  LayoutGrid, Tag, Users, Heart, PlusCircle, Inbox, Package, Cpu, Calendar,
  AlertTriangle, GitBranch, Eye, User, Mail, Zap, Settings, Archive, Download,
  Hash, SlidersHorizontal, ChevronDown, Search, Sun, Moon, LogOut, ExternalLink,
  Box, FileText, CheckCircle2, Circle, Star, Activity, Command, ArrowRight,
  type LucideIcon,
} from 'lucide-react'
import {
  MOCK_ITEMS, MOCK_STATS, MOCK_JOBS, MOCK_TAG_CLOUD, MOCK_CREATORS,
  MOCK_VERSION, RELEASES_URL, NAV_GROUPS, canSeeGroup,
  type Role,
} from './mockData'
import { useLocalStorage } from './useLocalStorage'

// ─── Color schemes ────────────────────────────────────────────────────────────

const DARK = {
  rootFrom:       '#050D1C',
  rootTo:         '#081728',
  glass:          'rgba(255,255,255,0.04)',
  glassBorder:    'rgba(255,255,255,0.08)',
  glassHover:     'rgba(255,255,255,0.07)',
  activePill:     'rgba(15,164,171,0.18)',
  activePillBorder:'rgba(15,164,171,0.45)',
  activeGlow:     '0 0 18px rgba(15,164,171,0.28)',
  cardGlass:      'rgba(255,255,255,0.03)',
  cardGlassBorder:'rgba(255,255,255,0.07)',
  cardGlassHover: 'rgba(255,255,255,0.065)',
  overlayBg:      'rgba(5,13,28,0.85)',
  paletteBg:      'rgba(10,20,38,0.97)',
  paletteBorder:  'rgba(255,255,255,0.12)',
  paletteHover:   'rgba(15,164,171,0.12)',
  text:           '#E0EAF4',
  textDim:        '#8BAFC7',
  muted:          '#4A6B84',
  accent:         '#0FA4AB',
  accentFg:       '#FFFFFF',
  accentGlow:     'rgba(15,164,171,0.4)',
  tag:            'rgba(255,255,255,0.06)',
  tagText:        '#7DB8D4',
  tagBorder:      'rgba(255,255,255,0.08)',
  divider:        'rgba(255,255,255,0.07)',
  inputBg:        'rgba(255,255,255,0.06)',
  inputBorder:    'rgba(255,255,255,0.1)',
  success:        '#22C55E',
  warn:           '#F59E0B',
  danger:         '#EF4444',
  stat1:          '#0FA4AB',
  stat2:          '#22C55E',
  stat3:          '#F59E0B',
  stat4:          '#8B5CF6',
  stat5:          '#EC4899',
}

const LIGHT = {
  rootFrom:       '#E8F4F5',
  rootTo:         '#F0F7FF',
  glass:          'rgba(255,255,255,0.72)',
  glassBorder:    'rgba(0,0,0,0.08)',
  glassHover:     'rgba(255,255,255,0.88)',
  activePill:     'rgba(15,164,171,0.1)',
  activePillBorder:'rgba(15,164,171,0.35)',
  activeGlow:     '0 0 16px rgba(15,164,171,0.2)',
  cardGlass:      'rgba(255,255,255,0.75)',
  cardGlassBorder:'rgba(0,0,0,0.07)',
  cardGlassHover: 'rgba(255,255,255,0.92)',
  overlayBg:      'rgba(230,244,245,0.8)',
  paletteBg:      'rgba(255,255,255,0.97)',
  paletteBorder:  'rgba(0,0,0,0.1)',
  paletteHover:   'rgba(15,164,171,0.08)',
  text:           '#0F1E2D',
  textDim:        '#2D4A62',
  muted:          '#7A9EB5',
  accent:         '#0FA4AB',
  accentFg:       '#FFFFFF',
  accentGlow:     'rgba(15,164,171,0.3)',
  tag:            'rgba(15,164,171,0.08)',
  tagText:        '#0c7a80',
  tagBorder:      'rgba(15,164,171,0.2)',
  divider:        'rgba(0,0,0,0.07)',
  inputBg:        'rgba(255,255,255,0.8)',
  inputBorder:    'rgba(0,0,0,0.1)',
  success:        '#16A34A',
  warn:           '#D97706',
  danger:         '#DC2626',
  stat1:          '#0FA4AB',
  stat2:          '#16A34A',
  stat3:          '#D97706',
  stat4:          '#7C3AED',
  stat5:          '#DB2777',
}

type C = typeof DARK

// ─── Icon map ─────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, LucideIcon> = {
  grid:             LayoutGrid,
  tag:              Tag,
  users:            Users,
  heart:            Heart,
  'plus-circle':    PlusCircle,
  inbox:            Inbox,
  package:          Package,
  cpu:              Cpu,
  calendar:         Calendar,
  'alert-triangle': AlertTriangle,
  'git-branch':     GitBranch,
  eye:              Eye,
  user:             User,
  mail:             Mail,
  zap:              Zap,
  settings:         Settings,
  archive:          Archive,
  download:         Download,
  hash:             Hash,
  sliders:          SlidersHorizontal,
}

function NavIcon({ name, size = 14 }: { name: string; size?: number }) {
  const Icon = ICON_MAP[name] ?? Box
  return <Icon size={size} />
}

// ─── Command Palette ──────────────────────────────────────────────────────────

const PALETTE_COMMANDS = [
  { label: 'Catalog',           icon: 'grid',          group: 'Navigate'  },
  { label: 'Tags',              icon: 'tag',           group: 'Navigate'  },
  { label: 'Creators',          icon: 'users',         group: 'Navigate'  },
  { label: 'Favorites',         icon: 'heart',         group: 'Navigate'  },
  { label: 'Add Asset',         icon: 'plus-circle',   group: 'Actions'   },
  { label: 'Import from URL',   icon: 'inbox',         group: 'Actions'   },
  { label: 'Jobs',              icon: 'cpu',           group: 'Ops'       },
  { label: 'Scheduled Jobs',    icon: 'calendar',      group: 'Ops'       },
  { label: 'Pending Tags',      icon: 'hash',          group: 'Admin'     },
  { label: 'AI Providers',      icon: 'zap',           group: 'Admin'     },
  { label: 'Settings',          icon: 'sliders',       group: 'Admin'     },
]

function CommandPalette({ c, onClose }: { c: C; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const filtered = PALETTE_COMMANDS.filter(cmd =>
    !query || cmd.label.toLowerCase().includes(query.toLowerCase()) || cmd.group.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => { setSelected(0) }, [query])

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
    if (e.key === 'Enter')     { onClose() }
    if (e.key === 'Escape')    { onClose() }
  }

  const groups = [...new Set(filtered.map(c => c.group))]

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 999,
      background: c.overlayBg,
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      paddingTop: '14vh',
    } as React.CSSProperties}
      onClick={onClose}
    >
      <div style={{
        background: c.paletteBg,
        border: `1px solid ${c.paletteBorder}`,
        borderRadius: 18,
        width: 560,
        maxHeight: 440,
        overflow: 'hidden',
        boxShadow: `0 24px 60px rgba(0,0,0,0.5), 0 0 0 1px ${c.paletteBorder}, inset 0 1px 0 rgba(255,255,255,0.08)`,
        backdropFilter: 'blur(40px)',
        WebkitBackdropFilter: 'blur(40px)',
      } as React.CSSProperties}
        onClick={e => e.stopPropagation()}
      >
        {/* Search input */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '14px 18px',
          borderBottom: `1px solid ${c.divider}`,
        }}>
          <Search size={16} style={{ color: c.muted, flexShrink: 0 }} />
          <input ref={inputRef} value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Search commands, pages, models…"
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: c.text, fontSize: 15, fontWeight: 400,
            }} />
          <button onClick={onClose}
            style={{ background: 'transparent', border: `1px solid ${c.divider}`, borderRadius: 6, padding: '2px 7px', color: c.muted, fontSize: 11, cursor: 'pointer' }}>
            esc
          </button>
        </div>

        {/* Results */}
        <div style={{ overflowY: 'auto', maxHeight: 340, padding: '8px 0' }}>
          {groups.map(group => {
            const cmds = filtered.filter(cmd => cmd.group === group)
            return (
              <div key={group}>
                <div style={{ padding: '6px 18px 3px', fontSize: 10.5, fontWeight: 700, color: c.muted, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                  {group}
                </div>
                {cmds.map((cmd, i) => {
                  const idx = filtered.indexOf(cmd)
                  const isSel = idx === selected
                  return (
                    <button key={cmd.label} onClick={onClose}
                      onMouseEnter={() => setSelected(i + (idx - cmds.indexOf(cmd)))}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        width: '100%', padding: '9px 18px',
                        background: isSel ? c.paletteHover : 'transparent',
                        border: 'none', cursor: 'pointer',
                        borderLeft: `2px solid ${isSel ? c.accent : 'transparent'}`,
                        transition: 'background 0.08s',
                      }}
                    >
                      <span style={{ color: isSel ? c.accent : c.muted, display: 'flex', flexShrink: 0 }}>
                        <NavIcon name={cmd.icon} size={15} />
                      </span>
                      <span style={{ fontSize: 13.5, color: isSel ? c.text : c.textDim, fontWeight: isSel ? 500 : 400, flex: 1, textAlign: 'left' }}>
                        {cmd.label}
                      </span>
                      {isSel && <ArrowRight size={13} style={{ color: c.accent }} />}
                    </button>
                  )
                })}
              </div>
            )
          })}
          {filtered.length === 0 && (
            <div style={{ padding: '28px 0', textAlign: 'center', color: c.muted, fontSize: 13.5 }}>
              No results for "{query}"
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Import Wizard ────────────────────────────────────────────────────────────

const WIZARD_STEPS = ['Source', 'Configure', 'Preview', 'Import']

function ImportWizard({ c }: { c: C }) {
  const [step, setStep] = useState(1)
  const [importing, setImporting] = useState(false)
  const [done, setDone] = useState(false)

  const startImport = () => {
    setImporting(true)
    setTimeout(() => { setImporting(false); setDone(true) }, 2200)
  }
  const reset = () => { setStep(0); setImporting(false); setDone(false) }

  return (
    <div style={{
      background: c.cardGlass, border: `1px solid ${c.cardGlassBorder}`,
      borderRadius: 14, overflow: 'hidden',
      backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
    } as React.CSSProperties}>
      {/* Steps */}
      <div style={{ padding: '12px 16px', borderBottom: `1px solid ${c.divider}` }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: c.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>Import Wizard</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          {WIZARD_STEPS.map((s, i) => (
            <React.Fragment key={s}>
              <button onClick={() => !importing && !done && setStep(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '3px 8px', borderRadius: 20, border: 'none', cursor: 'pointer',
                  fontSize: 11, fontWeight: i === step ? 700 : 400,
                  background: i === step ? c.activePill : 'transparent',
                  boxShadow: i === step ? c.activeGlow : 'none',
                  color: i === step ? c.accent : i < step ? c.textDim : c.muted,
                  transition: 'all 0.2s',
                  border: `1px solid ${i === step ? c.activePillBorder : 'transparent'}`,
                }}>
                <span style={{
                  width: 16, height: 16, borderRadius: '50%', display: 'inline-flex',
                  alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700,
                  background: i < step || done ? c.accent : i === step ? c.activePill : 'transparent',
                  border: `1.5px solid ${i <= step ? c.accent : c.divider}`,
                  color: i < step || done ? c.accentFg : i === step ? c.accent : c.muted,
                  flexShrink: 0,
                }}>
                  {i < step || done ? '✓' : i + 1}
                </span>
                {s}
              </button>
              {i < WIZARD_STEPS.length - 1 && (
                <div style={{ flex: 1, height: 1, background: c.divider, minWidth: 8 }} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div style={{ padding: 14, minHeight: 140 }}>
        {step === 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {['URL / Thingiverse', 'Local File', 'ZIP Archive', 'Template'].map((src, i) => (
              <button key={src} style={{
                padding: '10px 12px', borderRadius: 10, cursor: 'pointer', fontSize: 12,
                background: i === 0 ? c.activePill : c.glass,
                border: `1px solid ${i === 0 ? c.activePillBorder : c.glassBorder}`,
                boxShadow: i === 0 ? c.activeGlow : 'none',
                color: i === 0 ? c.accent : c.textDim,
                fontWeight: i === 0 ? 600 : 400, textAlign: 'left',
              }}>{src}</button>
            ))}
          </div>
        )}

        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ padding: '7px 10px', background: c.activePill, border: `1px solid ${c.activePillBorder}`, borderRadius: 8, fontSize: 11, color: c.accent, boxShadow: c.activeGlow }}>
              ✦ Scraped from Printables · 4 files · 1 image
            </div>
            {[['Title','Gridfinity Baseplate 2×4 Lite'],['Creator','Zack Freedman'],['Library','Primary Collection']].map(([label, val]) => (
              <div key={label}>
                <div style={{ fontSize: 10, fontWeight: 700, color: c.muted, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</div>
                <div style={{ padding: '7px 10px', border: `1px solid ${c.inputBorder}`, borderRadius: 8, background: c.inputBg, color: c.text, fontSize: 12 }}>{val}</div>
              </div>
            ))}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: c.muted, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Tags</div>
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                {['gridfinity','storage','organizer'].map(t => (
                  <span key={t} style={{ padding: '2px 8px', background: c.tag, color: c.tagText, borderRadius: 20, fontSize: 11, border: `1px solid ${c.tagBorder}` }}>#{t}</span>
                ))}
                {['2x4','lite'].map(t => (
                  <span key={t} style={{ padding: '2px 8px', background: c.activePill, color: c.accent, borderRadius: 20, fontSize: 11, border: `1px dashed ${c.activePillBorder}` }}>#{t} ·pending</span>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div style={{ fontSize: 11, color: c.muted, marginBottom: 8 }}>4 files detected</div>
            {['gridfinity-baseplate-2x4.3mf','gridfinity-baseplate-2x4.stl','gridfinity-baseplate-2x4.step','preview.png'].map(f => (
              <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: `1px solid ${c.divider}`, fontSize: 12, color: c.text }}>
                <FileText size={11} style={{ color: c.muted, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{f}</span>
                <span style={{ fontSize: 10, color: c.muted }}>{f.endsWith('.3mf') ? '1.2 MB' : f.endsWith('.stl') ? '840 KB' : f.endsWith('.step') ? '220 KB' : '48 KB'}</span>
              </div>
            ))}
          </div>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center', padding: '10px 0' }}>
            {done ? (
              <>
                <CheckCircle2 size={30} style={{ color: c.success, margin: '0 auto 8px', display: 'block' }} />
                <div style={{ fontSize: 15, fontWeight: 700, color: c.text }}>Import complete!</div>
                <div style={{ fontSize: 12, color: c.muted, marginTop: 4 }}>4 files added to Primary Collection</div>
                <button onClick={reset} style={{ marginTop: 12, padding: '6px 16px', background: c.activePill, color: c.accent, border: `1px solid ${c.activePillBorder}`, borderRadius: 20, fontSize: 12, cursor: 'pointer', boxShadow: c.activeGlow }}>
                  Import another
                </button>
              </>
            ) : importing ? (
              <>
                <div style={{ fontSize: 12, color: c.muted, marginBottom: 10 }}>Importing 4 files…</div>
                <div style={{ height: 4, background: c.glass, borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '65%', background: `linear-gradient(90deg, ${c.accent}, #17C5CE)`, borderRadius: 2, boxShadow: `0 0 8px ${c.accentGlow}` }} />
                </div>
              </>
            ) : (
              <>
                <Circle size={30} style={{ color: c.muted, margin: '0 auto 8px', display: 'block' }} />
                <div style={{ fontSize: 12, color: c.textDim }}>Ready to import 4 files</div>
                <button onClick={startImport} style={{ marginTop: 12, padding: '8px 22px', background: c.accent, color: c.accentFg, border: 'none', borderRadius: 20, fontSize: 12, fontWeight: 700, cursor: 'pointer', boxShadow: `0 4px 16px ${c.accentGlow}` }}>
                  Start Import
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {!done && (
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '9px 14px', borderTop: `1px solid ${c.divider}` }}>
          <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}
            style={{ padding: '4px 12px', border: `1px solid ${c.glassBorder}`, borderRadius: 20, background: 'transparent', color: step === 0 ? c.muted : c.textDim, fontSize: 12, cursor: step === 0 ? 'default' : 'pointer', opacity: step === 0 ? 0.4 : 1 }}>
            ← Back
          </button>
          {step < WIZARD_STEPS.length - 1 ? (
            <button onClick={() => setStep(s => Math.min(WIZARD_STEPS.length - 1, s + 1))}
              style={{ padding: '4px 14px', background: c.accent, color: c.accentFg, border: 'none', borderRadius: 20, fontSize: 12, fontWeight: 700, cursor: 'pointer', boxShadow: `0 4px 12px ${c.accentGlow}` }}>
              Next →
            </button>
          ) : <span />}
        </div>
      )}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function Example3() {
  const [isDark, setIsDark] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage('ex3-sidebar', false)
  const [collapsedGroups, setCollapsedGroups] = useLocalStorage<string[]>('ex3-groups', [])
  const [role, setRole] = useState<Role>('admin')
  const [activeNav, setActiveNav] = useState('Catalog')
  const [search, setSearch] = useState('')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [activeTab, setActiveTab] = useState<'catalog' | 'jobs' | 'tags'>('catalog')

  const c = isDark ? DARK : LIGHT
  const visibleGroups = NAV_GROUPS.filter(g => canSeeGroup(g, role))

  // ⌘K keyboard shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setPaletteOpen(p => !p)
      }
      if (e.key === 'Escape') setPaletteOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const toggleGroup = (id: string) => {
    setCollapsedGroups(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const filteredItems = MOCK_ITEMS.filter(item =>
    !search || item.title.toLowerCase().includes(search.toLowerCase()) || item.tags.some(t => t.includes(search.toLowerCase()))
  )

  const badgeColors: Record<string, string> = {
    new: '#0FA4AB', rendered: '#22C55E', printing: '#F59E0B', rendering: '#8B5CF6',
  }

  const rootBg = `linear-gradient(145deg, ${c.rootFrom} 0%, ${c.rootTo} 100%)`

  return (
    <div style={{
      display: 'flex', height: '100vh', overflow: 'hidden',
      background: rootBg,
      color: c.text,
      fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
      fontSize: 13,
    }}>
      {/* ── Command palette ── */}
      {paletteOpen && <CommandPalette c={c} onClose={() => setPaletteOpen(false)} />}

      {/* ── Glass sidebar ── */}
      <aside style={{
        width: sidebarCollapsed ? 56 : 234,
        minWidth: sidebarCollapsed ? 56 : 234,
        background: c.glass,
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        borderRight: `1px solid ${c.glassBorder}`,
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1)',
        overflow: 'hidden', zIndex: 10, flexShrink: 0,
      } as React.CSSProperties}>
        {/* Logo + toggle */}
        <div style={{
          display: 'flex', alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'space-between',
          padding: sidebarCollapsed ? '0 16px' : '0 10px 0 18px',
          height: 54, borderBottom: `1px solid ${c.glassBorder}`, flexShrink: 0,
        }}>
          {!sidebarCollapsed && (
            <div style={{ fontWeight: 800, fontSize: 15, letterSpacing: '-0.02em' }}>
              <span style={{ color: c.accent, textShadow: `0 0 20px ${c.accentGlow}` }}>Part</span>
              <span style={{ color: c.text }}>Folder</span>
              <span style={{ color: c.muted, fontSize: 12, fontWeight: 400 }}> 3D</span>
            </div>
          )}
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand' : 'Collapse'}
            style={{
              background: c.glass, border: `1px solid ${c.glassBorder}`,
              borderRadius: 8, cursor: 'pointer', color: c.muted,
              display: 'flex', padding: '5px 6px', transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = c.activePillBorder
              ;(e.currentTarget as HTMLButtonElement).style.color = c.accent
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = c.glassBorder
              ;(e.currentTarget as HTMLButtonElement).style.color = c.muted
            }}
          >
            {sidebarCollapsed
              ? <ChevronDown size={14} style={{ transform: 'rotate(-90deg)' }} />
              : <ChevronDown size={14} style={{ transform: 'rotate(90deg)' }} />
            }
          </button>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 0', scrollbarWidth: 'none' }}>
          {visibleGroups.map(group => {
            const isGroupOpen = !collapsedGroups.includes(group.id)
            return (
              <div key={group.id} style={{ marginBottom: 4 }}>
                {!sidebarCollapsed && (
                  <button onClick={() => toggleGroup(group.id)} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    width: '100%', padding: '4px 18px 4px 18px',
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    color: c.muted, fontSize: 10, fontWeight: 700,
                    letterSpacing: '0.1em', textTransform: 'uppercase',
                    transition: 'color 0.15s',
                  }}>
                    <span>{group.label}</span>
                    <ChevronDown size={11} style={{
                      transition: 'transform 0.2s cubic-bezier(0.4,0,0.2,1)',
                      transform: isGroupOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                    }} />
                  </button>
                )}
                {/* Animated collapse */}
                <div style={{
                  overflow: 'hidden',
                  maxHeight: isGroupOpen || sidebarCollapsed ? '400px' : '0',
                  transition: 'max-height 0.25s cubic-bezier(0.4,0,0.2,1)',
                }}>
                  {group.items.map(item => {
                    const isActive = activeNav === item.label
                    return (
                      <button key={item.label} onClick={() => setActiveNav(item.label)}
                        title={sidebarCollapsed ? item.label : undefined}
                        style={{
                          display: 'flex', alignItems: 'center',
                          gap: sidebarCollapsed ? 0 : 9,
                          width: sidebarCollapsed ? '100%' : 'calc(100% - 16px)',
                          padding: sidebarCollapsed ? '8px 0' : '6px 12px',
                          margin: sidebarCollapsed ? '0' : '0 8px',
                          justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                          background: isActive ? c.activePill : 'transparent',
                          border: `1px solid ${isActive ? c.activePillBorder : 'transparent'}`,
                          borderRadius: 10,
                          cursor: 'pointer',
                          color: isActive ? c.accent : c.textDim,
                          fontWeight: isActive ? 600 : 400,
                          fontSize: 13,
                          boxShadow: isActive ? c.activeGlow : 'none',
                          transition: 'all 0.15s cubic-bezier(0.4,0,0.2,1)',
                        }}
                        onMouseEnter={e => {
                          if (!isActive) {
                            (e.currentTarget as HTMLButtonElement).style.background = c.glassHover
                            ;(e.currentTarget as HTMLButtonElement).style.color = c.text
                          }
                        }}
                        onMouseLeave={e => {
                          if (!isActive) {
                            (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
                            ;(e.currentTarget as HTMLButtonElement).style.color = c.textDim
                          }
                        }}
                      >
                        <NavIcon name={item.icon} size={14} />
                        {!sidebarCollapsed && (
                          <>
                            <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
                            {item.badge != null && (
                              <span style={{
                                background: c.accent, color: c.accentFg,
                                borderRadius: 20, padding: '0 6px',
                                fontSize: 10, fontWeight: 700, lineHeight: '16px',
                                boxShadow: `0 0 8px ${c.accentGlow}`,
                              }}>{item.badge}</span>
                            )}
                          </>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </nav>

        {/* Footer */}
        <div style={{
          borderTop: `1px solid ${c.glassBorder}`,
          padding: sidebarCollapsed ? '10px 0' : '10px 18px',
          flexShrink: 0,
          display: 'flex', justifyContent: sidebarCollapsed ? 'center' : 'space-between', alignItems: 'center',
        }}>
          {sidebarCollapsed ? (
            <ExternalLink size={13} style={{ color: c.muted }} />
          ) : (
            <>
              <span style={{ fontSize: 11, color: c.muted }}>v{MOCK_VERSION}</span>
              <a href={RELEASES_URL} target="_blank" rel="noreferrer"
                style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: c.accent, textDecoration: 'none' }}>
                Release notes <ExternalLink size={10} />
              </a>
            </>
          )}
        </div>
      </aside>

      {/* ── Main ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
        onClick={() => showUserMenu && setShowUserMenu(false)}
      >
        {/* Top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '0 20px', height: 54,
          background: c.glass,
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderBottom: `1px solid ${c.glassBorder}`,
          flexShrink: 0,
        } as React.CSSProperties}>
          {/* ⌘K search bar */}
          <button onClick={() => setPaletteOpen(true)} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '7px 12px', background: c.inputBg,
            border: `1px solid ${c.inputBorder}`, borderRadius: 10,
            flex: 1, maxWidth: 300, cursor: 'text',
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = c.activePillBorder
              ;(e.currentTarget as HTMLButtonElement).style.boxShadow = `0 0 0 3px ${c.activePill}`
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = c.inputBorder
              ;(e.currentTarget as HTMLButtonElement).style.boxShadow = 'none'
            }}
          >
            <Search size={13} style={{ color: c.muted }} />
            <span style={{ color: c.muted, fontSize: 13, flex: 1, textAlign: 'left' }}>Search or press…</span>
            <span style={{
              display: 'flex', alignItems: 'center', gap: 3,
              padding: '2px 7px', background: c.glass,
              border: `1px solid ${c.glassBorder}`, borderRadius: 6,
              fontSize: 11, color: c.accent, fontWeight: 600,
            }}>
              <Command size={11} /> K
            </span>
          </button>

          {/* In-page search (filters catalog) */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '6px 11px', background: c.inputBg,
            border: `1px solid ${c.inputBorder}`, borderRadius: 10,
            width: 200,
          }}>
            <Search size={13} style={{ color: c.muted }} />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Filter catalog…"
              style={{ background: 'transparent', border: 'none', outline: 'none', color: c.text, fontSize: 13, width: '100%' }} />
          </div>

          <div style={{ flex: 1 }} />

          {/* Viewing as */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
            <span style={{ color: c.muted, marginRight: 3 }}>Viewing as:</span>
            {(['admin', 'editor', 'viewer'] as Role[]).map(r => (
              <button key={r} onClick={() => setRole(r)} style={{
                padding: '3px 10px', borderRadius: 20,
                border: `1px solid ${r === role ? c.activePillBorder : 'transparent'}`,
                cursor: 'pointer', fontSize: 11, fontWeight: r === role ? 700 : 400,
                background: r === role ? c.activePill : 'transparent',
                color: r === role ? c.accent : c.muted,
                boxShadow: r === role ? c.activeGlow : 'none',
                textTransform: 'capitalize', transition: 'all 0.15s',
              }}>{r}</button>
            ))}
          </div>

          {/* Theme */}
          <button onClick={() => setIsDark(!isDark)} style={{
            background: c.glass, border: `1px solid ${c.glassBorder}`,
            borderRadius: 9, cursor: 'pointer', color: c.muted, display: 'flex', padding: 7,
            transition: 'all 0.15s',
          }}>
            {isDark ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          {/* Avatar */}
          <div style={{ position: 'relative' }}>
            <button onClick={e => { e.stopPropagation(); setShowUserMenu(!showUserMenu) }} style={{
              width: 32, height: 32, borderRadius: '50%',
              background: `linear-gradient(135deg, #0FA4AB, #0c6d72)`,
              color: '#FFF', border: `2px solid ${c.activePillBorder}`,
              cursor: 'pointer', fontSize: 13, fontWeight: 800,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: `0 0 16px ${c.accentGlow}`,
            }}>A</button>
            {showUserMenu && (
              <div onClick={e => e.stopPropagation()} style={{
                position: 'absolute', top: 40, right: 0, zIndex: 200,
                background: c.paletteBg, border: `1px solid ${c.paletteBorder}`,
                borderRadius: 14, padding: '5px',
                minWidth: 180, boxShadow: `0 16px 48px rgba(0,0,0,0.4)`,
                backdropFilter: 'blur(30px)', WebkitBackdropFilter: 'blur(30px)',
              } as React.CSSProperties}>
                <div style={{ padding: '9px 14px 9px', borderBottom: `1px solid ${c.divider}`, marginBottom: 3 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: c.text }}>Admin User</div>
                  <div style={{ fontSize: 11, color: c.muted }}>admin@partfolder.local</div>
                </div>
                <button onClick={() => { setIsDark(!isDark); setShowUserMenu(false) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', padding: '8px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 13, color: c.textDim, borderRadius: 9 }}>
                  {isDark ? <Sun size={13} /> : <Moon size={13} />} Toggle theme
                </button>
                <a href={RELEASES_URL} target="_blank" rel="noreferrer"
                  style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', padding: '8px 14px', fontSize: 13, color: c.textDim, textDecoration: 'none', borderRadius: 9 }}>
                  <ExternalLink size={13} /> v{MOCK_VERSION} — Notes
                </a>
                <button onClick={() => setPaletteOpen(true)}
                  style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', padding: '8px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 13, color: c.accent, borderRadius: 9 }}>
                  <Command size={13} /> Command palette
                </button>
                <div style={{ borderTop: `1px solid ${c.divider}`, marginTop: 3, paddingTop: 3 }}>
                  <button style={{ display: 'flex', alignItems: 'center', gap: 9, width: '100%', padding: '8px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 13, color: c.danger, borderRadius: 9 }}>
                    <LogOut size={13} /> Sign out
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px', scrollbarWidth: 'thin', scrollbarColor: `${c.glass} transparent` }}>
          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 18 }}>
            {[
              { label: 'Total Assets',  value: MOCK_STATS.total.toLocaleString(),    icon: <LayoutGrid size={13} />, color: c.stat1 },
              { label: 'Prints Done',   value: MOCK_STATS.printed.toLocaleString(),   icon: <Activity size={13} />,   color: c.stat2 },
              { label: 'Filament',      value: `${MOCK_STATS.filamentKg} kg`,          icon: <Package size={13} />,    color: c.stat3 },
              { label: 'Success Rate',  value: `${MOCK_STATS.successRate}%`,            icon: <Star size={13} />,       color: c.stat4 },
              { label: 'Jobs Running',  value: String(MOCK_STATS.jobsRunning),          icon: <Cpu size={13} />,        color: c.stat5 },
            ].map(s => (
              <div key={s.label} style={{
                background: c.cardGlass, border: `1px solid ${c.cardGlassBorder}`,
                borderRadius: 12, padding: '12px 14px',
                backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
                transition: 'border-color 0.15s, box-shadow 0.15s',
              } as React.CSSProperties}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = `${s.color}40`
                  ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 0 20px ${s.color}20`
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLDivElement).style.borderColor = c.cardGlassBorder
                  ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, fontWeight: 700, color: c.muted, letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 5 }}>
                  <span style={{ color: s.color }}>{s.icon}</span> {s.label}
                </div>
                <div style={{ fontSize: 22, fontWeight: 800, color: c.text, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', textShadow: `0 0 30px ${s.color}30` }}>
                  {s.value}
                </div>
              </div>
            ))}
          </div>

          {/* Tab bar */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 14 }}>
            {(['catalog', 'jobs', 'tags'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)} style={{
                padding: '6px 16px', border: 'none', cursor: 'pointer',
                fontSize: 12, fontWeight: activeTab === tab ? 700 : 400,
                background: activeTab === tab ? c.activePill : 'transparent',
                border: `1px solid ${activeTab === tab ? c.activePillBorder : 'transparent'}`,
                borderRadius: 20, color: activeTab === tab ? c.accent : c.muted,
                boxShadow: activeTab === tab ? c.activeGlow : 'none',
                transition: 'all 0.15s', textTransform: 'capitalize',
              }}>{tab}</button>
            ))}
          </div>

          {/* Catalog */}
          {activeTab === 'catalog' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 10, alignContent: 'start' }}>
                {filteredItems.map(item => (
                  <div key={item.id} style={{
                    background: c.cardGlass, border: `1px solid ${c.cardGlassBorder}`,
                    borderRadius: 12, overflow: 'hidden', cursor: 'pointer',
                    backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
                    transition: 'all 0.15s cubic-bezier(0.4,0,0.2,1)',
                  } as React.CSSProperties}
                    onMouseEnter={e => {
                      (e.currentTarget as HTMLDivElement).style.borderColor = `${item.color}50`
                      ;(e.currentTarget as HTMLDivElement).style.boxShadow = `0 0 20px ${item.color}20`
                      ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'
                    }}
                    onMouseLeave={e => {
                      (e.currentTarget as HTMLDivElement).style.borderColor = c.cardGlassBorder
                      ;(e.currentTarget as HTMLDivElement).style.boxShadow = 'none'
                      ;(e.currentTarget as HTMLDivElement).style.transform = 'none'
                    }}
                  >
                    <div style={{
                      height: 86, position: 'relative',
                      background: `radial-gradient(ellipse at 50% 60%, ${item.color}25 0%, ${item.color}08 100%)`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Box size={26} style={{ color: item.color, filter: `drop-shadow(0 0 8px ${item.color}60)` }} />
                      {item.favorited && <Star size={11} style={{ position: 'absolute', top: 7, right: 8, color: '#FBBF24', fill: '#FBBF24', filter: 'drop-shadow(0 0 4px #FBBF2480)' }} />}
                      {item.badge && (
                        <span style={{
                          position: 'absolute', top: 7, left: 8,
                          padding: '1px 5px', borderRadius: 4, fontSize: 9, fontWeight: 700,
                          background: badgeColors[item.badge] ?? c.accent, color: '#FFF',
                          textTransform: 'uppercase', letterSpacing: '0.05em',
                          boxShadow: `0 0 8px ${badgeColors[item.badge] ?? c.accent}60`,
                        }}>{item.badge}</span>
                      )}
                    </div>
                    <div style={{ padding: '9px 11px' }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: c.text, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</div>
                      <div style={{ fontSize: 11, color: c.muted, marginBottom: 6 }}>{item.creator}</div>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {item.tags.slice(0, 2).map(t => (
                          <span key={t} style={{ fontSize: 10, padding: '1px 6px', background: c.tag, color: c.tagText, borderRadius: 10, border: `1px solid ${c.tagBorder}` }}>#{t}</span>
                        ))}
                        <span style={{ fontSize: 10, color: c.muted, marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 2 }}>
                          <FileText size={9} /> {item.files}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Wizard */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: c.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>Quick Import</div>
                <ImportWizard c={c} />
              </div>
            </div>
          )}

          {/* Jobs */}
          {activeTab === 'jobs' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {MOCK_JOBS.map(job => {
                const statusColor = job.status === 'running' ? c.accent : job.status === 'queued' ? c.warn : job.status === 'failed' ? c.danger : c.success
                return (
                  <div key={job.id} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px',
                    background: c.cardGlass, border: `1px solid ${c.cardGlassBorder}`,
                    borderRadius: 12,
                    backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
                  } as React.CSSProperties}>
                    <span style={{
                      width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                      background: statusColor,
                      boxShadow: job.status === 'running' ? `0 0 8px ${statusColor}` : 'none',
                    }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, color: c.text, fontWeight: 500, display: 'flex', gap: 8 }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.name}</span>
                        {job.target && <span style={{ color: c.muted, fontSize: 11, flexShrink: 0 }}>{job.target}</span>}
                      </div>
                      {job.status === 'running' && job.progress !== undefined && (
                        <div style={{ marginTop: 5, height: 3, background: c.glass, borderRadius: 2 }}>
                          <div style={{ height: '100%', width: `${job.progress}%`, background: `linear-gradient(90deg, ${c.accent}, #17C5CE)`, borderRadius: 2, boxShadow: `0 0 8px ${c.accentGlow}` }} />
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                      {job.status === 'running' && job.progress !== undefined && (
                        <span style={{ fontSize: 11, color: c.accent, fontWeight: 700 }}>{job.progress}%</span>
                      )}
                      <span style={{ fontSize: 10, color: c.muted }}>{job.since}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Tags */}
          {activeTab === 'tags' && (
            <div style={{
              background: c.cardGlass, border: `1px solid ${c.cardGlassBorder}`,
              borderRadius: 14, padding: '20px',
              backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
            } as React.CSSProperties}>
              <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: c.muted, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Tag cloud — {MOCK_STATS.tags} total</span>
                <div style={{ display: 'flex', gap: 6 }}>
                  {MOCK_CREATORS.slice(0, 3).map(cr => (
                    <div key={cr.id} title={cr.name} style={{
                      width: 26, height: 26, borderRadius: '50%',
                      background: `linear-gradient(135deg, ${cr.color}50, ${cr.color}90)`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 800, color: '#FFF',
                      border: `1.5px solid ${cr.color}60`,
                      boxShadow: `0 0 12px ${cr.color}30`,
                      cursor: 'pointer',
                    }}>{cr.name[0]}</div>
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                {MOCK_TAG_CLOUD.map(t => {
                  const max = MOCK_TAG_CLOUD[0].count
                  const rel = t.count / max
                  const size = 10 + Math.round(rel * 6)
                  return (
                    <button key={t.label} style={{
                      padding: '3px 10px', fontSize: size, fontWeight: rel > 0.5 ? 600 : 400,
                      background: rel > 0.6 ? c.activePill : c.tag,
                      color: rel > 0.6 ? c.accent : c.tagText,
                      border: `1px solid ${rel > 0.6 ? c.activePillBorder : c.tagBorder}`,
                      borderRadius: 20, cursor: 'pointer',
                      boxShadow: rel > 0.7 ? c.activeGlow : 'none',
                      transition: 'all 0.15s',
                    }}>#{t.label}</button>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
