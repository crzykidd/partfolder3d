/**
 * ModelViewer — in-browser 3D viewer (three.js + @react-three/fiber + drei).
 *
 * This file is ONLY imported via React.lazy in DownloadsPanel.tsx.
 * Vite code-splits it into its own async chunk so three.js never appears
 * in the initial bundle.
 *
 * Supports: .stl (STLLoader → BufferGeometry),
 *           .obj (OBJLoader → Group),
 *           .3mf (ThreeMFLoader → Group)
 *
 * Files are fetched from the existing /api/items/{key}/files/{path} endpoint.
 * Same-origin cookies are sent automatically by the browser — no special
 * auth headers needed.
 */

import React, {
  Component,
  type ReactNode,
  Suspense,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { Canvas, useLoader, useThree } from '@react-three/fiber'
import { OrbitControls, Bounds, Center, Html, useProgress } from '@react-three/drei'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js'
import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Error boundary — catches loader failures (bad mesh, 404, etc.)
// ---------------------------------------------------------------------------

interface ErrState { error: Error | null }
class LoaderErrorBoundary extends Component<
  { children: ReactNode; onError: (e: Error) => void },
  ErrState
> {
  state: ErrState = { error: null }

  static getDerivedStateFromError(error: Error): ErrState {
    return { error }
  }

  componentDidCatch(error: Error) {
    this.props.onError(error)
  }

  render() {
    if (this.state.error) return null // parent shows error overlay
    return this.props.children
  }
}

// ---------------------------------------------------------------------------
// Scene background — reads theme preference at mount time
// ---------------------------------------------------------------------------

function SceneBackground({ isDark }: { isDark: boolean }) {
  const { scene } = useThree()
  useEffect(() => {
    const prev = scene.background
    scene.background = new THREE.Color(isDark ? '#18181b' : '#f0f0f0')
    return () => {
      scene.background = prev
    }
  }, [scene, isDark])
  return null
}

// ---------------------------------------------------------------------------
// Loading progress overlay (inside Canvas via drei Html)
// ---------------------------------------------------------------------------

function LoadingOverlay() {
  const { active, progress } = useProgress()
  if (!active) return null
  return (
    <Html center>
      <div
        style={{
          color: '#fff',
          background: 'rgba(0,0,0,0.55)',
          padding: '6px 14px',
          borderRadius: 6,
          fontSize: 12,
          whiteSpace: 'nowrap',
        }}
      >
        Loading {progress.toFixed(0)}%
      </div>
    </Html>
  )
}

// ---------------------------------------------------------------------------
// STL model
// ---------------------------------------------------------------------------

function STLModel({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url)
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ color: '#9ca3af', roughness: 0.5, metalness: 0.1 }),
    [],
  )
  useEffect(() => () => material.dispose(), [material])

  return (
    <Center>
      <mesh geometry={geometry} material={material} />
    </Center>
  )
}

// ---------------------------------------------------------------------------
// OBJ model — apply neutral material to every mesh
// ---------------------------------------------------------------------------

function OBJModel({ url }: { url: string }) {
  const obj = useLoader(OBJLoader, url)
  const material = useMemo(
    () => new THREE.MeshStandardMaterial({ color: '#9ca3af', roughness: 0.5, metalness: 0.1 }),
    [],
  )

  useEffect(() => {
    obj.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.material = material
      }
    })
  }, [obj, material])

  useEffect(() => () => material.dispose(), [material])

  return (
    <Center>
      <primitive object={obj} />
    </Center>
  )
}

// ---------------------------------------------------------------------------
// 3MF model — preserves embedded slicer colours
// ---------------------------------------------------------------------------

function ThreeMFModel({ url }: { url: string }) {
  // ThreeMFLoader returns a Group; cast via unknown for r3f's generic loader type
  const group = useLoader(
    ThreeMFLoader as unknown as new () => THREE.Loader<THREE.Group>,
    url,
  )

  return (
    <Center>
      <primitive object={group} />
    </Center>
  )
}

// ---------------------------------------------------------------------------
// Scene switcher — picks loader by file extension
// ---------------------------------------------------------------------------

type SupportedExt = '.stl' | '.obj' | '.3mf'

function ModelScene({ fileUrl, ext }: { fileUrl: string; ext: SupportedExt }) {
  return (
    <>
      {ext === '.stl' && <STLModel url={fileUrl} />}
      {ext === '.obj' && <OBJModel url={fileUrl} />}
      {ext === '.3mf' && <ThreeMFModel url={fileUrl} />}
    </>
  )
}

// ---------------------------------------------------------------------------
// Two-light setup
// ---------------------------------------------------------------------------

function Lights() {
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 10, 5]} intensity={1.0} castShadow={false} />
      <directionalLight position={[-5, -5, -5]} intensity={0.4} />
    </>
  )
}

// ---------------------------------------------------------------------------
// Public component (default export — consumed by React.lazy in DownloadsPanel)
// ---------------------------------------------------------------------------

export interface ModelViewerProps {
  /** Full file URL, e.g. /api/items/{key}/files/{path} */
  fileUrl: string
  /** Lowercase extension without leading dot, e.g. "stl" */
  ext: string
  /** Called when the user closes the viewer */
  onClose: () => void
}

export default function ModelViewer({ fileUrl, ext, onClose }: ModelViewerProps) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const [loadError, setLoadError] = useState<Error | null>(null)

  // Normalise extension to include leading dot
  const normExt = (ext.startsWith('.') ? ext : '.' + ext).toLowerCase() as SupportedExt

  // ESC key closes the viewer
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    /* Modal backdrop — click outside the card to close */
    <div
      role="dialog"
      aria-modal="true"
      aria-label="3D model viewer"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.72)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* Viewer card */}
      <div
        style={{
          position: 'relative',
          width: '90vw',
          height: '85vh',
          maxWidth: 1200,
          borderRadius: 12,
          overflow: 'hidden',
          boxShadow: '0 25px 60px rgba(0,0,0,0.55)',
          background: isDark ? '#18181b' : '#f0f0f0',
        }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          aria-label="Close 3D viewer"
          style={{
            position: 'absolute',
            top: 10,
            right: 10,
            zIndex: 20,
            padding: '5px 12px',
            background: 'rgba(0,0,0,0.55)',
            color: '#fff',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          Close
        </button>

        {/* Error overlay (rendered outside Canvas so it shows even if WebGL fails) */}
        {loadError && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              zIndex: 10,
              color: isDark ? '#fca5a5' : '#b91c1c',
              background: isDark ? '#18181b' : '#f0f0f0',
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 600 }}>Failed to load 3D model</span>
            <span
              style={{
                fontSize: 11,
                color: isDark ? '#a1a1aa' : '#71717a',
                maxWidth: 320,
                textAlign: 'center',
              }}
            >
              {loadError.message || 'Unknown error'}
            </span>
            <button
              onClick={onClose}
              style={{
                marginTop: 8,
                padding: '4px 14px',
                cursor: 'pointer',
                fontSize: 12,
                borderRadius: 5,
                border: '1px solid currentColor',
                background: 'transparent',
                color: 'inherit',
              }}
            >
              Close
            </button>
          </div>
        )}

        {/* Canvas — only rendered when no error */}
        {!loadError && (
          <Canvas
            camera={{ position: [0, 0, 5], fov: 45, near: 0.01, far: 100000 }}
            gl={{ antialias: true }}
            style={{ width: '100%', height: '100%' }}
          >
            <SceneBackground isDark={isDark} />
            <Lights />
            {/* No maxDistance cap; near/far are wide (above) so dollying out never
                clips the model. `clip` intentionally omitted — it tightens the frustum
                to the object and made zoom-out clip the mesh. */}
            <OrbitControls makeDefault enableDamping dampingFactor={0.05} minDistance={0.01} />
            {/* Suspense is OUTSIDE Bounds so `fit` runs against the loaded geometry, not the
                loading placeholder — otherwise the default view opens zoomed all the way in. */}
            <LoaderErrorBoundary onError={setLoadError}>
              <Suspense fallback={<LoadingOverlay />}>
                <Bounds fit observe margin={1.2}>
                  <ModelScene fileUrl={fileUrl} ext={normExt} />
                </Bounds>
              </Suspense>
            </LoaderErrorBoundary>
          </Canvas>
        )}
      </div>
    </div>
  )
}
