import { useEffect, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/ui/page-header'
import { Section } from '@/components/ui/section'
import { Badge } from '@/components/ui/badge'
import { useAuth } from '@/lib/auth'
import { useClasses } from '@/lib/classes'
import { api } from '@/lib/api'
import { getTopicName } from '@/lib/curriculum'
import { notify } from '@/lib/toast'

// ─── Types ────────────────────────────────────────────────────────────────────

interface SavedWorksheet {
  id: string
  title: string
  subject: string
  grade: string
  topic: string
  created_at: string
}

interface TeacherAnalytics {
  total_worksheets: number
  topic_reuse_rate: number
  active_weeks: number
  subjects_covered: number
  top_topics: { topic: string; count: number }[]
}

interface ClassChild {
  id: string
  name: string
}

interface ClassDashboardData {
  class_name: string
  total_students: number
  children: ClassChild[]
  heatmap: Record<string, Record<string, string>>
  weak_topics: string[]
  child_summaries: Record<string, { name: string; mastered_count: number; needs_attention_count: number }>
}

interface ReportState {
  token: string
  share_url: string
  expires_at: string
}

interface ContactRow {
  child_id: string
  child_name: string
  parent_email: string
}

interface TeacherDashboardProps {
  onNavigate: (page: string) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const MASTERY_CELL: Record<string, { bg: string; label: string }> = {
  mastered:  { bg: 'bg-emerald-500', label: 'Mastered' },
  improving: { bg: 'bg-amber-400',   label: 'Improving' },
  learning:  { bg: 'bg-red-400',     label: 'Needs help' },
  unknown:   { bg: 'bg-red-300',     label: 'Not started' },
}

function cellStyle(level: string | undefined): { bg: string; label: string } {
  if (!level) return { bg: 'bg-gray-200', label: 'No data' }
  return MASTERY_CELL[level] ?? { bg: 'bg-gray-200', label: level }
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good Morning'
  if (h < 17) return 'Good Afternoon'
  return 'Good Evening'
}

// ─── WeakTopicsAlert ──────────────────────────────────────────────────────────

function WeakTopicsAlert({ weakTopics }: { weakTopics: string[] }) {
  if (weakTopics.length === 0) return null
  return (
    <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-xl">
      <svg className="shrink-0 w-5 h-5 mt-0.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-red-800 mb-0.5">
          These topics need attention across your class:
        </p>
        <p className="text-sm text-red-700 leading-relaxed">
          {weakTopics.map(getTopicName).join(', ')}
        </p>
      </div>
    </div>
  )
}

// ─── ClassHeatmap ─────────────────────────────────────────────────────────────

function ClassHeatmap({
  children,
  heatmap,
}: {
  children: ClassChild[]
  heatmap: Record<string, Record<string, string>>
}) {
  const [tooltip, setTooltip] = useState<{ student: string; topic: string; status: string } | null>(null)
  const topics = Object.keys(heatmap)

  if (topics.length === 0 || children.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-muted-foreground">
        No mastery data yet. Assign worksheets to students to see the heatmap.
      </div>
    )
  }

  return (
    <div className="relative overflow-x-auto">
      {/* Floating tooltip */}
      {tooltip && (
        <div className="absolute top-0 right-0 z-10 bg-popover text-popover-foreground text-xs px-3 py-2 rounded-lg shadow-lg border border-border/40 whitespace-nowrap pointer-events-none">
          <span className="font-semibold">{tooltip.student}</span>
          {' — '}
          {tooltip.topic}
          {' — '}
          <span className="font-medium">{tooltip.status}</span>
        </div>
      )}

      {/* Grid: first col = topic label, rest = student columns */}
      <div
        className="grid gap-0.5 min-w-max"
        style={{
          gridTemplateColumns: `minmax(140px, 180px) repeat(${children.length}, minmax(36px, 52px))`,
        }}
      >
        {/* Header row */}
        <div className="h-9" />
        {children.map((child) => (
          <div
            key={child.id}
            className="h-9 flex items-center justify-center text-[10px] font-bold text-muted-foreground truncate px-1"
            title={child.name}
          >
            {child.name.split(' ')[0]}
          </div>
        ))}

        {/* One row per topic */}
        {topics.map((topicSlug) => (
          <div key={topicSlug} className="contents">
            {/* Topic label */}
            <div
              className="h-8 flex items-center text-xs text-foreground font-medium truncate pr-2"
              title={getTopicName(topicSlug)}
            >
              {getTopicName(topicSlug)}
            </div>

            {/* Cells — one per student */}
            {children.map((child) => {
              const level = heatmap[topicSlug]?.[child.id]
              const { bg, label } = cellStyle(level)
              return (
                <div
                  key={`${topicSlug}-${child.id}`}
                  className={`h-8 rounded-sm ${bg} cursor-default transition-opacity hover:opacity-75`}
                  onMouseEnter={() =>
                    setTooltip({ student: child.name, topic: getTopicName(topicSlug), status: label })
                  }
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 flex-wrap">
        {Object.entries(MASTERY_CELL).map(([, { bg, label }]) => (
          <div key={label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className={`w-3 h-3 rounded-sm ${bg}`} />
            <span>{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div className="w-3 h-3 rounded-sm bg-gray-200" />
          <span>No data</span>
        </div>
      </div>
    </div>
  )
}

// ─── StudentCards ─────────────────────────────────────────────────────────────

function StudentCards({
  childSummaries,
}: {
  childSummaries: Record<string, { name: string; mastered_count: number; needs_attention_count: number }>
}) {
  const entries = Object.entries(childSummaries)
  if (entries.length === 0) return null

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {entries.map(([childId, s]) => (
        <Card key={childId} className="border-border/50 rounded-xl">
          <CardContent className="p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                <span className="text-sm font-bold text-primary">{s.name[0].toUpperCase()}</span>
              </div>
              <span className="font-semibold text-foreground truncate">{s.name}</span>
            </div>
            <div className="flex gap-3">
              <div className="flex-1 text-center py-2 rounded-lg bg-emerald-50 border border-emerald-100">
                <p className="text-lg font-bold text-emerald-700 font-fraunces">{s.mastered_count}</p>
                <p className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider">Mastered</p>
              </div>
              <div className="flex-1 text-center py-2 rounded-lg bg-red-50 border border-red-100">
                <p className="text-lg font-bold text-red-700 font-fraunces">{s.needs_attention_count}</p>
                <p className="text-[10px] font-bold text-red-600 uppercase tracking-wider">Needs Help</p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function TeacherDashboard({ onNavigate }: TeacherDashboardProps) {
  const { user } = useAuth()
  const { classes, loading: classesLoading } = useClasses()
  const [recentWorksheets, setRecentWorksheets] = useState<SavedWorksheet[]>([])
  const [worksheetsLoading, setWorksheetsLoading] = useState(true)
  const [analytics, setAnalytics] = useState<TeacherAnalytics | null>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)

  // Class-level heatmap state
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null)
  const [classDashboard, setClassDashboard] = useState<ClassDashboardData | null>(null)
  const [classDashLoading, setClassDashLoading] = useState(false)
  const [classDashError, setClassDashError] = useState<string | null>(null)

  // Report generation state
  const [reportState, setReportState] = useState<ReportState | null>(null)
  const [reportGenerating, setReportGenerating] = useState(false)

  // Email contacts state
  const [contacts, setContacts] = useState<ContactRow[]>([])
  const [showEmailModal, setShowEmailModal] = useState(false)
  const [emailInputs, setEmailInputs] = useState<Record<string, string>>({})
  const [savingContacts, setSavingContacts] = useState(false)
  const [emailSending, setEmailSending] = useState(false)
  const [showSendConfirm, setShowSendConfirm] = useState(false)

  const displayName = user?.user_metadata?.name?.split(' ')[0] || user?.email?.split('@')[0] || 'Teacher'

  // Auto-select first class
  useEffect(() => {
    if (!selectedClassId && classes.length > 0) {
      setSelectedClassId(classes[0].id)
    }
  }, [classes, selectedClassId])

  const fetchClassDashboard = useCallback(async (classId: string) => {
    setClassDashLoading(true)
    setClassDashError(null)
    try {
      const resp = await api.get(`/api/classes/${classId}/dashboard`)
      setClassDashboard(resp.data)
    } catch (err: unknown) {
      console.warn('[TeacherDashboard] Class dashboard fetch failed:', err)
      setClassDashError('Could not load class analytics.')
      setClassDashboard(null)
    } finally {
      setClassDashLoading(false)
    }
  }, [])

  const fetchContacts = useCallback(async (classId: string) => {
    try {
      const resp = await api.get(`/api/teacher/classes/${classId}/contacts`)
      const rows: ContactRow[] = resp.data
      setContacts(rows)
      // Pre-populate email inputs from existing contacts
      const inputs: Record<string, string> = {}
      for (const r of rows) inputs[r.child_id] = r.parent_email
      setEmailInputs(inputs)
    } catch (err) {
      console.warn('[TeacherDashboard] Contacts fetch failed:', err)
    }
  }, [])

  useEffect(() => {
    if (selectedClassId) {
      fetchClassDashboard(selectedClassId)
      fetchContacts(selectedClassId)
      // Reset per-class state when switching classes
      setReportState(null)
      setShowSendConfirm(false)
    }
  }, [selectedClassId, fetchClassDashboard, fetchContacts])

  const generateReport = useCallback(async () => {
    if (!selectedClassId) return
    setReportGenerating(true)
    try {
      const resp = await api.post(`/api/teacher/classes/${selectedClassId}/report`)
      setReportState(resp.data as ReportState)
    } catch (err: unknown) {
      console.warn('[TeacherDashboard] Report generation failed:', err)
      notify.error('Could not generate report. Please try again.')
    } finally {
      setReportGenerating(false)
    }
  }, [selectedClassId])

  const copyReportLink = useCallback(async () => {
    if (!reportState) return
    try {
      await navigator.clipboard.writeText(reportState.share_url)
      notify.success('Link copied to clipboard!')
    } catch {
      notify.error('Could not copy link. Please copy it manually.')
    }
  }, [reportState])

  const shareOnWhatsApp = useCallback(() => {
    if (!reportState || !selectedClassId) return
    const selectedClass = classes.find(c => c.id === selectedClassId)
    const className = selectedClass?.name ?? 'your class'
    const displayNameFull = user?.user_metadata?.name ?? user?.email?.split('@')[0] ?? 'Your Teacher'
    const message = [
      '*Weekly Learning Report*',
      `Class: ${className}`,
      `From: ${displayNameFull}`,
      '',
      'Dear Parents,',
      'Your child\'s weekly progress report is ready.',
      '',
      `View report: ${reportState.share_url}`,
      '',
      '_Valid for 7 days_',
      '_Powered by PracticeCraft_',
    ].join('\n')
    window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, '_blank')
  }, [reportState, selectedClassId, classes, user])

  const openEmailModal = useCallback(() => {
    // Ensure emailInputs covers every student currently in the dashboard
    const students = classDashboard?.children ?? []
    setEmailInputs(prev => {
      const next = { ...prev }
      for (const s of students) {
        if (!(s.id in next)) next[s.id] = ''
      }
      return next
    })
    setShowEmailModal(true)
  }, [classDashboard])

  const saveContacts = useCallback(async () => {
    if (!selectedClassId) return
    setSavingContacts(true)
    try {
      const payload = Object.entries(emailInputs)
        .filter(([, email]) => email.trim())
        .map(([child_id, parent_email]) => ({ child_id, parent_email: parent_email.trim() }))
      await api.post(`/api/teacher/classes/${selectedClassId}/contacts`, payload)
      await fetchContacts(selectedClassId)
      notify.success('Parent emails saved!')
      setShowEmailModal(false)
    } catch {
      notify.error('Could not save emails. Please try again.')
    } finally {
      setSavingContacts(false)
    }
  }, [selectedClassId, emailInputs, fetchContacts])

  const sendEmailReport = useCallback(async () => {
    if (!selectedClassId || !reportState) return
    setEmailSending(true)
    try {
      const resp = await api.post(
        `/api/teacher/classes/${selectedClassId}/report/send-email`,
        { report_token: reportState.token },
      )
      const { sent } = resp.data as { sent: number; skipped: number }
      notify.success(`Report emailed to ${sent} parent${sent !== 1 ? 's' : ''}!`)
      setShowSendConfirm(false)
    } catch {
      notify.error('Could not send emails. Please try again.')
    } finally {
      setEmailSending(false)
    }
  }, [selectedClassId, reportState])

  const handleEmailReportClick = useCallback(() => {
    const hasAnyEmail = contacts.some(c => c.parent_email)
    if (hasAnyEmail) {
      setShowSendConfirm(true)
    } else {
      openEmailModal()
    }
  }, [contacts, openEmailModal])

  useEffect(() => {
    const fetchRecent = async () => {
      try {
        const response = await api.get('/api/worksheets/saved/list?limit=5')
        setRecentWorksheets(response.data.worksheets || [])
      } catch (err) {
        console.error('[TeacherDashboard] Failed to fetch recent worksheets:', err)
      } finally {
        setWorksheetsLoading(false)
      }
    }

    const fetchAnalytics = async () => {
      try {
        const response = await api.get('/api/worksheets/analytics')
        setAnalytics(response.data)
      } catch (err) {
        console.error('[TeacherDashboard] Failed to fetch analytics:', err)
      } finally {
        setAnalyticsLoading(false)
      }
    }

    fetchRecent()
    fetchAnalytics()
  }, [])

  const selectedClass = classes.find((c) => c.id === selectedClassId)

  return (
    <div className="max-w-5xl mx-auto px-4 py-12 pb-28 space-y-12">

      {/* ── Greeting ── */}
      <PageHeader className="animate-in fade-in slide-in-from-top-4 duration-500">
        <PageHeader.Title className="text-pretty">
          {getGreeting()}, <span className="text-primary">{displayName}</span>
        </PageHeader.Title>
        <PageHeader.Subtitle className="text-pretty max-w-2xl">
          {classes.length > 0
            ? `You have ${classes.length} class${classes.length === 1 ? '' : 'es'} set up. Create practice for any of them.`
            : 'Start by adding a class to create worksheets for your students.'
          }
        </PageHeader.Subtitle>
      </PageHeader>

      {/* ── Empty state ── */}
      {!analyticsLoading && !worksheetsLoading && (analytics?.total_worksheets ?? 0) === 0 && recentWorksheets.length === 0 && (
        <div className="text-center py-16 px-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
            </svg>
          </div>
          <h3 className="font-serif text-xl font-semibold mb-2">Your workspace is ready</h3>
          <p className="text-muted-foreground text-sm mb-6 max-w-sm mx-auto">
            Generate your first worksheet to see analytics, track topics, and build your library.
          </p>
          <Button onClick={() => onNavigate('generator')}>Create first worksheet &rarr;</Button>
        </div>
      )}

      {/* ── Stats Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-in fade-in slide-in-from-bottom-2 duration-700">
        {[
          { label: 'Worksheets', value: analytics?.total_worksheets ?? 0, icon: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z', color: 'primary' },
          { label: 'Active Weeks', value: analytics?.active_weeks ?? 0, icon: 'M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5', color: 'accent' },
          { label: 'Reuse Rate', value: `${Math.round((analytics?.topic_reuse_rate ?? 0) * 100)}%`, icon: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99', color: 'emerald' },
          { label: 'Classes', value: classes.length, icon: 'M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5', color: 'rose' }
        ].map((stat, i) => (
          <Card key={i} className="border-border/50 bg-card/40 hover:bg-card/60 transition-colors rounded-2xl overflow-hidden shadow-sm">
            <CardContent className="p-6 text-center">
              <div className={`w-11 h-11 mx-auto mb-3 rounded-xl flex items-center justify-center shrink-0 border border-border/10 ${
                stat.color === 'primary'  ? 'bg-primary/10'    :
                stat.color === 'accent'   ? 'bg-accent/10'     :
                stat.color === 'emerald'  ? 'bg-emerald-500/10':
                'bg-rose-500/10'
              }`}>
                <svg className={`w-5 h-5 ${
                  stat.color === 'primary'  ? 'text-primary'    :
                  stat.color === 'accent'   ? 'text-accent'     :
                  stat.color === 'emerald'  ? 'text-emerald-600':
                  'text-rose-600'
                }`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={stat.icon} />
                </svg>
              </div>
              {classesLoading || analyticsLoading ? (
                <Skeleton className="h-8 w-12 mx-auto mb-1" />
              ) : (
                <p className="text-2xl font-bold font-jakarta text-foreground leading-tight">{stat.value}</p>
              )}
              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mt-1">{stat.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Quick Actions ── */}
      <div className="grid md:grid-cols-2 gap-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
        <Card
          tabIndex={0}
          role="button"
          aria-label="Create Practice"
          className="relative group card-hover border-primary/20 bg-gradient-to-br from-primary/5 via-primary/[0.02] to-transparent cursor-pointer rounded-2xl p-1"
          onClick={() => onNavigate('generator')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate('generator') } }}
        >
          <CardContent className="p-6">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-primary text-primary-foreground flex items-center justify-center shrink-0 shadow-lg shadow-primary/20 group-hover:scale-110 transition-transform duration-300">
                <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
                </svg>
              </div>
              <div className="space-y-1.5 pr-8">
                <h3 className="font-bold text-xl text-foreground font-fraunces">Create Practice</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Create worksheets aligned to your class syllabus, ready to print or save.
                </p>
              </div>
              <div className="absolute top-8 right-8 text-muted-foreground/30 group-hover:text-primary group-hover:translate-x-1 transition-all duration-300">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card
          tabIndex={0}
          role="button"
          aria-label="Manage Classes"
          className="relative group card-hover border-accent/20 bg-gradient-to-br from-accent/5 via-accent/[0.02] to-transparent cursor-pointer rounded-2xl p-1"
          onClick={() => onNavigate('classes')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate('classes') } }}
        >
          <CardContent className="p-6">
            <div className="flex items-start gap-6">
              <div className="w-14 h-14 rounded-2xl bg-accent text-accent-foreground flex items-center justify-center shrink-0 shadow-lg shadow-accent/20 group-hover:scale-110 transition-transform duration-300">
                <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <div className="space-y-1.5 pr-8">
                <h3 className="font-bold text-xl text-foreground font-fraunces">Manage Classes</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Add or update your classes and their subjects.
                </p>
              </div>
              <div className="absolute top-8 right-8 text-muted-foreground/30 group-hover:text-accent group-hover:translate-x-1 transition-all duration-300">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Class Analytics Section ── */}
      {classes.length > 0 && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold font-jakarta text-foreground">Class Analytics</h2>
            {classDashboard && (
              <Badge variant="secondary" className="text-xs font-semibold">
                {classDashboard.total_students} student{classDashboard.total_students !== 1 ? 's' : ''}
              </Badge>
            )}
          </div>

          {/* Class picker pills */}
          <div className="flex gap-2 overflow-x-auto pb-1">
            {classes.map((cls) => (
              <button
                key={cls.id}
                onClick={() => {
                  setSelectedClassId(cls.id)
                  setClassDashboard(null)
                }}
                className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors border ${
                  selectedClassId === cls.id
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card text-foreground border-border hover:border-primary/50'
                }`}
              >
                <span className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] ${
                  selectedClassId === cls.id ? 'bg-white/20' : 'bg-primary/10 text-primary'
                }`}>
                  {cls.subject[0]}
                </span>
                {cls.name}
                <span className="text-[10px] opacity-60">{cls.grade}</span>
              </button>
            ))}
          </div>

          {/* Loading skeleton for class dashboard */}
          {classDashLoading && (
            <div className="space-y-4">
              <Skeleton className="h-12 w-full rounded-xl" />
              <Skeleton className="h-64 w-full rounded-xl" />
              <div className="grid grid-cols-3 gap-4">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)}
              </div>
            </div>
          )}

          {/* Error state */}
          {classDashError && !classDashLoading && (
            <div className="flex items-center justify-between p-4 bg-destructive/5 border border-destructive/20 rounded-xl">
              <p className="text-sm text-destructive">{classDashError}</p>
              <button
                onClick={() => selectedClassId && fetchClassDashboard(selectedClassId)}
                className="text-xs font-semibold text-primary underline underline-offset-2"
              >
                Retry
              </button>
            </div>
          )}

          {/* Class dashboard content */}
          {!classDashLoading && !classDashError && classDashboard && (
            <div className="space-y-6">
              {/* Weak topics alert */}
              <WeakTopicsAlert weakTopics={classDashboard.weak_topics} />

              {/* No students yet */}
              {classDashboard.total_students === 0 && (
                <div className="py-10 text-center bg-secondary/20 rounded-2xl border border-dashed border-border/50">
                  <p className="text-sm text-muted-foreground mb-2 font-medium">No student data for this class yet.</p>
                  <p className="text-xs text-muted-foreground">
                    Assign worksheets to students via the generator to populate this view.
                  </p>
                </div>
              )}

              {/* Heatmap */}
              {classDashboard.total_students > 0 && (
                <Card className="border-border/50 rounded-2xl">
                  <CardContent className="p-6">
                    <h3 className="text-base font-bold font-jakarta text-foreground mb-4">
                      Mastery Heatmap — {selectedClass?.name}
                    </h3>
                    <ClassHeatmap
                      children={classDashboard.children}
                      heatmap={classDashboard.heatmap}
                    />
                  </CardContent>
                </Card>
              )}

              {/* Student cards */}
              {classDashboard.total_students > 0 && (
                <div className="space-y-3">
                  <h3 className="text-base font-bold font-jakarta text-foreground">Student Summaries</h3>
                  <StudentCards childSummaries={classDashboard.child_summaries} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Classes + Recent Worksheets ── */}
      <div className="grid lg:grid-cols-5 gap-10">
        <div className="lg:col-span-3 space-y-6">
          <Section>
            <Section.Header className="flex items-center justify-between border-none pb-0 mb-6">
              <h2 className="text-2xl font-bold font-jakarta text-foreground">Your Classes</h2>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('classes')} className="text-primary font-bold hover:bg-primary/5 rounded-xl">
                Manage All
              </Button>
            </Section.Header>
            <Section.Content>
              {classesLoading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 w-full rounded-2xl" />)}
                </div>
              ) : classes.length === 0 ? (
                <div className="p-8 text-center bg-secondary/20 rounded-2xl border border-dashed border-border/60">
                  <p className="text-sm text-muted-foreground font-medium mb-4">No classes yet. Add one to get started.</p>
                  <Button onClick={() => onNavigate('classes')} variant="outline" className="rounded-xl font-bold">Add a class</Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {classes.slice(0, 4).map((cls) => (
                    <Card
                      key={cls.id}
                      className={`group border-border/50 bg-card/40 hover:bg-card/80 transition-all rounded-2xl overflow-hidden cursor-pointer ${
                        selectedClassId === cls.id ? 'border-primary/40 bg-primary/5' : 'hover:border-primary/20'
                      }`}
                      onClick={() => {
                        setSelectedClassId(cls.id)
                        setClassDashboard(null)
                        window.scrollTo({ top: 0, behavior: 'smooth' })
                      }}
                    >
                      <CardContent className="p-5">
                        <div className="flex items-center gap-4">
                          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/10 to-accent/10 flex items-center justify-center shrink-0 border border-primary/10 group-hover:scale-105 transition-transform">
                            <span className="text-lg font-bold text-primary font-jakarta">{cls.subject[0]}</span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="font-bold text-base text-foreground truncate font-jakarta leading-tight group-hover:text-primary transition-colors">{cls.name}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/50">{cls.grade}</span>
                              <span className="w-1 h-1 rounded-full bg-border" />
                              <span className="text-[10px] font-bold uppercase tracking-widest text-primary/70">{cls.subject}</span>
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </Section.Content>
          </Section>
        </div>

        <div className="lg:col-span-2 space-y-6">
          <Section>
            <Section.Header className="flex items-center justify-between border-none pb-0 mb-6">
              <h2 className="text-2xl font-bold font-jakarta text-foreground">Recent Worksheets</h2>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('saved')} className="text-primary font-bold hover:bg-primary/5 rounded-xl">
                Library
              </Button>
            </Section.Header>
            <Section.Content>
              {worksheetsLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-2xl" />)}
                </div>
              ) : recentWorksheets.length === 0 ? (
                <div className="p-8 text-center bg-secondary/20 rounded-2xl border border-dashed border-border/60">
                  <p className="text-sm text-muted-foreground font-medium mb-4">No worksheets yet — create one in under a minute.</p>
                  <Button onClick={() => onNavigate('generator')} variant="outline" className="rounded-xl font-bold">Create today's practice</Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {recentWorksheets.map((ws) => (
                    <Card key={ws.id} className="group border-border/40 bg-card/60 hover:bg-background hover:shadow-lg hover:shadow-black/5 hover:border-primary/10 transition-all rounded-2xl cursor-pointer" onClick={() => onNavigate('saved')}>
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-8 h-8 rounded-lg bg-secondary/80 flex items-center justify-center shrink-0">
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                              </svg>
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-bold text-foreground truncate group-hover:text-primary transition-colors">{ws.title}</p>
                              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">{ws.subject} &middot; {ws.topic}</p>
                            </div>
                          </div>
                          <Badge variant="secondary" className="bg-secondary/40 text-[9px] font-bold uppercase tracking-tighter px-1.5 py-0 rounded-md border-none text-muted-foreground/60 shrink-0">
                            {formatDate(ws.created_at)}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </Section.Content>
          </Section>
        </div>
      </div>

      {/* ── Report Ready card (shown after generation) ── */}
      {reportState && (
        <Card className="border-emerald-200 bg-emerald-50/80 rounded-2xl">
          <CardContent className="p-5">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-8 h-8 rounded-lg bg-emerald-100 border border-emerald-200 flex items-center justify-center shrink-0">
                <svg className="w-4 h-4 text-emerald-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-bold text-emerald-800">Report Ready</p>
                <p className="text-[11px] text-emerald-700 mt-0.5">
                  Generated {new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                  {' · '}Valid until {new Date(reportState.expires_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                </p>
              </div>
            </div>

            {/* Row 1: WhatsApp + Copy Link */}
            <div className="flex gap-3">
              {/* WhatsApp share */}
              <button
                onClick={shareOnWhatsApp}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-[#25D366] hover:bg-[#20b858] active:bg-[#1da34f] text-white rounded-xl text-sm font-bold transition-colors"
              >
                <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                </svg>
                Share via WhatsApp
              </button>

              {/* Copy link */}
              <button
                onClick={copyReportLink}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 rounded-xl text-sm font-bold transition-colors border border-slate-200"
              >
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                </svg>
                Copy Link
              </button>
            </div>

            {/* Row 2: Send Email Report */}
            <div className="flex items-center gap-3 mt-3">
              <button
                onClick={handleEmailReportClick}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-sm font-bold transition-colors"
              >
                <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                </svg>
                Send Email Report
              </button>
              <button
                onClick={openEmailModal}
                className="text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
              >
                Edit emails
              </button>
            </div>

            {/* Send confirmation */}
            {showSendConfirm && (
              <div className="flex items-center justify-between mt-3 p-3 bg-primary/5 border border-primary/20 rounded-xl">
                <p className="text-sm font-medium text-foreground">
                  Send to {contacts.filter(c => c.parent_email).length} parent{contacts.filter(c => c.parent_email).length !== 1 ? 's' : ''}?
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowSendConfirm(false)}
                    className="text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={sendEmailReport}
                    disabled={emailSending}
                    className="text-xs font-bold px-3 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  >
                    {emailSending ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Add Parent Emails modal ── */}
      {showEmailModal && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-md bg-white dark:bg-card rounded-2xl shadow-2xl overflow-hidden">
            <div className="px-6 py-5 border-b border-stone-100 dark:border-border">
              <h3 className="font-bold text-lg text-stone-800 dark:text-foreground font-jakarta">
                Add Parent Emails
              </h3>
              <p className="text-sm text-stone-500 dark:text-muted-foreground mt-1">
                Parents will receive a personalised weekly summary for their child.
              </p>
            </div>

            <div className="px-6 py-4 max-h-80 overflow-y-auto space-y-3">
              {(classDashboard?.children ?? []).length === 0 ? (
                <p className="text-sm text-stone-500 text-center py-6">
                  No students in this class yet.
                </p>
              ) : (
                (classDashboard?.children ?? []).map(student => (
                  <div key={student.id} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                      <span className="text-xs font-bold text-primary">
                        {student.name[0].toUpperCase()}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-foreground w-24 shrink-0 truncate">
                      {student.name}
                    </p>
                    <input
                      type="email"
                      value={emailInputs[student.id] ?? ''}
                      onChange={e =>
                        setEmailInputs(prev => ({ ...prev, [student.id]: e.target.value }))
                      }
                      placeholder="parent@email.com"
                      className="flex-1 text-sm px-3 py-1.5 border border-stone-200 dark:border-border rounded-lg bg-white dark:bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                    />
                  </div>
                ))
              )}
            </div>

            <div className="px-6 py-4 border-t border-stone-100 dark:border-border flex justify-end gap-3">
              <button
                onClick={() => setShowEmailModal(false)}
                className="px-4 py-2 text-sm font-semibold text-stone-600 dark:text-muted-foreground hover:text-stone-800 dark:hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveContacts}
                disabled={savingContacts}
                className="px-5 py-2 text-sm font-bold bg-primary text-primary-foreground rounded-xl hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {savingContacts ? 'Saving…' : 'Save Emails'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Fixed bottom bar: Generate Weekly Class Report ── */}
      {selectedClassId && (
        <div className="fixed bottom-0 left-0 right-0 z-40 bg-background/90 backdrop-blur-xl border-t border-border/30 px-6 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] md:pb-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-foreground truncate">{selectedClass?.name}</p>
            <p className="text-[10px] text-muted-foreground">
              {classDashboard ? `${classDashboard.total_students} student${classDashboard.total_students !== 1 ? 's' : ''}` : 'Loading…'}
            </p>
          </div>
          <Button
            size="sm"
            disabled={reportGenerating}
            onClick={generateReport}
            className="shrink-0 font-semibold"
          >
            {reportGenerating ? 'Generating…' : reportState ? 'Regenerate Report' : 'Generate Weekly Class Report'}
          </Button>
        </div>
      )}
    </div>
  )
}
