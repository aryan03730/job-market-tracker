import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { money, num, pct } from '../format'
import ChartCard from './ChartCard'
import ChartTooltip from './Tooltip'

export default function SalaryChart({ data }) {
  const rows = data?.buckets || []
  return (
    <ChartCard
      title="Salary ranges"
      subtitle={data?.count
        ? `${num(data.count)} postings state a salary (${pct(data.coverage)}). Midpoint of each range, per year.`
        : 'No salaries yet'}
      table={{ columns: ['Range', 'Postings'], rows: rows.map((b) => [b.label, b.count]) }}
    >
      {data?.median && (
        <div className="stat-row">
          <div><span className="stat">{money(data.p25)}</span><span className="muted">25th pct</span></div>
          <div><span className="stat strong">{money(data.median)}</span><span className="muted">median</span></div>
          <div><span className="stat">{money(data.p75)}</span><span className="muted">75th pct</span></div>
        </div>
      )}
      <div className="chart" style={{ height: 190 }}>
        <ResponsiveContainer>
          <BarChart data={rows} barCategoryGap={2} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="from" tickFormatter={(v) => `$${v / 1000}k`} tick={{ fill: 'var(--muted)', fontSize: 12 }}
              axisLine={{ stroke: 'var(--axis)' }} tickLine={false} interval="preserveStartEnd" />
            <YAxis allowDecimals={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: 'var(--hover)' }}
              content={<ChartTooltip format={(v, p) => [`${num(v)} postings`, p.label]} />} />
            <Bar dataKey="count" fill="var(--series-1)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}
