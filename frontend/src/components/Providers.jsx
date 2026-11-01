import { ago, num, sourceLabel } from '../format'

const STATES = {
  healthy: { icon: '●', label: 'Healthy', cls: 'good' },
  waiting: { icon: '○', label: 'Waiting for first run', cls: 'muted' },
  failing: { icon: '▲', label: 'Failing, retrying', cls: 'warning' },
  cooling_down: { icon: '■', label: 'Resting after errors', cls: 'serious' },
  needs_key: { icon: '○', label: 'Needs API key', cls: 'muted' },
  disabled: { icon: '–', label: 'Turned off', cls: 'muted' },
}

export default function Providers({ providers }) {
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>Data sources</h2>
          <p className="muted">Each source is checked on every refresh. A failing source rests and retries on its own.</p>
        </div>
      </header>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Source</th><th>Status</th><th>Last success</th><th>Fetched</th><th>New</th><th>Note</th></tr>
          </thead>
          <tbody>
            {(providers || []).map((p) => {
              const s = STATES[p.state] || STATES.waiting
              const note = p.state === 'needs_key' ? `Set ${p.missing_env.join(', ')}`
                : p.state === 'cooling_down' ? `Back after ${new Date(p.cooldown_until + 'Z').toLocaleString()}`
                : p.last_error || ''
              return (
                <tr key={p.name}>
                  <td>{p.homepage ? <a href={p.homepage} target="_blank" rel="noopener noreferrer">{sourceLabel(p.name)}</a> : sourceLabel(p.name)}</td>
                  <td><span className={`status ${s.cls}`}><span aria-hidden>{s.icon}</span> {s.label}</span></td>
                  <td>{p.last_success_at ? ago(p.last_success_at) : '—'}</td>
                  <td>{p.last_run_at ? num(p.last_fetched) : '—'}</td>
                  <td>{p.last_run_at ? num(p.last_new) : '—'}</td>
                  <td className="note" title={note}>{note}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
