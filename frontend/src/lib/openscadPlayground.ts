/**
 * openscadPlayground.ts — deep-link encoder for the OpenSCAD web playground
 * (https://ochafik.com/openscad2), used by the item page's "Show SCAD" modal.
 *
 * v1 is read-only (view/copy/download in-app); this util only builds a URL that
 * opens the code in the external playground for editing/preview/STL export
 * (server-side rendering is tracked separately in FR #46 — not implemented here).
 *
 * Format reverse-engineered from openscad/openscad-playground:
 * - src/state/fragment-state.ts (`encodeStateParamsAsFragment` + `compressString`)
 * - src/state/app-state.ts (`State`)
 *
 * The fragment is `base64(gzip(JSON.stringify({ params, ... })))`, read raw from
 * `location.hash` by the playground's `readStateFromFragment` (it `atob`s + gunzips
 * the hash directly) — so the base64 must be passed UNENCODED (no encodeURIComponent).
 */

interface PlaygroundSource {
  path: string
  content: string
}

interface PlaygroundParams {
  activePath: string
  sources: PlaygroundSource[]
  features: string[]
}

interface PlaygroundState {
  params: PlaygroundParams
}

const PLAYGROUND_BASE_URL = 'https://ochafik.com/openscad2'

/**
 * Build a compressed OpenSCAD Playground deep-link that opens with `scadCode`
 * prefilled as the active file.
 *
 * Documented (simpler) fallback the playground itself marks "for testing":
 * `https://ochafik.com/openscad2#src=' + encodeURIComponent(scadCode)`.
 * We prefer the compressed format below because it is the playground's own
 * durable permalink format (and supports multi-file state).
 */
export async function playgroundUrl(scadCode: string, filename: string): Promise<string> {
  const path = '/' + (filename || 'model.scad') // leading slash per playground convention
  const state: PlaygroundState = {
    params: { activePath: path, sources: [{ path, content: scadCode }], features: [] },
  }

  const bytes = new TextEncoder().encode(JSON.stringify(state))
  // Uses Response(...).body rather than Blob(...).stream() — the latter isn't
  // implemented under jsdom (our test environment); both produce an equivalent
  // ReadableStream<Uint8Array> in real browsers.
  const gzipStream = new Response(bytes).body!.pipeThrough(new CompressionStream('gzip'))
  const buf = new Uint8Array(await new Response(gzipStream).arrayBuffer())

  // Chunk to avoid a String.fromCharCode(...huge) stack overflow on large files.
  let bin = ''
  const CHUNK_SIZE = 0x8000
  for (let i = 0; i < buf.length; i += CHUNK_SIZE) {
    bin += String.fromCharCode(...buf.subarray(i, i + CHUNK_SIZE))
  }

  // base64 is valid in a URL fragment — do NOT url-encode it.
  return `${PLAYGROUND_BASE_URL}#${btoa(bin)}`
}
