import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getTopicName } from '@/lib/curriculum'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TimelineSession {
  topic_slug: string
  subject: string
  score_pct: number | null
  created_at: string
}

interface DayData {
  dateStr: string
  sessions: TimelineSession[]
  avgScore: number | null
  topTopic: string | null
}

interface Props {
  sessions: TimelineSession[]
  loading: boolean
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toDateStr(d: Date): string {
  return d.toISOString().split('T')[0]
}

/** Build an array of YYYY-MM-DD strings for the last `n` days, ending today. */
function buildDayWindow(n: number): string[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days: string[] = []
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    days.push(toDateStr(d))
  }
  return days
}

function scoreColorClass(avgScore: number | null, hasSessions: boolean): string {
  if (!hasSessions) return 'bg-card border-2 border-gray-200'
  if (avgScore === null) return 'bg-gray-300'
  if (avgScore >= 80) return 'bg-emerald-500'
  if (avgScore >= 60) return 'bg-amber-400'
  return 'bg-red-400'
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ProgressTimeline({ sessions, loading }: Props) {
  const [activeDay, setActiveDay] = useState<string | null>(null)

  const allDays = buildDayWindow(30)
  const today = toDateStr(new Date())

  // Group sessions by local date extracted from created_at ISO string
  const sessionsByDate = new Map<string, TimelineSession[]>()
  for (const s of sessions) {
    const dateStr = s.created_at.split('T')[0]
    if (!sessionsByDate.has(dateStr)) sessionsByDate.set(dateStr, [])
    sessionsByDate.get(dateStr)!.push(s)
  }

  const dayData: DayData[] = allDays.map((dateStr) => {
    const daySessions = sessionsByDate.get(dateStr) ?? []
    const scores = daySessions
      .filter((s) => s.score_pct != null)
      .map((s) => s.score_pct as number)
    const avgScore =
      scores.length > 0
        ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
        : null
    return {
      dateStr,
      sessions: daySessions,
      avgScore,
      topTopic: daySessions[0]?.topic_slug ?? null,
    }
  })

  const activeDayData = activeDay
    ? dayData.find((d) => d.dateStr === activeDay) ?? null
    : null

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg font-fraunces">30-Day Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-10 w-full rounded-lg" />
        </CardContent>
      </Card>
    )
  }

  // Label for the start of the visible range
  const mobileStartLabel = new Date(allDays[16] + 'T12:00:00').toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
  })
  const desktopStartLabel = new Date(allDays[0] + 'T12:00:00').toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-lg font-fraunces">30-Day Activity</CardTitle>
          {/* Legend */}
          <div className="flex items-center gap-3">
            {(
              [
                { color: 'bg-emerald-500', label: '≥80%' },
                { color: 'bg-amber-400', label: '60–79%' },
                { color: 'bg-red-400', label: '<60%' },
              ] as const
            ).map(({ color, label }) => (
              <div key={label} className="flex items-center gap-1">
                <div className={`w-2.5 h-2.5 rounded-full ${color}`} />
                <span className="text-xs text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {/*
          Circle row.
          Mobile (<sm): show last 14 days only (idx >= 16).
          Desktop (≥sm): show all 30.
          Each button is at least 44px tall for mobile tap targets.
        */}
        <div className="flex justify-between items-stretch" style={{ minHeight: '44px' }}>
          {dayData.map((day, idx) => {
            const isActive = activeDay === day.dateStr
            const isToday = day.dateStr === today
            const circleBase = scoreColorClass(day.avgScore, day.sessions.length > 0)

            return (
              <button
                key={day.dateStr}
                onClick={() => setActiveDay((prev) => (prev === day.dateStr ? null : day.dateStr))}
                aria-label={`${day.dateStr}${day.sessions.length > 0 ? ': practiced' : ': no activity'}`}
                className={[
                  'flex items-center justify-center transition-all hover:brightness-90',
                  idx < 16 ? 'hidden sm:flex' : 'flex',
                ].join(' ')}
              >
                <span
                  className={[
                    'w-4 h-4 rounded-full block transition-transform',
                    isActive ? 'scale-125' : '',
                    isToday ? 'ring-2 ring-primary ring-offset-1' : '',
                    circleBase,
                  ].join(' ')}
                />
              </button>
            )
          })}
        </div>

        {/* Date range labels */}
        <div className="flex justify-between mt-1.5">
          <span className="text-xs text-muted-foreground hidden sm:inline">
            {desktopStartLabel}
          </span>
          <span className="text-xs text-muted-foreground sm:hidden">
            {mobileStartLabel}
          </span>
          <span className="text-xs text-muted-foreground">Today</span>
        </div>

        {/* Detail panel on tap/click */}
        {activeDayData && (
          <div className="mt-3 flex items-center justify-between px-3 py-2.5 bg-secondary/40 rounded-lg text-sm">
            {activeDayData.sessions.length > 0 ? (
              <>
                <span className="font-medium text-foreground truncate mr-2">
                  {activeDayData.topTopic
                    ? getTopicName(activeDayData.topTopic)
                    : 'Practice session'}
                </span>
                {activeDayData.avgScore !== null && (
                  <span
                    className={`font-semibold shrink-0 ${
                      activeDayData.avgScore >= 80
                        ? 'text-emerald-600'
                        : activeDayData.avgScore >= 60
                          ? 'text-amber-600'
                          : 'text-red-500'
                    }`}
                  >
                    {activeDayData.avgScore}%
                  </span>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">
                {activeDayData.dateStr === today
                  ? 'No activity today yet'
                  : 'No activity this day'}
              </span>
            )}
          </div>
        )}

        {/* Empty state */}
        {sessions.length === 0 && (
          <p className="text-sm text-muted-foreground text-center mt-3">
            Complete a worksheet to see your activity here.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
