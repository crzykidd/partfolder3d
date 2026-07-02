/**
 * Tests for lib/file-tree.ts — tree building from FileOut.path values.
 *
 * Covers:
 *  - buildFileTree: flat list, single level, deep nesting, mixed depth
 *  - is3mf: extension detection
 *  - isImagePath: image extension detection
 */

import { describe, it, expect } from 'vitest'
import { buildFileTree, is3mf, isImagePath, type FileTreeFile, type FileTreeFolder } from '@/lib/file-tree'
import type { FileOut } from '@/lib/api/items'

// ---------------------------------------------------------------------------
// Minimal FileOut factory
// ---------------------------------------------------------------------------

function makeFile(path: string, id = 0): FileOut {
  return {
    id,
    path,
    role: 'model',
    size: 1024,
    sha256: null,
    object_analysis: null,
    preview_3d: false,
  }
}

// ---------------------------------------------------------------------------
// buildFileTree
// ---------------------------------------------------------------------------

describe('buildFileTree', () => {
  it('returns an empty array for an empty file list', () => {
    expect(buildFileTree([])).toEqual([])
  })

  it('handles a single flat file (no slashes)', () => {
    const tree = buildFileTree([makeFile('model.stl', 1)])
    expect(tree).toHaveLength(1)
    expect(tree[0].type).toBe('file')
    expect((tree[0] as FileTreeFile).name).toBe('model.stl')
    expect((tree[0] as FileTreeFile).file.path).toBe('model.stl')
  })

  it('places multiple flat files at the top level', () => {
    const tree = buildFileTree([
      makeFile('a.stl', 1),
      makeFile('b.3mf', 2),
      makeFile('cover.png', 3),
    ])
    expect(tree).toHaveLength(3)
    expect(tree.every((n) => n.type === 'file')).toBe(true)
    expect(tree.map((n) => (n as FileTreeFile).name)).toEqual(['a.stl', 'b.3mf', 'cover.png'])
  })

  it('groups files under a single folder', () => {
    const tree = buildFileTree([
      makeFile('models/a.stl', 1),
      makeFile('models/b.stl', 2),
    ])
    expect(tree).toHaveLength(1)
    const folder = tree[0] as FileTreeFolder
    expect(folder.type).toBe('folder')
    expect(folder.name).toBe('models')
    expect(folder.children).toHaveLength(2)
    expect(folder.children.map((n) => (n as FileTreeFile).name)).toEqual(['a.stl', 'b.stl'])
  })

  it('handles mixed depth (root files + folder files)', () => {
    const tree = buildFileTree([
      makeFile('readme.txt', 1),
      makeFile('models/part.stl', 2),
    ])
    expect(tree).toHaveLength(2)
    const names = tree.map((n) => (n.type === 'file' ? (n as FileTreeFile).name : (n as FileTreeFolder).name))
    expect(names).toContain('readme.txt')
    expect(names).toContain('models')
  })

  it('handles deeply nested paths', () => {
    const tree = buildFileTree([makeFile('a/b/c/deep.stl', 1)])
    expect(tree).toHaveLength(1)
    const a = tree[0] as FileTreeFolder
    expect(a.type).toBe('folder')
    expect(a.name).toBe('a')
    const b = a.children[0] as FileTreeFolder
    expect(b.type).toBe('folder')
    expect(b.name).toBe('b')
    const c = b.children[0] as FileTreeFolder
    expect(c.type).toBe('folder')
    expect(c.name).toBe('c')
    const leaf = c.children[0] as FileTreeFile
    expect(leaf.type).toBe('file')
    expect(leaf.name).toBe('deep.stl')
  })

  it('reuses an existing folder node for siblings', () => {
    const tree = buildFileTree([
      makeFile('parts/a.stl', 1),
      makeFile('parts/b.3mf', 2),
      makeFile('images/cover.png', 3),
    ])
    expect(tree).toHaveLength(2)
    const parts = tree[0] as FileTreeFolder
    expect(parts.name).toBe('parts')
    expect(parts.children).toHaveLength(2)
    const images = tree[1] as FileTreeFolder
    expect(images.name).toBe('images')
    expect(images.children).toHaveLength(1)
  })

  it('preserves the original FileOut reference on leaf nodes', () => {
    const file = makeFile('model.stl', 99)
    const tree = buildFileTree([file])
    const leaf = tree[0] as FileTreeFile
    expect(leaf.file).toBe(file)
  })
})

// ---------------------------------------------------------------------------
// is3mf
// ---------------------------------------------------------------------------

describe('is3mf', () => {
  it('returns true for .3mf extension', () => {
    expect(is3mf('model.3mf')).toBe(true)
    expect(is3mf('models/part.3mf')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(is3mf('MODEL.3MF')).toBe(true)
    expect(is3mf('Model.3Mf')).toBe(true)
  })

  it('returns false for other extensions', () => {
    expect(is3mf('model.stl')).toBe(false)
    expect(is3mf('model.obj')).toBe(false)
    expect(is3mf('cover.png')).toBe(false)
    expect(is3mf('archive.zip')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// isImagePath
// ---------------------------------------------------------------------------

describe('isImagePath', () => {
  it('returns true for common image extensions', () => {
    expect(isImagePath('cover.png')).toBe(true)
    expect(isImagePath('photo.jpg')).toBe(true)
    expect(isImagePath('photo.jpeg')).toBe(true)
    expect(isImagePath('anim.gif')).toBe(true)
    expect(isImagePath('render.webp')).toBe(true)
    expect(isImagePath('icon.svg')).toBe(true)
    expect(isImagePath('modern.avif')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(isImagePath('COVER.PNG')).toBe(true)
    expect(isImagePath('Photo.JPG')).toBe(true)
  })

  it('returns false for non-image extensions', () => {
    expect(isImagePath('model.stl')).toBe(false)
    expect(isImagePath('model.3mf')).toBe(false)
    expect(isImagePath('doc.pdf')).toBe(false)
    expect(isImagePath('data.json')).toBe(false)
  })
})
