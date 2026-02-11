interface VisualProblemProps {
  visualType: string
  visualData: Record<string, unknown>
}

export default function VisualProblem({ visualType, visualData }: VisualProblemProps) {
  switch (visualType) {
    case 'clock':
      return <ClockVisual hour={Number(visualData.hour) || 12} minute={Number(visualData.minute) || 0} />
    case 'object_group':
      return <ObjectGroupVisual groups={(visualData.groups as GroupItem[]) || []} operation={String(visualData.operation || '+')} />
    case 'shapes':
      return <ShapeVisual shape={String(visualData.shape || 'circle')} sides={(visualData.sides as number[]) || []} />
    case 'number_line':
      return <NumberLineVisual start={Number(visualData.start) || 0} end={Number(visualData.end) || 20} step={Number(visualData.step) || 2} highlight={visualData.highlight != null ? Number(visualData.highlight) : undefined} />
    default:
      return null
  }
}

/* ── Clock ── */

function ClockVisual({ hour, minute }: { hour: number; minute: number }) {
  const cx = 50, cy = 50, r = 40
  const hAngle = ((hour % 12) + minute / 60) * 30 - 90
  const mAngle = minute * 6 - 90
  const rad = (d: number) => d * Math.PI / 180

  return (
    <svg viewBox="0 0 100 100" className="w-24 h-24 text-foreground print:text-black" role="img" aria-label={`Clock showing ${hour}:${String(minute).padStart(2, '0')}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor" strokeWidth="1.5" />
      {[...Array(12)].map((_, i) => {
        const a = rad(i * 30 - 90)
        return <line key={i} x1={cx + Math.cos(a) * 35} y1={cy + Math.sin(a) * 35} x2={cx + Math.cos(a) * r} y2={cy + Math.sin(a) * r} stroke="currentColor" strokeWidth="1.5" />
      })}
      {[1,2,3,4,5,6,7,8,9,10,11,12].map(n => {
        const a = rad(n * 30 - 90)
        return <text key={n} x={cx + Math.cos(a) * 30} y={cy + Math.sin(a) * 30} textAnchor="middle" dominantBaseline="central" fontSize="7" fill="currentColor" fontWeight="500">{n}</text>
      })}
      <line x1={cx} y1={cy} x2={cx + Math.cos(rad(hAngle)) * 20} y2={cy + Math.sin(rad(hAngle)) * 20} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={cx + Math.cos(rad(mAngle)) * 30} y2={cy + Math.sin(rad(mAngle)) * 30} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="2" fill="currentColor" />
    </svg>
  )
}

/* ── Object Group ── */

interface GroupItem { count: number; label: string }

function ObjectGroupVisual({ groups, operation }: { groups: GroupItem[]; operation: string }) {
  if (!groups.length) return null
  const maxCount = Math.max(...groups.map(g => g.count || 0))
  if (maxCount > 20) return null // too many to draw

  return (
    <div className="flex items-center gap-3 flex-wrap" role="img" aria-label={groups.map(g => `${g.count} ${g.label}`).join(` ${operation} `)}>
      {groups.map((group, gi) => (
        <div key={gi} className="flex items-center gap-3">
          {gi > 0 && <span className="text-lg font-semibold text-foreground/60 print:text-black/60">{operation}</span>}
          <div className="flex flex-col items-center gap-1">
            <div className="flex flex-wrap gap-1 max-w-[160px]">
              {[...Array(Math.min(group.count || 0, 20))].map((_, i) => (
                <svg key={i} viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
                  <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.2" />
                </svg>
              ))}
            </div>
            <span className="text-[10px] text-muted-foreground print:text-black/50">{group.label}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ── Shapes ── */

function ShapeVisual({ shape, sides }: { shape: string; sides: number[] }) {
  const size = 80

  const shapeElement = (() => {
    switch (shape) {
      case 'triangle':
        return (
          <>
            <polygon points={`${size/2},8 8,${size-8} ${size-8},${size-8}`} fill="none" stroke="currentColor" strokeWidth="1.5" />
            {sides[0] != null && <text x={size/4 - 4} y={size/2} fontSize="8" fill="currentColor" textAnchor="middle">{sides[0]}</text>}
            {sides[1] != null && <text x={size/2} y={size - 2} fontSize="8" fill="currentColor" textAnchor="middle">{sides[1]}</text>}
            {sides[2] != null && <text x={size*3/4 + 4} y={size/2} fontSize="8" fill="currentColor" textAnchor="middle">{sides[2]}</text>}
          </>
        )
      case 'rectangle':
        return (
          <>
            <rect x="8" y="16" width={size-16} height={size-32} fill="none" stroke="currentColor" strokeWidth="1.5" />
            {sides[0] != null && <text x={size/2} y="12" fontSize="8" fill="currentColor" textAnchor="middle">{sides[0]}</text>}
            {sides[1] != null && <text x={size - 4} y={size/2} fontSize="8" fill="currentColor" textAnchor="middle">{sides[1]}</text>}
          </>
        )
      case 'square':
        return (
          <>
            <rect x="12" y="12" width={size-24} height={size-24} fill="none" stroke="currentColor" strokeWidth="1.5" />
            {sides[0] != null && <text x={size/2} y="9" fontSize="8" fill="currentColor" textAnchor="middle">{sides[0]}</text>}
          </>
        )
      case 'circle':
      default:
        return (
          <>
            <circle cx={size/2} cy={size/2} r={size/2 - 10} fill="none" stroke="currentColor" strokeWidth="1.5" />
            {sides[0] != null && (
              <>
                <line x1={size/2} y1={size/2} x2={size - 10} y2={size/2} stroke="currentColor" strokeWidth="1" strokeDasharray="3 2" />
                <text x={size*3/4} y={size/2 - 4} fontSize="8" fill="currentColor" textAnchor="middle">{sides[0]}</text>
              </>
            )}
          </>
        )
    }
  })()

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-20 h-20 text-foreground print:text-black" role="img" aria-label={`${shape}${sides.length ? ` with sides ${sides.join(', ')}` : ''}`}>
      {shapeElement}
    </svg>
  )
}

/* ── Number Line ── */

function NumberLineVisual({ start, end, step, highlight }: { start: number; end: number; step: number; highlight?: number }) {
  if (step <= 0 || end <= start) return null
  const w = 280, h = 40, pad = 20
  const lineY = 20
  const range = end - start
  const toX = (val: number) => pad + ((val - start) / range) * (w - 2 * pad)
  const ticks: number[] = []
  for (let v = start; v <= end; v += step) ticks.push(v)

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-[280px] h-10 text-foreground print:text-black" role="img" aria-label={`Number line from ${start} to ${end}${highlight != null ? `, ${highlight} highlighted` : ''}`}>
      <line x1={pad} y1={lineY} x2={w - pad} y2={lineY} stroke="currentColor" strokeWidth="1.2" />
      <polygon points={`${w - pad},${lineY} ${w - pad - 5},${lineY - 3} ${w - pad - 5},${lineY + 3}`} fill="currentColor" />
      {ticks.map(v => (
        <g key={v}>
          <line x1={toX(v)} y1={lineY - 5} x2={toX(v)} y2={lineY + 5} stroke="currentColor" strokeWidth="1" />
          <text x={toX(v)} y={lineY + 15} textAnchor="middle" fontSize="7" fill="currentColor">{v}</text>
        </g>
      ))}
      {highlight != null && highlight >= start && highlight <= end && (
        <circle cx={toX(highlight)} cy={lineY} r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      )}
    </svg>
  )
}
