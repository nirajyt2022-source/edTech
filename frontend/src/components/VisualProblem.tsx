import React, { memo } from 'react'

/* ── Standardized visual sizes ── */
const VISUAL_SIZE: Record<string, string> = {
  clock: "w-full max-w-[350px]",
  number_line: "w-full",
  base_ten_regrouping: "w-full max-w-[400px]",
  grid_symmetry: "w-full max-w-[300px]",
  shapes: "w-full max-w-[400px]",
  pie_fraction: "w-full max-w-[350px]",
  money_coins: "w-full max-w-[400px]",
  pattern_tiles: "w-full max-w-[400px]",
  object_group: "w-full",
  abacus: "w-full max-w-[300px]",
  picture_word_match: "w-full max-w-[350px]",
  labeled_diagram: "w-full max-w-[350px]",
  match_columns: "w-full max-w-[400px]",
  ten_frame: "w-full max-w-[350px]",
  pictograph: "w-full max-w-[400px]",
  array_visual: "w-full max-w-[350px]",
  fraction_bar: "w-full max-w-[400px]",
  scenario_picture: "w-full max-w-[400px]",
  sequence_pictures: "w-full",
  bar_chart: "w-full max-w-[400px]",
  food_plate: "w-full max-w-[300px]",
  percentage_bar: "w-full max-w-[400px]",
}

function VisualContainer({ type, children }: { type: string; children: React.ReactNode }) {
  const size = VISUAL_SIZE[type] ?? "w-40 h-28"
  return (
    <div className={`flex items-center justify-center ${size} mx-auto my-2`}>
      {children}
    </div>
  )
}

interface VisualProblemProps {
  visualType: string
  visualData: Record<string, unknown>
  colorMode?: 'mono' | 'color'
  studentAnswer?: string
  onStudentAnswerChange?: (val: string) => void
}

export default memo(function VisualProblem({ visualType, visualData, colorMode = 'mono' }: VisualProblemProps) {
  const useColor = colorMode === 'color'
  switch (visualType) {
    case 'clock':
      return <VisualContainer type="clock"><ClockVisual hour={Number(visualData.hour) || 12} minute={Number(visualData.minute) || 0} /></VisualContainer>
    case 'object_group':
      return <VisualContainer type="object_group"><ObjectGroupVisual groups={(visualData.groups as GroupItem[]) || []} operation={String(visualData.operation || '+')} useColor={useColor} /></VisualContainer>
    case 'shapes':
      return <VisualContainer type="shapes"><ShapeIdentifyVisual shapes={(visualData.shapes as {name: string; sides: number; color: string}[]) || []} targetIndex={Number(visualData.target_index ?? -1)} /></VisualContainer>
    case 'number_line':
      return <VisualContainer type="number_line"><NumberLineVisual start={Number(visualData.start) || 0} end={Number(visualData.end) || 20} step={Number(visualData.step) || 2} highlight={visualData.highlight != null ? Number(visualData.highlight) : undefined} useColor={useColor} hopsFrom={Number(visualData.hops_from ?? -1)} hopsCount={Number(visualData.hops_count ?? 0)} hopsDirection={String(visualData.hops_direction || 'forward')} highlightStart={Number(visualData.highlight_start ?? -1)} /></VisualContainer>
    case 'base_ten_regrouping':
      return <VisualContainer type="base_ten_regrouping"><BaseTenBlocksVisual numbers={(visualData.numbers as number[]) || []} operation={String(visualData.operation || 'show')} /></VisualContainer>
    case 'pie_fraction':
      return <VisualContainer type="pie_fraction"><PieFractionVisual numerator={Number(visualData.numerator) || 1} denominator={Number(visualData.denominator) || 2} /></VisualContainer>
    case 'grid_symmetry':
      return <VisualContainer type="grid_symmetry"><GridSymmetryVisual gridSize={Number(visualData.grid_size) || 6} filledCells={(visualData.filled_cells as number[][]) || []} foldAxis={(visualData.fold_axis as 'vertical' | 'horizontal') || 'vertical'} /></VisualContainer>
    case 'money_coins':
      return <VisualContainer type="money_coins"><MoneyCoinsVisual items={(visualData.items as {value: number; type: string; label: string; color: string}[]) || []} total={Number(visualData.total) || 0} /></VisualContainer>
    case 'pattern_tiles':
      return <VisualContainer type="pattern_tiles"><PatternCompletionVisual tiles={(visualData.tiles as string[]) || []} blankPosition={visualData.blank_position != null ? Number(visualData.blank_position) : -1} /></VisualContainer>
    case 'abacus':
      return <VisualContainer type="abacus"><AbacusVisual hundreds={Number(visualData.hundreds) || 0} tens={Number(visualData.tens) || 0} ones={Number(visualData.ones) || 0} /></VisualContainer>
    case 'picture_word_match':
      return <VisualContainer type="picture_word_match"><PictureWordMatchVisual emoji={String(visualData.emoji || '❓')} /></VisualContainer>
    case 'labeled_diagram':
      return <VisualContainer type="labeled_diagram"><LabeledDiagramVisual labels={(visualData.labels as string[]) || []} blankIndex={Number(visualData.blank_index ?? -1)} /></VisualContainer>
    case 'match_columns':
      return <VisualContainer type="match_columns"><MatchColumnsVisual left={(visualData.left as {emoji: string; label: string}[]) || []} right={(visualData.right as {emoji: string; label: string}[]) || []} /></VisualContainer>
    case 'ten_frame':
      return <VisualContainer type="ten_frame"><TenFrameVisual filled={Number(visualData.filled) || 5} total={Number(visualData.total) || 10} color={String(visualData.color || '#6366F1')} /></VisualContainer>
    case 'pictograph':
      return <VisualContainer type="pictograph"><PictographVisual rows={(visualData.rows as {label: string; emoji: string; count: number}[]) || []} title={String(visualData.title || 'Picture Graph')} /></VisualContainer>
    case 'array_visual':
      return <VisualContainer type="array_visual"><ArrayVisual rows={Number(visualData.rows) || 3} cols={Number(visualData.cols) || 4} emoji={String(visualData.emoji || '⭐')} /></VisualContainer>
    case 'fraction_bar':
      return <VisualContainer type="fraction_bar"><FractionBarVisual numerator={Number(visualData.numerator) || 1} denominator={Number(visualData.denominator) || 4} color={String(visualData.color || '#6366F1')} second={visualData.second as {numerator: number; denominator: number} | null} /></VisualContainer>
    case 'scenario_picture':
      return <VisualContainer type="scenario_picture"><ScenarioPictureVisual scene={String(visualData.scene_emoji || '')} description={String(visualData.description || '')} /></VisualContainer>
    case 'sequence_pictures':
      return <VisualContainer type="sequence_pictures"><SequencePicturesVisual steps={(visualData.steps as string[]) || []} labels={(visualData.labels as string[]) || []} blankIndex={Number(visualData.blank_index ?? -1)} /></VisualContainer>
    case 'bar_chart':
      return <VisualContainer type="bar_chart"><BarChartVisual bars={(visualData.bars as {label: string; value: number; color: string}[]) || []} title={String(visualData.title || '')} /></VisualContainer>
    case 'food_plate':
      return <VisualContainer type="food_plate"><FoodPlateVisual groups={(visualData.groups as {name: string; emoji: string; color: string}[]) || []} blankIndex={Number(visualData.blank_index ?? -1)} /></VisualContainer>
    case 'percentage_bar':
      return <VisualContainer type="percentage_bar"><PercentageBarVisual percent={Number(visualData.percent) || 25} color={String(visualData.color || '#6366F1')} /></VisualContainer>
    default:
      return null
  }
})

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

const TokenIcon = memo(function TokenIcon({ type, useColor }: { type: string; useColor?: boolean }) {
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
})

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
  const size = 140, cx = size / 2, cy = size / 2, r = 55
  const hAngle = ((hour % 12 + minute / 60) * 30 - 90) * Math.PI / 180
  const mAngle = (minute * 6 - 90) * Math.PI / 180

  return (
    <div className="my-3 px-4 py-4 bg-gradient-to-br from-blue-50 to-sky-50 rounded-2xl border border-blue-200/60 w-full">
      <div className="flex justify-center">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="drop-shadow-lg" role="img" aria-label={`Clock showing ${hour}:${String(minute).padStart(2, '0')}`}>
          <circle cx={cx} cy={cy} r={r + 5} fill="#1E1B4B" />
          <circle cx={cx} cy={cy} r={r} fill="white" />
          {Array.from({ length: 12 }).map((_, i) => {
            const a = ((i + 1) * 30 - 90) * Math.PI / 180
            const nx = cx + (r - 15) * Math.cos(a)
            const ny = cy + (r - 15) * Math.sin(a)
            const tx1 = cx + (r - 5) * Math.cos(a)
            const ty1 = cy + (r - 5) * Math.sin(a)
            const tx2 = cx + r * Math.cos(a)
            const ty2 = cy + r * Math.sin(a)
            return (
              <g key={i}>
                <line x1={tx1} y1={ty1} x2={tx2} y2={ty2} stroke="#1E1B4B" strokeWidth="2" />
                <text x={nx} y={ny + 4} textAnchor="middle" fontSize="12" fontWeight="bold" fill="#1E1B4B">{i + 1}</text>
              </g>
            )
          })}
          <line x1={cx} y1={cy} x2={cx + 28 * Math.cos(hAngle)} y2={cy + 28 * Math.sin(hAngle)} stroke="#1E1B4B" strokeWidth="4" strokeLinecap="round" />
          <line x1={cx} y1={cy} x2={cx + 38 * Math.cos(mAngle)} y2={cy + 38 * Math.sin(mAngle)} stroke="#6366F1" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx={cx} cy={cy} r={4} fill="#F97316" />
        </svg>
      </div>
      <p className="text-center text-sm text-blue-600/80 mt-2 font-semibold">What time does the clock show?</p>
    </div>
  )
}

/* ── Object Group ── */

interface GroupItem { count: number; label: string; emoji?: string; type?: string }

function ObjectGroupVisual({ groups, operation, useColor }: { groups: GroupItem[]; operation: string; useColor?: boolean }) {
  if (!groups.length) return null
  const maxCount = Math.max(...groups.map(g => g.count || 0))
  if (maxCount > 20) return null // too many to draw

  const hasEmoji = groups.some(g => g.emoji)

  if (hasEmoji) {
    const bgClass = operation === '-'
      ? 'from-rose-50 to-pink-50 border-rose-200/60'
      : 'from-amber-50 to-orange-50 border-amber-200/60'
    const opColor = operation === '-' ? 'bg-rose-500 shadow-rose-200' : 'bg-orange-500 shadow-orange-200'
    const labelColor = operation === '-' ? 'text-rose-600/70' : 'text-amber-600/70'

    return (
      <div className={`my-3 px-4 py-4 bg-gradient-to-br ${bgClass} rounded-2xl border w-full`}>
        <div className="flex items-center justify-center gap-3 flex-wrap">
          {groups.map((group, gi) => (
            <React.Fragment key={gi}>
              {gi > 0 && (
                <div className={`w-9 h-9 rounded-full ${opColor} flex items-center justify-center shadow-md flex-shrink-0`}>
                  <span className="text-white text-lg font-bold">{operation}</span>
                </div>
              )}
              <div className="flex flex-wrap gap-1.5 items-center justify-center bg-white/70 rounded-xl px-3 py-2.5 border border-amber-100/80 shadow-sm max-w-[200px]">
                {Array.from({ length: Math.min(group.count || 0, 20) }).map((_, i) => (
                  <span key={i} className="text-2xl md:text-3xl leading-none select-none"
                        style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.1))" }}>
                    {group.emoji || "●"}
                  </span>
                ))}
              </div>
            </React.Fragment>
          ))}

          {operation !== "count" && (
            <>
              <div className="w-9 h-9 rounded-full bg-indigo-500 flex items-center justify-center shadow-md shadow-indigo-200 flex-shrink-0">
                <span className="text-white text-lg font-bold">=</span>
              </div>
              <div className="w-12 h-12 rounded-xl bg-white flex items-center justify-center shadow-inner"
                   style={{ borderWidth: '3px', borderStyle: 'dashed', borderColor: '#A5B4FC' }}>
                <span className="text-xl font-bold text-indigo-400">?</span>
              </div>
            </>
          )}
        </div>
        {groups[0]?.label && (
          <p className={`text-center text-xs ${labelColor} mt-2 font-medium`}>
            Count the {groups[0].label}s!
          </p>
        )}
      </div>
    )
  }

  // Fall back to old TokenIcon implementation for backward compatibility
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

/* ── Shapes (Identify) ── */

const SHAPE_PATHS: Record<string, string> = {
  circle: "M 25 5 a 20 20 0 1 0 0.001 0",
  triangle: "M 25 5 L 45 42 L 5 42 Z",
  square: "M 5 5 h 40 v 40 h -40 Z",
  rectangle: "M 2 12 h 46 v 26 h -46 Z",
  pentagon: "M 25 5 L 45 20 L 38 42 L 12 42 L 5 20 Z",
  hexagon: "M 15 5 L 35 5 L 45 25 L 35 45 L 15 45 L 5 25 Z",
}

function ShapeIdentifyVisual({ shapes }: { shapes: {name: string; sides: number; color: string}[]; targetIndex: number }) {
  if (!shapes.length) return null

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-emerald-50 to-teal-50 rounded-2xl border border-emerald-200/60 w-full">
      <div className="flex items-center justify-center gap-4 flex-wrap">
        {shapes.map((shape, i) => (
          <div key={i} className="flex flex-col items-center gap-1.5">
            <div className="w-16 h-16 flex items-center justify-center rounded-xl bg-white border border-emerald-100 shadow-sm">
              <svg width="50" height="50" viewBox="0 0 50 50">
                <path d={SHAPE_PATHS[shape.name] || SHAPE_PATHS.circle}
                      fill={shape.color + "30"} stroke={shape.color} strokeWidth="2.5" />
              </svg>
            </div>
            <span className="text-xs text-slate-500 font-bold">{String.fromCharCode(65 + i)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Base Ten Blocks ── */

function BaseTenBlocksVisual({ numbers }: { numbers: number[]; operation: string }) {
  const num = numbers[0] || 0
  const hundreds = Math.floor(num / 100)
  const tens = Math.floor((num % 100) / 10)
  const ones = num % 10

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-blue-50 to-sky-50 rounded-2xl border border-blue-200/60 w-full">
      <div className="flex items-end justify-center gap-4">
        {hundreds > 0 && (
          <div className="flex flex-col items-center gap-1">
            <div className="flex gap-1">
              {Array.from({ length: hundreds }).map((_, i) => (
                <div key={i} className="w-10 h-10 bg-blue-500 rounded border border-blue-600 shadow-sm" />
              ))}
            </div>
            <span className="text-xs text-blue-600 font-bold">{hundreds}00</span>
          </div>
        )}
        {tens > 0 && (
          <div className="flex flex-col items-center gap-1">
            <div className="flex gap-0.5">
              {Array.from({ length: tens }).map((_, i) => (
                <div key={i} className="w-3 h-10 bg-green-500 rounded-sm border border-green-600" />
              ))}
            </div>
            <span className="text-xs text-green-600 font-bold">{tens}0</span>
          </div>
        )}
        {ones > 0 && (
          <div className="flex flex-col items-center gap-1">
            <div className="flex gap-0.5 flex-wrap" style={{ maxWidth: '48px' }}>
              {Array.from({ length: ones }).map((_, i) => (
                <div key={i} className="w-3 h-3 bg-orange-400 rounded-sm border border-orange-500" />
              ))}
            </div>
            <span className="text-xs text-orange-600 font-bold">{ones}</span>
          </div>
        )}
      </div>
      <p className="text-center text-sm text-blue-700 font-bold mt-3">
        {num} = {hundreds > 0 ? `${hundreds} hundreds ` : ''}{tens > 0 ? `${tens} tens ` : ''}{ones > 0 ? `${ones} ones` : ''}
      </p>
    </div>
  )
}

/* ── Number Line ── */

function NumberLineVisual({ start, end, step, highlight, hopsFrom = -1, hopsCount = 0, hopsDirection = 'forward', highlightStart = -1 }: { start: number; end: number; step: number; highlight?: number; useColor?: boolean; hopsFrom?: number; hopsCount?: number; hopsDirection?: string; highlightStart?: number }) {
  if (step <= 0 || end <= start) return null
  const hasHops = hopsCount > 0 && hopsFrom >= 0
  const w = 400, h = hasHops ? 70 : 50, pad = 25
  const lineY = hasHops ? 45 : 28
  const range = end - start
  const toX = (val: number) => pad + ((val - start) / range) * (w - 2 * pad)
  const ticks: number[] = []
  for (let v = start; v <= end; v += step) ticks.push(v)

  return (
    <div className="my-3 px-4 py-4 bg-gradient-to-br from-sky-50 to-cyan-50 rounded-2xl border border-sky-200/60 w-full">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label={`Number line from ${start} to ${end}${highlight != null ? `, ${highlight} highlighted` : ''}`}>
        <line x1={pad} y1={lineY} x2={w - pad} y2={lineY} stroke="#1E293B" strokeWidth="1.5" />
        <polygon points={`${w - pad},${lineY} ${w - pad - 6},${lineY - 3.5} ${w - pad - 6},${lineY + 3.5}`} fill="#1E293B" />
        {ticks.map(v => (
          <g key={v}>
            <line x1={toX(v)} y1={lineY - 6} x2={toX(v)} y2={lineY + 6} stroke="#1E293B" strokeWidth="1.2" />
            <text x={toX(v)} y={lineY + 18} textAnchor="middle" fontSize="10" fill="#334155" fontWeight="500">{v}</text>
          </g>
        ))}
        {hasHops && Array.from({ length: hopsCount }).map((_, i) => {
          const fromN = hopsDirection === 'forward' ? hopsFrom + i : hopsFrom - i
          const toN = hopsDirection === 'forward' ? hopsFrom + i + 1 : hopsFrom - i - 1
          if (fromN < start || fromN > end || toN < start || toN > end) return null
          const x1 = toX(fromN)
          const x2 = toX(toN)
          const midX = (x1 + x2) / 2
          return (
            <path key={`hop-${i}`} d={`M ${x1} ${lineY - 4} Q ${midX} ${lineY - 22 - i * 2} ${x2} ${lineY - 4}`}
                  fill="none" stroke="#F97316" strokeWidth="2.5" strokeDasharray="5 3" />
          )
        })}
        {highlightStart >= 0 && highlightStart >= start && highlightStart <= end && (
          <circle cx={toX(highlightStart)} cy={lineY} r="6" fill="#F59E0B" stroke="#D97706" strokeWidth="1.5" />
        )}
        {highlight != null && highlight >= start && highlight <= end && (
          <circle cx={toX(highlight)} cy={lineY} r="5" fill="#6366F1" stroke="#4F46E5" strokeWidth="2" />
        )}
      </svg>
    </div>
  )
}

/* ── Pie Fraction ── */

function PieFractionVisual({ numerator, denominator }: { numerator: number; denominator: number }) {
  const size = 130
  const cx = size / 2
  const cy = size / 2
  const r = 50
  const clampedNum = Math.max(0, Math.min(numerator, denominator))
  const clampedDen = Math.max(1, denominator)

  const sectors = Array.from({ length: clampedDen }).map((_, i) => {
    const startAngle = (i * 360) / clampedDen - 90
    const endAngle = ((i + 1) * 360) / clampedDen - 90
    const startRad = (startAngle * Math.PI) / 180
    const endRad = (endAngle * Math.PI) / 180
    const x1 = cx + r * Math.cos(startRad)
    const y1 = cy + r * Math.sin(startRad)
    const x2 = cx + r * Math.cos(endRad)
    const y2 = cy + r * Math.sin(endRad)
    const largeArc = (endAngle - startAngle) > 180 ? 1 : 0
    const isFilled = i < clampedNum

    return (
      <path key={i}
        d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`}
        fill={isFilled ? "#6366F1" : "#EEF2FF"}
        stroke="#A5B4FC"
        strokeWidth="1.5"
      />
    )
  })

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-indigo-50 to-purple-50 rounded-2xl border border-indigo-200/60 w-full">
      <div className="flex items-center justify-center gap-6">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="drop-shadow-md" role="img" aria-label={`Fraction ${clampedNum}/${clampedDen} of a circle shaded`}>
          {sectors}
        </svg>
        <div className="text-center">
          <div className="text-3xl font-bold text-indigo-600">
            <span className="border-b-2 border-indigo-400 px-1">{clampedNum}</span>
            <br />
            <span className="px-1">{clampedDen}</span>
          </div>
          <div className="text-xs text-indigo-400 mt-2">
            {clampedNum} of {clampedDen} parts
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Grid Symmetry ── */

function GridSymmetryVisual({ gridSize, filledCells, foldAxis }: { gridSize: number; filledCells: number[][]; foldAxis: 'vertical' | 'horizontal' }) {
  const size = 180
  const pad = 15
  const cellSize = (size - 2 * pad) / Math.max(gridSize, 1)
  const filledSet = new Set(filledCells.map(([r, c]) => `${r},${c}`))

  const midIndex = gridSize / 2
  const foldCoord = pad + midIndex * cellSize

  return (
    <div className="my-3 px-4 py-4 bg-gradient-to-br from-purple-50 to-fuchsia-50 rounded-2xl border border-purple-200/60 w-full">
      <div className="flex justify-center">
        <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="drop-shadow-md" role="img" aria-label={`${gridSize}x${gridSize} symmetry grid with ${foldAxis} fold line`}>
          {Array.from({ length: gridSize + 1 }, (_, row) =>
            Array.from({ length: gridSize + 1 }, (_, col) => (
              <circle key={`dot-${row}-${col}`} cx={pad + col * cellSize} cy={pad + row * cellSize} r="1.5" fill="#7C3AED" opacity="0.3" />
            ))
          )}
          {Array.from({ length: gridSize }, (_, row) =>
            Array.from({ length: gridSize }, (_, col) =>
              filledSet.has(`${row},${col}`) ? (
                <rect key={`cell-${row}-${col}`} x={pad + col * cellSize + 1} y={pad + row * cellSize + 1}
                  width={cellSize - 2} height={cellSize - 2} fill="#7C3AED" opacity="0.25" rx="2" />
              ) : null
            )
          )}
          {foldAxis === 'vertical' ? (
            <line x1={foldCoord} y1={pad} x2={foldCoord} y2={size - pad} stroke="#DC2626" strokeWidth="2" strokeDasharray="6 3" opacity="0.8" />
          ) : (
            <line x1={pad} y1={foldCoord} x2={size - pad} y2={foldCoord} stroke="#DC2626" strokeWidth="2" strokeDasharray="6 3" opacity="0.8" />
          )}
        </svg>
      </div>
      <p className="text-center text-xs text-purple-600/70 mt-2 font-medium">Draw the mirror image along the dotted line</p>
    </div>
  )
}

/* ── Money Coins ── */

function MoneyCoinsVisual({ items }: { items: {value: number; type: string; label: string; color: string}[]; total: number }) {
  if (!items.length) return null

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-yellow-50 to-amber-50 rounded-2xl border border-yellow-200/60 w-full">
      <div className="flex items-center justify-center gap-2 flex-wrap">
        {items.map((item, i) => (
          item.type === 'coin' ? (
            <div key={i} className="w-11 h-11 rounded-full border-2 flex items-center justify-center shadow-md"
                 style={{ borderColor: item.color, background: `linear-gradient(135deg, ${item.color}30, ${item.color}60)` }}>
              <span className="text-xs font-bold" style={{ color: item.color }}>{item.label}</span>
            </div>
          ) : (
            <div key={i} className="px-3 py-1.5 rounded-lg border-2 flex items-center justify-center shadow-md"
                 style={{ borderColor: item.color, background: `linear-gradient(135deg, ${item.color}15, ${item.color}30)` }}>
              <span className="text-sm font-bold" style={{ color: item.color }}>{item.label}</span>
            </div>
          )
        ))}
        <div className="w-9 h-9 rounded-full bg-slate-700 flex items-center justify-center">
          <span className="text-white text-sm font-bold">=</span>
        </div>
        <div className="px-3 py-2 rounded-xl border-2 border-dashed border-amber-400 bg-white">
          <span className="text-lg font-bold text-amber-600">₹?</span>
        </div>
      </div>
    </div>
  )
}

/* ── Pattern Completion (emoji pattern with blank) ── */

function PatternCompletionVisual({ tiles, blankPosition }: { tiles: string[]; blankPosition: number }) {
  if (!tiles.length) return null

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-pink-50 to-rose-50 rounded-2xl border border-pink-200/60 w-full">
      <div className="flex items-center justify-center gap-2 flex-wrap">
        {tiles.map((tile, i) => {
          const isBlank = i === blankPosition
          return (
            <div key={i} className="w-12 h-12 rounded-xl flex items-center justify-center border-2 transition-all"
                 style={{
                   borderColor: isBlank ? '#F97316' : '#FECDD3',
                   backgroundColor: isBlank ? '#FFF7ED' : '#FFFFFF',
                   borderStyle: isBlank ? 'dashed' : 'solid',
                 }}>
              {isBlank ? (
                <span className="text-xl font-bold text-orange-400">?</span>
              ) : (
                <span className="text-2xl select-none">{tile}</span>
              )}
            </div>
          )
        })}
      </div>
      <p className="text-center text-xs text-pink-600/70 mt-2 font-medium">
        What comes next? Find the pattern!
      </p>
    </div>
  )
}

/* ── Ten Frame (2×5 grid with dots) ── */

function TenFrameVisual({ filled, total, color }: { filled: number; total: number; color: string }) {
  const frames = total === 20 ? 2 : 1

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-violet-50 to-indigo-50 rounded-2xl border border-violet-200/60 w-full">
      <div className="flex justify-center gap-4 flex-wrap">
        {Array.from({ length: frames }).map((_, f) => {
          const frameStart = f * 10
          return (
            <div key={f} className="grid grid-cols-5 gap-1.5 bg-white rounded-xl p-3 border border-violet-100 shadow-sm">
              {Array.from({ length: 10 }).map((_, i) => {
                const globalIdx = frameStart + i
                const isFilled = globalIdx < filled
                return (
                  <div key={i} className="w-9 h-9 rounded-lg border-2 flex items-center justify-center"
                       style={{
                         borderColor: isFilled ? color : '#E2E8F0',
                         backgroundColor: isFilled ? color + '15' : '#F8FAFC',
                       }}>
                    {isFilled && (
                      <div className="w-5 h-5 rounded-full shadow-sm" style={{ backgroundColor: color }} />
                    )}
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>
      <p className="text-center text-xs text-violet-600/70 mt-2 font-medium">
        How many dots? Count the filled circles.
      </p>
    </div>
  )
}

/* ── Pictograph (rows of emoji data) ── */

function PictographVisual({ rows, title }: { rows: {label: string; emoji: string; count: number}[]; title: string }) {
  if (!rows.length) return null

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-lime-50 to-green-50 rounded-2xl border border-lime-200/60 w-full">
      <p className="text-xs font-bold text-green-700 uppercase tracking-wider mb-2 text-center">{title}</p>
      <div className="space-y-2">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-600 w-20 text-right">{row.label}</span>
            <div className="flex-1 flex gap-0.5 bg-white/60 rounded-lg px-2 py-1">
              {Array.from({ length: row.count }).map((_, j) => (
                <span key={j} className="text-xl">{row.emoji}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 pt-2 border-t border-lime-200">
        <p className="text-xs text-green-600/70 font-medium text-center">
          Each {rows[0]?.emoji} = 1
        </p>
      </div>
    </div>
  )
}

/* ── Array Visual (rows × cols grid for multiplication) ── */

function ArrayVisual({ rows, cols, emoji }: { rows: number; cols: number; emoji: string }) {
  return (
    <div className="py-4 px-4 bg-gradient-to-br from-amber-50 to-yellow-50 rounded-2xl border border-amber-200/60 w-full">
      <div className="flex justify-center">
        <div className="bg-white/70 rounded-xl p-3 border border-amber-100 shadow-sm inline-grid gap-1.5"
             style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: rows * cols }).map((_, i) => (
            <span key={i} className="text-xl md:text-2xl text-center select-none">{emoji}</span>
          ))}
        </div>
      </div>
      <p className="text-center text-xs text-amber-600/70 mt-2 font-medium">
        {rows} rows × {cols} columns = ?
      </p>
    </div>
  )
}

/* ── Fraction Bar ── */

function FractionBarVisual({ numerator, denominator, color, second }: { numerator: number; denominator: number; color: string; second: {numerator: number; denominator: number} | null }) {
  const totalParts = 12

  const renderBar = (num: number, den: number, barColor: string) => {
    const filled = Math.round((num / den) * totalParts)
    return (
      <div className="flex items-center gap-3">
        <div className="flex-1 flex rounded-lg overflow-hidden border border-slate-200 h-8">
          {Array.from({ length: totalParts }).map((_, i) => (
            <div key={i} className="flex-1 border-r border-white/50 last:border-r-0"
                 style={{ backgroundColor: i < filled ? barColor : '#F1F5F9' }} />
          ))}
        </div>
        <span className="text-sm font-bold min-w-[40px]" style={{ color: barColor }}>
          {num}/{den}
        </span>
      </div>
    )
  }

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-indigo-50 to-purple-50 rounded-2xl border border-indigo-200/60 w-full space-y-2">
      {renderBar(numerator, denominator, color)}
      {second && renderBar(second.numerator, second.denominator, '#EF4444')}
      {second && (
        <p className="text-center text-xs text-indigo-600/70 font-medium">
          Which fraction is bigger?
        </p>
      )}
    </div>
  )
}

/* ── Scenario Picture ── */

function ScenarioPictureVisual({ scene, description }: { scene: string; description: string }) {
  return (
    <div className="py-4 px-4 bg-gradient-to-br from-rose-50 to-pink-50 rounded-2xl border border-rose-200/60 w-full">
      <div className="text-center">
        <div className="text-4xl md:text-5xl leading-relaxed tracking-wider mb-2 select-none">
          {scene}
        </div>
        <p className="text-sm text-rose-700/80 font-medium">{description}</p>
      </div>
    </div>
  )
}

/* ── Sequence Pictures ── */

function SequencePicturesVisual({ steps, labels, blankIndex }: { steps: string[]; labels: string[]; blankIndex: number }) {
  if (!steps.length) return null

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-sky-50 to-cyan-50 rounded-2xl border border-sky-200/60 w-full">
      <div className="flex items-center justify-center gap-1 flex-wrap">
        {steps.map((step, i) => (
          <React.Fragment key={i}>
            <div className="flex flex-col items-center">
              <div className={`w-14 h-14 rounded-xl flex items-center justify-center border-2 ${
                i === blankIndex ? 'border-dashed border-orange-400 bg-orange-50' : 'border-sky-200 bg-white'
              }`}>
                {i === blankIndex ? (
                  <span className="text-xl font-bold text-orange-400">?</span>
                ) : (
                  <span className="text-2xl select-none">{step}</span>
                )}
              </div>
              <span className="text-[9px] text-slate-500 mt-1 text-center max-w-[60px] leading-tight">
                {i === blankIndex ? '???' : labels[i]}
              </span>
            </div>
            {i < steps.length - 1 && (
              <span className="text-lg text-sky-300 mx-0.5">→</span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

/* ── Bar Chart ── */

function BarChartVisual({ bars, title }: { bars: {label: string; value: number; color: string}[]; title: string }) {
  if (!bars.length) return null
  const maxVal = Math.max(...bars.map(b => b.value), 1)

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-slate-50 to-gray-50 rounded-2xl border border-slate-200/60 w-full">
      {title && <p className="text-xs font-bold text-slate-600 text-center mb-3">{title}</p>}
      <div className="flex items-end justify-center gap-3 h-32">
        {bars.map((bar, i) => (
          <div key={i} className="flex flex-col items-center gap-1">
            <span className="text-xs font-bold" style={{ color: bar.color }}>{bar.value}</span>
            <div className="w-10 rounded-t-lg shadow-sm transition-all"
                 style={{
                   height: `${(bar.value / maxVal) * 100}px`,
                   backgroundColor: bar.color,
                   minHeight: '8px',
                 }} />
            <span className="text-[9px] text-slate-500 font-medium text-center max-w-[48px] leading-tight">{bar.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Food Plate ── */

function FoodPlateVisual({ groups, blankIndex }: { groups: {name: string; emoji: string; color: string}[]; blankIndex: number }) {
  if (!groups.length) return null

  return (
    <div className="py-4 px-4 bg-gradient-to-br from-lime-50 to-emerald-50 rounded-2xl border border-lime-200/60 w-full">
      <div className="relative w-48 h-48 mx-auto rounded-full border-4 border-lime-300 bg-white overflow-hidden">
        {groups.map((group, i) => {
          const angle = (i / groups.length) * 360
          const isBlank = i === blankIndex
          return (
            <div key={i} className="absolute text-center"
                 style={{
                   top: `${50 + 30 * Math.sin((angle - 90) * Math.PI / 180)}%`,
                   left: `${50 + 30 * Math.cos((angle - 90) * Math.PI / 180)}%`,
                   transform: 'translate(-50%, -50%)',
                 }}>
              {isBlank ? (
                <div className="text-lg font-bold text-orange-400">❓</div>
              ) : (
                <>
                  <div className="text-xl leading-none">{group.emoji.slice(0, 2)}</div>
                  <div className="text-[8px] font-bold mt-0.5" style={{ color: group.color }}>{group.name}</div>
                </>
              )}
            </div>
          )
        })}
      </div>
      <p className="text-center text-xs text-lime-600/70 mt-2 font-medium">Balanced Diet Plate</p>
    </div>
  )
}

/* ── Percentage Bar ── */

function PercentageBarVisual({ percent, color }: { percent: number; color: string }) {
  return (
    <div className="py-4 px-4 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-2xl border border-blue-200/60 w-full">
      <div className="relative w-full h-10 rounded-xl overflow-hidden border border-slate-200 bg-slate-100">
        <div className="absolute inset-y-0 left-0 rounded-xl transition-all flex items-center justify-center"
             style={{ width: `${percent}%`, backgroundColor: color }}>
          {percent >= 20 && <span className="text-white text-sm font-bold">{percent}%</span>}
        </div>
        {[25, 50, 75].map(mark => (
          <div key={mark} className="absolute inset-y-0 border-l border-dashed border-slate-300"
               style={{ left: `${mark}%` }} />
        ))}
      </div>
      <div className="flex justify-between mt-1 text-[9px] text-slate-400 font-medium px-1">
        <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
      </div>
    </div>
  )
}

/* ── Picture Word Match ── */

function PictureWordMatchVisual({ emoji }: { emoji: string }) {
  return (
    <div className="py-4 px-4 bg-gradient-to-br from-sky-50 to-cyan-50 rounded-2xl border border-sky-200/60 w-full">
      <div className="flex items-center justify-center">
        <span className="text-6xl md:text-7xl drop-shadow-lg">
          {emoji}
        </span>
      </div>
      <p className="text-center text-sm text-sky-600/80 mt-2 font-medium">
        What is this?
      </p>
    </div>
  )
}

/* ── Labeled Diagram ── */

function LabeledDiagramVisual({ labels, blankIndex }: { labels: string[]; blankIndex: number }) {
  return (
    <div className="py-4 px-4 bg-gradient-to-br from-emerald-50 to-teal-50 rounded-2xl border border-emerald-200/60 w-full">
      <div className="flex flex-col items-center gap-1">
        {labels.map((label, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className={`px-3 py-1 rounded-lg text-sm font-semibold ${
              i === blankIndex
                ? 'bg-orange-100 text-orange-600 border-2 border-dashed border-orange-300'
                : 'bg-emerald-100 text-emerald-700'
            }`}>
              {i === blankIndex ? '???' : label}
            </div>
            <span className="text-emerald-400">&larr;</span>
            <div className="w-2 h-6 bg-emerald-300 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Match Columns ── */

function MatchColumnsVisual({ left, right }: { left: {emoji: string; label: string}[]; right: {emoji: string; label: string}[] }) {
  return (
    <div className="py-4 px-4 bg-gradient-to-br from-violet-50 to-fuchsia-50 rounded-2xl border border-violet-200/60 w-full">
      <div className="flex justify-around">
        <div className="space-y-3">
          {left.map((item, i) => (
            <div key={i} className="flex items-center gap-2 bg-white rounded-lg px-3 py-2 border border-violet-100 shadow-sm">
              <span className="text-2xl">{item.emoji}</span>
              <span className="text-sm font-medium text-slate-700">{item.label}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-col justify-center">
          {left.map((_, i) => (
            <div key={i} className="h-10 flex items-center">
              <div className="w-16 border-t-2 border-dashed border-violet-300" />
            </div>
          ))}
        </div>
        <div className="space-y-3">
          {right.map((item, i) => (
            <div key={i} className="flex items-center gap-2 bg-white rounded-lg px-3 py-2 border border-violet-100 shadow-sm">
              <span className="text-2xl">{item.emoji}</span>
              <span className="text-sm font-medium text-slate-700">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Abacus ── */

function AbacusVisual({ hundreds, tens, ones }: { hundreds: number; ones: number; tens: number }) {
  const w = 200, h = 150
  const frameX = 20, frameY = 15, frameW = 160, frameH = 100
  const rodXs = [64, 100, 136]
  const rodLabels = ['H', 'T', 'O']
  const rodColors = ['#3B82F6', '#10B981', '#F97316']
  const rodValues = [Math.max(0, Math.min(hundreds, 9)), Math.max(0, Math.min(tens, 9)), Math.max(0, Math.min(ones, 9))]
  const rodTop = frameY + 10
  const rodBottom = frameY + frameH - 10
  const beadR = 6
  const beadSpacing = 13
  const maxBeads = 9

  return (
    <div className="my-3 px-4 py-4 bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl border border-orange-200/60 w-full">
      <div className="flex justify-center">
        <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} className="drop-shadow-md" role="img" aria-label={`Abacus: ${hundreds} hundreds, ${tens} tens, ${ones} ones`}>
          <rect x={frameX} y={frameY} width={frameW} height={frameH} rx="6" fill="#FEF3C7" stroke="#92400E" strokeWidth="2.5" />
          <line x1={frameX} y1={frameY + 16} x2={frameX + frameW} y2={frameY + 16} stroke="#92400E" strokeWidth="2" />
          <line x1={frameX} y1={frameY + frameH - 16} x2={frameX + frameW} y2={frameY + frameH - 16} stroke="#92400E" strokeWidth="2" />

          {rodXs.map((rx, ri) => {
            const count = rodValues[ri]
            const beadAreaTop = rodTop + 16
            const beadAreaBottom = rodBottom - 16
            const beadAreaH = beadAreaBottom - beadAreaTop
            const startY = beadAreaBottom - beadR

            return (
              <g key={ri}>
                <line x1={rx} y1={rodTop} x2={rx} y2={rodBottom} stroke="#92400E" strokeWidth="1.5" opacity="0.5" />
                {Array.from({ length: Math.min(count, maxBeads) }, (_, bi) => {
                  const beadY = startY - bi * Math.min(beadSpacing, beadAreaH / maxBeads)
                  return (
                    <circle key={bi} cx={rx} cy={beadY} r={beadR}
                      fill={rodColors[ri]} stroke={rodColors[ri]} strokeWidth="1.5" opacity="0.85" />
                  )
                })}
                <text x={rx} y={frameY + frameH + 16} textAnchor="middle" fontSize="12" fill="#78350F" fontWeight="700">
                  {rodLabels[ri]}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      <p className="text-center text-sm text-amber-700 font-semibold mt-2">
        {hundreds > 0 ? `${hundreds} hundreds, ` : ''}{tens > 0 ? `${tens} tens, ` : ''}{ones} ones = {hundreds * 100 + tens * 10 + ones}
      </p>
    </div>
  )
}
