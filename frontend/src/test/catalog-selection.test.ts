/** Unit tests for the useCatalogSelection hook (catalog multi-select state). */

import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useCatalogSelection } from '@/pages/catalog/useCatalogSelection'

const page = ['a', 'b', 'c', 'd', 'e'].map((k) => ({ key: k, title: `Title ${k}` }))

describe('useCatalogSelection', () => {
  it('starts inactive and empty; enter/exit toggle mode and exit clears', () => {
    const { result } = renderHook(() => useCatalogSelection())
    expect(result.current.active).toBe(false)
    act(() => result.current.enter())
    expect(result.current.active).toBe(true)
    act(() => result.current.click(page[0], page, false))
    expect(result.current.count).toBe(1)
    act(() => result.current.exit())
    expect(result.current.active).toBe(false)
    expect(result.current.count).toBe(0)
  })

  it('toggles an item on and off, storing its title', () => {
    const { result } = renderHook(() => useCatalogSelection())
    act(() => result.current.click(page[1], page, false))
    expect(result.current.isSelected('b')).toBe(true)
    expect(result.current.selected.get('b')).toEqual({ title: 'Title b' })
    act(() => result.current.click(page[1], page, false))
    expect(result.current.isSelected('b')).toBe(false)
  })

  it('shift-click selects the inclusive range from the last anchor (either direction)', () => {
    const { result } = renderHook(() => useCatalogSelection())
    act(() => result.current.click(page[1], page, false))
    act(() => result.current.click(page[3], page, true))
    expect(result.current.keys.sort()).toEqual(['b', 'c', 'd'])
    // anchor is now d; shift-click upward to a
    act(() => result.current.click(page[0], page, true))
    expect(result.current.keys.sort()).toEqual(['a', 'b', 'c', 'd'])
  })

  it('shift-click with no anchor on the page just toggles', () => {
    const { result } = renderHook(() => useCatalogSelection())
    act(() => result.current.click(page[2], page, true))
    expect(result.current.keys).toEqual(['c'])
  })

  it('persists across a page change (selection keyed by key, off-page titles retained)', () => {
    const { result } = renderHook(() => useCatalogSelection())
    act(() => result.current.click(page[0], page, false))
    const page2 = [{ key: 'z', title: 'Other page' }]
    act(() => result.current.click(page2[0], page2, false))
    expect(result.current.keys.sort()).toEqual(['a', 'z'])
    expect(result.current.selected.get('a')?.title).toBe('Title a')
  })

  it('selectAllOnPage adds every page item; remove/clear drop keys', () => {
    const { result } = renderHook(() => useCatalogSelection())
    act(() => result.current.selectAllOnPage(page))
    expect(result.current.count).toBe(5)
    act(() => result.current.remove(['a', 'b']))
    expect(result.current.keys.sort()).toEqual(['c', 'd', 'e'])
    act(() => result.current.clear())
    expect(result.current.count).toBe(0)
    expect(result.current.active).toBe(false)
  })
})
