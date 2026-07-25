/**
 * Tests for lib/openscadPlayground.ts — the OpenSCAD Playground deep-link encoder.
 *
 * Covers: playgroundUrl() round-trips through the playground's own decode format
 * (base64 → gunzip → JSON.parse), proving a fresh visit to the produced URL would
 * decode to the same code + active path.
 */

import { describe, it, expect } from 'vitest'
import { playgroundUrl } from '@/lib/openscadPlayground'

/** Mirror of the playground's own `readStateFromFragment`: atob + gunzip + JSON.parse. */
async function decodeFragment(hash: string): Promise<unknown> {
  const bin = atob(hash)
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
  const gunzipStream = new Response(bytes).body!.pipeThrough(new DecompressionStream('gzip'))
  const buf = new Uint8Array(await new Response(gunzipStream).arrayBuffer())
  return JSON.parse(new TextDecoder().decode(buf))
}

interface DecodedState {
  params: {
    activePath: string
    sources: { path: string; content: string }[]
    features: string[]
  }
}

describe('playgroundUrl', () => {
  it('produces a URL pointing at the playground origin with a fragment', async () => {
    const url = await playgroundUrl('cube([10, 10, 10]);', 'part.scad')
    expect(url.startsWith('https://ochafik.com/openscad2#')).toBe(true)
  })

  it('round-trips: decodes back to the original code and active path', async () => {
    const code = 'cube([10, 10, 10]);\nsphere(r=5);\n'
    const url = await playgroundUrl(code, 'widget.scad')
    const hash = url.split('#')[1]
    const decoded = (await decodeFragment(hash)) as DecodedState

    expect(decoded.params.activePath).toBe('/widget.scad')
    expect(decoded.params.sources).toHaveLength(1)
    expect(decoded.params.sources[0].content).toBe(code)
    expect(decoded.params.sources[0].path).toBe('/widget.scad')
  })

  it('defaults the filename to model.scad when none is given', async () => {
    const url = await playgroundUrl('cube(1);', '')
    const hash = url.split('#')[1]
    const decoded = (await decodeFragment(hash)) as DecodedState
    expect(decoded.params.activePath).toBe('/model.scad')
  })

  it('round-trips a larger file without a stack overflow (chunked base64 encode)', async () => {
    // Bigger than the 0x8000 chunk size used internally by the encoder.
    const code = 'cube([1,1,1]);\n'.repeat(5000)
    const url = await playgroundUrl(code, 'big.scad')
    const hash = url.split('#')[1]
    const decoded = (await decodeFragment(hash)) as DecodedState
    expect(decoded.params.sources[0].content).toBe(code)
  })
})
