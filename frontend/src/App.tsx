import { useState, useEffect } from 'react'
import WorksheetGenerator from './pages/WorksheetGenerator'
import SyllabusUpload from './pages/SyllabusUpload'
import SavedWorksheets from './pages/SavedWorksheets'
import ChildProfiles from './pages/ChildProfiles'
import TeacherDashboard from './pages/TeacherDashboard'
import ClassManager from './pages/ClassManager'
import Auth from './pages/Auth'
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

type Page = 'generator' | 'syllabus' | 'saved' | 'children' | 'dashboard' | 'classes'

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
      <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary border border-primary/20 rounded-full text-[10px] font-black uppercase tracking-wider shadow-sm">
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
  const { user, loading, signOut } = useAuth()
  const { activeRole, profile, switchRole } = useProfile()

  // When role switches, reset to default page for that role
  useEffect(() => {
    const isTeacherPage = ['dashboard', 'classes'].includes(currentPage)
    const isParentPage = ['generator', 'syllabus', 'children'].includes(currentPage)

    if (activeRole === 'teacher' && !isTeacherPage && currentPage !== 'saved') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCurrentPage('dashboard')
    } else if (activeRole === 'parent' && !isParentPage && currentPage !== 'saved') {
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
          <h2 className="text-xl font-bold font-fraunces text-foreground">Loading...</h2>
          <p className="text-sm text-muted-foreground font-medium tracking-wide">Preparing your workspace...</p>
        </div>
      </div>
    )
  }

  // Show auth page if not logged in
  if (!user) {
    return <Auth />
  }

  // Define tabs based on active role
  const isTeacher = activeRole === 'teacher'

  const teacherTabs: { id: Page; label: string; icon: React.ReactNode }[] = [
    {
      id: 'dashboard', label: 'Dashboard', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
        </svg>
      )
    },
    {
      id: 'classes', label: 'Classes', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      )
    },
    {
      id: 'generator', label: 'Create', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
        </svg>
      )
    },
    {
      id: 'saved', label: 'Saved', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
        </svg>
      )
    },
  ]

  const parentTabs: { id: Page; label: string; icon: React.ReactNode }[] = [
    {
      id: 'generator', label: 'Create', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
        </svg>
      )
    },
    {
      id: 'syllabus', label: 'Syllabus', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
        </svg>
      )
    },
    {
      id: 'saved', label: 'Saved', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0111.186 0z" />
        </svg>
      )
    },
    {
      id: 'children', label: 'Profiles', icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
        </svg>
      )
    },
  ]

  const tabs = isTeacher ? teacherTabs : parentTabs

  return (
    <div className="min-h-screen gradient-bg">
      <RoleSelector />
      {/* Navigation */}
      <nav className="bg-background/70 backdrop-blur-xl border-b border-border/40 sticky top-0 z-50 print:hidden transition-all duration-300">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <button className="flex items-center gap-3.5 group cursor-pointer bg-transparent border-none" onClick={() => setCurrentPage(isTeacher ? 'dashboard' : 'generator')} aria-label="Go to home page">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg shadow-primary/10 group-hover:scale-105 group-hover:rotate-3 transition-all duration-300">
                <svg className="w-5.5 h-5.5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <h1 className="text-2xl font-black tracking-tight font-fraunces">
                <span className="text-primary mr-px">Practice</span>
                <span className="text-accent-foreground/80">Craft</span>
              </h1>
            </button>

            {/* Navigation Tabs */}
            <div role="tablist" aria-label="Main navigation" className="hidden md:flex items-center gap-1.5 p-1 bg-secondary/30 border border-border/40 rounded-2xl">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={currentPage === tab.id}
                  onClick={() => setCurrentPage(tab.id)}
                  className={`flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all duration-300 ${currentPage === tab.id
                    ? 'bg-background text-primary shadow-sm border border-border/40 scale-[1.02]'
                    : 'text-muted-foreground/50 hover:text-foreground hover:bg-background/40 hover:scale-[1.01]'
                    }`}
                >
                  <span className={`${currentPage === tab.id ? 'text-primary' : 'text-muted-foreground/30'}`}>{tab.icon}</span>
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>

            {/* User Menu */}
            <div className="flex items-center gap-5">
              <UsageBadge />

              <div className="h-4 w-px bg-border/40 hidden sm:block" />

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-3 group focus:outline-none">
                    <div className="relative">
                      <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-primary/10 via-accent/10 to-secondary/30 flex items-center justify-center border border-border/40 shadow-sm group-hover:border-primary/30 transition-colors">
                        <span className="text-sm font-black text-primary font-jakarta">
                          {(user.user_metadata?.name || user.email || 'U')[0].toUpperCase()}
                        </span>
                      </div>
                      <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 border-2 border-background rounded-full shadow-sm" />
                    </div>

                    <div className="hidden lg:flex flex-col items-start transition-all">
                      <span className="text-xs font-bold text-foreground leading-tight max-w-[100px] truncate">
                        {user.user_metadata?.name || user.email?.split('@')[0]}
                      </span>
                      <span className="text-[10px] font-black uppercase tracking-tighter text-muted-foreground/60 leading-none mt-0.5">
                        {activeRole}
                      </span>
                    </div>

                    <svg className="w-3.5 h-3.5 text-muted-foreground/40 group-hover:text-primary transition-colors duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                    </svg>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64 p-2 rounded-2xl border-border/40 shadow-2xl animate-in zoom-in-95 duration-200">
                  <DropdownMenuLabel className="p-4 pt-3">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-black font-jakarta">{user.user_metadata?.name || user.email}</p>
                      <p className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest bg-secondary/50 px-2 py-0.5 rounded-md self-start mt-1">
                        Active as {activeRole}
                      </p>
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator className="bg-border/40 mx-2" />
                  <div className="p-1.5 space-y-1">
                    {profile && (
                      <DropdownMenuItem
                        onClick={() => switchRole(activeRole === 'parent' ? 'teacher' : 'parent')}
                        className="cursor-pointer rounded-xl py-3 px-4 focus:bg-primary/5 focus:text-primary group transition-all"
                      >
                        <svg className="w-4 h-4 mr-3 text-muted-foreground/50 group-hover:text-primary transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
                        </svg>
                        <span className="text-xs font-bold">Switch to {activeRole === 'parent' ? 'Teacher' : 'Parent'} Mode</span>
                      </DropdownMenuItem>
                    )}

                    <DropdownMenuItem
                      onClick={() => signOut()}
                      className="cursor-pointer rounded-xl py-3 px-4 text-destructive focus:bg-destructive/5 focus:text-destructive group transition-all"
                    >
                      <svg className="w-4 h-4 mr-3 opacity-50 group-hover:opacity-100 transition-opacity" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
                      </svg>
                      <span className="text-xs font-bold">Sign Out</span>
                    </DropdownMenuItem>
                  </div>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>

        {/* Mobile Navigation (Subtle Bottom Bar) */}
        <nav aria-label="Mobile navigation" className="md:hidden fixed bottom-6 left-1/2 -translate-x-1/2 w-[90%] bg-background/80 backdrop-blur-2xl border border-border/60 rounded-3xl shadow-2xl z-50 p-1.5 flex items-center justify-between">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={currentPage === tab.id}
              onClick={() => setCurrentPage(tab.id)}
              className={`flex flex-col items-center gap-1 flex-1 py-3 rounded-2xl transition-all ${currentPage === tab.id
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground/40'
                }`}
            >
              {tab.icon}
              <span className="text-[10px] font-black uppercase tracking-tighter scale-90">{tab.label}</span>
            </button>
          ))}
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
        {currentPage === 'children' && <ChildProfiles />}
      </main>
    </div>
  )
}

function App() {
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
