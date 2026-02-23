import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { useProfile } from '@/lib/profile'
import { useChildren } from '@/lib/children'
import { api } from '@/lib/api'
import { QuickActionCard } from '@/components/QuickActionCard'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  onNavigate: (page: string, preFill?: { grade?: string; subject?: string; topic?: string; mode?: 'worksheet' | 'revision' | 'flashcards' | 'textbook' }) => void
}

interface RecentWorksheet {
  id: string
  title: string
  subject: string
  topic: string
  created_at: string
}

// ─── Icons (inline SVGs matching NAV_ICONS style in App.tsx) ──────────────────

const ICONS = {
  pencil: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
    </svg>
  ),
  bookOpen: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
    </svg>
  ),
  camera: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" />
    </svg>
  ),
  layers: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.429 9.75L2.25 12l4.179 2.25m0-4.5l5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L12 12.75 6.429 9.75m11.142 0l4.179 2.25L12 17.25 2.25 12l4.179-2.25m11.142 0l4.179 2.25L12 22.5l-9.75-5.25 4.179-2.25" />
    </svg>
  ),
  book: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
    </svg>
  ),
  messageCircle: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM2.25 12.76c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443h2.887c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
    </svg>
  ),
  classes: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  sparkle: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
    </svg>
  ),
} as const

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
  })
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function HomeDashboard({ onNavigate }: Props) {
  const { user } = useAuth()
  const { activeRole } = useProfile()
  const { children } = useChildren()

  const [recentWorksheets, setRecentWorksheets] = useState<RecentWorksheet[]>([])
  const [recentLoading, setRecentLoading] = useState(true)

  const displayName =
    user?.user_metadata?.name?.split(' ')[0] ||
    user?.email?.split('@')[0] ||
    'there'

  const isTeacher = activeRole === 'teacher'
  const firstChild = children.length > 0 ? children[0] : null

  // ── Fetch recent activity ───────────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false

    async function fetchRecent() {
      try {
        const response = await api.get('/api/worksheets/saved/list?limit=5')
        if (!cancelled) {
          const items = response.data.worksheets || response.data || []
          setRecentWorksheets(Array.isArray(items) ? items.slice(0, 5) : [])
        }
      } catch (err) {
        console.warn('[HomeDashboard] Failed to fetch recent worksheets:', err)
        if (!cancelled) setRecentWorksheets([])
      } finally {
        if (!cancelled) setRecentLoading(false)
      }
    }

    fetchRecent()
    return () => { cancelled = true }
  }, [])

  // ── Current date string ─────────────────────────────────────────────────────

  const dateStr = new Date().toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 pb-28 md:pb-8 space-y-10">

      {/* ── 1. Greeting Section ─────────────────────────────────────────────── */}
      <div className="animate-in fade-in slide-in-from-top-4 duration-500">
        <h1
          className="text-2xl sm:text-3xl font-bold text-foreground"
          style={{ fontFamily: "'Fraunces', serif" }}
        >
          {getGreeting()},{' '}
          <span className="text-primary">{displayName}</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{dateStr}</p>
        {!isTeacher && firstChild && (
          <p className="text-sm text-muted-foreground mt-0.5">
            Practicing with <span className="font-medium text-foreground">{firstChild.name}</span>
          </p>
        )}
      </div>

      {/* ── 2. Quick Actions Grid ───────────────────────────────────────────── */}
      <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-700">
        <h2 className="text-lg font-semibold text-foreground">Quick Actions</h2>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
          <QuickActionCard
            icon={ICONS.pencil}
            label="Practice"
            description="Generate a worksheet"
            badge="active"
            onClick={() => onNavigate('generator')}
          />
          <QuickActionCard
            icon={ICONS.bookOpen}
            label="Revise"
            description="Topic revision notes"
            badge="new"
            onClick={() => onNavigate('generator', { mode: 'revision' })}
          />
          <QuickActionCard
            icon={ICONS.camera}
            label="Grade"
            description="Grade from photo"
            badge="active"
            onClick={() => onNavigate('progress')}
          />
          <QuickActionCard
            icon={ICONS.layers}
            label="Flashcards"
            description="Quick recall cards"
            badge="new"
            onClick={() => onNavigate('generator', { mode: 'flashcards' })}
          />
          <QuickActionCard
            icon={ICONS.book}
            label="Textbook"
            description="From any page"
            badge="new"
            onClick={() => onNavigate('generator', { mode: 'textbook' })}
          />
          <QuickActionCard
            icon={ICONS.sparkle}
            label="Syllabus"
            description="Upload & align"
            badge="active"
            onClick={() => onNavigate('syllabus')}
          />
        </div>

        {/* Ask Skolar — featured card below the grid */}
        <div
          onClick={() => onNavigate('ask')}
          className="mt-3 p-4 rounded-xl bg-gradient-to-r from-emerald-50 to-amber-50 border border-emerald-200 cursor-pointer hover:shadow-md transition-all"
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter') onNavigate('ask') }}
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center text-lg">
              🧠
            </div>
            <div className="flex-1">
              <div className="font-semibold text-foreground flex items-center gap-2">
                Ask Skolar
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-bold">NEW</span>
              </div>
              <p className="text-sm text-muted-foreground">Stuck on homework? Ask any question — I'll explain step by step</p>
            </div>
            <div className="ml-auto text-muted-foreground shrink-0">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. Recent Activity / My Classes ──────────────────────────────────── */}
      <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-700">
        <h2 className="text-lg font-semibold text-foreground">
          {isTeacher ? 'My Classes' : 'Recent Activity'}
        </h2>

        {isTeacher ? (
          /* Teacher: My Classes card */
          <button
            type="button"
            onClick={() => onNavigate('classes')}
            className="w-full group flex items-center gap-4 p-5 bg-white border border-border/60 rounded-xl text-left hover:shadow-md hover:border-primary/20 transition-all duration-200 cursor-pointer"
          >
            <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0 group-hover:bg-primary/15 transition-colors">
              {ICONS.classes}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                Manage your classes
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                View students, assign worksheets, and track progress
              </p>
            </div>
            <svg className="w-5 h-5 text-muted-foreground/40 group-hover:text-primary group-hover:translate-x-0.5 transition-all shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          </button>
        ) : (
          /* Parent: Recent Activity list */
          <>
            {recentLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-16 bg-white border border-border/40 rounded-xl animate-pulse" />
                ))}
              </div>
            ) : recentWorksheets.length === 0 ? (
              <div className="py-10 text-center bg-white border border-dashed border-border/60 rounded-xl">
                <div className="w-12 h-12 mx-auto mb-3 bg-primary/10 rounded-xl flex items-center justify-center">
                  {ICONS.sparkle}
                </div>
                <p className="text-sm font-medium text-muted-foreground">
                  No worksheets yet
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Generate your first practice to see activity here.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {recentWorksheets.map((ws) => (
                  <div
                    key={ws.id}
                    className="flex items-center gap-3 p-4 bg-white border border-border/40 rounded-xl hover:border-primary/20 hover:shadow-sm transition-all"
                  >
                    <div className="w-8 h-8 rounded-lg bg-secondary/80 flex items-center justify-center shrink-0">
                      <svg className="w-4 h-4 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-foreground truncate">
                        {ws.subject}
                        <span className="font-normal text-muted-foreground"> — </span>
                        {ws.topic}
                      </p>
                      <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-0.5">
                        {formatDate(ws.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* ── 4. Suggested Next (parent only, when children exist) ─────────────── */}
      {!isTeacher && children.length > 0 && (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="flex items-center gap-4 p-5 bg-gradient-to-r from-primary/5 via-primary/[0.02] to-transparent border border-primary/10 rounded-xl">
            <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
              {ICONS.sparkle}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground">
                Keep practicing!
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Try a new topic today to build strong foundations.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('generator')}
              className="shrink-0 px-4 py-2 text-xs font-bold text-primary bg-primary/10 hover:bg-primary/20 rounded-lg transition-colors"
            >
              Start
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
