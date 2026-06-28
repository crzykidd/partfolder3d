/**
 * Example 1 — "Mission Control"
 *
 * Dense pro dashboard, dark-first navy surfaces + teal accent.
 * Collapsible left rail (icon-only ↔ full), grouped nav, role-based menus,
 * ⌘K search, avatar menu, stats row, catalog grid, import wizard panel.
 *
 * All data is mock — no API calls, no auth context required.
 */

import React, { useState } from 'react'
import {
  LayoutGrid, Tag, Users, Heart, PlusCircle, Inbox, Package, Cpu, Calendar,
  AlertTriangle, GitBranch, Eye, User, Mail, Zap, Settings, Archive, Download,
  Hash, SlidersHorizontal, ChevronDown, ChevronRight, ChevronLeft, Search,
  Sun, Moon, LogOut, ExternalLink, Box, FileText, CheckCircle2, Circle,
  Star, Activity, type LucideIcon,
} from 'lucide-react'
import {
  MOCK_ITEMS, MOCK_STATS, MOCK_JOBS, MOCK_TAG_CLOUD,
  MOCK_VERSION, RELEASES_URL, NAV_GROUPS, canSeeGroup,
  type Role,
} from './mockData'
import { useLocalStorage } from './useLocalStorage'

// ─── Color schemes ────────────────────────────────────────────────────────────

const DARK = {
  root:            '#060F1A',
  sidebar:         '#091D35',
  sidebarBorder:   '#122843',
  card:            '#0D2540',
  cardBorder:      '#152E4D',
  cardHover:       '#102848',
  topBar:          '#091D35',
  topBarBorder:    '#122843',
  text:            '#DCE8F5',
  textDim:         '#94B4CC',
  muted:           '#5D7E9E',
  accent:          '#0FA4AB',
  accentFg:        '#FFFFFF',
  accentDim:       'rgba(15,164,171,0.12)',
  accentBorder:    'rgba(15,164,171,0.35)',
  tag:             '#122843',
  tagText:         '#7DB8D4',
  divider:         '#122843',
  inputBg:         'rgba(255,255,255,0.05)',
  hoverBg:         'rgba(255,255,255,0.04)',
  statCard:        '#0D2540',
  statBorder:      '#152E4D',
  badgeBg:         '#0FA4AB',
  badgeFg:         '#FFFFFF',
  danger:          '#EF4444',
  warn:            '#F59E0B',
  success:         '#22C55E',
}

const LIGHT = {
  root:            '#EEF3F8',
  sidebar:         '#FFFFFF',
  sidebarBorder:   '#E2E8F0',
  card:            '#FFFFFF',
  cardBorder:      '#E2E8F0',
  cardHover:       '#F8FAFC',
  topBar:          '#FFFFFF',
  topBarBorder:    '#E2E8F0',
  text:            '#0F172A',
  textDim:         '#334155',
  muted:           '#64748B',
  accent:          '#0FA4AB',
  accentFg:        '#FFFFFF',
  accentDim:       'rgba(15,164,171,0.08)',
  accentBorder:    'rgba(15,164,171,0.3)',
  tag:             '#E8F9FA',
  tagText:         '#0c7a80',
  divider:         '#E2E8F0',
  inputBg:         'rgba(0,0,0,0.04)',
  hoverBg:         'rgba(0,0,0,0.03)',
  statCard:        '#FFFFFF',
  statBorder:      '#E2E8F0',
  badgeBg:         '#0FA4AB',
  badgeFg:         '#FFFFFF',
  danger:          '#EF4444',
  warn:            '#F59E0B',
  success:         '#22C55E',
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

// ─── Import Wizard ────────────────────────────────────────────────────────────

const WIZARD_STEPS = ['Source', 'Configure', 'Preview', 'Import']

const WIZARD_PREVIEW_FILES = [
  'gridfinity-baseplate-2x4.3mf',
  'gridfinity-baseplate-2x4.stl',
  'gridfinity-baseplate-2x4.step',
  'gridfinity-baseplate-2x4_preview.png',
]

function ImportWizard({ c }: { c: C }) {
  const [step, setStep] = useState(1)
  const [importing, setImporting] = useState(false)
  const [done, setDone] = useState(false)

  const startImport = () => {
    setImporting(true)
    setTimeout(() => { setImporting(false); setDone(true) }, 2000)
  }

  const reset = () => { setStep(0); setImporting(false); setDone(false) }

  return (
    <div style={{ background: c.card, border: `1px solid ${c.cardBorder}`, borderRadius: 8, overflow: 'hidden' }}>
      {/* Steps */}
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${c.divider}` }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: c.muted, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
          Import Wizard
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {WIZARD_STEPS.map((s, i) => (
            <React.Fragment key={s}>
              <button
                onClick={() => !importing && !done && setStep(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '2px 6px', borderRadius: 4, border: 'none',
                  cursor: 'pointer', fontSize: 11,
                  fontWeight: i === step ? 600 : 400,
                  background: i === step ? c.accentDim : 'transparent',
                  color: i === step ? c.accent : i < step ? c.textDim : c.muted,
                }}
              >
                <span style={{
                  width: 16, height: 16, borderRadius: '50%',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, fontWeight: 700,
                  background: i < step || done ? c.accent : i === step ? c.accentDim : 'transparent',
                  border: `1.5px solid ${i <= step ? c.accent : c.divider}`,
                  color: i < step || done ? c.accentFg : i === step ? c.accent : c.muted,
                  flexShrink: 0,
                }}>
                  {i < step || done ? '✓' : i + 1}
                </span>
                <span>{s}</span>
              </button>
              {i < WIZARD_STEPS.length - 1 && (
                <div style={{ flex: 1, height: 1, background: c.divider, minWidth: 8 }} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: 14, minHeight: 148 }}>
        {step === 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {['URL / Thingiverse', 'Local File', 'ZIP Archive', 'Template'].map((src, i) => (
              <button key={src} style={{
                padding: '10px 12px', border: `1px solid ${i === 0 ? c.accent : c.cardBorder}`,
                borderRadius: 6, background: i === 0 ? c.accentDim : 'transparent',
                color: i === 0 ? c.accent : c.textDim,
                fontSize: 12, fontWeight: i === 0 ? 500 : 400, cursor: 'pointer', textAlign: 'left',
              }}>
                {src}
              </button>
            ))}
          </div>
        )}

        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* Scraped info banner */}
            <div style={{ padding: '7px 10px', background: c.accentDim, border: `1px solid ${c.accentBorder}`, borderRadius: 5, fontSize: 11, color: c.accent }}>
              ✦ Scraped from Printables — 4 files, 1 image detected
            </div>
            {[
              ['Title',   'Gridfinity Baseplate 2×4 Lite'],
              ['Creator', 'Zack Freedman'],
              ['Library', 'Primary Collection'],
            ].map(([label, val]) => (
              <div key={label}>
                <div style={{ fontSize: 10, fontWeight: 600, color: c.muted, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>{label}</div>
                <div style={{ padding: '6px 10px', border: `1px solid ${c.cardBorder}`, borderRadius: 4, background: c.inputBg, color: c.text, fontSize: 12 }}>{val}</div>
              </div>
            ))}
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: c.muted, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Tags</div>
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                {['gridfinity', 'storage', 'organizer'].map(t => (
                  <span key={t} style={{ padding: '2px 8px', background: c.tag, color: c.tagText, borderRadius: 4, fontSize: 11 }}>{t} ✓</span>
                ))}
                {['2x4', 'lite'].map(t => (
                  <span key={t} style={{ padding: '2px 8px', background: c.accentDim, color: c.accent, borderRadius: 4, fontSize: 11, border: `1px dashed ${c.accentBorder}` }}>{t} (pending)</span>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: c.muted, marginBottom: 8 }}>4 files detected</div>
            {WIZARD_PREVIEW_FILES.map(f => (
              <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: `1px solid ${c.divider}`, fontSize: 12, color: c.text }}>
                <FileText size={12} style={{ color: c.muted, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{f}</span>
                <span style={{ fontSize: 10, color: c.muted }}>{f.endsWith('.png') ? '48 KB' : f.endsWith('.3mf') ? '1.2 MB' : f.endsWith('.stl') ? '840 KB' : '220 KB'}</span>
              </div>
            ))}
          </div>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            {done ? (
              <>
                <CheckCircle2 size={28} style={{ color: c.success, margin: '0 auto 8px', display: 'block' }} />
                <div style={{ color: c.text, fontWeight: 600, fontSize: 14 }}>Import complete!</div>
                <div style={{ color: c.muted, fontSize: 12, marginTop: 4 }}>4 files added to Primary Collection</div>
                <button onClick={reset} style={{ marginTop: 12, padding: '5px 14px', background: c.accentDim, color: c.accent, border: `1px solid ${c.accentBorder}`, borderRadius: 6, fontSize: 12, cursor: 'pointer' }}>
                  Import another
                </button>
              </>
            ) : importing ? (
              <>
                <div style={{ color: c.muted, fontSize: 12, marginBottom: 8 }}>Importing 4 files…</div>
                <div style={{ height: 4, background: c.divider, borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '65%', background: c.accent, borderRadius: 2 }} />
                </div>
              </>
            ) : (
              <>
                <Circle size={28} style={{ color: c.muted, margin: '0 auto 8px', display: 'block' }} />
                <div style={{ color: c.textDim, fontSize: 12 }}>Ready to import 4 files</div>
                <button onClick={startImport} style={{ marginTop: 12, padding: '6px 20px', background: c.accent, color: c.accentFg, border: 'none', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                  Start Import
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {!done && (
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 14px', borderTop: `1px solid ${c.divider}` }}>
          <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}
            style={{ padding: '4px 12px', border: `1px solid ${c.cardBorder}`, borderRadius: 5, background: 'transparent', color: step === 0 ? c.muted : c.textDim, fontSize: 12, cursor: step === 0 ? 'default' : 'pointer', opacity: step === 0 ? 0.4 : 1 }}>
            ← Back
          </button>
          {step < WIZARD_STEPS.length - 1 ? (
            <button onClick={() => setStep(s => Math.min(WIZARD_STEPS.length - 1, s + 1))}
              style={{ padding: '4px 12px', background: c.accent, color: c.accentFg, border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
              Next →
            </button>
          ) : <span />}
        </div>
      )}
    </div>
  )
}

// ─── Tag Cloud ────────────────────────────────────────────────────────────────

function TagCloud({ c }: { c: C }) {
  const max = Math.max(...MOCK_TAG_CLOUD.map(t => t.count))
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {MOCK_TAG_CLOUD.slice(0, 14).map(t => {
        const rel = t.count / max
        const size = 10 + Math.round(rel * 5)
        const opacity = 0.55 + rel * 0.45
        return (
          <button key={t.label} style={{
            fontSize: size, fontWeight: rel > 0.6 ? 600 : 400,
            padding: '2px 8px', borderRadius: 4,
            border: `1px solid ${c.cardBorder}`,
            background: c.tag, color: c.tagText,
            opacity, cursor: 'pointer',
          }}>
            #{t.label}
          </button>
        )
      })}
    </div>
  )
}

// ─── Jobs Panel ───────────────────────────────────────────────────────────────

function JobsPanel({ c }: { c: C }) {
  const statusColor = (s: string) =>
    s === 'running' ? c.accent : s === 'queued' ? c.warn : s === 'failed' ? c.danger : c.success

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {MOCK_JOBS.slice(0, 5).map(job => (
        <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', background: c.card, border: `1px solid ${c.cardBorder}`, borderRadius: 6 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor(job.status), flexShrink: 0, boxShadow: job.status === 'running' ? `0 0 6px ${c.accent}` : 'none' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: c.text, fontWeight: 500, display: 'flex', gap: 6 }}>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.name}</span>
              {job.target && <span style={{ color: c.muted, fontSize: 11, flexShrink: 0 }}>{job.target}</span>}
            </div>
            {job.status === 'running' && job.progress !== undefined && (
              <div style={{ marginTop: 4, height: 3, background: c.divider, borderRadius: 2 }}>
                <div style={{ height: '100%', width: `${job.progress}%`, background: c.accent, borderRadius: 2, transition: 'width 0.5s' }} />
              </div>
            )}
          </div>
          <span style={{ fontSize: 10, color: c.muted, flexShrink: 0 }}>{job.since}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function Example1() {
  const [isDark, setIsDark] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useLocalStorage('ex1-sidebar', false)
  const [collapsedGroups, setCollapsedGroups] = useLocalStorage<string[]>('ex1-groups', [])
  const [role, setRole] = useState<Role>('admin')
  const [activeNav, setActiveNav] = useState('Catalog')
  const [search, setSearch] = useState('')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [activeTab, setActiveTab] = useState<'catalog' | 'tags' | 'jobs'>('catalog')

  const c = isDark ? DARK : LIGHT
  const visibleGroups = NAV_GROUPS.filter(g => canSeeGroup(g, role))

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

  return (
    <div style={{
      display: 'flex', height: '100vh', overflow: 'hidden',
      background: c.root, color: c.text,
      fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
      fontSize: 13,
    }}>
      {/* ── Sidebar ── */}
      <aside style={{
        width: sidebarCollapsed ? 52 : 228,
        minWidth: sidebarCollapsed ? 52 : 228,
        background: c.sidebar,
        borderRight: `1px solid ${c.sidebarBorder}`,
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.18s ease, min-width 0.18s ease',
        overflow: 'hidden', zIndex: 10,
      }}>
        {/* Logo + toggle */}
        <div style={{
          display: 'flex', alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'space-between',
          padding: sidebarCollapsed ? '0 14px' : '0 8px 0 16px',
          borderBottom: `1px solid ${c.sidebarBorder}`,
          height: 50, flexShrink: 0,
        }}>
          {!sidebarCollapsed && (
            <span style={{ fontWeight: 700, fontSize: 14.5, letterSpacing: '-0.01em', color: c.text }}>
              <span style={{ color: c.accent }}>Part</span>Folder 3D
            </span>
          )}
          <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: c.muted, padding: 5, borderRadius: 4, display: 'flex', alignItems: 'center' }}>
            {sidebarCollapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
          </button>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, overflowY: 'auto', padding: '6px 0', scrollbarWidth: 'none' }}>
          {visibleGroups.map(group => {
            const isGroupOpen = !collapsedGroups.includes(group.id)
            return (
              <div key={group.id} style={{ marginBottom: 2 }}>
                {!sidebarCollapsed && (
                  <button onClick={() => toggleGroup(group.id)} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    width: '100%', padding: '3px 8px 3px 16px',
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    color: c.muted, fontSize: 10, fontWeight: 700,
                    letterSpacing: '0.1em', textTransform: 'uppercase',
                  }}>
                    <span>{group.label}</span>
                    {isGroupOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                  </button>
                )}
                {(isGroupOpen || sidebarCollapsed) && group.items.map(item => {
                  const isActive = activeNav === item.label
                  return (
                    <button key={item.label} onClick={() => setActiveNav(item.label)}
                      title={sidebarCollapsed ? item.label : undefined}
                      style={{
                        display: 'flex', alignItems: 'center',
                        gap: sidebarCollapsed ? 0 : 8,
                        width: '100%',
                        padding: sidebarCollapsed ? '8px 0' : '6px 10px 6px 16px',
                        justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                        background: isActive ? c.accentDim : 'transparent',
                        border: 'none',
                        borderLeft: `2px solid ${isActive ? c.accent : 'transparent'}`,
                        cursor: 'pointer',
                        color: isActive ? c.accent : c.textDim,
                        fontWeight: isActive ? 600 : 400,
                        fontSize: 13,
                        transition: 'background 0.1s, color 0.1s',
                      }}>
                      <NavIcon name={item.icon} size={14} />
                      {!sidebarCollapsed && (
                        <>
                          <span style={{ flex: 1, textAlign: 'left' }}>{item.label}</span>
                          {item.badge != null && (
                            <span style={{
                              background: c.badgeBg, color: c.badgeFg,
                              borderRadius: 9, padding: '0 5px',
                              fontSize: 10, fontWeight: 700, lineHeight: '16px',
                            }}>{item.badge}</span>
                          )}
                        </>
                      )}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </nav>

        {/* Footer */}
        <div style={{ borderTop: `1px solid ${c.sidebarBorder}`, padding: sidebarCollapsed ? '10px 14px' : '10px 16px', flexShrink: 0 }}>
          {sidebarCollapsed ? (
            <ExternalLink size={14} style={{ color: c.muted }} />
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: c.muted, fontVariantNumeric: 'tabular-nums' }}>v{MOCK_VERSION}</span>
              <a href={RELEASES_URL} target="_blank" rel="noreferrer"
                style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: c.accent, textDecoration: 'none' }}>
                Release notes <ExternalLink size={10} />
              </a>
            </div>
          )}
        </div>
      </aside>

      {/* ── Main ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '0 18px', height: 50,
          background: c.topBar, borderBottom: `1px solid ${c.topBarBorder}`,
          flexShrink: 0,
        }}>
          {/* Search */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '5px 11px', background: c.inputBg,
            border: `1px solid ${c.divider}`, borderRadius: 6,
            flex: 1, maxWidth: 320,
          }}>
            <Search size={13} style={{ color: c.muted, flexShrink: 0 }} />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search catalog…  ⌘K"
              style={{ background: 'transparent', border: 'none', outline: 'none', color: c.text, fontSize: 13, width: '100%' }} />
          </div>

          <div style={{ flex: 1 }} />

          {/* Viewing as */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11 }}>
            <span style={{ color: c.muted, marginRight: 2 }}>Viewing as:</span>
            {(['admin', 'editor', 'viewer'] as Role[]).map(r => (
              <button key={r} onClick={() => setRole(r)} style={{
                padding: '3px 9px', borderRadius: 4, border: 'none', cursor: 'pointer',
                fontSize: 11, fontWeight: r === role ? 600 : 400,
                background: r === role ? c.accent : c.hoverBg,
                color: r === role ? c.accentFg : c.muted,
                textTransform: 'capitalize',
              }}>{r}</button>
            ))}
          </div>

          {/* Theme */}
          <button onClick={() => setIsDark(!isDark)}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: c.muted, display: 'flex', padding: 5 }}>
            {isDark ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          {/* Avatar */}
          <div style={{ position: 'relative' }}>
            <button onClick={() => setShowUserMenu(!showUserMenu)} style={{
              width: 30, height: 30, borderRadius: '50%',
              background: `linear-gradient(135deg, #0FA4AB, #091D35)`,
              color: '#FFF', border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>A</button>
            {showUserMenu && (
              <div style={{
                position: 'absolute', top: 38, right: 0, zIndex: 100,
                background: c.card, border: `1px solid ${c.cardBorder}`,
                borderRadius: 8, padding: '4px 0', minWidth: 160,
                boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
              }}>
                <div style={{ padding: '7px 14px', borderBottom: `1px solid ${c.divider}` }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: c.text }}>Admin User</div>
                  <div style={{ fontSize: 11, color: c.muted }}>admin@partfolder.local</div>
                </div>
                <button onClick={() => { setIsDark(!isDark); setShowUserMenu(false) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '7px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 12, color: c.textDim }}>
                  {isDark ? <Sun size={13} /> : <Moon size={13} />} Toggle theme
                </button>
                <button style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '7px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 12, color: c.danger }}>
                  <LogOut size={13} /> Sign out
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Page content */}
        <div onClick={() => showUserMenu && setShowUserMenu(false)}
          style={{ flex: 1, overflowY: 'auto', padding: 18, scrollbarWidth: 'thin', scrollbarColor: `${c.divider} transparent` }}>

          {/* Stats row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 18 }}>
            {[
              { label: 'Total Assets',   value: MOCK_STATS.total.toLocaleString(),    icon: <LayoutGrid size={13} /> },
              { label: 'Prints Done',    value: MOCK_STATS.printed.toLocaleString(),   icon: <Activity size={13} /> },
              { label: 'Filament Used',  value: `${MOCK_STATS.filamentKg} kg`,         icon: <Package size={13} /> },
              { label: 'Success Rate',   value: `${MOCK_STATS.successRate}%`,           icon: <Star size={13} /> },
              { label: 'Jobs Running',   value: String(MOCK_STATS.jobsRunning),         icon: <Cpu size={13} /> },
            ].map(s => (
              <div key={s.label} style={{
                background: c.statCard, border: `1px solid ${c.statBorder}`,
                borderRadius: 6, padding: '11px 14px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, fontWeight: 600, color: c.muted, letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 5 }}>
                  <span style={{ color: c.accent }}>{s.icon}</span> {s.label}
                </div>
                <div style={{ fontSize: 21, fontWeight: 700, color: c.text, fontVariantNumeric: 'tabular-nums' }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* Tab bar */}
          <div style={{ display: 'flex', gap: 2, marginBottom: 14, borderBottom: `1px solid ${c.divider}`, paddingBottom: 0 }}>
            {(['catalog', 'tags', 'jobs'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)} style={{
                padding: '6px 16px', border: 'none', background: 'transparent', cursor: 'pointer',
                fontSize: 12, fontWeight: activeTab === tab ? 600 : 400,
                color: activeTab === tab ? c.accent : c.muted,
                borderBottom: `2px solid ${activeTab === tab ? c.accent : 'transparent'}`,
                marginBottom: -1, textTransform: 'capitalize',
              }}>{tab}</button>
            ))}
          </div>

          {/* Tab: Catalog */}
          {activeTab === 'catalog' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 284px', gap: 16 }}>
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(176px, 1fr))', gap: 10 }}>
                  {filteredItems.map(item => (
                    <div key={item.id} style={{
                      background: c.card, border: `1px solid ${c.cardBorder}`,
                      borderRadius: 7, overflow: 'hidden', cursor: 'pointer',
                      transition: 'border-color 0.15s, transform 0.1s',
                    }}
                      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderColor = c.accent }}
                      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderColor = c.cardBorder }}
                    >
                      {/* Thumbnail */}
                      <div style={{
                        height: 88, position: 'relative',
                        background: `linear-gradient(135deg, ${item.color}18 0%, ${item.color}3A 100%)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <Box size={28} style={{ color: item.color }} />
                        {item.favorited && (
                          <Star size={11} style={{ position: 'absolute', top: 7, right: 8, color: '#FBBF24', fill: '#FBBF24' }} />
                        )}
                        {item.badge && (
                          <span style={{
                            position: 'absolute', top: 7, left: 8,
                            padding: '1px 5px', borderRadius: 3, fontSize: 9, fontWeight: 700,
                            background: badgeColors[item.badge] ?? c.accent, color: '#FFF',
                            textTransform: 'uppercase', letterSpacing: '0.05em',
                          }}>{item.badge}</span>
                        )}
                      </div>
                      {/* Info */}
                      <div style={{ padding: '9px 11px' }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: c.text, marginBottom: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {item.title}
                        </div>
                        <div style={{ fontSize: 11, color: c.muted, marginBottom: 6 }}>{item.creator}</div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                          {item.tags.slice(0, 2).map(t => (
                            <span key={t} style={{ fontSize: 10, padding: '1px 5px', background: c.tag, color: c.tagText, borderRadius: 3 }}>#{t}</span>
                          ))}
                          <span style={{ fontSize: 10, color: c.muted, marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 2 }}>
                            <FileText size={9} /> {item.files}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              {/* Import wizard */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: c.muted, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>Quick Import</div>
                <ImportWizard c={c} />
              </div>
            </div>
          )}

          {/* Tab: Tags */}
          {activeTab === 'tags' && (
            <div style={{ background: c.card, border: `1px solid ${c.cardBorder}`, borderRadius: 8, padding: 20 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: c.muted, marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Tag cloud — {MOCK_STATS.tags} total tags</div>
              <TagCloud c={c} />
            </div>
          )}

          {/* Tab: Jobs */}
          {activeTab === 'jobs' && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: c.muted, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{MOCK_STATS.jobsRunning} running · 1 queued · 1 failed</div>
              <JobsPanel c={c} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
