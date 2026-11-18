import { useEffect, useState } from 'react'

/// True on a wide screen (list beside detail, left rail). Matches the CSS breakpoint.
export function useWide(query = '(min-width: 900px)'): boolean {
  const [wide, setWide] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : false))
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setWide(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return wide
}
