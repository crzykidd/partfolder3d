/**
 * ProcessingOverlay — spinner shown while the session status is "processing".
 */

interface ProcessingOverlayProps {
  sessionId: string
}

export function ProcessingOverlay({ sessionId }: ProcessingOverlayProps) {
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
