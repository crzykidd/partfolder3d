/**
 * Example 2 — "Atelier"
 *
 * Airy, premium top-nav layout. Light-first, warm neutrals, generous whitespace,
 * rounded cards, soft shadows, tasteful teal CTAs — "polished consumer SaaS."
 * Uses @radix-ui/react-dropdown-menu for the primary nav dropdowns.
 *
 * All data is mock — no API calls, no auth context required.
 */

import { useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import {
  LayoutGrid, Tag, Users, Heart, PlusCircle, Inbox, Package, Cpu, Calendar,
  AlertTriangle, GitBranch, Eye, User, Mail, Zap, Settings, Archive, Download,
  Hash, SlidersHorizontal, Search, Sun, Moon, LogOut, ExternalLink,
  Box, FileText, CheckCircle2, Circle, Star, Activity, ChevronDown,
  type LucideIcon,
} from 'lucide-react'
import {
  MOCK_ITEMS, MOCK_STATS, MOCK_TAG_CLOUD, MOCK_CREATORS,
  MOCK_VERSION, RELEASES_URL, NAV_GROUPS, canSeeGroup,
  type Role, type NavGroup,
} from './mockData'

// ─── Color schemes ────────────────────────────────────────────────────────────

const LIGHT = {
  root:          '#FAFAF8',
  nav:           '#FFFFFF',
  navBorder:     '#ECEAE5',
  card:          '#FFFFFF',
  cardShadow:    '0 1px 4px rgba(0,0,0,0.07), 0 4px 14px rgba(0,0,0,0.04)',
  cardHoverShadow: '0 2px 8px rgba(0,0,0,0.1), 0 6px 20px rgba(0,0,0,0.06)',
  text:          '#1C1917',
  textDim:       '#44403C',
  muted:         '#78716C',
  accent:        '#0FA4AB',
  accentFg:      '#FFFFFF',
  accentLight:   '#E8F9FA',
  accentMid:     'rgba(15,164,171,0.15)',
  border:        '#E7E5E4',
  tag:           '#F5F3F0',
  tagText:       '#78716C',
  tagAccent:     '#E8F9FA',
  tagAccentText: '#0c7a80',
  input:         '#F5F3F0',
  inputBorder:   '#E7E5E4',
  section:       '#F5F3F0',
  sectionBorder: '#E7E5E4',
  success:       '#16A34A',
  warn:          '#D97706',
  danger:        '#DC2626',
  dropdownBg:    '#FFFFFF',
  dropdownBorder:'#E7E5E4',
  dropdownHover: '#F5F3F0',
  footerBg:      '#F5F3F0',
  footerText:    '#78716C',
}

const DARK = {
  root:          '#1C1917',
  nav:           '#0C0A09',
  navBorder:     '#292524',
  card:          '#292524',
  cardShadow:    '0 1px 4px rgba(0,0,0,0.3)',
  cardHoverShadow: '0 4px 12px rgba(0,0,0,0.4)',
  text:          '#FAFAF9',
  textDim:       '#D6D3D1',
  muted:         '#A8A29E',
  accent:        '#0FA4AB',
  accentFg:      '#FFFFFF',
  accentLight:   'rgba(15,164,171,0.12)',
  accentMid:     'rgba(15,164,171,0.18)',
  border:        '#44403C',
  tag:           '#3A3533',
  tagText:       '#D6D3D1',
  tagAccent:     'rgba(15,164,171,0.15)',
  tagAccentText: '#5ecdd3',
  input:         '#3A3533',
  inputBorder:   '#57534E',
  section:       '#292524',
  sectionBorder: '#44403C',
  success:       '#22C55E',
  warn:          '#F59E0B',
  danger:        '#EF4444',
  dropdownBg:    '#292524',
  dropdownBorder:'#57534E',
  dropdownHover: '#3A3533',
  footerBg:      '#0C0A09',
  footerText:    '#78716C',
}

type C = typeof LIGHT

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

function NavIcon({ name }: { name: string }) {
  const Icon = ICON_MAP[name] ?? Box
  return <Icon size={14} />
}

// ─── Radix nav dropdown ───────────────────────────────────────────────────────

function NavDropdown({ group, c }: { group: NavGroup; c: C }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '6px 12px', border: 'none', borderRadius: 8,
          background: 'transparent', color: c.textDim, fontSize: 13.5,
          fontWeight: 500, cursor: 'pointer',
          transition: 'background 0.12s, color 0.12s',
        }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.background = c.section
            ;(e.currentTarget as HTMLButtonElement).style.color = c.text
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent'
            ;(e.currentTarget as HTMLButtonElement).style.color = c.textDim
          }}
        >
          {group.label}
          <ChevronDown size={13} style={{ opacity: 0.6 }} />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          sideOffset={8}
          style={{
            background: c.dropdownBg,
            border: `1px solid ${c.dropdownBorder}`,
            borderRadius: 12,
            padding: '6px',
            minWidth: 200,
            boxShadow: '0 8px 30px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)',
            zIndex: 9999,
            animation: 'fadeIn 0.1s ease',
          }}
        >
          {group.items.map(item => (
            <DropdownMenu.Item key={item.label}
              onSelect={() => undefined}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 12px', borderRadius: 8,
                cursor: 'pointer', fontSize: 13.5, color: c.textDim,
                outline: 'none',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.background = c.dropdownHover
                ;(e.currentTarget as HTMLElement).style.color = c.text
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.background = 'transparent'
                ;(e.currentTarget as HTMLElement).style.color = c.textDim
              }}
            >
              <span style={{ color: c.accent, display: 'flex' }}><NavIcon name={item.icon} /></span>
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.badge != null && (
                <span style={{
                  background: c.accent, color: c.accentFg,
                  borderRadius: 10, padding: '1px 7px',
                  fontSize: 11, fontWeight: 700,
                }}>{item.badge}</span>
              )}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

// ─── Import Wizard ────────────────────────────────────────────────────────────

const WIZARD_STEPS = ['Source', 'Configure', 'Preview', 'Done']

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
    <div style={{
      background: c.card, borderRadius: 16,
      boxShadow: c.cardShadow, overflow: 'hidden',
    }}>
      {/* Step tabs */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${c.border}` }}>
        {WIZARD_STEPS.map((s, i) => (
          <button key={s} onClick={() => !importing && !done && setStep(i)}
            style={{
              flex: 1, padding: '14px 0', border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: i === step ? 700 : 400,
              background: 'transparent',
              color: i === step ? c.accent : i < step ? c.muted : c.muted,
              borderBottom: `2px solid ${i === step ? c.accent : 'transparent'}`,
              marginBottom: -1,
              transition: 'color 0.15s',
            }}
          >
            <span style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: 20, height: 20, borderRadius: '50%', marginRight: 6,
              fontSize: 10, fontWeight: 700,
              background: i < step || done ? c.accent : i === step ? c.accentMid : c.section,
              color: i < step || done ? c.accentFg : i === step ? c.accent : c.muted,
            }}>
              {i < step || done ? '✓' : i + 1}
            </span>
            {s}
          </button>
        ))}
      </div>

      {/* Body */}
      <div style={{ padding: '20px 24px' }}>
        {step === 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {['URL / Thingiverse', 'Local File', 'ZIP Archive', 'Template'].map((src, i) => (
              <button key={src} style={{
                padding: '14px 16px', borderRadius: 12,
                border: `1.5px solid ${i === 0 ? c.accent : c.border}`,
                background: i === 0 ? c.accentLight : 'transparent',
                color: i === 0 ? c.accent : c.textDim,
                fontSize: 13.5, fontWeight: i === 0 ? 600 : 400,
                cursor: 'pointer', textAlign: 'left',
                transition: 'all 0.12s',
              }}>{src}</button>
            ))}
          </div>
        )}

        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ padding: '10px 14px', background: c.accentLight, border: `1px solid ${c.accentMid}`, borderRadius: 10, fontSize: 12.5, color: c.accent, fontWeight: 500 }}>
              ✦ Scraped from Printables · 4 files · 1 preview image
            </div>
            {[
              ['Title',   'Gridfinity Baseplate 2×4 Lite'],
              ['Creator', 'Zack Freedman'],
              ['Library', 'Primary Collection'],
            ].map(([label, val]) => (
              <div key={label}>
                <div style={{ fontSize: 12, fontWeight: 600, color: c.muted, marginBottom: 5 }}>{label}</div>
                <div style={{
                  padding: '10px 14px', borderRadius: 10,
                  border: `1.5px solid ${c.inputBorder}`,
                  background: c.input, color: c.text, fontSize: 13.5,
                }}>{val}</div>
              </div>
            ))}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: c.muted, marginBottom: 8 }}>Tags</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {['gridfinity', 'storage', 'organizer'].map(t => (
                  <span key={t} style={{ padding: '4px 10px', background: c.tagAccent, color: c.tagAccentText, borderRadius: 20, fontSize: 12, fontWeight: 500 }}>#{t}</span>
                ))}
                {['2x4', 'lite'].map(t => (
                  <span key={t} style={{ padding: '4px 10px', background: c.accentLight, color: c.accent, borderRadius: 20, fontSize: 12, fontWeight: 500, border: `1px dashed ${c.accent}` }}>#{t} — pending</span>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <div style={{ fontSize: 12, color: c.muted, marginBottom: 12 }}>4 files ready to import</div>
            {['gridfinity-baseplate-2x4.3mf','gridfinity-baseplate-2x4.stl','gridfinity-baseplate-2x4.step','preview.png'].map(f => (
              <div key={f} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 0', borderBottom: `1px solid ${c.border}`,
                fontSize: 13.5, color: c.textDim,
              }}>
                <FileText size={14} style={{ color: c.muted, flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{f}</span>
                <span style={{ fontSize: 12, color: c.muted }}>{f.endsWith('.3mf') ? '1.2 MB' : f.endsWith('.stl') ? '840 KB' : f.endsWith('.step') ? '220 KB' : '48 KB'}</span>
              </div>
            ))}
          </div>
        )}

        {step === 3 && (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            {done ? (
              <>
                <CheckCircle2 size={40} style={{ color: c.success, margin: '0 auto 12px', display: 'block' }} />
                <div style={{ fontSize: 18, fontWeight: 700, color: c.text }}>All done!</div>
                <div style={{ fontSize: 13.5, color: c.muted, marginTop: 6 }}>4 files added to Primary Collection</div>
                <button onClick={reset} style={{ marginTop: 20, padding: '10px 24px', background: c.accentLight, color: c.accent, border: `1.5px solid ${c.accentMid}`, borderRadius: 10, fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>
                  Import another
                </button>
              </>
            ) : importing ? (
              <>
                <div style={{ fontSize: 13.5, color: c.muted, marginBottom: 14 }}>Importing 4 files…</div>
                <div style={{ height: 6, background: c.section, borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '65%', background: c.accent, borderRadius: 3 }} />
                </div>
              </>
            ) : (
              <>
                <Circle size={40} style={{ color: c.border, margin: '0 auto 12px', display: 'block' }} />
                <div style={{ fontSize: 13.5, color: c.muted }}>Ready to import 4 files</div>
                <button onClick={startImport} style={{ marginTop: 20, padding: '11px 28px', background: c.accent, color: c.accentFg, border: 'none', borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: 'pointer', boxShadow: `0 4px 14px rgba(15,164,171,0.35)` }}>
                  Start Import
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Footer nav */}
      {!done && (
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 24px', borderTop: `1px solid ${c.border}`, background: c.section }}>
          <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}
            style={{ padding: '8px 18px', borderRadius: 10, border: `1.5px solid ${c.border}`, background: 'transparent', color: step === 0 ? c.muted : c.textDim, fontSize: 13.5, cursor: step === 0 ? 'default' : 'pointer', opacity: step === 0 ? 0.5 : 1 }}>
            ← Back
          </button>
          {step < WIZARD_STEPS.length - 1 ? (
            <button onClick={() => setStep(s => Math.min(WIZARD_STEPS.length - 1, s + 1))}
              style={{ padding: '8px 20px', background: c.accent, color: c.accentFg, border: 'none', borderRadius: 10, fontSize: 13.5, fontWeight: 600, cursor: 'pointer', boxShadow: `0 4px 12px rgba(15,164,171,0.3)` }}>
              Continue →
            </button>
          ) : <span />}
        </div>
      )}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function Example2() {
  const [isDark, setIsDark] = useState(false)
  const [role, setRole] = useState<Role>('admin')
  const [search, setSearch] = useState('')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [activeSection, setActiveSection] = useState<'catalog' | 'creators' | 'wizard'>('catalog')

  const c = isDark ? DARK : LIGHT
  const visibleGroups = NAV_GROUPS.filter(g => canSeeGroup(g, role))

  const filteredItems = MOCK_ITEMS.filter(item =>
    !search || item.title.toLowerCase().includes(search.toLowerCase()) || item.tags.some(t => t.includes(search.toLowerCase()))
  )

  const badgeColors: Record<string, string> = {
    new: '#0FA4AB', rendered: '#16A34A', printing: '#D97706', rendering: '#8B5CF6',
  }

  return (
    <div style={{
      minHeight: '100vh', background: c.root, color: c.text,
      fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
    }}
      onClick={() => showUserMenu && setShowUserMenu(false)}
    >
      {/* ── Top Nav ── */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 50,
        background: c.nav, borderBottom: `1px solid ${c.navBorder}`,
        height: 60,
      }}>
        <div style={{
          display: 'flex', alignItems: 'center',
          height: '100%', padding: '0 28px', gap: 8,
          maxWidth: 1400, margin: '0 auto',
        }}>
          {/* Logo */}
          <div style={{ fontWeight: 800, fontSize: 16.5, letterSpacing: '-0.02em', marginRight: 16 }}>
            <span style={{ color: c.accent }}>Part</span><span style={{ color: c.text }}>Folder</span>
            <span style={{ color: c.muted, fontWeight: 400, fontSize: 14 }}> 3D</span>
          </div>

          {/* Nav dropdowns */}
          <div style={{ display: 'flex', gap: 2, flex: 1 }}>
            {visibleGroups.map(group => (
              <NavDropdown key={group.id} group={group} c={c} />
            ))}
          </div>

          {/* Search */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '7px 14px', background: c.input,
            border: `1.5px solid ${c.inputBorder}`, borderRadius: 10,
            width: 240, transition: 'border-color 0.15s, width 0.2s',
          }}
            onFocus={() => undefined}
          >
            <Search size={14} style={{ color: c.muted, flexShrink: 0 }} />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search models, tags…"
              style={{ background: 'transparent', border: 'none', outline: 'none', color: c.text, fontSize: 13.5, width: '100%' }} />
            <span style={{ color: c.muted, fontSize: 11, flexShrink: 0, opacity: 0.7 }}>⌘K</span>
          </div>

          {/* Theme */}
          <button onClick={() => setIsDark(!isDark)}
            style={{ background: c.input, border: `1.5px solid ${c.border}`, borderRadius: 9, cursor: 'pointer', color: c.muted, display: 'flex', padding: '7px', marginLeft: 4 }}>
            {isDark ? <Sun size={15} /> : <Moon size={15} />}
          </button>

          {/* Avatar */}
          <div style={{ position: 'relative', marginLeft: 4 }}>
            <button onClick={e => { e.stopPropagation(); setShowUserMenu(!showUserMenu) }} style={{
              width: 34, height: 34, borderRadius: '50%',
              background: `linear-gradient(135deg, #0FA4AB 0%, #091D35 100%)`,
              color: '#FFF', border: 'none', cursor: 'pointer',
              fontSize: 13.5, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(15,164,171,0.35)',
            }}>A</button>
            {showUserMenu && (
              <div onClick={e => e.stopPropagation()} style={{
                position: 'absolute', top: 42, right: 0, zIndex: 200,
                background: c.dropdownBg, border: `1px solid ${c.dropdownBorder}`,
                borderRadius: 14, padding: '6px',
                minWidth: 200, boxShadow: '0 8px 30px rgba(0,0,0,0.15)',
              }}>
                <div style={{ padding: '10px 14px 10px', borderBottom: `1px solid ${c.border}`, marginBottom: 4 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: c.text }}>Admin User</div>
                  <div style={{ fontSize: 12, color: c.muted }}>admin@partfolder.local</div>
                </div>
                <button onClick={() => { setIsDark(!isDark); setShowUserMenu(false) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 13.5, color: c.textDim, borderRadius: 9 }}>
                  {isDark ? <Sun size={14} /> : <Moon size={14} />} Toggle theme
                </button>
                <a href={RELEASES_URL} target="_blank" rel="noreferrer"
                  style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 14px', fontSize: 13.5, color: c.textDim, textDecoration: 'none', borderRadius: 9 }}>
                  <ExternalLink size={14} /> v{MOCK_VERSION} — Release notes
                </a>
                <div style={{ borderTop: `1px solid ${c.border}`, marginTop: 4, paddingTop: 4 }}>
                  <button style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 14px', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 13.5, color: c.danger, borderRadius: 9 }}>
                    <LogOut size={14} /> Sign out
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* ── Role banner ── */}
      <div style={{
        background: c.accentLight, borderBottom: `1px solid ${c.accentMid}`,
        padding: '8px 28px', display: 'flex', alignItems: 'center', gap: 12,
        maxWidth: 1400, margin: '0 auto',
      }}>
        <span style={{ fontSize: 12.5, color: c.accent, fontWeight: 500 }}>Viewing as:</span>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['admin', 'editor', 'viewer'] as Role[]).map(r => (
            <button key={r} onClick={() => setRole(r)} style={{
              padding: '3px 12px', borderRadius: 20, border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: r === role ? 700 : 400,
              background: r === role ? c.accent : 'transparent',
              color: r === role ? c.accentFg : c.accent,
              textTransform: 'capitalize',
            }}>{r}</button>
          ))}
        </div>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: c.accent, opacity: 0.7 }}>
          {visibleGroups.reduce((n, g) => n + g.items.length, 0)} nav items visible
        </span>
      </div>

      {/* ── Page content ── */}
      <main style={{ maxWidth: 1400, margin: '0 auto', padding: '36px 28px' }}>
        {/* Stats row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 36 }}>
          {[
            { label: 'Total Models',  value: MOCK_STATS.total.toLocaleString(), sub: '+14 this week',     icon: <LayoutGrid size={16} />, color: c.accent  },
            { label: 'Prints Done',   value: MOCK_STATS.printed.toLocaleString(), sub: '91% success rate', icon: <Activity size={16} />,   color: '#16A34A' },
            { label: 'Filament',      value: `${MOCK_STATS.filamentKg} kg`,        sub: `${MOCK_STATS.filamentKm} km used`, icon: <Package size={16} />, color: '#D97706' },
            { label: 'Creators',      value: MOCK_STATS.creators.toLocaleString(), sub: '12 linked to users', icon: <Users size={16} />, color: '#8B5CF6' },
            { label: 'Jobs Running',  value: String(MOCK_STATS.jobsRunning),        sub: '1 queued · 1 failed', icon: <Cpu size={16} />,   color: c.accent  },
          ].map(s => (
            <div key={s.label} style={{
              background: c.card, borderRadius: 16,
              boxShadow: c.cardShadow, padding: '20px 22px',
              transition: 'box-shadow 0.2s, transform 0.15s',
            }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLDivElement).style.boxShadow = c.cardHoverShadow
                ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-1px)'
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLDivElement).style.boxShadow = c.cardShadow
                ;(e.currentTarget as HTMLDivElement).style.transform = 'none'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: c.muted }}>{s.label}</div>
                <div style={{ color: s.color, opacity: 0.8 }}>{s.icon}</div>
              </div>
              <div style={{ fontSize: 26, fontWeight: 800, color: c.text, fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>{s.value}</div>
              <div style={{ fontSize: 11.5, color: c.muted, marginTop: 4 }}>{s.sub}</div>
            </div>
          ))}
        </div>

        {/* Section tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
          {(['catalog', 'creators', 'wizard'] as const).map(tab => (
            <button key={tab} onClick={() => setActiveSection(tab)} style={{
              padding: '9px 20px', borderRadius: 10, border: 'none', cursor: 'pointer',
              fontSize: 13.5, fontWeight: activeSection === tab ? 600 : 400,
              background: activeSection === tab ? c.accent : c.card,
              color: activeSection === tab ? c.accentFg : c.muted,
              boxShadow: activeSection === tab ? `0 4px 12px rgba(15,164,171,0.3)` : c.cardShadow,
              textTransform: 'capitalize', transition: 'all 0.15s',
            }}>{tab === 'wizard' ? 'Import Wizard' : tab.charAt(0).toUpperCase() + tab.slice(1)}</button>
          ))}
        </div>

        {/* Catalog */}
        {activeSection === 'catalog' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 18 }}>
            {filteredItems.map(item => (
              <div key={item.id} style={{
                background: c.card, borderRadius: 16,
                boxShadow: c.cardShadow, overflow: 'hidden', cursor: 'pointer',
                transition: 'box-shadow 0.2s, transform 0.15s',
              }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLDivElement).style.boxShadow = c.cardHoverShadow
                  ;(e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLDivElement).style.boxShadow = c.cardShadow
                  ;(e.currentTarget as HTMLDivElement).style.transform = 'none'
                }}
              >
                {/* Thumbnail */}
                <div style={{
                  height: 128, position: 'relative',
                  background: `linear-gradient(135deg, ${item.color}12 0%, ${item.color}28 100%)`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Box size={36} style={{ color: item.color, opacity: 0.85 }} />
                  {item.favorited && (
                    <Star size={14} style={{ position: 'absolute', top: 10, right: 12, color: '#F59E0B', fill: '#F59E0B' }} />
                  )}
                  {item.badge && (
                    <span style={{
                      position: 'absolute', top: 10, left: 12,
                      padding: '2px 8px', borderRadius: 6, fontSize: 10, fontWeight: 700,
                      background: badgeColors[item.badge] ?? c.accent, color: '#FFF',
                      textTransform: 'uppercase', letterSpacing: '0.04em',
                    }}>{item.badge}</span>
                  )}
                </div>
                {/* Info */}
                <div style={{ padding: '14px 16px 16px' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: c.text, marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.title}
                  </div>
                  <div style={{ fontSize: 12.5, color: c.muted, marginBottom: 10 }}>{item.creator}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
                    {item.tags.slice(0, 3).map(t => (
                      <span key={t} style={{ padding: '3px 8px', background: c.tag, color: c.tagText, borderRadius: 6, fontSize: 11.5 }}>#{t}</span>
                    ))}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, color: c.muted }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <FileText size={11} /> {item.files} files
                    </span>
                    <span>{(item.sizeKb / 1024).toFixed(1)} MB</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Creators */}
        {activeSection === 'creators' && (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16, marginBottom: 28 }}>
              {MOCK_CREATORS.map(creator => (
                <div key={creator.id} style={{
                  background: c.card, borderRadius: 16, padding: '20px 22px',
                  boxShadow: c.cardShadow, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14,
                }}>
                  <div style={{
                    width: 46, height: 46, borderRadius: '50%', flexShrink: 0,
                    background: `linear-gradient(135deg, ${creator.color}33, ${creator.color}66)`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 18, fontWeight: 800, color: creator.color,
                  }}>
                    {creator.name[0]}
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: c.text }}>{creator.name}</div>
                    <div style={{ fontSize: 12.5, color: c.muted }}>{creator.models} models</div>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ background: c.card, borderRadius: 16, padding: '22px 24px', boxShadow: c.cardShadow }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: c.text, marginBottom: 14 }}>Popular tags</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {MOCK_TAG_CLOUD.map(tag => {
                  const max = MOCK_TAG_CLOUD[0].count
                  const rel = tag.count / max
                  return (
                    <span key={tag.label} style={{
                      padding: '5px 12px',
                      fontSize: 11 + Math.round(rel * 5),
                      background: rel > 0.6 ? c.tagAccent : c.tag,
                      color: rel > 0.6 ? c.tagAccentText : c.tagText,
                      borderRadius: 20, cursor: 'pointer',
                      fontWeight: rel > 0.5 ? 600 : 400,
                    }}>#{tag.label}<span style={{ fontSize: 10, opacity: 0.7, marginLeft: 4 }}>{tag.count}</span></span>
                  )
                })}
              </div>
            </div>
          </div>
        )}

        {/* Import Wizard */}
        {activeSection === 'wizard' && (
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <div style={{ marginBottom: 20 }}>
              <h2 style={{ fontSize: 22, fontWeight: 800, color: c.text, letterSpacing: '-0.02em', margin: 0 }}>Import an Asset</h2>
              <p style={{ fontSize: 13.5, color: c.muted, marginTop: 6 }}>Paste a URL or upload files to add a new model to your collection.</p>
            </div>
            <ImportWizard c={c} />
          </div>
        )}
      </main>

      {/* ── Footer ── */}
      <footer style={{ background: c.footerBg, borderTop: `1px solid ${c.border}`, padding: '16px 28px', marginTop: 40 }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: c.footerText }}>PartFolder 3D · v{MOCK_VERSION}</span>
          <a href={RELEASES_URL} target="_blank" rel="noreferrer"
            style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: c.accent, textDecoration: 'none', fontWeight: 500 }}>
            Release notes <ExternalLink size={11} />
          </a>
        </div>
      </footer>
    </div>
  )
}
