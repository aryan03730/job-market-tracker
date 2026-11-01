import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { num, pct } from '../format'
import ChartCard from './ChartCard'
import ChartTooltip from './Tooltip'

export default function SkillsChart({ data, selected, onSelect }) {
  const rows = (data || []).slice(0, 15)
  return (
    <ChartCard
      title="Most requested skills"
      subtitle="Share of postings that mention each skill. Click a bar to filter the postings below."
      table={{ columns: ['Skill', 'Postings', 'Share'], rows: (data || []).map((d) => [d.skill, d.count, pct(d.share)]) }}
    >
      <div className="chart" style={{ height: Math.max(220, rows.length * 26) }}>
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" barCategoryGap={2} margin={{ top: 0, right: 44, bottom: 0, left: 0 }}>
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis type="category" dataKey="skill" width={118} tick={{ fill: 'var(--text-2)', fontSize: 13 }}
              axisLine={{ stroke: 'var(--axis)' }} tickLine={false} />
            <Tooltip cursor={{ fill: 'var(--hover)' }}
              content={<ChartTooltip format={(v, p) => [`${num(v)} postings (${pct(p.share)})`, p.skill]} />} />
            <Bar dataKey="count" radius={[0, 4, 4, 0]} isAnimationActive={false} cursor="pointer"
              onClick={(d) => { const name = d?.payload?.skill ?? d?.skill; onSelect(selected === name ? "" : name) }}>
              {rows.map((d) => (
                <Cell key={d.skill} fill="var(--series-1)"
                  fillOpacity={selected && selected !== d.skill ? 0.35 : 1} />
              ))}
              <LabelList dataKey="share" position="right" formatter={pct}
                style={{ fill: 'var(--text-2)', fontSize: 12 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}
