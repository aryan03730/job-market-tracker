import { useEffect, useState } from 'react'
import { getJSON, qs } from '../api'
import { ago, num, salaryRange, sourceLabel } from '../format'

export default function Postings({ skill, setSkill, sources, skills }) {
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [source, setSource] = useState('')
  const [remote, setRemote] = useState('')
  const [hasSalary, setHasSalary] = useState(false)
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const LIMIT = 20

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  const filters = { q: debouncedQ, source, skill, remote, has_salary: hasSalary ? 1 : '' }
  const key = JSON.stringify(filters)

  useEffect(() => { setOffset(0) }, [key])

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    getJSON(`/postings${qs({ ...filters, limit: LIMIT, offset })}`, { signal: ctrl.signal })
      .then((d) => {
        setItems((prev) => (offset === 0 ? d.items : [...prev, ...d.items]))
        setTotal(d.total)
        setError(null)
      })
      .catch((e) => e.name !== 'AbortError' && setError('Could not load postings.'))
      .finally(() => setLoading(false))
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, offset])

  const clear = () => { setQ(''); setSource(''); setSkill(''); setRemote(''); setHasSalary(false) }
  const anyFilter = q || source || skill || remote || hasSalary

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>Newest postings</h2>
          <p className="muted">{num(total)} matching · each link opens the original listing</p>
        </div>
      </header>

      <div className="filters">
        <input type="search" placeholder="Search title or company" value={q} onChange={(e) => setQ(e.target.value)}
          aria-label="Search title or company" />
        <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
          <option value="">All sources</option>
          {sources.map((s) => <option key={s} value={s}>{sourceLabel(s)}</option>)}
        </select>
        <select value={skill} onChange={(e) => setSkill(e.target.value)} aria-label="Skill">
          <option value="">All skills</option>
          {skills.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={remote} onChange={(e) => setRemote(e.target.value)} aria-label="Work type">
          <option value="">Remote and on-site</option>
          <option value="true">Remote only</option>
          <option value="false">On-site / hybrid</option>
        </select>
        <label className="check">
          <input type="checkbox" checked={hasSalary} onChange={(e) => setHasSalary(e.target.checked)} /> Has salary
        </label>
        {anyFilter && <button className="ghost" onClick={clear}>Clear</button>}
      </div>

      {error && <p className="error">{error}</p>}
      <ul className="postings">
        {items.map((p) => (
          <li key={p.id}>
            <a href={p.url} target="_blank" rel="noopener noreferrer" className="posting">
              <div className="posting-main">
                <div className="posting-title">{p.title}</div>
                <div className="posting-meta">
                  <span>{p.company || 'Unknown company'}</span>
                  <span aria-hidden>·</span>
                  <span>{p.location}</span>
                </div>
                {p.skills.length > 0 && (
                  <div className="tags">{p.skills.slice(0, 6).map((s) => <span key={s} className="tag">{s}</span>)}</div>
                )}
              </div>
              <div className="posting-side">
                {salaryRange(p.salary_min, p.salary_max) && (
                  <div className="salary">
                    {salaryRange(p.salary_min, p.salary_max)}
                    {p.salary_is_predicted && <span className="muted" title="Estimated by the source"> est.</span>}
                  </div>
                )}
                <div className="muted small">{ago(p.posted_at)} · via {sourceLabel(p.source)}</div>
              </div>
            </a>
          </li>
        ))}
      </ul>
      {!loading && items.length === 0 && <p className="muted empty">No postings match these filters.</p>}
      {items.length < total && (
        <button className="more" disabled={loading} onClick={() => setOffset(items.length)}>
          {loading ? 'Loading…' : `Show more (${num(total - items.length)} left)`}
        </button>
      )}
    </section>
  )
}
