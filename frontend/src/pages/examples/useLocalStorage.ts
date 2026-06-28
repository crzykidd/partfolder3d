import { useState } from 'react'

/**
 * Like useState but synced to localStorage. Reads the initial value on mount;
 * writes on every set. Silently ignores parse/write errors (private browsing,
 * storage full, etc.).
 */
export function useLocalStorage<T>(key: string, initialValue: T): [T, (v: T) => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key)
      return raw !== null ? (JSON.parse(raw) as T) : initialValue
    } catch {
      return initialValue
    }
  })

  const setValue = (value: T) => {
    try {
      setStoredValue(value)
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // Ignore (private browsing / quota exceeded)
    }
  }

  return [storedValue, setValue]
}
