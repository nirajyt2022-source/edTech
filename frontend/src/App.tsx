import React, { useState, useEffect, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate, useLocation, useParams } from 'react-router-dom'

// Lazy load all pages — only the active page is loaded
const Auth = lazy(() => import('./pages/Auth'))
const Landing = lazy(() => import('./pages/Landing'))
const HomeDashboard = lazy(() => import('./pages/HomeDashboard'))
const SharedWorksheet = lazy(() => import('./pages/SharedWorksheet'))
const ClassReport = lazy(() => import('./pages/ClassReport'))
const WorksheetGenerator = lazy(() => import('./pages/WorksheetGenerator'))
const SyllabusUpload = lazy(() => import('./pages/SyllabusUpload'))
const SavedWorksheets = lazy(() => import('./pages/SavedWorksheets'))
const ChildProfiles = lazy(() => import('./pages/ChildProfiles'))
const TeacherDashboard = lazy(() => import('./pages/TeacherDashboard'))
const ClassManager = lazy(() => import('./pages/ClassManager'))
const History = lazy(() => import('./pages/History'))
const ParentDashboard = lazy(() => import('./pages/ParentDashboard'))
const AskSkolar = lazy(() => import('./pages/AskSkolar'))
import RoleSelector from '@/components/RoleSelector'
import OnboardingWizard from '@/components/OnboardingWizard'
import AppFeedback from '@/components/AppFeedback'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Toaster } from 'sonner'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ChildrenProvider } from '@/lib/children'
import { ClassesProvider } from '@/lib/classes'
import { SubscriptionProvider, useSubscription } from '@/lib/subscription'
import { ProfileProvider, useProfile } from '@/lib/profile'
import { EngagementProvider } from '@/lib/engagement'
import ChildSwitcher from '@/components/ChildSwitcher'
import ErrorBoundary from '@/components/ErrorBoundary'
import './index.css'

type Page = 'home' | 'generator' | 'syllabus' | 'saved' | 'children' | 'dashboard' | 'classes' | 'history' | 'progress' | 'ask'

const PAGE_TO_PATH: Record<Page, string> = {
  home: '/',
  generator: '/generate',
  syllabus: '/syllabus',
  saved: '/saved',
  children: '/children',
  dashboard: '/dashboard',
  classes: '/classes',
  history: '/history',
  progress: '/progress',
  ask: '/ask',
}

const PATH_TO_PAGE: Record<string, Page> = {
  '/': 'home',
  '/generate': 'generator',
  '/syllabus': 'syllabus',
  '/saved': 'saved',
  '/children': 'children',
  '/dashboard': 'dashboard',
  '/classes': 'classes',
  '/history': 'history',
  '/progress': 'progress',
  '/ask': 'ask',
}

// ── Nav Icons ────────────────────────────────────────────────────────────────
const NAV_ICONS: Record<string, React.ReactElement> = {
  home:      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1h-2z"/></svg>,
  generator: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>,
  classes:   <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>,
  saved:     <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"/></svg>,
  history:   <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>,
  dashboard: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>,
  progress:  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>,
  syllabus:  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>,
  children:  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>,
}

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
  const navigate = useNavigate()
  const location = useLocation()
  const [generatorPreFill, setGeneratorPreFill] = useState<{ grade?: string; subject?: string; topic?: string; mode?: 'worksheet' | 'revision' | 'flashcards' | 'textbook' } | null>(null)
  const [syllabus, setSyllabus] = useState<ParsedSyllabus | null>(null)
  const [showAuth, setShowAuth] = useState(false)
  const [authDefaultMode, setAuthDefaultMode] = useState<'login' | 'signup'>('login')
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false)
  const { user, loading, signOut } = useAuth()
  const profileCtx = useProfile()
  const { activeRole, profile } = profileCtx

  // Derive currentPage from pathname
  const currentPage: Page = PATH_TO_PAGE[location.pathname] || 'home'

  // Helper: navigate by page name (used by onNavigate callbacks)
  const navigateToPage = (page: string, preFill?: { grade?: string; subject?: string; topic?: string; mode?: 'worksheet' | 'revision' | 'flashcards' | 'textbook' }) => {
    if (preFill) setGeneratorPreFill(preFill)
    const path = PAGE_TO_PATH[page as Page] || '/'
    navigate(path)
  }

  // When role switches, reset to home if on wrong-role page
  useEffect(() => {
    const isTeacherPage = ['home', 'dashboard', 'classes', 'generator'].includes(currentPage)
    const isParentPage = ['home', 'generator', 'syllabus', 'children', 'progress', 'ask'].includes(currentPage)

    const sharedPages = ['saved', 'history']
    if (activeRole === 'teacher' && !isTeacherPage && !sharedPages.includes(currentPage)) {
      navigate('/')
    } else if (activeRole === 'parent' && !isParentPage && !sharedPages.includes(currentPage)) {
      navigate('/')
    }
  }, [activeRole, currentPage, navigate])

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-6 bg-background">
        <div className="relative">
          <div className="w-16 h-16 border-4 rounded-full animate-spin border-primary/20 border-t-primary" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-1 h-1 rounded-full animate-ping bg-primary" />
          </div>
        </div>
        <div className="text-center space-y-2">
          <h2 className="text-xl font-bold font-fraunces text-foreground">Getting ready</h2>
          <p className="text-sm font-medium tracking-wide text-muted-foreground">Preparing your practice workspace...</p>
        </div>
      </div>
    )
  }

  // Show landing or auth page if not logged in
  if (!user) {
    return (
      <Suspense fallback={
        <div className="flex items-center justify-center min-h-screen">
          <div className="spinner" />
        </div>
      }>
        {showAuth ? (
          <Auth defaultMode={authDefaultMode} onBack={() => setShowAuth(false)} />
        ) : (
          <Landing
            onGetStarted={() => { setAuthDefaultMode('signup'); setShowAuth(true) }}
            onSignIn={() => { setAuthDefaultMode('login'); setShowAuth(true) }}
          />
        )}
      </Suspense>
    )
  }

  // Define tabs based on active role
  const isTeacher = activeRole === 'teacher'

  const teacherTabs: { id: Page; label: string }[] = [
    { id: 'home', label: 'Home' },
    { id: 'generator', label: 'Practice' },
    { id: 'classes', label: 'Classes' },
    { id: 'saved', label: 'Saved' },
    { id: 'dashboard', label: 'Dashboard' },
  ]

  const parentTabs: { id: Page; label: string }[] = [
    { id: 'home', label: 'Home' },
    { id: 'generator', label: 'Practice' },
    { id: 'progress', label: 'Progress' },
    { id: 'saved', label: 'Saved' },
    { id: 'children', label: 'Profile' },
  ]

  const tabs = isTeacher ? teacherTabs : parentTabs

  return (
    <TooltipProvider delayDuration={400}>
    <div className="min-h-screen bg-background">
      <Toaster position="top-right" richColors />
      <RoleSelector />
      <OnboardingWizard onNavigate={(page, preFill) => navigateToPage(page, preFill)} />
      {/* Navigation */}
      <nav className="backdrop-blur-xl border-b border-border/30 sticky top-0 z-50 print:hidden bg-primary">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Logo */}
          <button className="flex items-center gap-2.5 group cursor-pointer bg-transparent border-none shrink-0" onClick={() => navigate('/')} aria-label="Go to home page">
            <span className="text-lg font-bold tracking-tight hidden sm:inline font-fraunces text-white">
              Skolar
            </span>
            <span className="sm:hidden text-lg font-bold font-fraunces text-white">
              S
            </span>
          </button>

          {/* Global child switcher */}
          <ChildSwitcher />

          {/* Navigation Tabs */}
          <div role="tablist" aria-label="Main navigation" className="hidden md:flex items-center gap-0.5">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={currentPage === tab.id}
                onClick={() => navigate(PAGE_TO_PATH[tab.id])}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${currentPage === tab.id
                  ? 'font-semibold text-white bg-white/15'
                  : 'text-white/55 hover:text-white/85 hover:bg-white/[0.08]'
                  }`}
              >
                {NAV_ICONS[tab.id]}
                {tab.label}
              </button>
            ))}
          </div>

          {/* Right side — usage + user menu */}
          <div className="flex items-center gap-3">
            <UsageBadge />

            <DropdownMenu>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <button className="flex items-center gap-2 group focus:outline-none focus-visible:ring-2 focus-visible:ring-white/40 rounded-lg px-1 -mr-1">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center border transition-colors bg-white/15 border-white/25">
                        <span className="text-xs font-semibold text-white">
                          {(user.user_metadata?.name || user.email || 'U')[0].toUpperCase()}
                        </span>
                      </div>
                      <svg className="w-3 h-3 text-white/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                      </svg>
                    </button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent side="bottom">Account menu</TooltipContent>
              </Tooltip>
              <DropdownMenuContent align="end" className="w-56 p-1.5 rounded-xl border-border/40 shadow-lg">
                <DropdownMenuLabel className="px-3 py-2">
                  <p className="text-sm font-semibold truncate">{user.user_metadata?.name || user.email}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {activeRole === 'teacher' ? 'Teacher Account' : 'Parent Account'}
                  </p>
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


                <DropdownMenuItem
                  onClick={() => setShowFeedbackDialog(true)}
                  className="cursor-pointer rounded-lg py-2 px-3 text-sm"
                >
                  <svg className="w-4 h-4 mr-2.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                  Send Feedback
                </DropdownMenuItem>

                <DropdownMenuSeparator className="mx-1.5" />
                <DropdownMenuItem
                  onClick={() => { setShowAuth(false); signOut() }}
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

        {/* Mobile bottom nav — icon + label */}
        <nav aria-label="Mobile navigation" className="md:hidden fixed bottom-0 left-0 right-0 backdrop-blur-xl border-t border-border/30 z-50 pb-[env(safe-area-inset-bottom)] bg-background/95">
          <div className="flex items-center justify-around h-14 px-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={currentPage === tab.id}
                onClick={() => navigate(PAGE_TO_PATH[tab.id])}
                className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-lg min-w-[44px] min-h-[44px] justify-center transition-colors cursor-pointer ${currentPage === tab.id ? 'text-primary' : 'text-muted-foreground'}`}
              >
                {NAV_ICONS[tab.id]}
                <span className="text-[10px] font-medium leading-none">{tab.label}</span>
              </button>
            ))}
          </div>
        </nav>
      </nav>

      {/* Page Content */}
      <main className="animate-in fade-in duration-700 pb-20 md:pb-0">
        <Suspense fallback={
          <div className="flex items-center justify-center min-h-[50vh]">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-emerald-600" />
          </div>
        }>
        <Routes>
          <Route path="/" element={
            <HomeDashboard onNavigate={(page, preFill) => navigateToPage(page, preFill)} />
          } />
          <Route path="/generate" element={
            <WorksheetGenerator
              syllabus={syllabus}
              onClearSyllabus={() => setSyllabus(null)}
              preFill={generatorPreFill}
              onPreFillConsumed={() => setGeneratorPreFill(null)}
            />
          } />
          <Route path="/syllabus" element={
            <SyllabusUpload
              onSyllabusReady={(parsedSyllabus) => {
                setSyllabus(parsedSyllabus)
                navigate('/generate')
              }}
            />
          } />
          <Route path="/saved" element={<SavedWorksheets />} />
          <Route path="/children" element={<ChildProfiles />} />
          <Route path="/dashboard" element={
            <TeacherDashboard onNavigate={(page) => navigateToPage(page)} />
          } />
          <Route path="/classes" element={<ClassManager onNavigate={(page) => navigateToPage(page)} />} />
          <Route path="/history" element={
            <History onNavigateToGenerator={(preFill) => navigateToPage('generator', preFill)} />
          } />
          <Route path="/progress" element={<ParentDashboard onNavigate={(page) => navigateToPage(page)} />} />
          <Route path="/ask" element={
            <AskSkolar onNavigate={(page, preFill) => navigateToPage(page, preFill)} />
          } />
          {/* Fallback — redirect unknown routes to home */}
          <Route path="*" element={
            <HomeDashboard onNavigate={(page, preFill) => navigateToPage(page, preFill)} />
          } />
        </Routes>
        </Suspense>
      </main>

      <AppFeedback
        currentPage={currentPage}
        open={showFeedbackDialog}
        onOpenChange={setShowFeedbackDialog}
      />

      {/* WhatsApp floating button — above mobile nav bar, below Edit FAB */}
      <a
        href="https://wa.me/919999999999?text=Hi%2C%20I%20want%20to%20know%20more%20about%20Skolar"
        target="_blank"
        rel="noopener noreferrer"
        className="fixed bottom-20 md:bottom-6 right-4 md:right-6 z-40 w-12 h-12 md:w-14 md:h-14 bg-green-500 hover:bg-green-600 rounded-full flex items-center justify-center shadow-lg shadow-green-500/30 hover:shadow-xl transition-all hover:-translate-y-0.5 print:hidden"
        aria-label="Chat on WhatsApp"
      >
        <svg className="w-6 h-6 md:w-7 md:h-7 text-white" viewBox="0 0 24 24" fill="currentColor">
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
        </svg>
      </a>
    </div>
    </TooltipProvider>
  )
}

// Wrapper components to extract route params for public pages
function SharedWorksheetRoute() {
  const { id } = useParams<{ id: string }>()
  if (!id) return null
  return <SharedWorksheet worksheetId={id} />
}

function ClassReportRoute() {
  const { token } = useParams<{ token: string }>()
  if (!token) return null
  return <ClassReport token={token} />
}

function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={
        <div className="flex items-center justify-center min-h-[50vh]">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-emerald-600" />
        </div>
      }>
        <Routes>
          {/* Public routes — no auth providers needed */}
          <Route path="/shared/:id" element={
            <>
              <SharedWorksheetRoute />
              <a
                href="https://wa.me/919999999999?text=Hi%2C%20I%20need%20help%20with%20Skolar"
                target="_blank"
                rel="noopener noreferrer"
                className="fixed bottom-6 right-4 z-50 w-12 h-12 rounded-full bg-[#25D366] text-white flex items-center justify-center shadow-lg hover:shadow-xl hover:scale-105 transition-all print:hidden"
                aria-label="Chat on WhatsApp"
              >
                <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                </svg>
              </a>
            </>
          } />
          <Route path="/report/:token" element={<ClassReportRoute />} />

          {/* All other routes — wrapped in auth providers */}
          <Route path="/*" element={
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
          } />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  )
}

export default App
