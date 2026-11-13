import { useEffect, useState } from 'react'
import { getJSON, postJSON } from '../api'

// Daily email alerts. Hidden until the API reports that email is configured.
export default function AlertsCard({ topSkills, selectedSkill }) {
  const [enabled, setEnabled] = useState(false)
  const [email, setEmail] = useState('')
  const [skills, setSkills] = useState([])
  const [keyword, setKeyword] = useState('')
  const [remoteOnly, setRemoteOnly] = useState(false)
  const [state, setState] = useState({ status: 'idle', message: '' })

  useEffect(() => {
    getJSON('/alerts/status', { retries: 1 }).then((d) => setEnabled(!!d.enabled)).catch(() => {})
  }, [])

  // Clicking a skill bar on the dashboard pre-selects it here.
  useEffect(() => {
    if (selectedSkill) setSkills((prev) => (prev.includes(selectedSkill) ? prev : [...prev, selectedSkill]))
  }, [selectedSkill])

  if (!enabled) return null

  const toggle = (s) => setSkills((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]))

  async function submit(e) {
    e.preventDefault()
    setState({ status: 'sending', message: '' })
    try {
      const d = await postJSON('/alerts/subscribe', { email, skills, keyword, remote_only: remoteOnly })
      setState({ status: 'done', message: d.message })
    } catch (err) {
      setState({ status: 'error', message: err.message })
    }
  }

  if (state.status === 'done') {
    return (
      <section className="card alerts">
        <h2>Almost done</h2>
        <p className="muted">{state.message} The link is in an email from Job Market Tracker; check spam if you don't see it.</p>
      </section>
    )
  }

  return (
    <section className="card alerts">
      <header className="card-head">
        <div>
          <h2>Get new jobs by email</h2>
          <p className="muted">One email a day with new postings that match. Pick skills, or leave them empty for everything.</p>
        </div>
      </header>
      <form onSubmit={submit}>
        <div className="chips" role="group" aria-label="Skills">
          {topSkills.slice(0, 16).map((s) => (
            <button type="button" key={s} className={`chip ${skills.includes(s) ? 'on' : ''}`}
              aria-pressed={skills.includes(s)} onClick={() => toggle(s)}>{s}</button>
          ))}
        </div>
        <div className="filters">
          <input type="email" required placeholder="you@example.com" value={email}
            onChange={(e) => setEmail(e.target.value)} aria-label="Email address" />
          <input type="text" placeholder="Title keyword (optional), e.g. backend" value={keyword} maxLength={100}
            onChange={(e) => setKeyword(e.target.value)} aria-label="Title keyword" />
          <label className="check">
            <input type="checkbox" checked={remoteOnly} onChange={(e) => setRemoteOnly(e.target.checked)} /> Remote only
          </label>
          <button className="primary" disabled={state.status === 'sending'}>
            {state.status === 'sending' ? 'Sending…' : 'Subscribe'}
          </button>
        </div>
        {state.status === 'error' && <p className="error">{state.message}</p>}
        <p className="muted small">We'll email you a confirmation link first. Every alert has a one-click unsubscribe, which deletes your address.</p>
      </form>
    </section>
  )
}
