/**
 * /examples — landing page that links to all three UI prototypes.
 * The owner can flip between them and pick a direction.
 */

import { type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

const EXAMPLES = [
  {
    path: '/example1',
    name: 'Mission Control',
    tagline: 'Dense · Dark-first · Left rail',
    description:
      'Linear/Vercel-grade pro dashboard. Navy surfaces, teal accent, compact spacing, collapsible icon rail, keyboard-friendly. The "serious tool" aesthetic.',
    accent: '#0FA4AB',
    bg: 'linear-gradient(135deg, #091D35 0%, #050E1A 100%)',
    fg: '#DCE8F5',
    border: '#152E4D',
    tag: 'rgba(15,164,171,0.18)',
    tagText: '#0FA4AB',
    previewItems: ['Dense compact nav groups', 'Stats bar with live jobs', 'Dark catalog grid', 'Inline import wizard'],
  },
  {
    path: '/example2',
    name: 'Atelier',
    tagline: 'Airy · Light-first · Top nav',
    description:
      'Polished consumer SaaS. Warm off-white canvas, generous whitespace, rounded cards with soft shadows, Radix dropdown menus, tasteful teal CTAs.',
    accent: '#0FA4AB',
    bg: 'linear-gradient(135deg, #FAFAF8 0%, #F0F7F8 100%)',
    fg: '#1C1917',
    border: '#E7E5E4',
    tag: '#E8F9FA',
    tagText: '#0c7a80',
    previewItems: ['Radix dropdown top nav', 'Role-based menus', 'Card grid + big stats', 'Stepped import wizard'],
  },
  {
    path: '/example3',
    name: 'Aurora',
    tagline: 'Glassy · Dark canvas · ⌘K palette',
    description:
      'Highest-polish, most distinctive. Deep gradient backdrop, frosted-glass sidebar with animated collapse, pill nav with teal glow, and a fully functional ⌘K command palette.',
    accent: '#0FA4AB',
    bg: 'linear-gradient(135deg, #050D1C 0%, #081728 100%)',
    fg: '#E0EAF4',
    border: 'rgba(255,255,255,0.08)',
    tag: 'rgba(15,164,171,0.18)',
    tagText: '#0FA4AB',
    previewItems: ['⌘K command palette', 'Glassy animated sidebar', 'Pill nav + teal glow', 'Glass import wizard'],
  },
]

export function ExamplesIndex() {
  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(145deg, #060F1A 0%, #091D35 100%)',
      color: '#DCE8F5',
      fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
      padding: '0 24px 60px',
    }}>
      {/* Header */}
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <div style={{ paddingTop: 60, paddingBottom: 48, textAlign: 'center' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '4px 14px', borderRadius: 20,
            background: 'rgba(15,164,171,0.12)', border: '1px solid rgba(15,164,171,0.3)',
            fontSize: 12, fontWeight: 600, color: '#0FA4AB',
            marginBottom: 20, letterSpacing: '0.06em', textTransform: 'uppercase',
          }}>
            UI Prototype Review
          </div>
          <h1 style={{
            margin: '0 0 16px', fontSize: 40, fontWeight: 800,
            letterSpacing: '-0.03em', lineHeight: 1.15,
            background: 'linear-gradient(135deg, #DCE8F5 0%, #0FA4AB 100%)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          } as CSSProperties}>
            Pick your direction
          </h1>
          <p style={{ margin: 0, fontSize: 16, color: '#5D7E9E', lineHeight: 1.6, maxWidth: 560, marginInline: 'auto' }}>
            Three distinct aesthetics, same feature set. Browse each, then tell me which one to build from.
          </p>
        </div>

        {/* Cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {EXAMPLES.map((ex, i) => (
            <div key={ex.path} style={{
              borderRadius: 20, overflow: 'hidden',
              border: '1px solid rgba(255,255,255,0.07)',
              background: 'rgba(255,255,255,0.02)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              transition: 'border-color 0.2s, transform 0.15s, box-shadow 0.2s',
              display: 'grid', gridTemplateColumns: '1fr 260px',
            } as CSSProperties}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLDivElement
                el.style.borderColor = 'rgba(15,164,171,0.3)'
                el.style.transform = 'translateY(-2px)'
                el.style.boxShadow = '0 12px 40px rgba(0,0,0,0.4)'
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLDivElement
                el.style.borderColor = 'rgba(255,255,255,0.07)'
                el.style.transform = 'none'
                el.style.boxShadow = 'none'
              }}
            >
              {/* Info panel */}
              <div style={{ padding: '32px 36px' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 12 }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 28, height: 28, borderRadius: '50%',
                    background: 'rgba(15,164,171,0.12)', border: '1px solid rgba(15,164,171,0.3)',
                    fontSize: 13, fontWeight: 800, color: '#0FA4AB', flexShrink: 0,
                  }}>{i + 1}</span>
                  <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#E0EAF4' }}>
                    {ex.name}
                  </h2>
                  <span style={{ fontSize: 12, color: '#5D7E9E', fontWeight: 500 }}>{ex.tagline}</span>
                </div>

                <p style={{ margin: '0 0 20px', fontSize: 14, color: '#8BAFC7', lineHeight: 1.65 }}>
                  {ex.description}
                </p>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 24 }}>
                  {ex.previewItems.map(item => (
                    <span key={item} style={{
                      padding: '3px 10px', borderRadius: 20,
                      background: 'rgba(15,164,171,0.1)', border: '1px solid rgba(15,164,171,0.2)',
                      fontSize: 12, color: '#0FA4AB',
                    }}>{item}</span>
                  ))}
                </div>

                <Link to={ex.path} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  padding: '10px 22px', borderRadius: 10,
                  background: '#0FA4AB', color: '#FFFFFF',
                  fontWeight: 700, fontSize: 14, textDecoration: 'none',
                  boxShadow: '0 4px 16px rgba(15,164,171,0.4)',
                  transition: 'opacity 0.15s, transform 0.1s',
                }}>
                  View {ex.name} <ExternalLink size={14} />
                </Link>
              </div>

              {/* Mini preview */}
              <div style={{ background: ex.bg, position: 'relative', overflow: 'hidden', minHeight: 180 }}>
                {/* Simulated sidebar or top bar */}
                {ex.path !== '/example2' ? (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex' }}>
                    {/* Sidebar strip */}
                    <div style={{
                      width: 56, background: 'rgba(0,0,0,0.25)', borderRight: `1px solid ${ex.border}`,
                      display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 12, gap: 8,
                    }}>
                      {[1,2,3,4,5,6].map(n => (
                        <div key={n} style={{
                          width: 28, height: 28, borderRadius: n === 1 ? '50%' : 6,
                          background: n === 1 ? ex.accent : 'rgba(255,255,255,0.06)',
                          border: n === 2 ? `1px solid ${ex.accent}55` : '1px solid transparent',
                        }} />
                      ))}
                    </div>
                    {/* Content */}
                    <div style={{ flex: 1, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {[1,2,3,4].map(n => (
                          <div key={n} style={{ flex: 1, height: 36, borderRadius: 6, background: 'rgba(255,255,255,0.04)', border: `1px solid ${ex.border}` }} />
                        ))}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                        {[1,2,3,4,5,6].map(n => (
                          <div key={n} style={{
                            height: 48, borderRadius: 6,
                            background: n === 1 ? `${ex.accent}22` : 'rgba(255,255,255,0.04)',
                            border: `1px solid ${n === 1 ? ex.accent + '44' : ex.border}`,
                          }} />
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column' }}>
                    {/* Top nav */}
                    <div style={{
                      height: 44, borderBottom: `1px solid ${ex.border}`,
                      background: ex.path === '/example2' ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.05)',
                      display: 'flex', alignItems: 'center', padding: '0 14px', gap: 10,
                    }}>
                      <div style={{ width: 60, height: 10, borderRadius: 4, background: ex.accent + '55' }} />
                      {[1,2,3].map(n => (
                        <div key={n} style={{ width: 40, height: 8, borderRadius: 4, background: `${ex.fg}33` }} />
                      ))}
                      <div style={{ flex: 1 }} />
                      <div style={{ width: 80, height: 24, borderRadius: 6, background: `${ex.fg}11`, border: `1px solid ${ex.border}` }} />
                      <div style={{ width: 24, height: 24, borderRadius: '50%', background: ex.accent + '44' }} />
                    </div>
                    {/* Content */}
                    <div style={{ flex: 1, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ display: 'flex', gap: 8 }}>
                        {[1,2,3,4,5].map(n => (
                          <div key={n} style={{ flex: 1, height: 44, borderRadius: 10, background: `${ex.fg}08`, border: `1px solid ${ex.border}`, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }} />
                        ))}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                        {[1,2,3,4,5,6].map(n => (
                          <div key={n} style={{
                            height: 50, borderRadius: 10,
                            background: `${ex.fg}08`,
                            border: `1px solid ${ex.border}`,
                            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                          }} />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ textAlign: 'center', marginTop: 48, color: '#4A6B84', fontSize: 13 }}>
          <p style={{ margin: 0 }}>
            Each prototype is at{' '}
            {['/example1', '/example2', '/example3'].map((p, i, arr) => (
              <span key={p}>
                <Link to={p} style={{ color: '#0FA4AB', textDecoration: 'none' }}>{p}</Link>
                {i < arr.length - 1 ? ', ' : ''}
              </span>
            ))}.
            {' '}All data is mocked — no backend needed.
          </p>
        </div>
      </div>
    </div>
  )
}
