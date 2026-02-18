import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

// ─── Types ────────────────────────────────────────────────────────────────────

interface EngagementData {
  child_id: string
  total_stars: number
  current_streak: number
  longest_streak: number
  total_worksheets_completed: number
  last_activity_date: string | null
}

export interface StreakSession {
  created_at: string
}

interface Props {
  childId: string
  /** Sessions from the history endpoint — used to populate Mon–Sun week dots. */
  sessions: StreakSession[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toDateStr(d: Date): string {
  return d.toISOString().split('T')[0]
}

/** Returns the Mon–Sun days of the current ISO week as { dateStr, label }[]. */
function getCurrentWeekDays(): { dateStr: string; label: string }[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const dow = today.getDay() // 0 = Sun
  const mondayOffset = dow === 0 ? -6 : 1 - dow
  const monday = new Date(today)
  monday.setDate(today.getDate() + mondayOffset)

  return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label, i) => {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    return { dateStr: toDateStr(d), label }
  })
}

// ─── Component ────────────────────────────────────────────────────────────────

export function StreakCard({ childId, sessions }: Props) {
  const [engagement, setEngagement] = useState<EngagementData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!childId) return
    setLoading(true)
    api
      .get(`/api/engagement/${childId}`)
      .then((r) => setEngagement(r.data))
      .catch((err) => console.warn('[StreakCard] Failed to fetch engagement:', err))
      .finally(() => setLoading(false))
  }, [childId])

  const weekDays = getCurrentWeekDays()
  const today = toDateStr(new Date())

  // Derive which days had activity from the sessions prop
  const activeDates = new Set(sessions.map((s) => s.created_at.split('T')[0]))

  if (loading) {
    return (
      <Card>
        <CardContent className="p-5">
          <Skeleton className="h-20 w-full rounded-lg" />
        </CardContent>
      </Card>
    )
  }

  if (!engagement) return null

  const streak = engagement.current_streak
  const longest = engagement.longest_streak
  const showCelebration = streak >= 7

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">

          {/* ── Left: flame + streak number ── */}
          <div className="flex items-center gap-4">
            <span className="text-4xl select-none" aria-hidden="true">🔥</span>
            <div>
              {streak > 0 ? (
                <>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-3xl font-bold font-fraunces text-foreground leading-none">
                      {streak}
                    </span>
                    <span className="text-base text-muted-foreground">day streak</span>
                  </div>
                  {showCelebration && (
                    <p className="text-sm font-medium text-amber-600 mt-0.5">
                      Amazing week! 🎉
                    </p>
                  )}
                </>
              ) : (
                <p className="text-base font-semibold text-muted-foreground">
                  Start your streak today!
                </p>
              )}
              <p className="text-xs text-muted-foreground mt-1">
                Personal best:{' '}
                <span className="font-semibold text-foreground">
                  {longest} day{longest !== 1 ? 's' : ''}
                </span>
              </p>
            </div>
          </div>

          {/* ── Right: Mon–Sun week dots ── */}
          <div className="flex items-start gap-1 sm:gap-1.5">
            {weekDays.map(({ dateStr, label }) => {
              const isActive = activeDates.has(dateStr)
              const isToday = dateStr === today
              // Future days: can't have activity
              const isFuture = dateStr > today

              return (
                <div
                  key={dateStr}
                  className="flex flex-col items-center gap-1 min-w-[40px] min-h-[56px] justify-start"
                >
                  <div
                    className={[
                      'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                      isActive
                        ? 'bg-amber-400'
                        : isFuture
                          ? 'bg-gray-50 border border-dashed border-gray-200'
                          : 'bg-gray-100 border border-gray-200',
                      isToday ? 'ring-2 ring-primary ring-offset-1' : '',
                    ].join(' ')}
                  >
                    {isActive && (
                      /* Checkmark SVG */
                      <svg
                        className="w-4 h-4 text-white"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        aria-hidden="true"
                      >
                        <path
                          fillRule="evenodd"
                          d="M19.916 4.626a.75.75 0 01.208 1.04l-9 13.5a.75.75 0 01-1.154.114l-6-6a.75.75 0 011.06-1.06l5.353 5.353 8.493-12.739a.75.75 0 011.04-.208z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </div>
                  <span
                    className={`text-xs font-medium ${
                      isToday ? 'text-primary' : 'text-muted-foreground'
                    }`}
                  >
                    {label}
                  </span>
                </div>
              )
            })}
          </div>

        </div>
      </CardContent>
    </Card>
  )
}
