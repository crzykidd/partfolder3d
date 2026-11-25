/**
 * useCatalogSelection — multi-select state for the catalog.
 *
 * Owns: select-mode flag, the selected set (key → minimal display info so the
 * action bar / dialogs can name items that are no longer on the current page),
 * and the last-clicked key for shift-click range selection.
 *
 * Selection persists across pagination / filter / sort changes (keyed by item
 * key); it clears on exit or when the owning page unmounts.
 */

import { useCallback, useMemo, useRef, useState } from 'react'

export interface SelectedInfo {
  title: string
}

export interface SelectableItem {
  key: string
  title: string
}

export interface CatalogSelection {
  active: boolean
  /** key → display info, insertion-ordered. */
  selected: ReadonlyMap<string, SelectedInfo>
  count: number
  keys: string[]
  isSelected: (key: string) => boolean
  enter: () => void
  /** Leave select mode and clear the selection. */
  exit: () => void
  clear: () => void
  /**
   * Click on an item. With `shift` and a previous anchor on the same page,
   * selects the range between anchor and this item (inclusive); otherwise toggles.
   */
  click: (item: SelectableItem, pageItems: SelectableItem[], shift: boolean) => void
  selectAllOnPage: (pageItems: SelectableItem[]) => void
  /** Drop specific keys (e.g. after a successful delete/move). */
  remove: (keys: string[]) => void
}

export function useCatalogSelection(): CatalogSelection {
  const [active, setActive] = useState(false)
  const [selected, setSelected] = useState<Map<string, SelectedInfo>>(() => new Map())
  const anchor = useRef<string | null>(null)

  const enter = useCallback(() => setActive(true), [])

  const clear = useCallback(() => {
    anchor.current = null
    setSelected(new Map())
  }, [])

  const exit = useCallback(() => {
    anchor.current = null
    setSelected(new Map())
    setActive(false)
  }, [])

  const click = useCallback(
    (item: SelectableItem, pageItems: SelectableItem[], shift: boolean) => {
      const anchorKey = anchor.current
      const from = shift && anchorKey ? pageItems.findIndex((i) => i.key === anchorKey) : -1
      const to = pageItems.findIndex((i) => i.key === item.key)
      setSelected((prev) => {
        const next = new Map(prev)
        if (from >= 0 && to >= 0) {
          const [lo, hi] = from <= to ? [from, to] : [to, from]
          for (let i = lo; i <= hi; i++) {
            next.set(pageItems[i].key, { title: pageItems[i].title })
          }
        } else if (next.has(item.key)) {
          next.delete(item.key)
        } else {
          next.set(item.key, { title: item.title })
        }
        return next
      })
      anchor.current = item.key
    },
    [],
  )

  const selectAllOnPage = useCallback((pageItems: SelectableItem[]) => {
    setSelected((prev) => {
      const next = new Map(prev)
      for (const i of pageItems) next.set(i.key, { title: i.title })
      return next
    })
  }, [])

  const remove = useCallback((keys: string[]) => {
    setSelected((prev) => {
      const next = new Map(prev)
      for (const k of keys) next.delete(k)
      return next
    })
  }, [])

  const isSelected = useCallback((key: string) => selected.has(key), [selected])

  return useMemo(
    () => ({
      active,
      selected,
      count: selected.size,
      keys: [...selected.keys()],
      isSelected,
      enter,
      exit,
      clear,
      click,
      selectAllOnPage,
      remove,
    }),
    [active, selected, isSelected, enter, exit, clear, click, selectAllOnPage, remove],
  )
}

/** Props the catalog views receive to render selection affordances. */
export interface SelectionViewProps {
  active: boolean
  isSelected: (key: string) => boolean
  onSelect: (item: SelectableItem, shift: boolean) => void
}
