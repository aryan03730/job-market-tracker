export const SOURCE_LABELS = {
  adzuna: 'Adzuna', usajobs: 'USAJOBS', remotive: 'Remotive', jobicy: 'Jobicy',
  themuse: 'The Muse', remoteok: 'Remote OK', himalayas: 'Himalayas', arbeitnow: 'Arbeitnow',
}
export const sourceLabel = (s) => SOURCE_LABELS[s] || s

export const num = (n) => (n ?? 0).toLocaleString('en-US')
export const pct = (x) => `${Math.round((x ?? 0) * 100)}%`
export const money = (n) => (n == null ? '—' : `$${Math.round(n / 1000)}k`)

export function salaryRange(lo, hi) {
  if (lo == null) return null
  return lo === hi ? money(lo) : `${money(lo)}–${money(hi)}`
}

export function ago(iso) {
  if (!iso) return 'never'
  const then = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
  const mins = Math.round((Date.now() - then.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const h = Math.round(mins / 60)
  if (h < 48) return `${h} h ago`
  return `${Math.round(h / 24)} days ago`
}

export const shortDate = (d) =>
  new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
