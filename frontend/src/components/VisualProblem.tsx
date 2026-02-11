interface VisualProblemProps {
  visualType: string
  visualData: Record<string, unknown>
  colorMode?: 'mono' | 'color'
}

export default function VisualProblem({ visualType, visualData, colorMode = 'mono' }: VisualProblemProps) {
  const useColor = colorMode === 'color'
  switch (visualType) {
    case 'clock':
      return <ClockVisual hour={Number(visualData.hour) || 12} minute={Number(visualData.minute) || 0} />
    case 'object_group':
      return <ObjectGroupVisual groups={(visualData.groups as GroupItem[]) || []} operation={String(visualData.operation || '+')} useColor={useColor} />
    case 'shapes':
      return <ShapeVisual shape={String(visualData.shape || 'circle')} sides={(visualData.sides as number[]) || []} />
    case 'number_line':
      return <NumberLineVisual start={Number(visualData.start) || 0} end={Number(visualData.end) || 20} step={Number(visualData.step) || 2} highlight={visualData.highlight != null ? Number(visualData.highlight) : undefined} useColor={useColor} />
    default:
      return null
  }
}

/* ── Token Icons ── */

const TOKEN_COLORS: Record<string, string> = {
  fruit: '#c8a07a',
  bird: '#7ea898',
  star: '#c8b858',
  coin: '#b8a468',
  marble: '#88a0b8',
  balloon: '#b88888',
  candy: '#b888b8',
  flower: '#c89898',
  pencil: '#b8a888',
  book: '#a8b8a0',
  generic: 'none',
}

function TokenIcon({ type, useColor }: { type: string; useColor?: boolean }) {
  const fill = useColor ? (TOKEN_COLORS[type] || 'none') : 'none'
  const cf = fill !== 'none' ? 'token-cf' : undefined

  switch (type) {
    case 'fruit':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <path d="M6 1.5C6 1.5 6.8 0.5 7.5 0.8C8.2 1.1 7.2 2 6.5 2.2" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" />
          <path d="M6 2.5C4 2.5 1.5 4 1.5 7C1.5 9.5 3.5 11.5 6 11.5C8.5 11.5 10.5 9.5 10.5 7C10.5 4 8 2.5 6 2.5Z" fill={fill} className={cf} stroke="currentColor" strokeWidth="1" />
          <path d="M6 2.5C6 4.5 6 6 6 6" stroke="currentColor" strokeWidth="0.6" strokeLinecap="round" />
        </svg>
      )
    case 'bird':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <path d="M1 7C1 7 2.5 4 5 4C6 4 6.5 4.5 7 5C7.5 4 9 3 10 3.5" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
          <path d="M7 5C7 5 7.5 7 7 8.5C6.5 10 5 10.5 3.5 10C2 9.5 1.5 8 1.5 7" fill={fill} className={cf} stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
          <circle cx="4" cy="5.5" r="0.5" fill="currentColor" />
          <path d="M2 6.5L0.5 6" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" />
          <path d="M5.5 10L5 11.5M7 9.5L7 11" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" />
        </svg>
      )
    case 'star':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <polygon
            points="6,0.8 7.4,4.2 11.2,4.4 8.2,7 9.2,10.8 6,8.8 2.8,10.8 3.8,7 0.8,4.4 4.6,4.2"
            fill={fill} className={cf} stroke="currentColor" strokeWidth="1" strokeLinejoin="round"
          />
        </svg>
      )
    case 'coin':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <circle cx="6" cy="6" r="5" fill={fill} className={cf} stroke="currentColor" strokeWidth="1" />
          <circle cx="6" cy="6" r="3.5" fill="none" stroke="currentColor" strokeWidth="0.6" />
          <text x="6" y="7.2" textAnchor="middle" fontSize="4" fill="currentColor" fontWeight="600">$</text>
        </svg>
      )
    case 'marble':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <circle cx="6" cy="6" r="5" fill={fill} className={cf} stroke="currentColor" strokeWidth="1" />
          <ellipse cx="4.5" cy="4.5" rx="1.5" ry="1" fill="none" stroke="currentColor" strokeWidth="0.5" transform="rotate(-30 4.5 4.5)" />
        </svg>
      )
    case 'balloon':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <ellipse cx="6" cy="5" rx="4" ry="4.5" fill={fill} className={cf} stroke="currentColor" strokeWidth="1" />
          <polygon points="5,9.3 6,11 7,9.3" fill="none" stroke="currentColor" strokeWidth="0.7" strokeLinejoin="round" />
          <path d="M6 11L6 11.8" stroke="currentColor" strokeWidth="0.6" strokeLinecap="round" />
        </svg>
      )
    case 'candy':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <ellipse cx="6" cy="6" rx="3.2" ry="2.8" fill={fill} className={cf} stroke="currentColor" strokeWidth="1" />
          <path d="M2.8 5.5C2.2 4.5 1 4 0.5 4.5" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" fill="none" />
          <path d="M2.8 6.5C2.2 7.5 1 8 0.5 7.5" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" fill="none" />
          <path d="M9.2 5.5C9.8 4.5 11 4 11.5 4.5" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" fill="none" />
          <path d="M9.2 6.5C9.8 7.5 11 8 11.5 7.5" stroke="currentColor" strokeWidth="0.8" strokeLinecap="round" fill="none" />
        </svg>
      )
    case 'flower':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          {[0, 72, 144, 216, 288].map(angle => (
            <ellipse key={angle} cx="6" cy="3" rx="1.8" ry="2.5" fill={fill} className={cf} stroke="currentColor" strokeWidth="0.8" transform={`rotate(${angle} 6 6)`} />
          ))}
          <circle cx="6" cy="6" r="1.5" fill="currentColor" stroke="currentColor" strokeWidth="0.5" />
        </svg>
      )
    case 'pencil':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <rect x="3" y="1" width="6" height="8.5" rx="0.5" fill={fill} className={cf} stroke="currentColor" strokeWidth="0.8" />
          <polygon points="3,9.5 6,12 9,9.5" fill="none" stroke="currentColor" strokeWidth="0.8" strokeLinejoin="round" />
          <line x1="6" y1="10.5" x2="6" y2="12" stroke="currentColor" strokeWidth="0.5" />
          <rect x="3" y="1" width="6" height="1.5" fill="none" stroke="currentColor" strokeWidth="0.5" />
        </svg>
      )
    case 'book':
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <path d="M1.5 2C1.5 2 3 1 6 1.5L6 10.5C3 10 1.5 11 1.5 11Z" fill={fill} className={cf} stroke="currentColor" strokeWidth="0.8" strokeLinejoin="round" />
          <path d="M10.5 2C10.5 2 9 1 6 1.5L6 10.5C9 10 10.5 11 10.5 11Z" fill={fill} className={cf} stroke="currentColor" strokeWidth="0.8" strokeLinejoin="round" />
        </svg>
      )
    default:
      return (
        <svg viewBox="0 0 12 12" className="w-4 h-4 text-foreground/70 print:text-black/70">
          <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      )
  }
}

const TOKEN_KEYWORDS: Record<string, string[]> = {
  fruit: ['mango', 'mangoes', 'apple', 'apples', 'orange', 'oranges', 'banana', 'bananas', 'fruit', 'fruits', 'guava', 'guavas'],
  bird: ['bird', 'birds', 'parrot', 'parrots', 'sparrow', 'sparrows', 'crow', 'crows', 'pigeon', 'pigeons', 'hen', 'hens', 'duck', 'ducks'],
  star: ['star', 'stars', 'sticker', 'stickers'],
  coin: ['coin', 'coins', 'rupee', 'rupees', 'money', 'paise'],
  marble: ['marble', 'marbles', 'ball', 'balls', 'bead', 'beads'],
  balloon: ['balloon', 'balloons'],
  candy: ['candy', 'candies', 'sweet', 'sweets', 'toffee', 'toffees', 'chocolate', 'chocolates', 'lollipop', 'lollipops'],
  flower: ['flower', 'flowers', 'rose', 'roses', 'lily', 'lilies', 'sunflower', 'sunflowers'],
  pencil: ['pencil', 'pencils', 'pen', 'pens', 'crayon', 'crayons', 'eraser', 'erasers'],
  book: ['book', 'books', 'notebook', 'notebooks', 'copy', 'copies'],
}

function resolveTokenType(label: string): string {
  const lower = label.toLowerCase()
  for (const [type, keywords] of Object.entries(TOKEN_KEYWORDS)) {
    if (keywords.some(kw => lower.includes(kw))) return type
  }
  return 'generic'
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

function ObjectGroupVisual({ groups, operation, useColor }: { groups: GroupItem[]; operation: string; useColor?: boolean }) {
  if (!groups.length) return null
  const maxCount = Math.max(...groups.map(g => g.count || 0))
  if (maxCount > 20) return null // too many to draw

  return (
    <div className="flex items-center gap-3 flex-wrap" role="img" aria-label={groups.map(g => `${g.count} ${g.label}`).join(` ${operation} `)}>
      {groups.map((group, gi) => {
        const tokenType = resolveTokenType(group.label)
        return (
          <div key={gi} className="flex items-center gap-3">
            {gi > 0 && <span className="text-lg font-semibold text-foreground/60 print:text-black/60">{operation}</span>}
            <div className="flex flex-col items-center gap-1">
              <div className="flex flex-wrap gap-1 max-w-[160px]">
                {[...Array(Math.min(group.count || 0, 20))].map((_, i) => (
                  <TokenIcon key={i} type={tokenType} useColor={useColor} />
                ))}
              </div>
              <span className="text-[10px] text-muted-foreground print:text-black/50">{group.label}</span>
            </div>
          </div>
        )
      })}
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

function NumberLineVisual({ start, end, step, highlight, useColor }: { start: number; end: number; step: number; highlight?: number; useColor?: boolean }) {
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
        <circle cx={toX(highlight)} cy={lineY} r="4" fill={useColor ? '#88a0b8' : 'none'} className={useColor ? 'token-cf' : undefined} stroke="currentColor" strokeWidth="2" />
      )}
    </svg>
  )
}
