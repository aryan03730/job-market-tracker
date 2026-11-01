import { useState } from 'react'

// A card that can flip between the chart and a plain table of the same numbers.
export default function ChartCard({ title, subtitle, table, children, action }) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
        <div className="card-actions">
          {action}
          {table && (
            <button className="ghost" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
              {asTable ? 'Chart' : 'Table'}
            </button>
          )}
        </div>
      </header>
      {asTable && table ? (
        <div className="table-wrap">
          <table>
            <thead><tr>{table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : children}
    </section>
  )
}
