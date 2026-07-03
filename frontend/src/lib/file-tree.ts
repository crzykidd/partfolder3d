/**
 * file-tree.ts — build a folder hierarchy from a flat list of FileOut records.
 *
 * Each file's `path` is split on '/' to determine nesting. Files at the root
 * (no directory separator) land at the top level. Folder order follows
 * insertion order of the first file encountered under that folder.
 */

import type { FileOut } from '@/lib/api/items'

// ---------------------------------------------------------------------------
// Node types
// ---------------------------------------------------------------------------

export interface FileTreeFile {
  type: 'file'
  /** The basename (final path segment). */
  name: string
  /** The original FileOut record. */
  file: FileOut
}

export interface FileTreeFolder {
  type: 'folder'
  /** The folder name (one path segment). */
  name: string
  /** Child nodes — may be files or nested folders. */
  children: FileTreeNode[]
}

export type FileTreeNode = FileTreeFile | FileTreeFolder

// ---------------------------------------------------------------------------
// Builder
// ---------------------------------------------------------------------------

/**
 * Build a folder hierarchy from a flat list of FileOut records.
 *
 * Splits each `file.path` on '/' and inserts folder nodes as needed.
 * The returned array represents the top-level nodes.
 */
export function buildFileTree(files: FileOut[]): FileTreeNode[] {
  const root: FileTreeNode[] = []

  for (const file of files) {
    const parts = file.path.split('/')
    let current = root

    // Walk / create intermediate folder nodes
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i]
      let folder = current.find(
        (n): n is FileTreeFolder => n.type === 'folder' && n.name === part,
      )
      if (!folder) {
        folder = { type: 'folder', name: part, children: [] }
        current.push(folder)
      }
      current = folder.children
    }

    // Leaf node
    current.push({ type: 'file', name: parts[parts.length - 1], file })
  }

  // Float 3D-renderable model files (stl/obj/3mf/ply) to the top of each level.
  sortModelsFirst(root)
  return root
}

/** Extensions treated as 3D model files, shown first in the file tree. */
const MODEL_EXTS = ['.stl', '.obj', '.3mf', '.ply']

export function isModelFile(name: string): boolean {
  const lower = name.toLowerCase()
  return MODEL_EXTS.some((ext) => lower.endsWith(ext))
}

/** Stable sort: model files rank first; folders + other files keep their order. */
function sortModelsFirst(nodes: FileTreeNode[]): void {
  const rank = (n: FileTreeNode): number =>
    n.type === 'file' && isModelFile(n.name) ? 0 : 1
  nodes.sort((a, b) => rank(a) - rank(b))
  for (const n of nodes) {
    if (n.type === 'folder') sortModelsFirst(n.children)
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns true if the file path ends with a 3MF extension (case-insensitive). */
export function is3mf(path: string): boolean {
  return path.toLowerCase().endsWith('.3mf')
}

/** Returns true if the file path is a common image extension. */
export function isImagePath(path: string): boolean {
  return /\.(png|jpe?g|gif|webp|avif|svg)$/i.test(path)
}
