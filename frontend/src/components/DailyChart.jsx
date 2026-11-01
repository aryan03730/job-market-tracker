import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { num, shortDate } from '../format'
import ChartCard from './ChartCard'
import ChartTooltip from './Tooltip'

export default function DailyChart({ data, days, setDays }) {
  const rows = data || []
  const total = rows.reduce((s, d) => s + d.total, 0)
  const ranges = [7, 30, 90]
  return (
    <ChartCard
      title="Postings per day"
      subtitle={`${num(total)} postings in the last ${days} days, by date posted`}
      action={
        <div className="seg" role="group" aria-label="Time range">
          {ranges.map((r) => (
            <button key={r} className={r === days ? 'on' : ''} onClick={() => setDays(r)}>{r}d</button>
          ))}
        </div>
      }
      table={{ columns: ['Date', 'Postings'], rows: rows.map((d) => [d.date, d.total]) }}
    >
      <div className="chart" style={{ height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fill: 'var(--muted)', fontSize: 12 }}
              axisLine={{ stroke: 'var(--axis)' }} tickLine={false} minTickGap={24} />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ stroke: 'var(--axis)' }}
              content={<ChartTooltip format={(v, _p, label) => [`${num(v)} postings`, shortDate(label)]} />} />
            <Line type="monotone" dataKey="total" stroke="var(--series-1)" strokeWidth={2} dot={false}
              activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}
