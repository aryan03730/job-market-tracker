import { num, sourceLabel } from '../format'
import ChartCard from './ChartCard'

// Simple labeled bars in HTML: easier to read than a chart for two short lists.
function Bars({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <ul className="hbars">
      {rows.map((r) => (
        <li key={r.label} title={`${r.label}: ${num(r.count)}`}>
          <span className="hbar-label">{r.label}</span>
          <span className="hbar-track"><span className="hbar-fill" style={{ width: `${(r.count / max) * 100}%` }} /></span>
          <span className="hbar-value">{num(r.count)}</span>
        </li>
      ))}
    </ul>
  )
}

export default function BreakdownCard({ summary }) {
  const sources = Object.entries(summary?.by_source || {})
    .map(([k, v]) => ({ label: sourceLabel(k), count: v }))
    .sort((a, b) => b.count - a.count)
  const states = (summary?.top_states || []).map((s) => ({ label: s.state, count: s.count }))
  return (
    <ChartCard title="Where postings come from" subtitle="By job source, and top states for on-site roles">
      <div className="split">
        <div><h3>Sources</h3><Bars rows={sources} /></div>
        <div><h3>States</h3>{states.length ? <Bars rows={states} /> : <p className="muted">No on-site postings yet</p>}</div>
      </div>
    </ChartCard>
  )
}
