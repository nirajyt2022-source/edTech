import { useState, useEffect, useMemo } from 'react'
import SharedWorksheet from './pages/SharedWorksheet'
import WorksheetGenerator from './pages/WorksheetGenerator'
import SyllabusUpload from './pages/SyllabusUpload'
import SavedWorksheets from './pages/SavedWorksheets'
import ChildProfiles from './pages/ChildProfiles'
import TeacherDashboard from './pages/TeacherDashboard'
import ClassManager from './pages/ClassManager'
import Auth from './pages/Auth'
import Landing from './pages/Landing'
import History from './pages/History'
import ParentDashboard from './pages/ParentDashboard'
import RoleSelector from '@/components/RoleSelector'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ChildrenProvider } from '@/lib/children'
import { ClassesProvider } from '@/lib/classes'
import { SubscriptionProvider, useSubscription } from '@/lib/subscription'
import { ProfileProvider, useProfile } from '@/lib/profile'
import { EngagementProvider } from '@/lib/engagement'
import './index.css'

type Page = 'generator' | 'syllabus' | 'saved' | 'children' | 'dashboard' | 'classes' | 'history' | 'progress'

interface ParsedSyllabus {
  id: string
  name: string
  board?: string
  grade?: string
  subject?: string
  chapters: {
    name: string
    topics: { name: string; subtopics?: string[] }[]
  }[]
}

function UsageBadge() {
  const { status } = useSubscription()

  if (!status) return null

  if (status.tier === 'paid') {
    return (
      <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary border border-primary/20 rounded-full text-[10px] font-bold uppercase tracking-wider shadow-sm">
        <svg className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
        </svg>
        Elite Pro
      </span>
    )
  }

  const isExhausted = status.worksheets_remaining === 0
  const isLow = status.worksheets_remaining && status.worksheets_remaining <= 1

  return (
    <span className={`hidden sm:inline-flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest transition-all border ${isExhausted
      ? 'bg-destructive/5 text-destructive border-destructive/20'
      : isLow
        ? 'bg-amber-500/5 text-amber-600 border-amber-500/20'
        : 'bg-secondary/40 text-muted-foreground border-border/40'
      }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isExhausted ? 'bg-destructive animate-pulse' : isLow ? 'bg-amber-500' : 'bg-primary/50'
        }`} />
      {status.worksheets_remaining}/{3} Credits
    </span>
  )
}

function AppContent() {
  const [currentPage, setCurrentPage] = useState<Page>('generator')
  const [syllabus, setSyllabus] = useState<ParsedSyllabus | null>(null)
  const [showAuth, setShowAuth] = useState(false)
  const [authDefaultMode, setAuthDefaultMode] = useState<'login' | 'signup'>('login')
  const { user, loading, signOut } = useAuth()
  const profileCtx = useProfile()
  const { activeRole, profile, switchRole } = profileCtx

  // When role switches, reset to default page for that role
  useEffect(() => {
    const isTeacherPage = ['dashboard', 'classes', 'generator'].includes(currentPage)
    const isParentPage = ['generator', 'syllabus', 'children', 'progress'].includes(currentPage)

    const sharedPages = ['saved', 'history']
    if (activeRole === 'teacher' && !isTeacherPage && !sharedPages.includes(currentPage)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCurrentPage('dashboard')
    } else if (activeRole === 'parent' && !isParentPage && !sharedPages.includes(currentPage)) {
      setCurrentPage('generator')
    }
  }, [activeRole, currentPage])

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen gradient-bg flex flex-col items-center justify-center gap-6">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-1 h-1 bg-primary rounded-full animate-ping" />
          </div>
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-xl font-bold font-fraunces text-foreground">Getting ready</h2>
          <p className="text-sm text-muted-foreground font-medium tracking-wide">Preparing your practice workspace...</p>
        </div>
      </div>
    )
  }

  // Show landing or auth page if not logged in
  if (!user) {
    if (showAuth) {
      return <Auth defaultMode={authDefaultMode} onBack={() => setShowAuth(false)} />
    }
    return (
      <Landing
        onGetStarted={() => { setAuthDefaultMode('signup'); setShowAuth(true) }}
        onSignIn={() => { setAuthDefaultMode('login'); setShowAuth(true) }}
      />
    )
  }

  // Define tabs based on active role
  const isTeacher = activeRole === 'teacher'

  const teacherTabs: { id: Page; label: string }[] = [
    { id: 'generator', label: 'Practice' },
    { id: 'classes', label: 'Classes' },
    { id: 'saved', label: 'Saved' },
    { id: 'history', label: 'History' },
    { id: 'dashboard', label: 'Dashboard' },
  ]

  const parentTabs: { id: Page; label: string }[] = [
    { id: 'generator', label: 'Practice' },
    { id: 'progress', label: 'Progress' },
    { id: 'saved', label: 'Saved' },
    { id: 'history', label: 'History' },
    { id: 'syllabus', label: 'Syllabus' },
    { id: 'children', label: 'Profile' },
  ]

  const tabs = isTeacher ? teacherTabs : parentTabs

  return (
    <div className="min-h-screen gradient-bg">
      <RoleSelector />
      {/* Navigation */}
      <nav className="bg-background/80 backdrop-blur-xl border-b border-border/30 sticky top-0 z-50 print:hidden">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Logo */}
          <button className="flex items-center gap-2.5 group cursor-pointer bg-transparent border-none shrink-0" onClick={() => setCurrentPage(isTeacher ? 'dashboard' : 'generator')} aria-label="Go to home page">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <svg className="w-4.5 h-4.5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <span className="text-lg font-semibold tracking-tight hidden sm:inline">
              <span className="text-foreground">Practice</span><span className="text-primary">Craft</span>
            </span>
          </button>

          {/* Navigation Tabs — text only, calm */}
          <div role="tablist" aria-label="Main navigation" className="hidden md:flex items-center gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={currentPage === tab.id}
                onClick={() => setCurrentPage(tab.id)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${currentPage === tab.id
                  ? 'text-foreground bg-secondary/60'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary/30'
                  }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Right side — usage + user menu */}
          <div className="flex items-center gap-3">
            <UsageBadge />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 group focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-lg px-1 -mr-1">
                  <div className="w-8 h-8 rounded-lg bg-secondary/60 flex items-center justify-center border border-border/40 group-hover:border-primary/20 transition-colors">
                    <span className="text-xs font-semibold text-foreground">
                      {(user.user_metadata?.name || user.email || 'U')[0].toUpperCase()}
                    </span>
                  </div>
                  <svg className="w-3 h-3 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                  </svg>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 p-1.5 rounded-xl border-border/40 shadow-lg">
                <DropdownMenuLabel className="px-3 py-2">
                  <p className="text-sm font-semibold truncate">{user.user_metadata?.name || user.email}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 capitalize">{activeRole}</p>
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="mx-1.5" />

                {/* Region toggle */}
                {profile && (
                  <DropdownMenuItem
                    onClick={() => {
                      const newRegion = profileCtx.region === 'India' ? 'UAE' : 'India'
                      profileCtx.setRegion(newRegion)
                    }}
                    className="cursor-pointer rounded-lg py-2 px-3 text-sm"
                  >
                    <svg className="w-4 h-4 mr-2.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
                    </svg>
                    Region: {profileCtx.region === 'India' ? 'India' : 'UAE'}
                  </DropdownMenuItem>
                )}

                {profile && (
                  <DropdownMenuItem
                    onClick={() => switchRole(activeRole === 'parent' ? 'teacher' : 'parent')}
                    className="cursor-pointer rounded-lg py-2 px-3 text-sm"
                  >
                    <svg className="w-4 h-4 mr-2.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                    </svg>
                    Switch to {activeRole === 'parent' ? 'Teacher' : 'Parent'}
                  </DropdownMenuItem>
                )}

                <DropdownMenuSeparator className="mx-1.5" />
                <DropdownMenuItem
                  onClick={() => signOut()}
                  className="cursor-pointer rounded-lg py-2 px-3 text-sm text-destructive focus:text-destructive"
                >
                  <svg className="w-4 h-4 mr-2.5 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
                  </svg>
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Mobile bottom nav — text labels, no icons */}
        <nav aria-label="Mobile navigation" className="md:hidden fixed bottom-0 left-0 right-0 bg-background/90 backdrop-blur-xl border-t border-border/30 z-50 px-2 pb-[env(safe-area-inset-bottom)]">
          <div className="flex items-center justify-around h-12">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={currentPage === tab.id}
                onClick={() => setCurrentPage(tab.id)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${currentPage === tab.id
                  ? 'text-foreground bg-secondary/60'
                  : 'text-muted-foreground'
                  }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </nav>
      </nav>

      {/* Page Content */}
      <main className="animate-in fade-in duration-700">
        {currentPage === 'dashboard' && (
          <TeacherDashboard onNavigate={(page) => setCurrentPage(page as Page)} />
        )}
        {currentPage === 'classes' && <ClassManager />}
        {currentPage === 'generator' && (
          <WorksheetGenerator
            syllabus={syllabus}
            onClearSyllabus={() => setSyllabus(null)}
          />
        )}
        {currentPage === 'syllabus' && (
          <SyllabusUpload
            onSyllabusReady={(parsedSyllabus) => {
              setSyllabus(parsedSyllabus)
              setCurrentPage('generator')
            }}
          />
        )}
        {currentPage === 'saved' && <SavedWorksheets />}
        {currentPage === 'history' && (
          <History onNavigateToGenerator={() => setCurrentPage('generator')} />
        )}
        {currentPage === 'progress' && <ParentDashboard />}
        {currentPage === 'children' && <ChildProfiles />}
      </main>
    </div>
  )
}

function App() {
  // Check if we're on a public /shared/:id route (no auth required)
  const sharedWorksheetId = useMemo(() => {
    const match = window.location.pathname.match(/^\/shared\/([a-f0-9-]+)$/i)
    return match ? match[1] : null
  }, [])

  // Public shared worksheet route — no auth providers needed
  if (sharedWorksheetId) {
    return <SharedWorksheet worksheetId={sharedWorksheetId} />
  }

  return (
    <AuthProvider>
      <ProfileProvider>
        <SubscriptionProvider>
          <ChildrenProvider>
            <ClassesProvider>
              <EngagementProvider>
                <AppContent />
              </EngagementProvider>
            </ClassesProvider>
          </ChildrenProvider>
        </SubscriptionProvider>
      </ProfileProvider>
    </AuthProvider>
  )
}

export default App
