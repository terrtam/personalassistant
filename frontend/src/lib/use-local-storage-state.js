import { useEffect, useState } from 'react'

function useLocalStorageState(key, initialValue) {
  const [value, setValue] = useState(() => {
    if (typeof window === 'undefined') return initialValue
    try {
      const stored = window.localStorage.getItem(key)
      return stored === null ? initialValue : JSON.parse(stored)
    } catch {
      return initialValue
    }
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // Ignore write errors (e.g. storage full or disabled)
    }
  }, [key, value])

  return [value, setValue]
}

export { useLocalStorageState }
