import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useChildren } from '@/lib/children'
import { getTopicName } from '@/lib/curriculum'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ProgressTimeline, type TimelineSession } from '@/components/ProgressTimeline'
import { StreakCard } from '@/components/StreakCard'
import { InsightCard } from '@/components/InsightCard'
import GradeFromPhoto from '@/components/GradeFromPhoto'

// ─── Interfaces ──────────────────────────────────────────────────────────────

interface OverallStats {
  total_worksheets: number
  total_stars: number
  current_streak: number
  longest_streak: number
}

interface SkillProgress {
  skill_tag: string
  mastery_level: string
  streak: number
  total_attempts: number
  correct_attempts: number
  accuracy: number
}

interface RecentTopic {
  topic: string
  count: number
  last_generated: string
}

interface DashboardData {
  student_id: string
  overall_stats: OverallStats
  skills: SkillProgress[]
  recent_topics: RecentTopic[]
}

interface GraphTopicData {
  mastery_level: 'unknown' | 'learning' | 'improving' | 'mastered'
  streak: number
  last_practiced_at: string | null
}

interface GraphSummary {
  child_id: string
  mastered_topics: string[]
  improving_topics: string[]
  needs_attention: string[]
  strongest_subject: string | null
  weakest_subject: string | null
  total_sessions: number
  total_questions: number
  overall_accuracy: number
  learning_velocity: string
  last_updated_at: string | null
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatSkillTag(tag: string): string {
  return tag
    .replace(/^(mth|eng|sci|hin|comp|gk|moral|health)_c\d+_/, '')
    .replace(/_/g, ' ')
    .split(' ')
    .map((w, i) => {
      if (i === 0) return w.charAt(0).toUpperCase() + w.slice(1)
      if (['and', 'or', 'of', 'in', 'the', 'a'].includes(w)) return w
      return w.charAt(0).toUpperCase() + w.slice(1)
    })
    .join(' ')
}

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function masteryColor(level: string): string {
  switch (level) {
    case 'mastered': return 'bg-emerald-100 text-emerald-800 border-emerald-200'
    case 'improving': return 'bg-blue-100 text-blue-800 border-blue-200'
    case 'learning':  return 'bg-amber-100 text-amber-800 border-amber-200'
    default:          return 'bg-gray-100 text-gray-600 border-gray-200'
  }
}

function masteryLabel(level: string): string {
  switch (level) {
    case 'mastered': return 'Mastered'
    case 'improving': return 'Improving'
    case 'learning':  return 'Learning'
    case 'unknown':   return 'Not Started'
    default: return level.charAt(0).toUpperCase() + level.slice(1)
  }
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function MasteryDistribution({ skills }: { skills: SkillProgress[] }) {
  const counts = { mastered: 0, improving: 0, learning: 0, unknown: 0 }
  for (const s of skills) {
    const level = s.mastery_level as keyof typeof counts
    if (level in counts) counts[level]++
    else counts.unknown++
  }
  const total = skills.length || 1
  const segments = [
    { label: 'Mastered',     count: counts.mastered,  color: 'bg-emerald-500' },
    { label: 'Improving',    count: counts.improving, color: 'bg-blue-500' },
    { label: 'Learning',     count: counts.learning,  color: 'bg-amber-500' },
    { label: 'Not Started',  count: counts.unknown,   color: 'bg-gray-300' },
  ]

  return (
    <div className="space-y-3">
      <div className="h-3 rounded-full bg-gray-100 overflow-hidden flex">
        {segments.map((seg) =>
          seg.count > 0 ? (
            <div
              key={seg.label}
              className={`${seg.color} transition-all duration-500`}
              style={{ width: `${(seg.count / total) * 100}%` }}
            />
          ) : null
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className={`w-2.5 h-2.5 rounded-full ${seg.color}`} />
            <span>{seg.label}</span>
            <span className="font-semibold text-foreground">{seg.count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// Learning Health Card — three-bucket summary
function LearningHealthCard({ summary }: { summary: GraphSummary }) {
  const sections = [
    {
      count: summary.mastered_topics.length,
      label: 'Mastered',
      textColor: 'text-emerald-700',
      bg: 'bg-emerald-50',
      border: 'border-emerald-200',
      dot: 'bg-emerald-500',
    },
    {
      count: summary.improving_topics.length,
      label: 'Working On',
      textColor: 'text-amber-700',
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      dot: 'bg-amber-500',
    },
    {
      count: summary.needs_attention.length,
      label: 'Needs Practice',
      textColor: 'text-red-700',
      bg: 'bg-red-50',
      border: 'border-red-200',
      dot: 'bg-red-500',
    },
  ]

  const totalTopics = sections.reduce((s, x) => s + x.count, 0)

  if (totalTopics === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg font-fraunces">Learning Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-4">
            Complete a worksheet to see progress here.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-fraunces">Learning Progress</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3">
          {sections.map((s) => (
            <div
              key={s.label}
              className={`${s.bg} ${s.border} border rounded-xl p-4 text-center flex flex-col items-center justify-center gap-1.5 min-h-[88px]`}
            >
              <span className={`text-3xl font-bold font-fraunces ${s.textColor}`}>
                {s.count}
              </span>
              <div className="flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${s.dot}`} />
                <span className={`text-xs font-medium ${s.textColor}`}>{s.label}</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// Subject grid — expandable per-subject topic list
function SubjectGrid({
  graph,
}: {
  graph: Record<string, Record<string, GraphTopicData>>
}) {
  const [expanded, setExpanded] = useState<string | null>(null)

  const subjects = Object.entries(graph).filter(
    ([, topics]) => Object.keys(topics).length > 0
  )

  if (subjects.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-fraunces">Progress by Subject</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {subjects.map(([subject, topics]) => {
            const topicList = Object.entries(topics)
            const masteredCount = topicList.filter(
              ([, t]) => t.mastery_level === 'mastered'
            ).length
            const isOpen = expanded === subject

            return (
              <div
                key={subject}
                className="border border-border/30 rounded-xl overflow-hidden"
              >
                {/* Subject row — always visible */}
                <button
                  onClick={() => setExpanded(isOpen ? null : subject)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-secondary/20 active:bg-secondary/40 transition-colors min-h-[52px]"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-semibold text-foreground">{subject}</span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {masteredCount}/{topicList.length}
                    </span>
                  </div>
                  {/* Mini progress bar */}
                  <div className="flex items-center gap-3">
                    <div className="hidden sm:block w-20 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                      {masteredCount > 0 && (
                        <div
                          className="h-full bg-emerald-500 rounded-full transition-all"
                          style={{ width: `${(masteredCount / topicList.length) * 100}%` }}
                        />
                      )}
                    </div>
                    <svg
                      className={`w-4 h-4 text-muted-foreground transition-transform ${isOpen ? 'rotate-180' : ''}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                {/* Topic list — shown when expanded */}
                {isOpen && (
                  <div className="border-t border-border/20 divide-y divide-border/10">
                    {topicList.map(([topicSlug, topicData]) => {
                      const level = topicData.mastery_level
                      const dotColor =
                        level === 'mastered'  ? 'bg-emerald-500' :
                        level === 'improving' ? 'bg-amber-500'   :
                        'bg-red-400'
                      const badgeClass =
                        level === 'mastered'  ? 'text-emerald-700 bg-emerald-50' :
                        level === 'improving' ? 'text-amber-700 bg-amber-50'     :
                        'text-red-700 bg-red-50'
                      const label =
                        level === 'mastered'  ? 'Mastered'       :
                        level === 'improving' ? 'Working On'     :
                        'Needs Practice'

                      return (
                        <div
                          key={topicSlug}
                          className="flex items-center justify-between px-4 py-3 min-h-[52px]"
                        >
                          <div className="flex items-center gap-2.5 flex-1 min-w-0">
                            <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${dotColor}`} />
                            <span className="text-sm text-foreground truncate">
                              {getTopicName(topicSlug)}
                            </span>
                          </div>
                          <span
                            className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ml-2 ${badgeClass}`}
                          >
                            {label}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// Shimmer skeletons for the initial load
function LoadingSkeleton() {
  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64 rounded-lg" />
        <Skeleton className="h-5 w-48 rounded-lg" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-40 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  )
}

// Shimmer for the learning graph section only
function LearningGraphSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-40 rounded-xl" />
      <Skeleton className="h-52 rounded-xl" />
    </div>
  )
}

// ─── Grading types ───────────────────────────────────────────────────────────

interface RecentWorksheetItem {
  id: string
  title: string
  grade: string
  subject: string
  topic: string
  question_count: number
  created_at: string
  child_id: string | null
}

interface FullWorksheetForGrading {
  id: string
  title: string
  grade: string
  subject: string
  topic: string
  questions: { id: string; type: string; text: string; options?: string[]; correct_answer?: string; format?: string }[]
}

interface GradingHistoryItem {
  id: string
  worksheet_title: string
  topic: string
  score: number
  total: number
  created_at: string
  results: {
    question_number: number
    student_answer: string
    correct_answer: string
    is_correct: boolean
    confidence: number
    needs_review: boolean
    feedback: string
  }[]
}

// ─── Grade a Worksheet Card ─────────────────────────────────────────────────

function GradeWorksheetCard({
  recentWorksheets,
  loadingWorksheets,
  onGradeWorksheet,
  onUploadDirect,
}: {
  recentWorksheets: RecentWorksheetItem[]
  loadingWorksheets: boolean
  onGradeWorksheet: (id: string) => void
  onUploadDirect: () => void
}) {
  return (
    <Card className="border-primary/20 bg-primary/[0.02]">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-fraunces flex items-center gap-2">
          <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
          </svg>
          Grade a Worksheet
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Upload your child's answer sheet to update progress
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Upload buttons */}
        <div className="flex gap-3">
          <Button
            onClick={onUploadDirect}
            className="flex-1 h-11"
            style={{ backgroundColor: '#1E1B4B', color: '#FFFFFF' }}
          >
            <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
            </svg>
            Take Photo
          </Button>
          <Button
            onClick={onUploadDirect}
            variant="outline"
            className="flex-1 h-11"
          >
            <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            Upload File
          </Button>
        </div>

        {/* Recent worksheets to grade */}
        {loadingWorksheets ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-40 rounded" />
            <Skeleton className="h-14 rounded-lg" />
            <Skeleton className="h-14 rounded-lg" />
          </div>
        ) : recentWorksheets.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Recent worksheets (not yet graded)
            </p>
            {recentWorksheets.slice(0, 5).map((ws) => (
              <div
                key={ws.id}
                className="flex items-center justify-between p-3 rounded-lg bg-background border border-border/30 hover:border-primary/30 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-foreground truncate">{ws.topic}</p>
                  <p className="text-xs text-muted-foreground">
                    {ws.grade} &middot; {ws.subject} &middot; {ws.question_count}q
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onGradeWorksheet(ws.id)}
                  className="text-primary text-xs font-semibold shrink-0 h-auto py-1.5 px-3"
                >
                  Grade this &rarr;
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-2">
            Generate a worksheet first, then grade it here.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Grading History Section ─────────────────────────────────────────────────

function GradingHistorySection({ history, loading: histLoading }: { history: GradingHistoryItem[]; loading: boolean }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (histLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg font-fraunces">Grading History</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-12 rounded-lg" />
          <Skeleton className="h-12 rounded-lg" />
        </CardContent>
      </Card>
    )
  }

  if (history.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-fraunces">Grading History</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {history.map((item) => {
          const isExpanded = expandedId === item.id
          const pct = Math.round((item.score / item.total) * 100)
          const scoreColor = pct >= 80 ? 'text-emerald-600' : pct >= 50 ? 'text-amber-600' : 'text-red-500'

          return (
            <div key={item.id} className="border border-border/30 rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedId(isExpanded ? null : item.id)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-secondary/20 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{item.topic}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(item.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                      {item.worksheet_title && ` \u00b7 ${item.worksheet_title}`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-sm font-bold ${scoreColor}`}>
                    {item.score}/{item.total}
                  </span>
                  <svg
                    className={`w-4 h-4 text-muted-foreground transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {isExpanded && item.results && (
                <div className="border-t border-border/20 px-4 py-3 space-y-1.5">
                  {item.results.map((r) => (
                    <div key={r.question_number} className="flex items-start gap-2 text-sm">
                      <span className="mt-0.5">
                        {r.needs_review ? '⚠️' : r.is_correct ? '✅' : '❌'}
                      </span>
                      <div className="min-w-0 flex-1">
                        <span className="font-medium">Q{r.question_number}</span>
                        <span className="text-muted-foreground ml-1.5">
                          {r.student_answer === 'BLANK' ? '(no answer)' : r.student_answer}
                        </span>
                        {!r.is_correct && !r.needs_review && (
                          <span className="text-xs text-muted-foreground ml-1">→ {r.correct_answer}</span>
                        )}
                        {r.feedback && (
                          <p className="text-xs text-muted-foreground mt-0.5">{r.feedback}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ParentDashboard({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const { user } = useAuth()
  const { children: childrenList, loading: childrenLoading } = useChildren()
  const displayName = user?.user_metadata?.name?.split(' ')[0] || 'there'

  const [selectedChildId, setSelectedChildId] = useState<string | null>(null)
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [graphSummary, setGraphSummary] = useState<GraphSummary | null>(null)
  const [graph, setGraph] = useState<Record<string, Record<string, GraphTopicData>> | null>(null)
  const [sessions, setSessions] = useState<TimelineSession[]>([])
  const [loading, setLoading] = useState(false)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Grading state
  const [recentWorksheets, setRecentWorksheets] = useState<RecentWorksheetItem[]>([])
  const [loadingWorksheets, setLoadingWorksheets] = useState(false)
  const [gradingHistory, setGradingHistory] = useState<GradingHistoryItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [showGrading, setShowGrading] = useState(false)
  const [gradingWorksheet, setGradingWorksheet] = useState<FullWorksheetForGrading | null>(null)
  const [loadingGradingWorksheet, setLoadingGradingWorksheet] = useState(false)

  // Auto-select first child
  useEffect(() => {
    if (!selectedChildId && childrenList.length > 0) {
      setSelectedChildId(childrenList[0].id)
    }
  }, [childrenList, selectedChildId])

  const fetchDashboard = useCallback(async (childId: string) => {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.get('/api/v1/dashboard/parent', {
        params: { student_id: childId },
      })
      setDashboard(resp.data)
    } catch (err: unknown) {
      console.warn('[ParentDashboard] Failed to fetch dashboard:', err)
      setError('Could not load progress data. Please try again.')
      setDashboard(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchLearningGraph = useCallback(async (childId: string) => {
    setGraphLoading(true)
    // Use allSettled so a failure in one endpoint doesn't block the others
    const [summaryResult, graphResult, historyResult] = await Promise.allSettled([
      api.get(`/api/children/${childId}/graph/summary`),
      api.get(`/api/children/${childId}/graph`),
      api.get(`/api/children/${childId}/graph/history?limit=30`),
    ])

    if (summaryResult.status === 'fulfilled') {
      setGraphSummary(summaryResult.value.data)
    } else {
      console.warn('[ParentDashboard] Graph summary failed:', summaryResult.reason)
      setGraphSummary(null)
    }

    if (graphResult.status === 'fulfilled') {
      setGraph(graphResult.value.data?.graph ?? {})
    } else {
      console.warn('[ParentDashboard] Graph data failed:', graphResult.reason)
      setGraph(null)
    }

    if (historyResult.status === 'fulfilled') {
      setSessions(historyResult.value.data?.sessions ?? [])
    } else {
      console.warn('[ParentDashboard] Graph history failed:', historyResult.reason)
      setSessions([])
    }

    setGraphLoading(false)
  }, [])

  // Fetch recent worksheets for "grade this" list
  const fetchRecentWorksheets = useCallback(async (childId: string) => {
    setLoadingWorksheets(true)
    try {
      const response = await api.get(`/api/worksheets/saved/list?child_id=${childId}`)
      setRecentWorksheets((response.data.worksheets || []).slice(0, 5))
    } catch {
      setRecentWorksheets([])
    } finally {
      setLoadingWorksheets(false)
    }
  }, [])

  // Fetch grading history
  const fetchGradingHistory = useCallback(async (childId: string) => {
    setLoadingHistory(true)
    try {
      const response = await api.get(`/api/v1/grading/history?child_id=${childId}`)
      setGradingHistory(response.data.results || [])
    } catch {
      // Grading history endpoint may not exist yet — fail silently
      setGradingHistory([])
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  // Load a full worksheet for grading
  const handleGradeWorksheet = useCallback(async (worksheetId: string) => {
    setLoadingGradingWorksheet(true)
    try {
      const response = await api.get(`/api/worksheets/saved/${worksheetId}`)
      const ws = response.data.worksheet || response.data
      setGradingWorksheet({
        id: ws.id || worksheetId,
        title: ws.title,
        grade: ws.grade,
        subject: ws.subject,
        topic: ws.topic,
        questions: ws.questions || [],
      })
      setShowGrading(true)
    } catch {
      console.warn('[ParentDashboard] Failed to load worksheet for grading')
    } finally {
      setLoadingGradingWorksheet(false)
    }
  }, [])

  // Open grading dialog without a specific worksheet (direct upload)
  const handleDirectUpload = useCallback(() => {
    if (recentWorksheets.length > 0) {
      // Grade the most recent worksheet
      handleGradeWorksheet(recentWorksheets[0].id)
    }
  }, [recentWorksheets, handleGradeWorksheet])

  useEffect(() => {
    if (selectedChildId) {
      fetchDashboard(selectedChildId)
      fetchLearningGraph(selectedChildId)
      fetchRecentWorksheets(selectedChildId)
      fetchGradingHistory(selectedChildId)
    }
  }, [selectedChildId, fetchDashboard, fetchLearningGraph, fetchRecentWorksheets, fetchGradingHistory])

  if (childrenLoading) return <LoadingSkeleton />

  if (childrenList.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-16">
        <EmptyState
          icon={
            <svg className="w-16 h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
            </svg>
          }
          title="No child profiles yet"
          description="Add a child profile first, then generate worksheets to see progress here."
        />
      </div>
    )
  }

  const selectedChild = childrenList.find((c) => c.id === selectedChildId)

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
      {/* Greeting */}
      <div>
        <h1 className="text-2xl font-bold font-fraunces text-foreground">
          {getGreeting()}, <span className="text-primary">{displayName}</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          {selectedChild ? `${selectedChild.name}\u2019s progress` : 'Select a child to see progress'}
        </p>
      </div>

      {/* Child picker pills */}
      {childrenList.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {childrenList.map((child) => (
            <button
              key={child.id}
              onClick={() => setSelectedChildId(child.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors border ${
                selectedChildId === child.id
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-card text-foreground border-border hover:border-primary/50'
              }`}
            >
              <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs">
                {child.name[0].toUpperCase()}
              </span>
              {child.name}
            </button>
          ))}
        </div>
      )}
      {childrenList.length === 1 && selectedChild && (
        <div className="text-sm font-medium text-muted-foreground">
          {selectedChild.name} &middot; Class {selectedChild.grade}
        </div>
      )}

      {/* Grade a Worksheet card */}
      <GradeWorksheetCard
        recentWorksheets={recentWorksheets}
        loadingWorksheets={loadingWorksheets || loadingGradingWorksheet}
        onGradeWorksheet={handleGradeWorksheet}
        onUploadDirect={handleDirectUpload}
      />

      {/* Error state */}
      {error && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-6 flex items-center justify-between">
            <p className="text-sm text-destructive">{error}</p>
            <button
              onClick={() => selectedChildId && fetchDashboard(selectedChildId)}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Retry
            </button>
          </CardContent>
        </Card>
      )}

      {/* Loading */}
      {loading && <LoadingSkeleton />}

      {/* Dashboard content */}
      {!loading && !error && dashboard && (
        <>
          {/* Stats cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Total Worksheets
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                    <svg className="w-5 h-5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                    </svg>
                  </div>
                  <span className="text-3xl font-bold text-foreground font-fraunces">
                    {dashboard.overall_stats.total_worksheets}
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Current Streak
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
                    <svg className="w-5 h-5 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
                      <path fillRule="evenodd" d="M12.963 2.286a.75.75 0 00-1.071-.136 9.742 9.742 0 00-3.539 6.177A7.547 7.547 0 016.648 6.61a.75.75 0 00-1.152-.082A9 9 0 1015.68 4.534a7.46 7.46 0 01-2.717-2.248zM15.75 14.25a3.75 3.75 0 11-7.313-1.172c.628.465 1.35.81 2.133 1a5.99 5.99 0 011.925-3.545 3.75 3.75 0 013.255 3.717z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div>
                    <span className="text-3xl font-bold text-foreground font-fraunces">
                      {dashboard.overall_stats.current_streak}
                    </span>
                    <span className="text-sm text-muted-foreground ml-1">days</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Total Stars
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                    <svg className="w-5 h-5 text-yellow-500" viewBox="0 0 24 24" fill="currentColor">
                      <path fillRule="evenodd" d="M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <span className="text-3xl font-bold text-foreground font-fraunces">
                    {dashboard.overall_stats.total_stars}
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Mastery Overview
                </CardTitle>
              </CardHeader>
              <CardContent>
                {dashboard.skills.length > 0 ? (
                  <MasteryDistribution skills={dashboard.skills} />
                ) : (
                  <p className="text-sm text-muted-foreground">No skill data yet</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Insight Card — plain-English report + today's recommendation */}
          <InsightCard
            childId={selectedChildId ?? ''}
            onNavigate={onNavigate ? () => onNavigate('generator') : undefined}
          />

          {/* Learning Health Card */}
          {graphLoading ? (
            <LearningGraphSkeleton />
          ) : graphSummary ? (
            <LearningHealthCard summary={graphSummary} />
          ) : null}

          {/* Streak card — fetches engagement independently */}
          <StreakCard childId={selectedChildId ?? ''} sessions={sessions} />

          {/* 30-day activity timeline */}
          <ProgressTimeline sessions={sessions} loading={graphLoading} />

          {/* Subject deep dive — only after graph data loaded */}
          {!graphLoading && graph && Object.keys(graph).length > 0 && (
            <SubjectGrid graph={graph} />
          )}

          {/* Skills Table */}
          {dashboard.skills.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg font-fraunces">Skill Progress</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border/50">
                        <th className="text-left py-3 px-2 font-medium text-muted-foreground">Skill</th>
                        <th className="text-left py-3 px-2 font-medium text-muted-foreground">Level</th>
                        <th className="text-right py-3 px-2 font-medium text-muted-foreground">Accuracy</th>
                        <th className="text-right py-3 px-2 font-medium text-muted-foreground">Streak</th>
                        <th className="text-right py-3 px-2 font-medium text-muted-foreground">Attempts</th>
                        <th className="py-3 px-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.skills
                        .sort((a, b) => b.accuracy - a.accuracy)
                        .map((skill) => (
                          <tr key={skill.skill_tag} className="border-b border-border/20 hover:bg-secondary/20 transition-colors">
                            <td className="py-3 px-2 font-medium text-foreground">
                              {formatSkillTag(skill.skill_tag)}
                            </td>
                            <td className="py-3 px-2">
                              <Badge variant="outline" className={masteryColor(skill.mastery_level)}>
                                {masteryLabel(skill.mastery_level)}
                              </Badge>
                            </td>
                            <td className="py-3 px-2 text-right">
                              <span className={`font-semibold ${
                                skill.accuracy >= 80 ? 'text-emerald-600' :
                                skill.accuracy >= 60 ? 'text-amber-600' : 'text-red-500'
                              }`}>
                                {skill.accuracy}%
                              </span>
                            </td>
                            <td className="py-3 px-2 text-right text-foreground">{skill.streak}</td>
                            <td className="py-3 px-2 text-right text-muted-foreground">
                              {skill.correct_attempts}/{skill.total_attempts}
                            </td>
                            <td className="py-3 px-2 text-right">
                              {onNavigate && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => onNavigate('generator')}
                                  className="text-primary text-xs font-semibold shrink-0 h-auto py-1 px-2"
                                >
                                  Practice &rarr;
                                </Button>
                              )}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recent Topics */}
          {dashboard.recent_topics.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg font-fraunces">Recent Topics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {dashboard.recent_topics.map((topic) => (
                    <div
                      key={topic.topic}
                      className="flex items-center justify-between p-3 rounded-lg bg-secondary/30 border border-border/20"
                    >
                      <div>
                        <p className="text-sm font-medium text-foreground">{topic.topic}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {topic.count} worksheet{topic.count !== 1 ? 's' : ''} &middot;{' '}
                          {new Date(topic.last_generated).toLocaleDateString('en-IN', {
                            day: 'numeric',
                            month: 'short',
                          })}
                        </p>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                        <span className="text-xs font-bold text-primary">{topic.count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Empty state when no data at all */}
          {dashboard.overall_stats.total_worksheets === 0 && dashboard.skills.length === 0 && (
            <EmptyState
              icon={
                <svg className="w-16 h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                </svg>
              }
              title="No progress yet"
              description="Complete a worksheet to see progress here."
            />
          )}

          {/* Grading History */}
          <GradingHistorySection history={gradingHistory} loading={loadingHistory} />
        </>
      )}

      {/* GradeFromPhoto dialog */}
      {gradingWorksheet && (
        <GradeFromPhoto
          open={showGrading}
          onOpenChange={(open) => {
            setShowGrading(open)
            if (!open) {
              setGradingWorksheet(null)
              // Refresh data after grading
              if (selectedChildId) {
                fetchGradingHistory(selectedChildId)
                fetchDashboard(selectedChildId)
              }
            }
          }}
          worksheet={gradingWorksheet}
          childId={selectedChildId ?? undefined}
        />
      )}
    </div>
  )
}
