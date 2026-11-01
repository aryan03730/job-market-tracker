import { num, pct } from '../format'

export default function Kpis({ summary }) {
  const items = [
    { label: 'Open postings', value: num(summary?.total) },
    { label: 'New in last 24 h', value: num(summary?.new_24h) },
    { label: 'Hiring companies', value: num(summary?.companies) },
    { label: 'List a salary', value: pct(summary?.salary_share) },
    { label: 'Remote', value: pct(summary?.remote_share) },
  ]
  return (
    <div className="kpis">
      {items.map((k) => (
        <div className="kpi" key={k.label}>
          <div className="kpi-value">{summary ? k.value : '—'}</div>
          <div className="kpi-label">{k.label}</div>
        </div>
      ))}
    </div>
  )
}
