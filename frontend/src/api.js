const BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

// Render's free tier sleeps; the first request can take ~30s or fail. Retry gently.
export async function getJSON(path, { retries = 2, signal } = {}) {
  let lastError
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(`${BASE}${path}`, { signal })
      if (!res.ok && res.status !== 503) throw new Error(`HTTP ${res.status}`)
      return await res.json()
    } catch (err) {
      if (err.name === 'AbortError') throw err
      lastError = err
      await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)))
    }
  }
  throw lastError
}

export function qs(params) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}
