import { useCallback, useEffect, useState } from 'react'
import { getJSON, qs } from './api'
import { ago, sourceLabel } from './format'
import BreakdownCard from './components/BreakdownCard'
import DailyChart from './components/DailyChart'
import Kpis from './components/Kpis'
import Postings from './components/Postings'
import Providers from './components/Providers'
import SalaryChart from './components/SalaryChart'
import SkillsChart from './components/SkillsChart'

export default function App() {
  const [health, setHealth] = useState(null)
  const [summary, setSummary] = useState(null)
  const [daily, setDaily] = useState(null)
  const [skills, setSkills] = useState(null)
  const [salary, setSalary] = useState(null)
  const [providers, setProviders] = useState(null)
  const [days, setDays] = useState(30)
  const [skill, setSkill] = useState('')
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      const [h, s, sk, sal, pr] = await Promise.all([
        getJSON('/health'), getJSON('/stats/summary'), getJSON('/stats/skills?limit=30'),
        getJSON('/stats/salary'), getJSON('/providers'),
      ])
      setHealth(h); setSummary(s); setSkills(sk); setSalary(sal); setProviders(pr); setError(null)
    } catch {
      setError('The API is not responding. If it was asleep, it should wake within a minute.')
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    getJSON(`/stats/daily${qs({ days })}`).then(setDaily).catch(() => {})
  }, [days])

  // Salary chart follows the selected skill, so you can see e.g. what Python roles pay.
  useEffect(() => {
    getJSON(`/stats/salary${qs({ skill })}`).then(setSalary).catch(() => {})
  }, [skill])

  const healthy = (providers || []).filter((p) => p.state === 'healthy')
  const lastRun = health?.last_run?.finished_at

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Job Market Tracker</h1>
          <p className="muted">
            US software job postings from {healthy.length || 'several'} job sources, refreshed automatically every day.
          </p>
        </div>
        {health && (
          <div className={`freshness ${health.stale ? 'warning' : 'good'}`}>
            <span aria-hidden>{health.stale ? '▲' : '●'}</span>
            {health.stale ? ' Data may be out of date' : ' Up to date'}
            <span className="muted"> · updated {ago(lastRun)}</span>
          </div>
        )}
      </header>

      {error && <div className="banner error">{error} <button className="ghost" onClick={load}>Retry</button></div>}

      <Kpis summary={summary} />

      <div className="grid two">
        <DailyChart data={daily} days={days} setDays={setDays} />
        <SalaryChart data={salary} />
      </div>
      {skill && <p className="filter-note">Salary chart and postings filtered to <strong>{skill}</strong>. <button className="link" onClick={() => setSkill('')}>Clear</button></p>}
      <div className="grid two">
        <SkillsChart data={skills} selected={skill} onSelect={setSkill} />
        <BreakdownCard summary={summary} />
      </div>

      <Postings skill={skill} setSkill={setSkill}
        sources={Object.keys(summary?.by_source || {})}
        skills={(skills || []).map((s) => s.skill).sort()} />

      <Providers providers={providers} />

      <footer className="foot muted">
        <p>
          Postings come from{' '}
          {(providers || []).filter((p) => p.last_success_at).map((p, i, arr) => (
            <span key={p.name}>
              <a href={p.homepage} target="_blank" rel="noopener noreferrer">{sourceLabel(p.name)}</a>
              {i < arr.length - 1 ? ', ' : ''}
            </span>
          ))}
          . Every listing links to its original page. Salaries are shown only when the source states them.
        </p>
        <p>A personal project by Aryan Arora · <a href="https://github.com/aryan03730">GitHub</a></p>
      </footer>
    </div>
  )
}
