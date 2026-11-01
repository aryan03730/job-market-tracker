export default function ChartTooltip({ active, payload, label, format }) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  const [value, name] = format ? format(p.value, p.payload, label) : [p.value, label]
  return (
    <div className="tooltip">
      <div className="tooltip-label">{name}</div>
      <div className="tooltip-value">{value}</div>
    </div>
  )
}
