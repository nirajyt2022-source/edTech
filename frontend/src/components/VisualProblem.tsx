import { useRef, useCallback, useMemo } from 'react'

interface VisualProblemProps {
  visualType: string
  visualData: Record<string, unknown>
  colorMode?: 'mono' | 'color'
  studentAnswer?: string
  onStudentAnswerChange?: (val: string) => void
}

export default function VisualProblem({ visualType, visualData, colorMode = 'mono', studentAnswer, onStudentAnswerChange }: VisualProblemProps) {
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
    case 'base_ten_regrouping':
      return <BaseTenRegroupingVisual numbers={(visualData.numbers as number[]) || []} operation={String(visualData.operation || 'addition')} studentAnswer={studentAnswer} onStudentAnswerChange={onStudentAnswerChange} />
    case 'pie_fraction':
      return <PieFractionVisual numerator={Number(visualData.numerator) || 1} denominator={Number(visualData.denominator) || 2} />
    case 'grid_symmetry':
      return <GridSymmetryVisual gridSize={Number(visualData.grid_size) || 6} filledCells={(visualData.filled_cells as number[][]) || []} foldAxis={(visualData.fold_axis as 'vertical' | 'horizontal') || 'vertical'} />
    case 'money_coins':
      return <MoneyCoinsVisual coins={(visualData.coins as { value: number; count: number }[]) || []} />
    case 'pattern_tiles':
      return <PatternTilesVisual tiles={(visualData.tiles as string[]) || []} blankPosition={visualData.blank_position != null ? Number(visualData.blank_position) : -1} />
    case 'abacus':
      return <AbacusVisual hundreds={Number(visualData.hundreds) || 0} tens={Number(visualData.tens) || 0} ones={Number(visualData.ones) || 0} />
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

/* ── Base Ten Regrouping (column form) ── */

interface BaseTenRegroupingProps {
  numbers: number[]
  operation: string
  studentAnswer?: string
  onStudentAnswerChange?: (val: string) => void
}

function BaseTenRegroupingVisual({ numbers, operation, studentAnswer, onStudentAnswerChange }: BaseTenRegroupingProps) {
  // All hooks must be called before any early return
  const inputRefs = useRef<(HTMLInputElement | null)[]>([null, null, null])

  // Derive answer digits from the controlled prop — no effect + setState needed
  const answerDigits = useMemo(() => {
    if (studentAnswer == null) return ['', '', '']
    const padded = studentAnswer.padStart(3, ' ')
    return [
      padded[padded.length - 3] === ' ' ? '' : padded[padded.length - 3],
      padded[padded.length - 2] === ' ' ? '' : padded[padded.length - 2],
      padded[padded.length - 1] === ' ' ? '' : padded[padded.length - 1],
    ]
  }, [studentAnswer])

  const handleDigitChange = useCallback((idx: number, value: string) => {
    if (!onStudentAnswerChange) return
    const digit = value.replace(/\D/g, '').slice(-1)
    const next = [...answerDigits]
    next[idx] = digit
    onStudentAnswerChange(next.join(''))
    if (digit && idx < 2) {
      inputRefs.current[idx + 1]?.focus()
    }
  }, [answerDigits, onStudentAnswerChange])

  const handleKeyDown = useCallback((idx: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !answerDigits[idx] && idx > 0) {
      inputRefs.current[idx - 1]?.focus()
    }
  }, [answerDigits])

  if (numbers.length < 2) return null
  const [a, b] = numbers
  const opSymbol = operation === 'addition' ? '+' : '\u2212'

  const digits = (n: number) => {
    const s = String(Math.abs(n)).padStart(3, '0')
    return s.split('').map(Number)
  }

  const dA = digits(a)
  const dB = digits(b)

  const w = 160, svgH = 72
  const cols = [52, 84, 116] // H, T, O x-positions
  const headerY = 16, rowA = 36, rowB = 56, lineY = 66, labels = ['H', 'T', 'O']

  return (
    <div className="relative inline-block">
      <svg viewBox={`0 0 ${w} ${svgH}`} className="w-40 h-[72px] text-foreground print:text-black font-mono block" role="img" aria-label={`Column form: ${a} ${opSymbol} ${b}`}>
        {/* Column headers */}
        {labels.map((l, i) => (
          <text key={l} x={cols[i]} y={headerY} textAnchor="middle" fontSize="10" fill="currentColor" fontWeight="600">{l}</text>
        ))}
        {/* First number */}
        {dA.map((d, i) => (
          <text key={`a${i}`} x={cols[i]} y={rowA} textAnchor="middle" fontSize="13" fill="currentColor">{d}</text>
        ))}
        {/* Operation symbol */}
        <text x={28} y={rowB} textAnchor="middle" fontSize="13" fill="currentColor" fontWeight="600">{opSymbol}</text>
        {/* Second number */}
        {dB.map((d, i) => (
          <text key={`b${i}`} x={cols[i]} y={rowB} textAnchor="middle" fontSize="13" fill="currentColor">{d}</text>
        ))}
        {/* Horizontal rule */}
        <line x1={20} y1={lineY} x2={140} y2={lineY} stroke="currentColor" strokeWidth="1.5" />
      </svg>
      {/* Answer input boxes aligned under H/T/O columns */}
      <div className="flex mt-1" style={{ width: '160px', paddingLeft: '30px', paddingRight: '22px' }}>
        {labels.map((l, i) => (
          <div key={l} className="flex-1 flex justify-center">
            <input
              ref={el => { inputRefs.current[i] = el }}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={answerDigits[i]}
              onChange={e => handleDigitChange(i, e.target.value)}
              onKeyDown={e => handleKeyDown(i, e)}
              aria-label={`${l} digit`}
              className="w-6 h-7 text-center text-sm font-mono border border-border rounded bg-white/80 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary print:border-b print:border-black print:border-t-0 print:border-l-0 print:border-r-0 print:bg-transparent print:shadow-none print:outline-none print:rounded-none"
            />
          </div>
        ))}
      </div>
    </div>
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

/* ── Pie Fraction ── */

function PieFractionVisual({ numerator, denominator }: { numerator: number; denominator: number }) {
  const cx = 60, cy = 60, r = 48
  const clampedNum = Math.max(0, Math.min(numerator, denominator))
  const clampedDen = Math.max(1, denominator)

  const wedges = Array.from({ length: clampedDen }, (_, i) => {
    const startAngle = (i / clampedDen) * 2 * Math.PI - Math.PI / 2
    const endAngle = ((i + 1) / clampedDen) * 2 * Math.PI - Math.PI / 2
    const x1 = cx + Math.cos(startAngle) * r
    const y1 = cy + Math.sin(startAngle) * r
    const x2 = cx + Math.cos(endAngle) * r
    const y2 = cy + Math.sin(endAngle) * r
    const largeArc = clampedDen === 1 ? 1 : 0
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
    return { d, shaded: i < clampedNum }
  })

  return (
    <svg viewBox="0 0 120 140" className="w-28 h-32 text-foreground print:text-black" role="img" aria-label={`Fraction ${clampedNum} out of ${clampedDen}: ${clampedNum}/${clampedDen} of a circle shaded`}>
      {wedges.map((w, i) => (
        <path
          key={i}
          d={w.d}
          fill={w.shaded ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="1"
          opacity={w.shaded ? 0.25 : 1}
        />
      ))}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor" strokeWidth="1.5" />
      <text x={cx} y={cy + r + 20} textAnchor="middle" fontSize="12" fill="currentColor" fontWeight="600">
        {clampedNum}/{clampedDen}
      </text>
    </svg>
  )
}

/* ── Grid Symmetry ── */

function GridSymmetryVisual({ gridSize, filledCells, foldAxis }: { gridSize: number; filledCells: number[][]; foldAxis: 'vertical' | 'horizontal' }) {
  const size = 150
  const pad = 10
  const cellSize = (size - 2 * pad) / Math.max(gridSize, 1)
  const filledSet = new Set(filledCells.map(([r, c]) => `${r},${c}`))

  const midIndex = gridSize / 2
  const foldCoord = pad + midIndex * cellSize

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-36 h-36 text-foreground print:text-black" role="img" aria-label={`${gridSize}x${gridSize} symmetry grid with ${foldAxis} fold line`}>
      {/* Dot grid */}
      {Array.from({ length: gridSize + 1 }, (_, row) =>
        Array.from({ length: gridSize + 1 }, (_, col) => (
          <circle
            key={`dot-${row}-${col}`}
            cx={pad + col * cellSize}
            cy={pad + row * cellSize}
            r="1.2"
            fill="currentColor"
            opacity="0.35"
          />
        ))
      )}
      {/* Filled cells */}
      {Array.from({ length: gridSize }, (_, row) =>
        Array.from({ length: gridSize }, (_, col) =>
          filledSet.has(`${row},${col}`) ? (
            <rect
              key={`cell-${row}-${col}`}
              x={pad + col * cellSize + 1}
              y={pad + row * cellSize + 1}
              width={cellSize - 2}
              height={cellSize - 2}
              fill="currentColor"
              opacity="0.22"
              rx="1"
            />
          ) : null
        )
      )}
      {/* Fold line */}
      {foldAxis === 'vertical' ? (
        <line
          x1={foldCoord}
          y1={pad}
          x2={foldCoord}
          y2={size - pad}
          stroke="currentColor"
          strokeWidth="1.8"
          strokeDasharray="5 3"
          opacity="0.7"
        />
      ) : (
        <line
          x1={pad}
          y1={foldCoord}
          x2={size - pad}
          y2={foldCoord}
          stroke="currentColor"
          strokeWidth="1.8"
          strokeDasharray="5 3"
          opacity="0.7"
        />
      )}
    </svg>
  )
}

/* ── Money Coins ── */

function MoneyCoinsVisual({ coins }: { coins: { value: number; count: number }[] }) {
  if (!coins.length) return null

  const itemW = 52
  const h = 80
  const totalW = Math.max(250, coins.length * itemW + 20)

  return (
    <svg
      viewBox={`0 0 ${totalW} ${h}`}
      className="w-full max-w-[300px] text-foreground print:text-black"
      role="img"
      aria-label={coins.map(c => `${c.count} x ₹${c.value}`).join(', ')}
    >
      {coins.map((coin, i) => {
        const cx = 26 + i * itemW
        const isCoin = coin.value <= 10
        return (
          <g key={i}>
            {isCoin ? (
              /* Coin: circle */
              <>
                <circle cx={cx} cy={30} r={18} fill="none" stroke="currentColor" strokeWidth="1.5" />
                <circle cx={cx} cy={30} r={14} fill="none" stroke="currentColor" strokeWidth="0.6" />
                <text x={cx} y={28} textAnchor="middle" fontSize="7" fill="currentColor">&#8377;</text>
                <text x={cx} y={38} textAnchor="middle" fontSize="9" fill="currentColor" fontWeight="600">{coin.value}</text>
              </>
            ) : (
              /* Note: rectangle */
              <>
                <rect x={cx - 18} y={14} width={36} height={22} rx="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <rect x={cx - 14} y={17} width={28} height={16} rx="2" fill="none" stroke="currentColor" strokeWidth="0.6" />
                <text x={cx} y={26} textAnchor="middle" fontSize="7" fill="currentColor">&#8377;</text>
                <text x={cx} y={34} textAnchor="middle" fontSize="7" fill="currentColor" fontWeight="600">{coin.value}</text>
              </>
            )}
            {/* Count label */}
            <text x={cx} y={62} textAnchor="middle" fontSize="8" fill="currentColor" opacity="0.7">
              x{coin.count}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ── Pattern Tiles ── */

function PatternTilesVisual({ tiles, blankPosition }: { tiles: string[]; blankPosition: number }) {
  if (!tiles.length) return null

  const tileW = 40, tileH = 40, gap = 6, pad = 8
  const totalW = Math.max(250, tiles.length * (tileW + gap) - gap + 2 * pad)
  const totalH = 60

  return (
    <svg
      viewBox={`0 0 ${totalW} ${totalH}`}
      className="w-full max-w-[300px] text-foreground print:text-black"
      role="img"
      aria-label={`Pattern sequence: ${tiles.join(', ')}${blankPosition >= 0 ? `, blank at position ${blankPosition + 1}` : ''}`}
    >
      {tiles.map((label, i) => {
        const x = pad + i * (tileW + gap)
        const y = (totalH - tileH) / 2
        const isBlank = i === blankPosition
        const isEven = i % 2 === 0

        return (
          <g key={i}>
            <rect
              x={x}
              y={y}
              width={tileW}
              height={tileH}
              rx="4"
              fill={isBlank ? 'none' : isEven ? 'currentColor' : 'none'}
              stroke="currentColor"
              strokeWidth={isBlank ? 1.5 : 1}
              strokeDasharray={isBlank ? '4 3' : undefined}
              opacity={isEven && !isBlank ? 0.15 : 1}
            />
            {/* Slightly darker border for even filled tiles */}
            {!isBlank && isEven && (
              <rect x={x} y={y} width={tileW} height={tileH} rx="4" fill="none" stroke="currentColor" strokeWidth="1" />
            )}
            <text
              x={x + tileW / 2}
              y={y + tileH / 2 + 1}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={isBlank ? '14' : '13'}
              fill="currentColor"
              fontWeight="600"
            >
              {label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ── Abacus ── */

function AbacusVisual({ hundreds, tens, ones }: { hundreds: number; ones: number; tens: number }) {
  const w = 160, h = 120
  const frameX = 16, frameY = 10, frameW = 128, frameH = 90
  const rodXs = [52, 80, 108]
  const rodLabels = ['H', 'T', 'O']
  const rodValues = [Math.max(0, Math.min(hundreds, 9)), Math.max(0, Math.min(tens, 9)), Math.max(0, Math.min(ones, 9))]
  const rodTop = frameY + 8
  const rodBottom = frameY + frameH - 8
  const beadR = 5
  const beadSpacing = 12
  const maxBeads = 9

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-40 h-28 text-foreground print:text-black" role="img" aria-label={`Abacus: ${hundreds} hundreds, ${tens} tens, ${ones} ones`}>
      {/* Frame */}
      <rect x={frameX} y={frameY} width={frameW} height={frameH} rx="4" fill="none" stroke="currentColor" strokeWidth="2" />
      {/* Top and bottom bars */}
      <line x1={frameX} y1={frameY + 14} x2={frameX + frameW} y2={frameY + 14} stroke="currentColor" strokeWidth="1.5" />
      <line x1={frameX} y1={frameY + frameH - 14} x2={frameX + frameW} y2={frameY + frameH - 14} stroke="currentColor" strokeWidth="1.5" />

      {rodXs.map((rx, ri) => {
        const count = rodValues[ri]
        const beadAreaTop = rodTop + 14
        const beadAreaBottom = rodBottom - 14
        const beadAreaH = beadAreaBottom - beadAreaTop
        const startY = beadAreaBottom - beadR

        return (
          <g key={ri}>
            {/* Rod */}
            <line x1={rx} y1={rodTop} x2={rx} y2={rodBottom} stroke="currentColor" strokeWidth="1.2" opacity="0.4" />
            {/* Beads */}
            {Array.from({ length: Math.min(count, maxBeads) }, (_, bi) => {
              const beadY = startY - bi * Math.min(beadSpacing, beadAreaH / maxBeads)
              return (
                <circle
                  key={bi}
                  cx={rx}
                  cy={beadY}
                  r={beadR}
                  fill="currentColor"
                  opacity="0.25"
                  stroke="currentColor"
                  strokeWidth="1"
                />
              )
            })}
            {/* Column label */}
            <text x={rx} y={frameY + frameH + 14} textAnchor="middle" fontSize="10" fill="currentColor" fontWeight="600">
              {rodLabels[ri]}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
